"""
Export trained model weights and a test snippet as C header files.
Folds BatchNorm into Conv weights so the C code is just conv + relu + pool + linear.
"""

import numpy as np
import torch
from pathlib import Path
from train import SpikeCNN, load_shank_data


def fold_bn_into_conv(conv_w, conv_b, bn_weight, bn_bias, bn_mean, bn_var, eps=1e-5):
    """Fold BatchNorm parameters into preceding Conv weights and bias."""
    scale = bn_weight / torch.sqrt(bn_var + eps)
    w = conv_w * scale.view(-1, 1, 1)
    b = (conv_b - bn_mean) * scale + bn_bias
    return w, b


def export_array(f, name, arr, dtype="float"):
    """Write a C array declaration."""
    flat = arr.flatten()
    # Write shape as comment
    f.write(f"// shape: {list(arr.shape)}\n")
    f.write(f"static const {dtype} {name}[{len(flat)}] = {{\n")
    for i in range(0, len(flat), 8):
        chunk = flat[i:i+8]
        f.write("    " + ", ".join(f"{v:.6f}f" for v in chunk) + ",\n")
    f.write("};\n\n")


def main():
    shank = 0
    checkpoint_path = Path(__file__).parent / "checkpoints" / f"shank{shank}_best.pt"
    dataset_path = Path(__file__).parent.parent / "dataset" / "dataset.npz"
    output_dir = Path(__file__).parent.parent / "firmware" / "spike_classifier"

    # Load model
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    n_classes = ckpt["n_classes"]
    model = SpikeCNN(n_channels=8, n_samples=40, n_classes=n_classes)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    # Extract and fold weights
    sd = model.state_dict()

    # Conv blocks: conv + batchnorm folded
    blocks = []
    for i, layer_idx in enumerate([0, 4, 8]):  # indices in nn.Sequential
        conv_w = sd[f"features.{layer_idx}.weight"]    # (C_out, C_in, K)
        conv_b = sd[f"features.{layer_idx}.bias"]      # (C_out,)
        bn_w = sd[f"features.{layer_idx+1}.weight"]    # (C_out,)
        bn_b = sd[f"features.{layer_idx+1}.bias"]      # (C_out,)
        bn_m = sd[f"features.{layer_idx+1}.running_mean"]
        bn_v = sd[f"features.{layer_idx+1}.running_var"]
        w, b = fold_bn_into_conv(conv_w, conv_b, bn_w, bn_b, bn_m, bn_v)
        blocks.append((w.numpy(), b.numpy()))

    # Linear layers
    fc1_w = sd["classifier.0.weight"].numpy()  # (64, 320)
    fc1_b = sd["classifier.0.bias"].numpy()    # (64,)
    fc2_w = sd["classifier.2.weight"].numpy()  # (n_classes, 64)
    fc2_b = sd["classifier.2.bias"].numpy()    # (n_classes,)

    # Write weights header
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = output_dir / "model_weights.h"
    with open(weights_path, "w") as f:
        f.write("#ifndef MODEL_WEIGHTS_H\n#define MODEL_WEIGHTS_H\n\n")
        f.write(f"#define N_CLASSES {n_classes}\n\n")

        for i, (w, b) in enumerate(blocks):
            export_array(f, f"conv{i+1}_w", w)
            export_array(f, f"conv{i+1}_b", b)

        export_array(f, "fc1_w", fc1_w)
        export_array(f, "fc1_b", fc1_b)
        export_array(f, "fc2_w", fc2_w)
        export_array(f, "fc2_b", fc2_b)

        f.write("#endif\n")

    print(f"Weights written to {weights_path}")
    print(f"  Conv1: w{list(blocks[0][0].shape)}, b{list(blocks[0][1].shape)}")
    print(f"  Conv2: w{list(blocks[1][0].shape)}, b{list(blocks[1][1].shape)}")
    print(f"  Conv3: w{list(blocks[2][0].shape)}, b{list(blocks[2][1].shape)}")
    print(f"  FC1:   w{list(fc1_w.shape)}, b{list(fc1_b.shape)}")
    print(f"  FC2:   w{list(fc2_w.shape)}, b{list(fc2_b.shape)}")

    # Pick a test snippet and verify against PyTorch
    X, y, label_map, mean, std = load_shank_data(dataset_path, shank)
    inv_map = {v: k for k, v in label_map.items()}

    # Pick one from each class for testing
    test_indices = []
    for cls in range(n_classes):
        idx = np.where(y == cls)[0]
        if len(idx) > 0:
            test_indices.append(idx[0])

    # Use the first test snippet for the hardcoded demo
    test_idx = test_indices[0]
    test_input = X[test_idx]    # (8, 40), already normalized
    test_label = int(y[test_idx])
    test_unit = inv_map[test_label]

    # Verify with PyTorch
    with torch.no_grad():
        pt_out = model(torch.from_numpy(test_input).unsqueeze(0))
        pt_pred = pt_out.argmax(1).item()
        pt_conf = torch.softmax(pt_out, 1).max().item()
    print(f"\nPyTorch prediction: class {pt_pred} (unit {inv_map[pt_pred]}), "
          f"confidence {pt_conf:.3f}, true label: class {test_label} (unit {test_unit})")

    # Write test data header
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
