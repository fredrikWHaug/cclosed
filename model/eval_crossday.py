"""
Cross-day generalization test for the logreg spike classifier.

Question: does a classifier trained on DAY 1 still identify the same neurons on
DAY 2, or does representational drift break it?

Protocol (no leakage, no shortcuts):
  - features  = peak-channel 40-sample waveform (shape alone; see build_crossday)
  - fit a StandardScaler on DAY-1 TRAIN only, apply everywhere
  - train multinomial logistic regression on 80% of day 1
  - evaluate on:
        (a) held-out 20% of day 1  -> within-day ceiling
        (b) ALL of day 2           -> cross-day generalization
  - the gap between (a) and (b) is the cost of one day of drift.

Class imbalance is large (unit 47 ~35k vs unit 68 ~368 on day 1), so we use
balanced class weights and report balanced accuracy (macro recall) + per-class
recall + confusion, not just overall accuracy.

Caveats — this is a CONSERVATIVE BASELINE, not a headline result:
  - Host-side only. Nothing here runs on the nRF54; on-chip portability is a
    separate, unverified step (export weights -> flash -> match predictions).
  - Selection effect. We can only test neurons match_dict could TRACK across
    days, and trackable => stable. Drifted neurons are untrackable and excluded,
    so "a day-1 model still works on day-2" is close to tautological here.
  - Information floor. The 4 neurons' single-channel waveforms correlate
    0.97-1.00, so ~66% balanced accuracy is a shape/amplitude ceiling, not a
    model-capacity limit. NOT comparable to the earlier 99% (same-day,
    8-channel, per-shank) — that result differs on three axes at once, so the
    drop cannot be attributed to drift alone. Next step: same-shank 8-channel
    detection, varying one axis at a time.

Usage:
    python model/eval_crossday.py
"""

import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, recall_score

DATA = Path(__file__).parent.parent / "dataset" / "crossday.npz"
SEED = 42


def report(name, y_true, y_pred, classes):
    acc = (y_true == y_pred).mean()
    bal = balanced_accuracy_score(y_true, y_pred)
    rec = recall_score(y_true, y_pred, labels=classes, average=None, zero_division=0)
    print(f"\n=== {name} ===  (n={len(y_true)})")
    print(f"  overall accuracy : {acc:.3f}")
    print(f"  balanced accuracy: {bal:.3f}   (mean per-class recall)")
    print(f"  per-class recall : " + "  ".join(f"u{c}={r:.3f}" for c, r in zip(classes, rec)))
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    print(f"  confusion (rows=true {classes}, cols=pred):")
    for c, row in zip(classes, cm):
        print(f"    u{c:>2} | " + " ".join(f"{v:6d}" for v in row))
    return acc, bal


def main():
    d = np.load(DATA)
    X, y, sess = d["waveforms"], d["labels"], d["sessions"]
    classes = sorted(np.unique(y).tolist())

    d1 = sess == 0
    d2 = sess == 1
    X1, y1 = X[d1], y[d1]
    X2, y2 = X[d2], y[d2]

    # stratified 80/20 split of day 1
    rng = np.random.default_rng(SEED)
    tr = np.zeros(len(y1), dtype=bool)
    for c in classes:
        idx = np.where(y1 == c)[0]
        rng.shuffle(idx)
        tr[idx[: int(0.8 * len(idx))]] = True
    te = ~tr

    scaler = StandardScaler().fit(X1[tr])          # day-1 train stats only
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    clf.fit(scaler.transform(X1[tr]), y1[tr])

    _, bal1 = report("DAY 1 held-out (within-day ceiling)",
                     y1[te], clf.predict(scaler.transform(X1[te])), classes)
    _, bal2 = report("DAY 2 (cross-day generalization)",
                     y2, clf.predict(scaler.transform(X2)), classes)

    print(f"\nDrift cost: balanced accuracy {bal1:.3f} (day1) -> {bal2:.3f} (day2)"
          f"  = {(bal1 - bal2) * 100:.1f} pts")


if __name__ == "__main__":
    main()
