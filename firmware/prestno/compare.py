"""Does the windowed path reproduce the raw signal?  One channel, FB128 in SYNC 100 Hz, same bench for both captures.

    python compare.py RAW.bin EVENTS.bin [RATE_HZ]

RAW.bin    was recorded with RAW_STREAM 1: every sample. The firmware's detector is replayed on it here, sample for
           sample, so this row is what the device should find on that signal.
EVENTS.bin was recorded with RAW_STREAM 0: what the device actually found and sent.
Prints one table and saves compare.png: the two mean waveforms with their spread, the gaps between spikes, the amplitudes.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from formats import read_log, is_raw, raw_samples, events, detector_filter

raw_path, ev_path = sys.argv[1], sys.argv[2]
rate = float(sys.argv[3]) if len(sys.argv) > 3 else 30000.0
PRE, POST = int(rate * 2 // 3000), int(rate * 41 // 30000)          # the window the firmware uses
SYNC_MS, SYNC_RATE = 10.5, 95.2
BLUE, PINK = "#2c6fad", "#c76bae"


def offline_detect(x):
    """the firmware's detector replayed sample for sample on the raw stream (process() in src/main.c):
    causal 300 Hz high-pass and low-pass, running mean of |y| clipped at 3x itself, threshold 4 x 1.3263 x that mean,
    deepest point within 1 ms, 3 ms dead time and 3 ms without noise updates after each spike, 0.5 s settle."""
    y = detector_filter(x, rate)
    mean_abs, state, quiet, blank = 1000 * 0.195, 0, int(0.5 * rate), 0
    look, dead = int(rate / 1000), int(3 * rate / 1000)
    t_tr = v_tr = search_end = 0
    troughs = []
    for n, v in enumerate(y):
        if state == 0 and n >= blank and abs(v) < 3 * mean_abs:
            mean_abs += (abs(v) - mean_abs) / 8192
        if n < quiet:
            continue
        if state == 0:
            if v < -4 * 1.3263 * mean_abs:
                state, t_tr, v_tr, search_end = 1, n, v, n + look
        elif state == 1:
            if v < v_tr:
                v_tr, t_tr = v, n
            if n >= search_end:
                state = 2
        elif n + 1 >= t_tr + POST:
            lo = max(0, t_tr - look)                       # like emit(): the raw minimum in the 1 ms before the filtered trough
            t_raw = lo + int(np.argmin(x[lo:t_tr + 1]))
            if t_raw >= PRE:
                troughs.append(t_raw)
            state, quiet, blank = 0, t_tr + dead, t_tr + dead
    return np.array(troughs), 1.3263 * mean_abs


# raw capture: stitch the stream, note packet gaps, detect offline
records = [p for _, p in read_log(raw_path) if is_raw(p)]
seqs = np.array([raw_samples(p)[0] for p in records])
raw_lost = int(((np.diff(seqs.astype(int)) % 65536) - 1).sum())
x = np.concatenate([raw_samples(p)[1] for p in records])
raw_seconds = len(x) / rate
troughs, sigma_raw = offline_detect(x)
raw_win = np.array([x[t - PRE:t + POST] for t in troughs])
raw_gaps = np.diff(troughs) / rate * 1000

# event capture: what the device sent
ev = [e for _, p in read_log(ev_path) if not is_raw(p) for e in events(p)]
ev_seq = np.array([e[0] for e in ev]); ev_lost = int(((np.diff(ev_seq.astype(int)) % 65536) - 1).sum())
ev_idx = np.array([e[3] for e in ev], dtype=np.int64)
ev_win = np.array([e[4] for e in ev]); ev_pre = ev[0][2]
ev_seconds = (ev_idx[-1] - ev_idx[0]) / rate
ev_gaps = np.diff(ev_idx) / rate * 1000
wall = [t for t, p in read_log(ev_path) if not is_raw(p)]; ev_wall = wall[-1] - wall[0]


def row(name, win, gaps, seconds, lost, pre):
    on_grid = np.mean(np.abs(gaps - SYNC_MS) < 0.5) * 100
    jitter = np.std(gaps[np.abs(gaps - SYNC_MS) < 0.5]) * 1000
    trough = win.min(1)                                   # the window minimum, wherever it falls
    noise = np.median(win[:, :max(3, pre // 2)].std(1))
    print(f"{name:22s} {len(win) / seconds:7.1f} {len(win) / seconds / SYNC_RATE * 100:6.0f}% {on_grid:8.0f}% {jitter:8.0f}"
          f" {trough.mean():8.0f} {trough.std():6.0f} {noise:7.0f} {lost:6d}")


print(f"{'':22s} {'spikes/s':>7} {'of 95.2':>7} {'on grid':>9} {'jitter us':>9} {'trough uV':>9} {'sd':>6} {'noise':>7} {'lost':>6}")
row("raw, device replayed", raw_win, raw_gaps, raw_seconds, raw_lost, PRE)
row("events, from device", ev_win, ev_gaps, ev_wall, ev_lost, ev_pre)
print(f"\nraw stream: {raw_seconds:.1f} s, {len(x)} samples, replayed noise estimate {sigma_raw:.0f} uV, threshold {4 * sigma_raw:.0f} uV")
print(f"events: {ev_wall:.1f} s of wall time, window {ev_win.shape[1]} samples with the trough at sample {ev_pre}")

# the figure
fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
ms = (np.arange(PRE + POST) - PRE) / rate * 1000
for win, pre, color, label in ((raw_win, PRE, BLUE, "raw stream, device detector replayed"), (ev_win, ev_pre, PINK, "windows sent by the device")):
    m = (np.arange(win.shape[1]) - pre) / rate * 1000
    ax[0].fill_between(m, win.mean(0) - win.std(0), win.mean(0) + win.std(0), color=color, alpha=0.15)
    ax[0].plot(m, win.mean(0), color=color, lw=2, label=f"{label} ({len(win)})")
ax[0].set(xlabel="ms from trough", ylabel="uV", title="mean spike, band = one standard deviation"); ax[0].legend(frameon=False, fontsize=8)
bins = np.arange(0, 40, 0.25)
ax[1].hist(raw_gaps, bins, color=BLUE, alpha=0.6, label="raw"); ax[1].hist(ev_gaps, bins, color=PINK, alpha=0.6, label="events")
ax[1].axvline(SYNC_MS, color="0.3", ls="--", lw=1)
ax[1].set(xlabel="ms between consecutive spikes", ylabel="count", title="gaps, truth 10.5 ms"); ax[1].legend(frameon=False)
abins = np.arange(-1200, 0, 20)
ax[2].hist(raw_win.min(1), abins, color=BLUE, alpha=0.6, label="raw"); ax[2].hist(ev_win.min(1), abins, color=PINK, alpha=0.6, label="events")
ax[2].set(xlabel="trough amplitude (uV)", ylabel="count", title="spike amplitudes"); ax[2].legend(frameon=False)
fig.tight_layout(); fig.savefig("compare.png", dpi=150); print("saved compare.png")
plt.show()
