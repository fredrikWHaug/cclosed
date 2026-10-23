"""Quick, interpretable spike sorting + deployable classification on a Theo capture.

    python sort_classify.py CAPTURE.bin [OUT.png]

Every acquisition-side stage is causal and portable to the nRF: 2nd-order IIR
bandpass, threshold on the filtered sample, trough alignment with a 1 ms
lookahead, fixed-length snippet. Sorting (unsupervised, offline) defines the
units; the classifier that would run on the device (nearest template) is scored
on a held-out second half against the sorter's labels, with logistic regression
as a drop-in comparison and a second sorter as the agreement ceiling.
"""
import struct, sys
import numpy as np
from scipy import signal as sig
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score
from sklearn.linear_model import LogisticRegression

RATE = 20000.0
PRE, POST = 12, 24                      # snippet = 1.8 ms around the trough

def load(path):
    data = open(path, "rb").read(); pls, i = [], 0
    while i + 10 <= len(data):
        t, ln = struct.unpack_from("<dH", data, i); i += 10
        pls.append(np.frombuffer(data[i+2:i+ln], dtype="<u2")); i += ln
    return (np.concatenate(pls).astype(np.float64) - 32768.0) * 0.195

def detect(x):
    """Causal: IIR bandpass, threshold crossing, trough within the next 20 samples."""
    sos = sig.butter(2, [300/(RATE/2), 5000/(RATE/2)], "bandpass", output="sos")
    y = sig.sosfilt(sos, x)
    thr = 4 * np.median(np.abs(y[:int(5*RATE)])) / 0.6745     # from the first 5 s only
    below = y < -thr
    on = np.flatnonzero(below[1:] & ~below[:-1]) + 1
    troughs, last = [], -1e9
    for o in on:
        if o - last < 0.0015*RATE or o + 20 >= len(y) or o < PRE: continue
        t = o + np.argmin(y[o:o+20]); troughs.append(t); last = t
    troughs = np.array(troughs)
    snips = np.array([y[t-PRE:t+POST] for t in troughs])
    return y, thr, troughs, snips

def agreement(pred, ref):
    """Best label permutation agreement (labels are arbitrary across methods)."""
    from itertools import permutations
    k = max(pred.max(), ref.max()) + 1
    return max(np.mean(np.array([p[v] for v in pred]) == ref) for p in permutations(range(k)))

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else None
x = load(path)
y, thr, troughs, snips = detect(x)
n = len(snips)
print(f"{path}: {len(x)/RATE:.0f} s, threshold {thr:.0f} uV, {n} spikes ({n/(len(x)/RATE):.1f}/s)")

# ---- sorting (offline, unsupervised): PCA -> k-means, k by silhouette ----
pcs = PCA(n_components=3).fit_transform(snips)
def violations(lab, k):
    return max(np.mean(np.diff(troughs[lab == u] / RATE) < 0.002) for u in range(k) if (lab == u).sum() > 1)
# unit count: the smallest k whose units are all refractory-clean (a merged
# cluster shows <2 ms intervals); silhouette alone under-splits small units
fits = {k: KMeans(k, n_init=10, random_state=0).fit_predict(pcs) for k in range(2, 6)}
best = next((k for k in fits if violations(fits[k], k) == 0), 2)
labels = fits[best]
sil = silhouette_score(pcs, labels)
order = np.argsort([snips[labels == u].mean(0).min() for u in range(best)])   # unit 0 = largest spike
labels = np.argsort(order)[labels]
print(f"sorter: k-means on 3 PCs, smallest refractory-clean k = {best} units (silhouette {sil:.2f})")
for u in range(best):
    t = troughs[labels == u] / RATE
    viol = np.mean(np.diff(t) < 0.002) if len(t) > 1 else 0
    print(f"  unit {u}: {np.sum(labels==u):4d} spikes, trough {snips[labels==u].mean(0).min():6.0f} uV, "
          f"refractory violations {100*viol:.1f}%")

# ---- second sorter: agreement ceiling ----
gmm = GaussianMixture(best, n_init=5, random_state=0).fit_predict(pcs)
ceiling = agreement(gmm, labels)
print(f"second sorter (GMM) agrees with k-means on {100*ceiling:.1f}% of spikes  <- ceiling")

# ---- deployable classifiers: train on first half (time split), test on second ----
half = troughs < troughs[len(troughs)//2]
templates = np.array([snips[half & (labels == u)].mean(0) for u in range(best)])
d = ((snips[~half][:, None, :] - templates[None]) ** 2).sum(-1)
tm = d.argmin(1)
acc_tm = np.mean(tm == labels[~half])
lr = LogisticRegression(max_iter=2000).fit(snips[half], labels[half])
acc_lr = np.mean(lr.predict(snips[~half]) == labels[~half])
print(f"held-out second half ({(~half).sum()} spikes):")
print(f"  nearest-template agreement with sorter: {100*acc_tm:.1f}%")
print(f"  logistic-regression agreement:          {100*acc_lr:.1f}%")
conf = np.array([[np.sum((labels[~half] == r) & (tm == c)) for c in range(best)] for r in range(best)])
print("  confusion (rows = sorter unit, cols = template decision):\n" + "\n".join("    " + " ".join(f"{v:4d}" for v in row) for row in conf))

if out:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Helvetica", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False})
    cols = ["#2c6fad", "#c76bae", "#e0a030", "#4f9d69"]
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.4), gridspec_kw={"width_ratios": [1, 1.3, 0.8]})
    for u in range(best):
        ax[0].plot(pcs[labels == u, 0], pcs[labels == u, 1], ".", ms=4, color=cols[u], alpha=0.6)
    ax[0].set_xlabel("PC 1"); ax[0].set_ylabel("PC 2")
    ax[0].set_title(f"sorting: {best} units (silhouette {sil:.2f})", fontsize=9, loc="left")
    ts = (np.arange(PRE+POST) - PRE) / RATE * 1000
    for u in range(best):
        s = snips[labels == u]
        ax[1].fill_between(ts, s.mean(0)-s.std(0), s.mean(0)+s.std(0), color=cols[u], alpha=0.15)
        ax[1].plot(ts, s.mean(0), color=cols[u], lw=2, label=f"unit {u}  n={len(s)}")
    ax[1].axhline(-thr, color="#8a8a87", ls=":", lw=1)
    ax[1].text(ts[-1], -thr, " threshold", color="#8a8a87", va="center", fontsize=8)
    ax[1].set_xlabel("ms from trough"); ax[1].set_ylabel("uV")
    ax[1].set_title("templates (mean ± sd)", fontsize=9, loc="left"); ax[1].legend(frameon=False, fontsize=8)
    ax[2].imshow(conf, cmap="Blues", vmin=0)
    for r in range(best):
        for c in range(best):
            ax[2].text(c, r, conf[r, c], ha="center", va="center", fontsize=9,
                       color="white" if conf[r, c] > conf.max()/2 else "#1f1f1e")
    ax[2].set_xticks(range(best)); ax[2].set_yticks(range(best))
    ax[2].set_xlabel("template decision"); ax[2].set_ylabel("sorter unit")
    ax[2].set_title(f"held-out agreement {100*acc_tm:.0f}%", fontsize=9, loc="left")
    fig.suptitle(f"{path.split('/')[-1]} - {n} spikes, nearest-template {100*acc_tm:.0f}% vs sorter "
                 f"(logreg {100*acc_lr:.0f}%, sorter-vs-sorter ceiling {100*ceiling:.0f}%)",
                 fontsize=10, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(out, dpi=150)
    print("saved", out)
