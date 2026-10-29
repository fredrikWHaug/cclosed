"""The verdict plot for one raw capture: 50 ms of trace, and every detected spike overlaid with the mean.

    python verdict.py CAPTURE.bin [RATE_HZ]        rate defaults to 30000; pass 6000 for a 6 kS/s capture

Needs a raw capture (RAW_STREAM 1, or theo). The whole recording is band-passed zero-phase from 300 Hz to 3000 Hz,
or to 0.4 x the rate when that is lower (2400 Hz at 6 kS/s). Spikes are troughs below 4 robust sigma, the deepest
point within 1 ms, with a 3 ms dead time. Saves CAPTURE_verdict.png and prints the numbers for the table.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt
from formats import read_log, is_raw, raw_samples

path = sys.argv[1]
fs = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
plt.rcParams.update({"font.family": "Helvetica", "font.size": 10})
BLUE, PINK = "#2c6fad", "#c76bae"

# the stream, filtered over its whole length
x = np.concatenate([raw_samples(p)[1] for _, p in read_log(path) if is_raw(p)])
if len(x) == 0:
    raise SystemExit(f"{path} has no raw packets; record it with RAW_STREAM 1")
high = min(3000, 0.4 * fs)
y = sosfiltfilt(butter(3, [300, high], "bandpass", fs=fs, output="sos"), x)

# spikes
sigma = np.median(np.abs(y)) / 0.6745
troughs, i = [], fs
while i < len(y) - fs // 100:
    if y[i] < -4 * sigma:
        t = i + int(np.argmin(y[i:i + fs // 1000]))
        troughs.append(t)
        i = t + 3 * fs // 1000
    else:
        i += 1
pre, post = int(1.5e-3 * fs), int(2.5e-3 * fs)
troughs = np.array([t for t in troughs if pre < t < len(y) - post])
windows = np.array([y[t - pre:t + post] for t in troughs])

# the numbers: SYNC fires every 10.5 ms, so the 3 to 8 ms after a spike that has a successor 10.5 ms later is spike-free
seconds = len(y) / fs
gaps = np.diff(troughs) / fs * 1000
on_grid = np.mean(np.abs(gaps - 10.5) < 0.6) * 100
confirmed = troughs[:-1][np.abs(gaps - 10.5) < 0.4]
quiet = np.concatenate([y[t + 3 * fs // 1000:t + 8 * fs // 1000] for t in confirmed])
trough = -np.median(windows[:, pre])
print(f"{path}: {fs} S/s, band 300-{high:.0f} Hz")
print(f"  {len(troughs)} spikes in {seconds:.1f} s = {len(troughs) / seconds:.1f}/s of 95.2, on the 10.5 ms grid {on_grid:.0f}%")
print(f"  trough {trough:.0f} uV, noise between spikes {quiet.std():.0f} uV, spike-to-noise {trough / quiet.std():.1f}")

# the figure
fig, (ax_t, ax_s) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [1.6, 1]})
start = troughs[len(troughs) // 2] - int(0.004 * fs)
seg = slice(start, start + int(0.05 * fs))
t_ms = np.arange(seg.stop - seg.start) / fs * 1000
ax_t.plot(t_ms, x[seg] - np.median(x[seg]), color="0.8", lw=0.6, label="raw")
ax_t.plot(t_ms, y[seg], color=BLUE, lw=1.0, label=f"filtered 300-{high:.0f} Hz")
ax_t.set(xlabel="ms", ylabel="uV", title=f"50 ms of SYNC 100 Hz, one channel at {fs / 1000:g} kS/s")
ax_t.legend(frameon=False, loc="lower right")
ms = np.arange(-pre, post) / fs * 1000
for w in windows[::max(1, len(windows) // 400)]:
    ax_s.plot(ms, w, color=BLUE, lw=0.3, alpha=0.25)
ax_s.plot(ms, windows.mean(0), color=PINK, lw=2)
ax_s.set(xlabel="ms", ylabel="uV", xlim=(ms[0], ms[-1]),
         title=f"all detected spikes overlaid (n={len(windows)}), mean in magenta")
for a in (ax_t, ax_s):
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
out = path.rsplit(".", 1)[0] + "_verdict.png"
fig.savefig(out, dpi=200)
print("  saved", out)
