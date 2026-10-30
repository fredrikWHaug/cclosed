"""Score an event capture against the SYNC truth. Any channel count.

    python score.py EVENTS.bin [RATE_HZ]        rate defaults to 30000

Per channel: spikes caught as a share of the SYNC rate (with 95% confidence interval across seconds), false
detections per second, timing jitter, trough, noise before the spike. Lost events from the sequence counter.
"""
import sys
import numpy as np
from formats import read_log, is_raw, events
from metrics import event_metrics, ci95

path = sys.argv[1]
rate = int(sys.argv[2]) if len(sys.argv) > 2 else 30000

ev = [e for _, p in read_log(path) if not is_raw(p) for e in events(p)]
if not ev:
    raise SystemExit(f"no events in {path}; record it with RAW_STREAM 0")
seq = np.array([e[0] for e in ev]); ch = np.array([e[1] for e in ev]); pre = ev[0][2]
idx = np.array([e[3] for e in ev], dtype=np.int64); uv = np.array([e[4] for e in ev])
lost = int(((np.diff(seq.astype(int)) % 65536) - 1).sum())

wall = [t for t, p in read_log(path) if not is_raw(p)]; seconds = wall[-1] - wall[0]
print(f"{path}: {len(ev)} events, {len(set(ch))} channel(s) at {rate} S/s, {seconds:.0f} s, lost events {lost}")
print(f"  {'ch':>3} {'caught':>12} {'false/s':>8} {'jitter us':>9} {'trough uV':>9} {'noise uV':>8}")
for c in sorted(set(ch)):
    sel = ch == c
    order = np.argsort(idx[sel])
    m = event_metrics(idx[sel][order], uv[sel][order], rate, pre, seconds)
    caught, half = ci95(m["caught_ps"])
    print(f"  {c:>3} {caught:6.0f}% ± {half:3.0f} {m['false_per_s']:8.1f} {m['jitter_us']:9.0f} {m['trough_uv']:9.0f} {m['noise_uv']:8.0f}")
