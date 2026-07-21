"""
Zoom into a single spike from the SAME synthetic signal that sim/scope.py streams.

The signal-generation block below is copied verbatim from sim/scope.py (same seed,
same template, same noise), so this plots exactly the spikes you see scrolling by —
just frozen and zoomed in on one, with the underlying noiseless template overlaid.

Run:  python sim/spike_zoom.py
"""
import numpy as np
import matplotlib.pyplot as plt

# ---- identical to sim/scope.py ------------------------------------------------
FS = 30_000
tt = (np.arange(-30, 30) / FS) * 1000                                  # ms
spike = -100 * np.exp(-(tt ** 2) / 0.02) + 35 * np.exp(-((tt - 0.4) ** 2) / 0.05)  # µV
rng = np.random.default_rng(0)
N = 20 * FS
signal = rng.normal(0, 8, N)
spots = np.where(rng.random(N) < 5 / FS)[0]
for t0 in spots:
    signal[t0:t0 + spike.size] += spike[:N - t0]
# ------------------------------------------------------------------------------

t0 = spots[0]                        # first spike; try spots[1], spots[2], ... to see others
W = 90                               # ±3 ms zoom window
peak = t0 + 30                       # the trough sits 30 samples into the template
seg = signal[peak - W:peak + W]
axis = (np.arange(seg.size) - W) / FS * 1000

plt.figure(figsize=(7, 4))
plt.plot(axis, seg, lw=1.2, color="blue", label="recorded (spike + noise)")
plt.plot(tt, spike, lw=2.0, color="red", ls="--", label="underlying template (noiseless)")
plt.axhline(0, color="gray", lw=0.5)
plt.xlabel("time (ms)"); plt.ylabel("µV"); plt.title("one spike, zoomed in")
plt.legend(); plt.tight_layout(); plt.show()
