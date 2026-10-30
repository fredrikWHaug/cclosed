"""Score an event capture against the FB128 SYNC truth alone. Works for any channel count.

    python score.py EVENTS.bin [RATE_HZ]        rate defaults to 30000

In SYNC mode every channel fires one spike per period (10.5 ms nominal). The period is taken from the gaps between
events; an event is real when its gap to a neighbour is a whole number of periods (within 0.4 ms), false otherwise.
Per channel: real spikes/s as a share of the SYNC rate, false detections/s, timing jitter, trough, noise, lost events.
"""
import sys
import numpy as np
from formats import read_log, is_raw, events

path = sys.argv[1]
rate = float(sys.argv[2]) if len(sys.argv) > 2 else 30000.0
TOL_MS = 0.4


def on_sync_grid(t_ms):
    """period (ms) from the gaps, then: an event is real if its gap to a neighbour is a whole number of periods.
    Judged locally from neighbours so a slow drift of the FB128 clock cannot accumulate over the capture."""
    gaps = np.diff(t_ms)
    one = gaps[(gaps > 10.3) & (gaps < 10.7)]
    period = np.median(one) if len(one) else 10.5
    prev = np.r_[np.inf, gaps]; nxt = np.r_[gaps, np.inf]
    def on_grid(g):
        k = np.clip(np.round(g / period), 1, 4)
        return np.abs(g - k * period) < TOL_MS
    real = on_grid(prev) | on_grid(nxt)
    jitter_us = np.std(one - period) / np.sqrt(2) * 1000 if len(one) > 1 else 0
    return period, real, jitter_us


ev = [e for _, p in read_log(path) if not is_raw(p) for e in events(p)]
if not ev:
    raise SystemExit(f"no events in {path}")
seq = np.array([e[0] for e in ev]); ch = np.array([e[1] for e in ev])
idx = np.array([e[3] for e in ev], dtype=np.int64); uv = np.array([e[4] for e in ev]); pre = ev[0][2]
lost = int(((np.diff(seq.astype(int)) % 65536) - 1).sum())
seconds = (idx.max() - idx.min()) / rate
channels = sorted(set(ch))

print(f"{path}: {len(ev)} events, {len(channels)} channel(s) at {rate:.0f} S/s, {seconds:.1f} s, lost events {lost}")
print(f"  {'ch':>3} {'period ms':>9} {'real/s':>7} {'caught':>7} {'false/s':>8} {'jitter us':>9} {'trough uV':>9} {'noise uV':>8}")
for c in channels:
    sel = ch == c
    order = np.argsort(idx[sel])
    t_ms = idx[sel][order] / rate * 1000
    w = uv[sel][order]
    period, real, jitter_us = on_sync_grid(t_ms)
    print(f"  {c:>3} {period:9.3f} {real.sum() / seconds:7.1f} {real.sum() / seconds / (1000 / period) * 100:6.0f}% "
          f"{(~real).sum() / seconds:8.1f} {jitter_us:9.0f} {np.median(w[real].min(1)) if real.any() else 0:9.0f} "
          f"{np.median(w[:, :max(2, pre // 2)].std(1)):8.0f}")
