"""
Time-split validation: train on first half of recording, test on second half.
This tests whether the model learned waveform shapes vs memorizing temporal patterns.

Usage:
    python time_split_test.py
"""

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, TensorDataset
from train import SpikeCNN, load_shank_data


class LogisticRegression(nn.Module):
    def __init__(self, n_channels, n_samples, n_classes):
        super().__init__()
        self.linear = nn.Linear(n_channels * n_samples, n_classes)

    def forward(self, x):
        return self.linear(x.flatten(1))


def train_and_eval(model, X_train, y_train, X_val, y_val,
                   epochs=30, batch_size=128, lr=1e-3):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(device)

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
        batch_size=batch_size, shuffle=True,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    best_val_acc = 0.0
    best_preds = None

    for epoch in range(epochs):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            loss = criterion(model(xb), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            X_v = torch.from_numpy(X_val).to(device)
            preds = model(X_v).argmax(1).cpu().numpy()

        val_acc = (preds == y_val).mean()
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_preds = preds

    return best_val_acc, best_preds


def main():
    dataset_path = Path(__file__).parent.parent / "dataset" / "dataset.npz"
    shank = 0

    # Load raw data (before shuffling)
    data = np.load(dataset_path)
    snippets = data["snippets"]
    labels = data["labels"]
    shank_ids = data["shank_ids"]
    times = data["times"]

    # Filter to shank
    mask = shank_ids == shank
    X = snippets[mask]
    y = labels[mask]
    t = times[mask]

    # Re-index labels
    unique_labels = np.unique(y)
    label_map = {old: new for new, old in enumerate(unique_labels)}
    inv_map = {v: k for k, v in label_map.items()}
    y = np.array([label_map[l] for l in y], dtype=np.int64)
    n_classes = len(label_map)

    # Transpose and normalize
    X = X.transpose(0, 2, 1).astype(np.float32)
    mean = X.mean(axis=(0, 2), keepdims=True)
    std = X.std(axis=(0, 2), keepdims=True) + 1e-8
    X = (X - mean) / std

    # TIME SPLIT: sort by spike time, first half train, second half test
    time_order = np.argsort(t)
    split = len(time_order) // 2

    train_idx = time_order[:split]
    val_idx = time_order[split:]

    X_train, X_val = X[train_idx], X[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]

    print(f"Shank {shank}: {len(X_train)} train (first half), {len(X_val)} val (second half)")
    print(f"Classes: {n_classes}\n")

    # Also run random split for direct comparison
    rng = np.random.default_rng(42)
    rand_idx = rng.permutation(len(X))
    rand_split = int(0.8 * len(X))
    X_train_rand, X_val_rand = X[rand_idx[:rand_split]], X[rand_idx[rand_split:]]
    y_train_rand, y_val_rand = y[rand_idx[:rand_split]], y[rand_idx[rand_split:]]

    print("=" * 55)
    print("Logistic Regression")
    print("=" * 55)

    print("  Training (random split)...")
    rand_acc, _ = train_and_eval(
        LogisticRegression(8, 40, n_classes),
        X_train_rand, y_train_rand, X_val_rand, y_val_rand)

    print("  Training (time split)...")
    time_acc, time_preds = train_and_eval(
        LogisticRegression(8, 40, n_classes),
        X_train, y_train, X_val, y_val)

    print(f"\n  Random split: {rand_acc:.1%}")
    print(f"  Time split:   {time_acc:.1%}")
    print(f"  Drop:         {rand_acc - time_acc:+.1%}")

    # Per-unit for time split
    print(f"\n  Per-unit (time split):")
    print(f"  {'Unit':>6} {'Correct':>8} {'Total':>6} {'Acc':>7}")
    print(f"  {'-'*32}")
    for cls in range(n_classes):
        cls_mask = y_val == cls
        n = cls_mask.sum()
        if n == 0:
            continue
        correct = (time_preds[cls_mask] == cls).sum()
        print(f"  {inv_map[cls]:>6} {correct:>8} {n:>6} {correct/n:>7.1%}")


if __name__ == "__main__":
    main()
