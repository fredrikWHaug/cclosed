"""
Export trained logistic regression weights and a test snippet as C header files.
"""

import numpy as np
import torch
from pathlib import Path
from train import load_shank_data
from compare_models import LogisticRegression


def export_array(f, name, arr, dtype="float"):
    flat = arr.flatten()
    f.write(f"// shape: {list(arr.shape)}\n")
    f.write(f"static const {dtype} {name}[{len(flat)}] = {{\n")
    for i in range(0, len(flat), 8):
        chunk = flat[i:i+8]
        f.write("    " + ", ".join(f"{v:.6f}f" for v in chunk) + ",\n")
    f.write("};\n\n")


def main():
    shank = 0
    dataset_path = Path(__file__).parent.parent / "dataset" / "dataset.npz"
    output_dir = Path(__file__).parent.parent / "firmware" / "logreg_classifier"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data and train
    X, y, label_map, mean, std = load_shank_data(dataset_path, shank)
    n_classes = len(label_map)
    inv_map = {v: k for k, v in label_map.items()}

    # Train the model
    print("Training logistic regression...")
    model = LogisticRegression(8, 40, n_classes)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = torch.nn.CrossEntropyLoss()

    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    split = int(0.8 * len(X))
    X_train = torch.from_numpy(X[idx[:split]])
    y_train = torch.from_numpy(y[idx[:split]])

    from torch.utils.data import DataLoader, TensorDataset
    loader = DataLoader(TensorDataset(X_train, y_train), batch_size=128, shuffle=True)

    for epoch in range(30):
        model.train()
        for xb, yb in loader:
            loss = criterion(model(xb), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    model.eval()
    sd = model.state_dict()
    W = sd["linear.weight"].numpy()  # (n_classes, 320)
    b = sd["linear.bias"].numpy()    # (n_classes,)

    print(f"  W shape: {W.shape}, b shape: {b.shape}")

    # Write weights
    weights_path = output_dir / "model_weights.h"
    with open(weights_path, "w") as f:
        f.write("#ifndef MODEL_WEIGHTS_H\n#define MODEL_WEIGHTS_H\n\n")
        f.write(f"#define N_CLASSES {n_classes}\n")
        f.write(f"#define INPUT_DIM 320\n\n")
        export_array(f, "logreg_w", W)
        export_array(f, "logreg_b", b)
        f.write("#endif\n")

    # Pick a test snippet
    test_idx = np.where(y == 0)[0][0]
    test_input = X[test_idx]  # (8, 40)
    test_label = int(y[test_idx])
    test_unit = inv_map[test_label]

    with torch.no_grad():
        pt_out = model(torch.from_numpy(test_input).unsqueeze(0))
        pt_pred = pt_out.argmax(1).item()
        pt_conf = torch.softmax(pt_out, 1).max().item()
    print(f"  PyTorch prediction: class {pt_pred} (unit {inv_map[pt_pred]}), "
          f"confidence {pt_conf:.3f}, true: class {test_label} (unit {test_unit})")

    # Write test data
    test_path = output_dir / "test_data.h"
    with open(test_path, "w") as f:
        f.write("#ifndef TEST_DATA_H\n#define TEST_DATA_H\n\n")
        f.write(f"#define TEST_TRUE_CLASS {test_label}\n")
        f.write(f"#define TEST_TRUE_UNIT {test_unit}\n\n")
        export_array(f, "test_snippet", test_input)
        f.write("#endif\n")

    print(f"  Weights: {weights_path}")
    print(f"  Test data: {test_path}")


if __name__ == "__main__":
    main()
