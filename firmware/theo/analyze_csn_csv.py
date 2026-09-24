"""Regularity of sampling from a scope CSV capture of the CS (CSN) line.

Usage: python analyze_csn_csv.py TEK00000.CSV [nominal_rate_hz]

Feed it a Tektronix TBS2000B waveform CSV (Save > Waveform > CSV) of the
Intan chip-select line while streaming. Every falling edge is one sample
request; this computes the full distribution of inter-sample intervals:
mean / sigma / min / max, plus a histogram and interval-vs-time plot, and
saves <name>_regularity.png and <name>_regularity.txt next to the CSV.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt

path = sys.argv[1]
nominal_hz = float(sys.argv[2]) if len(sys.argv) > 2 else 20000.0
nominal_us = 1e6 / nominal_hz

# --- load: Tek CSVs have a header block; data rows are "time,volts" ---
t, v = [], []
with open(path, errors="ignore") as f:
    for line in f:
        parts = line.strip().split(",")
        # accept rows whose last two fields parse as floats
        try:
            ti = float(parts[-2]); vi = float(parts[-1])
        except (ValueError, IndexError):
            continue
        t.append(ti); v.append(vi)
t = np.asarray(t); v = np.asarray(v)
if len(t) < 100:
    raise SystemExit(f"only {len(t)} data rows parsed - is this a waveform CSV?")

dt_scope = np.median(np.diff(t))
print(f"{len(t)} points, scope resolution {dt_scope*1e9:.0f} ns, "
      f"span {(t[-1]-t[0])*1e3:.1f} ms")

# --- falling-edge times at the midpoint threshold, linearly interpolated ---
lo, hi = np.percentile(v, [1, 99])
thresh = (lo + hi) / 2
above = v > thresh
idx = np.where(above[:-1] & ~above[1:])[0]          # high -> low crossings
if len(idx) < 3:
    raise SystemExit("fewer than 3 falling edges found - wrong channel/level?")
frac = (v[idx] - thresh) / (v[idx] - v[idx + 1])    # sub-sample interpolation
edges = t[idx] + frac * (t[idx + 1] - t[idx])

iv = np.diff(edges) * 1e6                            # intervals in microseconds
print(f"{len(iv)} intervals")

mean, sd = iv.mean(), iv.std()
report = (f"CSN regularity report: {path}\n"
          f"intervals          {len(iv)}\n"
          f"nominal            {nominal_us:.2f} us ({nominal_hz:.0f} S/s)\n"
          f"mean               {mean:.2f} us  ({1e6/mean:.1f} S/s average)\n"
          f"std dev            {sd:.2f} us\n"
          f"min                {iv.min():.2f} us\n"
          f"max                {iv.max():.2f} us\n"
          f"within +/-10% of nominal: {100*np.mean(np.abs(iv-nominal_us) < 0.1*nominal_us):.1f}%\n")
print("\n" + report)
base = path.rsplit(".", 1)[0]
open(base + "_regularity.txt", "w").write(report)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
a1.hist(iv, bins=100)
a1.axvline(nominal_us, color="r", ls="--", label=f"nominal {nominal_us:.1f} us")
a1.set_xlabel("interval (us)"); a1.set_ylabel("count"); a1.set_yscale("log")
a1.set_title(f"inter-sample intervals: mean {mean:.1f}, sd {sd:.1f} us"); a1.legend()
a2.plot(edges[1:] * 1e3, iv, ".", ms=2)
a2.axhline(nominal_us, color="r", ls="--")
a2.set_xlabel("time (ms)"); a2.set_ylabel("interval (us)")
a2.set_title("interval vs time (bursts show as low outliers)")
plt.tight_layout()
fig.savefig(base + "_regularity.png", dpi=150)
print(f"saved {base}_regularity.txt and _regularity.png")
plt.show()
