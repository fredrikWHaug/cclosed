"""
Compare three model architectures on spike classification:
  1. Logistic regression (single linear layer)
  2. CNN (current model)
  3. Small ResNet (heaviest deployable option)

Usage:
    python compare_models.py              # shank 0
    python compare_models.py --shank 6
"""

import argparse
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, TensorDataset
from train import SpikeCNN, load_shank_data


class LogisticRegression(nn.Module):
    """Single linear layer. Input is flattened (8*40=320) -> n_classes."""

    def __init__(self, n_channels: int, n_samples: int, n_classes: int):
        super().__init__()
        self.linear = nn.Linear(n_channels * n_samples, n_classes)

    def forward(self, x):
        return self.linear(x.flatten(1))


class ResBlock(nn.Module):
    """Residual block: two conv layers with a skip connection."""

    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(channels)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(channels)

    def forward(self, x):
        residual = x
        out = torch.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return torch.relu(out + residual)


class SpikeResNet(nn.Module):
    """Small ResNet for spike classification."""

    def __init__(self, n_channels: int, n_samples: int, n_classes: int):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(n_channels, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
        )
        self.res1 = ResBlock(64)
        self.pool1 = nn.MaxPool1d(2)  # 40 -> 20

        self.expand = nn.Sequential(
            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
        )
        self.res2 = ResBlock(128)
        self.pool2 = nn.MaxPool1d(2)  # 20 -> 10

        self.res3 = ResBlock(128)
        self.pool3 = nn.MaxPool1d(2)  # 10 -> 5

        self.classifier = nn.Sequential(
            nn.Linear(128 * 5, 128),
            nn.ReLU(),
            nn.Linear(128, n_classes),
        )

    def forward(self, x):
        x = self.stem(x)
        x = self.pool1(self.res1(x))
        x = self.expand(x)
        x = self.pool2(self.res2(x))
        x = self.pool3(self.res3(x))
        return self.classifier(x.flatten(1))


def train_and_eval(model, name, X_train, y_train, X_val, y_val,
                   epochs=30, batch_size=128, lr=1e-3):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = model.to(device)

    param_count = sum(p.numel() for p in model.parameters())

    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
        batch_size=batch_size, shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
        batch_size=batch_size,
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
        all_preds = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                all_preds.append(model(xb).argmax(1).cpu().numpy())

        preds = np.concatenate(all_preds)
        val_acc = (preds == y_val).mean()

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_preds = preds

    return name, param_count, best_val_acc, best_preds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path,
                        default=Path(__file__).parent.parent / "dataset" / "dataset.npz")
    parser.add_argument("--shank", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()

    X, y, label_map, _, _ = load_shank_data(args.dataset, args.shank)
    inv_map = {v: k for k, v in label_map.items()}
    n_classes = len(label_map)

    # Same split as train.py
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    split = int(0.8 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    y_train, y_val = y[idx[:split]], y[idx[split:]]

    print(f"Shank {args.shank}: {len(X_train)} train, {len(X_val)} val, {n_classes} classes\n")

    models = [
        (LogisticRegression(8, 40, n_classes), "Logistic Regression"),
        (SpikeCNN(8, 40, n_classes), "CNN (current)"),
        (SpikeResNet(8, 40, n_classes), "Small ResNet"),
    ]

    results = []
    for model, name in models:
        print(f"Training {name}...")
        result = train_and_eval(model, name, X_train, y_train, X_val, y_val,
                                epochs=args.epochs)
        results.append(result)
        print(f"  Done: {result[2]:.1%}\n")

    # Summary table
    print(f"\n{'Model':<25} {'Params':>10} {'Val Acc':>10}")
    print("-" * 47)
    for name, params, acc, _ in results:
        print(f"{name:<25} {params:>10,} {acc:>10.1%}")

    # Per-class comparison
    print(f"\nPer-unit accuracy:")
    header = f"{'Unit':>6}"
    for name, _, _, _ in results:
        header += f"  {name[:8]:>10}"
    print(header)
    print("-" * len(header))

    for cls in range(n_classes):
        mask = y_val == cls
        n = mask.sum()
        if n == 0:
            continue
        unit_id = inv_map[cls]
        row = f"{unit_id:>6}"
        for _, _, _, preds in results:
            cls_acc = (preds[mask] == cls).sum() / n
            row += f"  {cls_acc:>10.1%}"
        row += f"  (n={n})"
        print(row)


if __name__ == "__main__":
    main()
