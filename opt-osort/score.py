#!/usr/bin/env python3
"""
Score opt_osort's predicted clusters against the true unit labels.

opt-OSort is unsupervised, so its cluster ids are arbitrary — we find the optimal
cluster->unit assignment (Hungarian) and report sorting accuracy. Discarded spikes
(label -1) count as errors in the honest number.

    python score.py
"""
import numpy as np
from scipy.optimize import linear_sum_assignment

true = np.loadtxt("true_labels.txt", dtype=int)
pred = np.loadtxt("labels.txt", dtype=int)          # -1 = discarded
assert len(true) == len(pred), "length mismatch between true_labels and labels"

units = sorted(set(true.tolist()))
clusters = sorted(set(pred[pred >= 0].tolist()))
ui = {u: i for i, u in enumerate(units)}
ci = {c: i for i, c in enumerate(clusters)}

conf = np.zeros((len(clusters), len(units)), dtype=int)   # rows=cluster, cols=unit
for t, p in zip(true, pred):
    if p >= 0:
        conf[ci[p], ui[t]] += 1

# optimal cluster -> unit assignment (maximise correct)
r, c = linear_sum_assignment(-conf)
correct = int(conf[r, c].sum())
total = len(true)
discarded = int((pred < 0).sum())

print(f"spikes {total} | true units {len(units)} | clusters {len(clusters)} | discarded {discarded}")
print("\ncluster -> unit   (correct / cluster size = purity):")
for ri, cj in zip(r, c):
    cl, un, n = clusters[ri], units[cj], conf[ri].sum()
    print(f"  cluster {cl} -> neuron_{un}: {conf[ri, cj]:5d} / {n:5d}  ({conf[ri, cj]/n:.0%})")

print(f"\nsorting accuracy (discards = errors):  {correct/total:.1%}  ({correct}/{total})")
assigned = total - discarded
if assigned:
    print(f"accuracy among assigned spikes only  :  {correct/assigned:.1%}  ({correct}/{assigned})")
