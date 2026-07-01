"""
Train a 1D CNN to classify spike snippets by unit ID.

Trains per-shank: each shank has its own set of units, and on-chip
you'd know which shank a spike came from before classifying.

Usage:
    python train.py                    # defaults to shank 0 (most data)
    python train.py --shank 6          # train on shank 6
    python train.py --shank all        # train all shanks sequentially
"""

import argparse
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, TensorDataset


class SpikeCNN(nn.Module):
    """Small 1D CNN for spike classification. Designed to be INT8-quantizable."""

    def __init__(self, n_channels: int, n_samples: int, n_classes: int):
        super().__init__()
        self.features = nn.Sequential(
            # Block 1: (batch, 8, 40) -> (batch, 32, 20)
            nn.Conv1d(n_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),
            # Block 2: (batch, 32, 20) -> (batch, 64, 10)
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
            # Block 3: (batch, 64, 10) -> (batch, 64, 5)
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )
        self.classifier = nn.Sequential(
            nn.Linear(64 * 5, 64),
            nn.ReLU(),
            nn.Linear(64, n_classes),
        )

    def forward(self, x):
        # x: (batch, n_channels, n_samples)
        x = self.features(x)
        x = x.flatten(1)
        return self.classifier(x)


def load_shank_data(dataset_path: Path, shank: int):
    """Load and prepare data for one shank. Returns X, y, label_map."""
    data = np.load(dataset_path)
    snippets = data["snippets"]    # (N, 40, 8)
    labels = data["labels"]        # (N,)
    shank_ids = data["shank_ids"]  # (N,)

    # Filter to this shank
    mask = shank_ids == shank
    X = snippets[mask]  # (n, 40, 8)
    y = labels[mask]    # (n,)

    # Re-index labels to 0..K-1
    unique_labels = np.unique(y)
    label_map = {old: new for new, old in enumerate(unique_labels)}
    y = np.array([label_map[l] for l in y], dtype=np.int64)

    # Transpose to (n, 8, 40) for Conv1d (channels first)
    X = X.transpose(0, 2, 1).astype(np.float32)

    # Normalize per-channel (zero mean, unit variance)
    mean = X.mean(axis=(0, 2), keepdims=True)
    std = X.std(axis=(0, 2), keepdims=True) + 1e-8
    X = (X - mean) / std

    return X, y, label_map, mean, std


def train_shank(dataset_path: Path, shank: int, output_dir: Path,
                epochs: int = 30, batch_size: int = 128, lr: float = 1e-3):
    print(f"\n{'='*50}")
    print(f"Shank {shank}")
    print(f"{'='*50}")

    X, y, label_map, mean, std = load_shank_data(dataset_path, shank)
    n_classes = len(label_map)
    print(f"  Samples: {len(X)}, Classes: {n_classes}")

    if n_classes < 2:
        print("  Skipping — fewer than 2 classes")
        return

    # Print class distribution
    for old_id, new_id in sorted(label_map.items(), key=lambda x: x[1]):
        count = (y == new_id).sum()
        print(f"    Unit {old_id} -> class {new_id}: {count} spikes")

    # Train/val split (80/20, shuffled)
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    split = int(0.8 * len(X))
    train_idx, val_idx = idx[:split], idx[split:]

    X_train = torch.from_numpy(X[train_idx])
    y_train = torch.from_numpy(y[train_idx])
    X_val = torch.from_numpy(X[val_idx])
    y_val = torch.from_numpy(y[val_idx])

    train_loader = DataLoader(
        TensorDataset(X_train, y_train),
        batch_size=batch_size, shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(X_val, y_val),
        batch_size=batch_size,
    )

    # Model
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SpikeCNN(n_channels=8, n_samples=40, n_classes=n_classes).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  Model params: {param_count:,}")
    print(f"  Device: {device}")
    print(f"  Training...")

    best_val_acc = 0.0
    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            out = model(xb)
            loss = criterion(out, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(xb)
            train_correct += (out.argmax(1) == yb).sum().item()
            train_total += len(xb)

        # Validate
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                out = model(xb)
                val_correct += (out.argmax(1) == yb).sum().item()
                val_total += len(xb)

        train_acc = train_correct / train_total
        val_acc = val_correct / val_total
        avg_loss = train_loss / train_total

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            save_path = output_dir / f"shank{shank}_best.pt"
            torch.save({
                "model_state": model.state_dict(),
                "label_map": label_map,
                "n_classes": n_classes,
                "norm_mean": mean,
                "norm_std": std,
                "val_acc": val_acc,
                "epoch": epoch,
            }, save_path)

        if epoch % 5 == 0 or epoch == epochs - 1:
            print(f"    Epoch {epoch:3d}  loss={avg_loss:.4f}  "
                  f"train_acc={train_acc:.3f}  val_acc={val_acc:.3f}"
                  f"{'  *best*' if val_acc >= best_val_acc else ''}")

    print(f"  Best val accuracy: {best_val_acc:.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path,
                        default=Path(__file__).parent.parent / "dataset" / "dataset.npz")
    parser.add_argument("--shank", type=str, default="0",
                        help="Shank index (0-9) or 'all'")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    output_dir = Path(__file__).parent / "checkpoints"
    output_dir.mkdir(exist_ok=True)

    shanks = range(10) if args.shank == "all" else [int(args.shank)]
    for s in shanks:
        train_shank(args.dataset, s, output_dir,
                    epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)


if __name__ == "__main__":
    main()
