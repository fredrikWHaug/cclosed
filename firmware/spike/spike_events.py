"""Inspect a spike-event capture: python spike_events.py EVENTS.bin [RATE_HZ]

Per channel: event rate, trough amplitude, ISI median, fraction of gaps on the 10.5 ms SYNC grid.
Saves <name>_events.png: waveform overlay per channel + raster.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from events import read_events, lost_packets

path = sys.argv[1]
rate = float(sys.argv[2]) if len(sys.argv) > 2 else 30000.0

ev = read_events(path)
wall = ev["wall"][-1] - ev["wall"][0]
chans = sorted(set(ev["ch"]))
n_win = ev["uv"].shape[1]; pre = int(ev["pre"][0])
print(f"{len(ev['seq'])} events in {wall:.1f} s ({len(ev['seq'])/wall:.1f}/s), lost events {lost_packets(ev['seq'])}, "
      f"window {n_win} samples ({n_win/rate*1000:.2f} ms) at {rate:.0f} Hz")
print(f"  {'ch':>3} {'events/s':>9} {'trough uV':>10} {'ISI med ms':>11} {'on 10.5ms grid':>15}")

cols = ["#2c6fad", "#c76bae", "#e0a030", "#4f9d69", "#7b5ea7", "#d2553d", "#3aa6a6", "#8c8c4a"]
fig, (ax_w, ax_r) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [1, 2]})
ms = (np.arange(n_win) - pre) / rate * 1000
for k, c in enumerate(chans):
    sel = ev["ch"] == c
    waves, idx = ev["uv"][sel], ev["idx"][sel].astype(float)
    isi = np.diff(idx) / rate * 1000
    slots = np.round(isi / 10.5)
    grid = 100 * np.mean(np.abs(isi - slots * 10.5) < 0.6) if len(isi) else 0
    print(f"  {c:>3} {sel.sum()/wall:9.1f} {waves.min(1).mean():10.0f} {np.median(isi) if len(isi) else 0:11.2f} {grid:14.0f}%")
    for w in waves[:300]:
        ax_w.plot(ms, w, lw=0.4, color=cols[k % 8], alpha=0.15)
    ax_w.plot(ms, waves.mean(0), lw=2, color=cols[k % 8], label=f"in{c} ({sel.sum()})")
    ax_r.plot(idx / rate, np.full(len(idx), c), "|", color=cols[k % 8], ms=8)
ax_w.set(xlabel="ms from trough", ylabel="uV", title="spike windows received over BLE"); ax_w.legend(frameon=False, fontsize=8)
ax_r.set(xlabel="channel sample index / rate (s)", ylabel="channel", title="spike times", yticks=chans)
fig.tight_layout()
fig.savefig(path.rsplit(".", 1)[0] + "_events.png", dpi=150)
print("saved", path.rsplit(".", 1)[0] + "_events.png")
plt.show()
