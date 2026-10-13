"""Histogram figures of inter-sample intervals for the CP1 document.

Usage: python3 plot_regularity_hist.py BEFORE.CSV AFTER.CSV OUTDIR

Reads the two Tek waveform CSVs (software-paced and hardware-timed CSN
captures), extracts falling-edge intervals exactly as analyze_csn_csv.py
does, and writes two candidate figures with a SHARED x axis:
  OUTDIR/regularity_hist_two.pdf   - two stacked panels
  OUTDIR/regularity_hist_one.pdf   - single panel, overlaid colors
Vector PDF output; styling matched to the document figures (Helvetica,
minimal ink, simplified labels).
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "pdf.fonttype": 42,         # embed TrueType, not Type 3 (IEEE PDF eXpress rejects Type 3)
    "font.family": "Helvetica",
    "font.size": 8,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "mathtext.fontset": "custom",
    "mathtext.rm": "Helvetica",
    "mathtext.it": "Helvetica:italic",
    "mathtext.bf": "Helvetica:bold",
})

def edges_us(path):
    t, v = [], []
    with open(path, errors="ignore") as f:
        for line in f:
            parts = line.strip().split(",")
            try:
                ti = float(parts[-2]); vi = float(parts[-1])
            except (ValueError, IndexError):
                continue
            t.append(ti); v.append(vi)
    t = np.asarray(t); v = np.asarray(v)
    lo, hi = np.percentile(v, [1, 99])
    thresh = (lo + hi) / 2
    above = v > thresh
    idx = np.where(above[:-1] & ~above[1:])[0]
    frac = (v[idx] - thresh) / (v[idx] - v[idx + 1])
    edges = t[idx] + frac * (t[idx + 1] - t[idx])
    return np.diff(edges) * 1e6

before_csv, after_csv, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
sw = edges_us(before_csv)
hw = edges_us(after_csv)
print(f"software-paced: n={len(sw)}, sd={sw.std():.2f} us")
print(f"hardware-timed: n={len(hw)}, sd={hw.std():.2f} us")

XMAX = 120            # shared x axis; covers the bulk of both (note outliers in text)
bins = np.linspace(0, XMAX, 121)
C_SW, C_HW = "#c76bae", "#2c6fad"   # red-ish = software, blue = hardware

# --- candidate A: two stacked panels, shared x ---
fig, (a1, a2) = plt.subplots(2, 1, figsize=(5.4, 2.8), sharex=True)
a1.hist(np.clip(sw, 0, XMAX), bins=bins, color=C_SW)
a2.hist(np.clip(hw, 0, XMAX), bins=bins, color=C_HW)
a1.set_title("software-paced", fontsize=8, loc="left")
a2.set_title("hardware-timed", fontsize=8, loc="left")
for a in (a1, a2):
    a.set_yscale("log")
    a.set_ylabel("count")
a2.set_xlabel("interval (µs)")
a2.set_xlim(0, XMAX)
fig.tight_layout()
fig.savefig(f"{outdir}/regularity_hist_two.pdf")

# --- candidate B: one panel, overlaid ---
fig2, ax = plt.subplots(figsize=(3.1, 1.9))
ax.hist(np.clip(sw, 0, XMAX), bins=bins, color=C_SW, alpha=0.75, label="software-paced")
ax.hist(np.clip(hw, 0, XMAX), bins=bins, color=C_HW, alpha=0.75, label="hardware-timed")
ax.set_yscale("log")
ax.set_xlim(0, XMAX)
ax.set_xlabel("interval (µs)")
ax.set_ylabel("count")
ax.legend(frameon=False, fontsize=8)
fig2.tight_layout()
fig2.savefig(f"{outdir}/regularity_hist_one.pdf")
print(f"wrote {outdir}/regularity_hist_two.pdf and regularity_hist_one.pdf")
