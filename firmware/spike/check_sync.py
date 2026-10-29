"""Check a SYNC-mode event capture against the FB128 ground truth, by eye.

    python check_sync.py EVENTS.bin [RATE_HZ]

Ground truth in SYNC 100 Hz mode: every channel fires a fixed-shape spike every 10.50 ms (95.2/s).
So a correct detector shows (1) one tick per 10.5 ms slot, (2) one narrow ISI peak at 10.5 ms,
(3) one tight waveform bundle, and (4) events/s close to 95.2 with no lost packets.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from events import read_events, lost_packets

path = sys.argv[1]
rate = float(sys.argv[2]) if len(sys.argv) > 2 else 30000.0
SYNC_PERIOD_MS, SYNC_RATE = 10.5, 95.2

ev = read_events(path)
seconds = ev["wall"][-1] - ev["wall"][0]
lost = lost_packets(ev["seq"])
channels = sorted(set(ev["ch"]))
cols = ["#2c6fad", "#c76bae", "#e0a030", "#4f9d69", "#7b5ea7", "#d2553d", "#3aa6a6", "#8c8c4a"]

fig, ax = plt.subplots(2, 2, figsize=(12, 7))
for k, c in enumerate(channels):
    sel = ev["ch"] == c
    t_ms = ev["idx"][sel] / rate * 1000
    isi = np.diff(t_ms)
    on_grid = np.mean(np.abs(isi - SYNC_PERIOD_MS) < 0.5) * 100
    print(f"in{c}: {sel.sum() / seconds:5.1f} events/s (truth {SYNC_RATE}),  "
          f"{on_grid:3.0f}% of gaps are 10.5 ms,  median gap {np.median(isi):.2f} ms")

    start = t_ms[len(t_ms) // 2]
    view = t_ms[(t_ms >= start) & (t_ms < start + 1000)] - start
    ax[0, 0].vlines(view, c - 0.4, c + 0.4, color=cols[k % 8], lw=1)
    ax[0, 1].hist(isi, bins=np.arange(0, 60, 0.25), color=cols[k % 8], alpha=0.6)
    w = ev["uv"][sel]; ms = (np.arange(w.shape[1]) - ev["pre"][sel][0]) / rate * 1000
    ax[1, 0].plot(ms, w[:150].T, color=cols[k % 8], lw=0.3, alpha=0.15)
    ax[1, 0].plot(ms, w.mean(0), color=cols[k % 8], lw=2)

for g in range(1, 96):
    ax[0, 0].axvline(view[0] + g * SYNC_PERIOD_MS, color="0.85", lw=0.5, zorder=0)
ax[0, 0].set(title="1 s of spike times; grey lines every 10.5 ms", xlabel="ms", yticks=channels, ylabel="channel")
ax[0, 1].axvline(SYNC_PERIOD_MS, color="0.3", lw=1, ls="--")
ax[0, 1].set(title="gap between consecutive spikes (truth 10.5 ms)", xlabel="ms", ylabel="count", xlim=(0, 60))
ax[1, 0].set(title="received spike windows and their means", xlabel="ms from trough", ylabel="uV")
ax[1, 1].axis("off")
ax[1, 1].text(0, 0.9, f"{len(ev['seq'])} events in {seconds:.1f} s\n"
                      f"{len(ev['seq']) / seconds / len(channels):.1f} events/s per channel  (truth {SYNC_RATE})\n"
                      f"lost events {lost}\n"
                      f"window {ev['uv'].shape[1]} samples, trough at sample {ev['pre'][0]}",
              va="top", fontsize=12, family="monospace")
fig.tight_layout()
out = path.rsplit(".", 1)[0] + "_check.png"
fig.savefig(out, dpi=150); print(f"lost events {lost};  saved {out}")
plt.show()
