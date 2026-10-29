"""One figure that states the problem: spikes caught and noise, against total conversions per second.

    python compare.py a_1ch_30k.bin:30000 b_4ch_6k.bin:6000 c_4ch_30k.bin:30000

Each argument is CAPTURE.bin:RATE_HZ. Channel count is read from the file. Saves compare.png.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from check import read, SYNC_MS, SYNC_RATE

rows = []
for arg in sys.argv[1:]:
    path, rate = arg.rsplit(":", 1); rate = float(rate)
    ev = read(path)
    seconds = ev["wall"][-1] - ev["wall"][0]
    channels = sorted(set(ev["ch"])); pre = int(ev["pre"][0])
    caught, noise = [], []
    for c in channels:
        sel = ev["ch"] == c
        gaps = np.diff(ev["idx"][sel]) / rate * 1000
        on_grid = np.mean(np.abs(gaps - np.round(gaps / SYNC_MS) * SYNC_MS) < 0.6)
        caught.append(sel.sum() / seconds / SYNC_RATE * on_grid * 100)      # events on the SYNC grid, as % of 95.2/s
        noise.append(np.median(ev["uv"][sel][:, :max(3, pre // 2)].std(1)))
    rows.append((len(channels) * rate, f"{len(channels)} ch x {rate / 1000:g} kS/s", np.mean(caught), np.mean(noise)))
    print(f"{path}: {rows[-1][1]:>14}  {rows[-1][0]:>8.0f} conv/s  spikes caught {rows[-1][2]:4.0f}%  noise {rows[-1][3]:4.0f} uV")

rows.sort()
x = [r[0] for r in rows]
fig, ax1 = plt.subplots(figsize=(7, 4.2))
ax1.plot(x, [r[2] for r in rows], "o-", color="#2c6fad", lw=2)
ax1.set(xlabel="total conversions per second (channels x rate)", ylabel="SYNC spikes caught (%)", ylim=(0, 105), xscale="log")
ax1.yaxis.label.set_color("#2c6fad")
ax2 = ax1.twinx()
ax2.plot(x, [r[3] for r in rows], "s--", color="#c76bae", lw=2)
ax2.set(ylabel="noise before each spike (uV)", ylim=(0, None))
ax2.yaxis.label.set_color("#c76bae")
for r in rows:
    ax1.annotate(r[1], (r[0], r[2]), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
ax1.set_title("on-device threshold detection vs. how fast the Intan is read")
fig.tight_layout()
fig.savefig("compare.png", dpi=150); print("saved compare.png")
plt.show()
