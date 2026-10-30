"""The yardstick: judge a raw capture offline, without the device's detector, and draw it.

    python verdict.py RAW.bin [RATE_HZ]        rate defaults to 30000

Prints spikes caught (with 95% confidence interval across seconds), false detections, trough, noise, spike-to-noise,
and the same spike-to-noise as the device's own causal filter sees it. Saves RAW_verdict.png.
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from formats import read_log, is_raw, raw_samples
from metrics import raw_metrics, bandpass, find_troughs, ci95

path = sys.argv[1]
rate = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
plt.rcParams.update({"font.family": "Helvetica", "font.size": 10})
BLUE, PINK = "#2c6fad", "#c76bae"

x = np.concatenate([raw_samples(p)[1] for _, p in read_log(path) if is_raw(p)])
if len(x) == 0:
    raise SystemExit(f"{path} has no raw packets; record it with RAW_STREAM 1")
m = raw_metrics(x, rate)
caught, caught_ci = ci95(m["caught_ps"])
noise, noise_ci = ci95(m["noise_ps"])
print(f"{path}: {rate} S/s, {m['seconds']:.0f} s, period {m['period_ms']:.3f} ms")
print(f"  spikes caught {caught:.0f}% ± {caught_ci:.0f}   false {m['false_per_s']:.1f}/s   jitter {m['jitter_us']:.0f} us")
print(f"  trough {m['trough_uv']:.0f} uV   noise {noise:.0f} ± {noise_ci:.0f} uV   spike-to-noise {m['snr']:.1f}"
      f"   (device filter: trough {m['dev_trough_uv']:.0f}, noise {m['dev_noise_uv']:.0f}, ratio {m['dev_snr']:.1f})")

# the figure: 50 ms of trace, and every spike overlaid
y = bandpass(x, rate)
troughs = find_troughs(y[rate:], rate) + rate
pre, post = int(1.5e-3 * rate), int(2.5e-3 * rate)
troughs = troughs[(troughs > pre) & (troughs < len(y) - post)]
win = np.array([y[t - pre:t + post] for t in troughs])
fig, (ax_t, ax_s) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [1.6, 1]})
start = troughs[len(troughs) // 2] - int(0.004 * rate); seg = slice(start, start + int(0.05 * rate))
t_ms = np.arange(seg.stop - seg.start) / rate * 1000
ax_t.plot(t_ms, x[seg] - np.median(x[seg]), color="0.8", lw=0.6, label="raw")
ax_t.plot(t_ms, y[seg], color=BLUE, lw=1.0, label=f"filtered 300-{min(3000, 0.4 * rate):.0f} Hz")
ax_t.set(xlabel="ms", ylabel="uV", title=f"50 ms of SYNC 100 Hz, one channel at {rate / 1000:g} kS/s")
ax_t.legend(frameon=False, loc="lower right")
ms = np.arange(-pre, post) / rate * 1000
for w in win[::max(1, len(win) // 400)]:
    ax_s.plot(ms, w, color=BLUE, lw=0.3, alpha=0.25)
ax_s.plot(ms, win.mean(0), color=PINK, lw=2)
ax_s.set(xlabel="ms", ylabel="uV", xlim=(ms[0], ms[-1]), title=f"all detected spikes overlaid (n={len(win)}), mean in magenta")
for a in (ax_t, ax_s):
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
out = path.rsplit(".", 1)[0] + "_verdict.png"
fig.savefig(out, dpi=200)
print("  saved", out)
