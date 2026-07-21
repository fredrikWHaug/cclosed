"""
Step 1 result: the HONEST per-shank classifier on the on-chip representation.

Loads dataset/onchip_260413.npz (raw .rhd -> bandpass -> CMR -> decimate snippets,
grouped per shank). For each shank with >= 2 units:
  - TIME split: train on the earliest 80% of spikes, test on the latest 20%.
    This is forward generalization = the deploy condition, not a random split.
  - logreg, balanced class weights.
  - report balanced accuracy vs the majority-class baseline and chance.

"accuracy" here = fidelity to the offline sorter's labels (goal A).

Usage:  python model/train_onchip.py
"""
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score, recall_score

ROOT = Path(__file__).resolve().parent.parent
d = np.load(ROOT / "dataset" / "onchip_260413.npz")
X, y, sh, t = d["snippets"], d["labels"], d["shanks"], d["times"]

print(f"{len(X)} snippets, shanks {sorted(set(sh.tolist()))}\n")
bals = []
for s in sorted(set(sh.tolist())):
    m = sh == s
    units = sorted(set(y[m].tolist()))
    if len(units) < 2:
        print(f"shank {s}: 1 unit (u{units[0]}) — nothing to classify, skip")
        continue
    Xs = X[m].reshape(m.sum(), -1)
    ys, ts = y[m], t[m]
    order = np.argsort(ts)
    cut = int(0.8 * len(order))
    tr, te = order[:cut], order[cut:]

    sc = StandardScaler().fit(Xs[tr])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    clf.fit(sc.transform(Xs[tr]), ys[tr])
    pred = clf.predict(sc.transform(Xs[te]))

    bal = balanced_accuracy_score(ys[te], pred)
    overall = (pred == ys[te]).mean()
    maj = max((ys[te] == u).mean() for u in units)
    rec = recall_score(ys[te], pred, labels=units, average=None, zero_division=0)
    bals.append(bal)
    print(f"shank {s}: {len(units)} units {units}  (train {len(tr)}, test {len(te)})")
    print(f"  balanced {bal:.3f} | overall {overall:.3f} | majority {maj:.3f} | chance {1/len(units):.3f}")
    print("  per-class recall: " + "  ".join(f"u{u}={r:.2f}" for u, r in zip(units, rec)))

if bals:
    print(f"\nmean balanced accuracy across multi-unit shanks: {np.mean(bals):.3f}")
