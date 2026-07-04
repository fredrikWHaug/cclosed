"""
Per-class accuracy evaluation of a trained spike classifier.

Usage:
    python evaluate.py                # defaults to shank 0
    python evaluate.py --shank 6
"""

import argparse
import numpy as np
import torch
from pathlib import Path
from train import SpikeCNN, load_shank_data


def evaluate(dataset_path: Path, shank: int, checkpoint_dir: Path):
    ckpt_path = checkpoint_dir / f"shank{shank}_best.pt"
    if not ckpt_path.exists():
        print(f"No checkpoint for shank {shank}")
        return

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    n_classes = ckpt["n_classes"]

    model = SpikeCNN(n_channels=8, n_samples=40, n_classes=n_classes)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    X, y, label_map, _, _ = load_shank_data(dataset_path, shank)
    inv_map = {v: k for k, v in label_map.items()}

    # Use same val split as training (seed=42, last 20%)
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(X))
    val_idx = idx[int(0.8 * len(X)):]

    X_val = torch.from_numpy(X[val_idx])
    y_val = y[val_idx]

    with torch.no_grad():
        logits = model(X_val)
        preds = logits.argmax(1).numpy()

    print(f"\nShank {shank} — Per-unit accuracy ({len(val_idx)} val samples)")
    print(f"{'Unit':>6} {'Class':>6} {'Correct':>8} {'Total':>6} {'Acc':>7}")
    print("-" * 38)

    total_correct = 0
    total = 0
    for cls in range(n_classes):
        mask = y_val == cls
        n = mask.sum()
        if n == 0:
            continue
        correct = (preds[mask] == cls).sum()
        acc = correct / n
        total_correct += correct
        total += n
        unit_id = inv_map[cls]
        print(f"{unit_id:>6} {cls:>6} {correct:>8} {n:>6} {acc:>7.1%}")

    print("-" * 38)
    print(f"{'ALL':>6} {'':>6} {total_correct:>8} {total:>6} {total_correct/total:>7.1%}")

    # Confusion pairs: show top misclassifications
    mistakes = preds != y_val
    if mistakes.sum() > 0:
        print(f"\nTop misclassifications:")
        print(f"{'True':>6} {'Pred':>6} {'Count':>6}")
        print("-" * 22)
        pairs = {}
        for true, pred in zip(y_val[mistakes], preds[mistakes]):
            key = (inv_map[true], inv_map[pred])
            pairs[key] = pairs.get(key, 0) + 1
        for (true_u, pred_u), count in sorted(pairs.items(), key=lambda x: -x[1])[:10]:
            print(f"{true_u:>6} {pred_u:>6} {count:>6}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path,
                        default=Path(__file__).parent.parent / "dataset" / "dataset.npz")
    parser.add_argument("--shank", type=int, default=0)
    args = parser.parse_args()

    checkpoint_dir = Path(__file__).parent / "checkpoints"
    evaluate(args.dataset, args.shank, checkpoint_dir)
