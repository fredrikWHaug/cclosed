"""
Train the Small ResNet and export its weights + a test snippet as C headers.

Self-contained like export_logreg_to_c.py: trains from scratch (seed 42, same
80/20 split as train.py) so no checkpoint is needed, saves the checkpoint for
reproducibility, folds every BatchNorm into its preceding Conv, and writes
firmware/classifiers/resnet/{model_weights.h,test_data.h}.

The exported layer names line up 1:1 with the hand-written forward pass in
firmware/classifiers/resnet/src/main.c:

  stem   Conv(8->64)  +ReLU
  res1   r1c1 +ReLU , r1c2 , add(stem) +ReLU        MaxPool -> /2
  expand Conv(64->128)+ReLU
  res2   r2c1 +ReLU , r2c2 , add(expand)+ReLU        MaxPool -> /2
  res3   r3c1 +ReLU , r3c2 , add(pool2) +ReLU        MaxPool -> /2
  fc1    Linear(640->128)+ReLU
  fc2    Linear(128->N_CLASSES)
"""

import argparse
import numpy as np
import torch
from pathlib import Path
from torch.utils.data import DataLoader, TensorDataset

from train import load_shank_data
from compare_models import SpikeResNet


def fold_bn_into_conv(conv_w, conv_b, bn_w, bn_b, bn_mean, bn_var, eps=1e-5):
    """Fold BatchNorm params into the preceding Conv weights and bias."""
    scale = bn_w / torch.sqrt(bn_var + eps)
    w = conv_w * scale.view(-1, 1, 1)
    b = (conv_b - bn_mean) * scale + bn_b
    return w, b


def export_array(f, name, arr, dtype="float"):
    flat = arr.flatten()
    f.write(f"// shape: {list(arr.shape)}\n")
    f.write(f"static const {dtype} {name}[{len(flat)}] = {{\n")
    for i in range(0, len(flat), 8):
        chunk = flat[i:i + 8]
        f.write("    " + ", ".join(f"{v:.6f}f" for v in chunk) + ",\n")
    f.write("};\n\n")


def conv_bn(sd, conv_prefix, bn_prefix):
    """Return (w, b) numpy arrays for a Conv+BatchNorm pair, BN folded in."""
    w, b = fold_bn_into_conv(
        sd[f"{conv_prefix}.weight"], sd[f"{conv_prefix}.bias"],
        sd[f"{bn_prefix}.weight"], sd[f"{bn_prefix}.bias"],
        sd[f"{bn_prefix}.running_mean"], sd[f"{bn_prefix}.running_var"],
    )
    return w.numpy(), b.numpy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shank", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()

    shank = args.shank
    root = Path(__file__).parent.parent
    dataset_path = root / "dataset" / "dataset.npz"
    output_dir = root / "firmware" / "classifiers" / "resnet"
    output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = Path(__file__).parent / "checkpoints" / f"resnet_shank{shank}_best.pt"

    X, y, label_map, mean, std = load_shank_data(dataset_path, shank)
    n_classes = len(label_map)
    inv_map = {v: k for k, v in label_map.items()}

    # Same split as train.py / compare_models.py
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    split = int(0.8 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    y_train, y_val = y[idx[:split]], y[idx[split:]]

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Training Small ResNet on shank {shank}: "
          f"{len(X_train)} train, {len(X_val)} val, {n_classes} classes "
          f"({args.epochs} epochs, {device})")

    model = SpikeResNet(8, 40, n_classes).to(device)
    param_count = sum(p.numel() for p in model.parameters())
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = torch.nn.CrossEntropyLoss()

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
        batch_size=128, shuffle=True)
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
        batch_size=256)

    best_val_acc = 0.0
    best_state = None
    for epoch in range(args.epochs):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            loss = criterion(model(xb), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        preds = []
        with torch.no_grad():
            for xb, _ in val_loader:
                preds.append(model(xb.to(device)).argmax(1).cpu().numpy())
        val_acc = (np.concatenate(preds) == y_val).mean()
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        print(f"  epoch {epoch + 1:2d}/{args.epochs}  val_acc={val_acc:.4f}")

    print(f"\nBest val acc: {best_val_acc:.4f}  ({param_count:,} params)")

    # Restore best weights and save the checkpoint
    model.load_state_dict(best_state)
    model.eval().cpu()
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state": best_state, "n_classes": n_classes,
                "val_acc": float(best_val_acc)}, ckpt_path)
    print(f"Checkpoint saved to {ckpt_path}")

    # ---- fold BN and gather all weights ----
    sd = model.state_dict()
    layers = {
        "stem":   conv_bn(sd, "stem.0", "stem.1"),
        "r1c1":   conv_bn(sd, "res1.conv1", "res1.bn1"),
        "r1c2":   conv_bn(sd, "res1.conv2", "res1.bn2"),
        "expand": conv_bn(sd, "expand.0", "expand.1"),
        "r2c1":   conv_bn(sd, "res2.conv1", "res2.bn1"),
        "r2c2":   conv_bn(sd, "res2.conv2", "res2.bn2"),
        "r3c1":   conv_bn(sd, "res3.conv1", "res3.bn1"),
        "r3c2":   conv_bn(sd, "res3.conv2", "res3.bn2"),
    }
    fc1_w = sd["classifier.0.weight"].numpy()
    fc1_b = sd["classifier.0.bias"].numpy()
    fc2_w = sd["classifier.2.weight"].numpy()
    fc2_b = sd["classifier.2.bias"].numpy()

    weights_path = output_dir / "model_weights.h"
    with open(weights_path, "w") as f:
        f.write("#ifndef MODEL_WEIGHTS_H\n#define MODEL_WEIGHTS_H\n\n")
        f.write(f"#define N_CLASSES {n_classes}\n\n")
        for name, (w, b) in layers.items():
            export_array(f, f"{name}_w", w)
            export_array(f, f"{name}_b", b)
        export_array(f, "fc1_w", fc1_w)
        export_array(f, "fc1_b", fc1_b)
        export_array(f, "fc2_w", fc2_w)
        export_array(f, "fc2_b", fc2_b)
        f.write("#endif\n")
    print(f"Weights written to {weights_path}")

    # ---- test snippet (same selection as export_to_c.py: first class-0 sample) ----
    test_indices = [np.where(y == cls)[0][0] for cls in range(n_classes)
                    if len(np.where(y == cls)[0]) > 0]
    test_idx = test_indices[0]
    test_input = X[test_idx]
    test_label = int(y[test_idx])
    test_unit = inv_map[test_label]

    with torch.no_grad():
        pt_out = model(torch.from_numpy(test_input).unsqueeze(0))
        pt_pred = pt_out.argmax(1).item()
        pt_conf = torch.softmax(pt_out, 1).max().item()
    print(f"\nPyTorch prediction: class {pt_pred} (unit {inv_map[pt_pred]}), "
          f"confidence {pt_conf:.3f}, true label: class {test_label} (unit {test_unit})")

    test_path = output_dir / "test_data.h"
    with open(test_path, "w") as f:
        f.write("#ifndef TEST_DATA_H\n#define TEST_DATA_H\n\n")
        f.write(f"#define TEST_TRUE_CLASS {test_label}\n")
        f.write(f"#define TEST_TRUE_UNIT {test_unit}\n\n")
        export_array(f, "test_snippet", test_input)
        f.write("#endif\n")
    print(f"Test data written to {test_path}")


if __name__ == "__main__":
    main()
