"""The measurements, shared by verdict.py, score.py, sweep.py and the tests.

Ground truth: in SYNC 100 Hz mode the FB128 fires one identical spike per period on every channel (10.533 ms measured).

raw_metrics    judges a raw stream offline, independent of the device's detector (the yardstick).
event_metrics  judges the windows the device chose to send (the thing under test).
ci95           mean and 95% confidence half-width of per-second values, so every number comes with its spread.
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch
from scipy.stats import t as student_t
from formats import detector_filter

SYNC_PERIOD_MS = 10.533
GRID_TOL_MS = 0.4


def ci95(values):
    """-> (mean, half-width of the 95% confidence interval) over independent per-second values."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return (float(v.mean()) if len(v) else float("nan")), float("nan")
    return float(v.mean()), float(student_t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)))


def bandpass(x, rate):
    """zero-phase 300 Hz to 3 kHz, or to 0.4 x rate when that is lower."""
    sos = butter(3, [300, min(3000, 0.4 * rate)], "bandpass", fs=rate, output="sos")
    return sosfiltfilt(sos, x)


def find_troughs(y, rate):
    """troughs below 4 robust sigma: deepest point within 1 ms of the crossing, then 3 ms dead time."""
    sigma = np.median(np.abs(y)) / 0.6745
    look, dead = max(1, int(rate / 1000)), int(3 * rate / 1000)
    troughs, i = [], 0
    while i < len(y) - look:
        if y[i] < -4 * sigma:
            t = i + int(np.argmin(y[i:i + look]))
            troughs.append(t)
            i = t + dead
        else:
            i += 1
    return np.array(troughs, dtype=int)


def on_sync_grid(t_ms, tol_ms=GRID_TOL_MS):
    """-> (period_ms, real_mask, jitter_us). An event is real when its gap to a neighbour is a whole number of
    periods; judged locally, so a slow drift of the FB128 clock cannot accumulate over a capture.
    A random false event passes this test about 8% of the time (2 x 0.4 ms / 10.533 ms), so false detections are
    undercounted by that much and real ones overcounted by the same number of events."""
    gaps = np.diff(t_ms)
    one = gaps[(gaps > SYNC_PERIOD_MS - 0.25) & (gaps < SYNC_PERIOD_MS + 0.25)]
    period = float(one.mean()) if len(one) else SYNC_PERIOD_MS      # mean, not median: gaps are whole samples
    prev, nxt = np.r_[np.inf, gaps], np.r_[gaps, np.inf]

    def fits(g):
        k = np.clip(np.round(g / period), 1, 4)
        return np.abs(g - k * period) < tol_ms

    real = fits(prev) | fits(nxt)
    jitter_us = float(np.std(one - period) / np.sqrt(2) * 1000) if len(one) > 1 else 0.0
    return period, real, jitter_us


def per_second(times_s, mask, seconds):
    """count of mask-true events in each whole second."""
    bins = np.arange(0, int(seconds) + 1)
    return np.histogram(times_s[mask], bins)[0]


def raw_metrics(x, rate):
    """x: microvolts, one channel. -> dict of overall numbers plus per-second arrays for confidence intervals."""
    y = bandpass(x, rate)
    settle = int(rate)                                      # first second: filter and FB128 settling
    troughs = find_troughs(y[settle:], rate) + settle
    t_ms = troughs / rate * 1000
    period, real, jitter_us = on_sync_grid(t_ms)
    seconds = (len(x) - settle) / rate
    expected_per_s = 1000 / period
    real_troughs = troughs[real]
    # noise: the 3 to 8 ms after a spike whose successor is exactly one period later is guaranteed spike-free;
    # the median over those segments keeps one glitch from inflating the whole capture
    gaps = np.diff(troughs) / rate * 1000
    quiet_after = troughs[:-1][np.abs(gaps - period) < GRID_TOL_MS]
    noise_segments = [y[t + int(0.003 * rate):t + int(0.008 * rate)] for t in quiet_after if t + int(0.008 * rate) < len(y)]
    segment_std = np.array([s.std() for s in noise_segments])
    noise = float(np.median(segment_std)) if len(segment_std) else float("nan")
    trough = float(-np.median(y[real_troughs])) if real.any() else float("nan")
    # the device's view: its causal filter, its clipped noise estimate, the deepest point per SYNC period
    d = detector_filter(x, rate)[settle:]
    m = 1000 * 0.195
    for v in np.abs(d):
        if v < 3 * m:
            m += (v - m) / 8192
    slot = int(period / 1000 * rate); n = len(d) // slot
    dev_trough = float(np.median(-d[:n * slot].reshape(n, slot).min(1))) if n else float("nan")
    dev_noise = float(1.3263 * m)
    f, p = welch(x - x.mean(), fs=rate, nperseg=min(len(x), 1 << 15))
    hum = float(np.sqrt(np.trapezoid(p[(f > 55) & (f < 65)], f[(f > 55) & (f < 65)])))   # mains pickup, below the band
    sec = (troughs[real] - settle) / rate
    quiet_sec = ((quiet_after - settle) / rate).astype(int)
    noise_ps = [np.median(segment_std[quiet_sec == s]) for s in range(int(seconds)) if np.any(quiet_sec == s)]
    return dict(seconds=seconds, period_ms=period, spikes_per_s=len(real_troughs) / seconds,
                caught_pct=len(real_troughs) / seconds / expected_per_s * 100,
                false_per_s=(~real).sum() / seconds, on_grid_pct=float(real.mean() * 100) if len(real) else 0.0,
                jitter_us=jitter_us, trough_uv=trough, noise_uv=noise, snr=trough / noise if noise else float("nan"),
                dev_trough_uv=dev_trough, dev_noise_uv=dev_noise, dev_snr=dev_trough / dev_noise, hum_uv=hum,
                caught_ps=per_second(sec, np.ones(len(sec), bool), seconds) / expected_per_s * 100,
                noise_ps=np.array(noise_ps))


def event_metrics(idx, uv, rate, pre, seconds=None):
    """idx: trough sample index per event (one channel, sorted); uv: windows; seconds: capture length, taken from the
    events' own span when not given (a channel with few events then needs it from the caller). -> dict like raw_metrics."""
    if len(idx) == 0:                                       # a converted channel that sent nothing
        seconds = seconds or 1.0
        return dict(seconds=seconds, period_ms=SYNC_PERIOD_MS, spikes_per_s=0.0, caught_pct=0.0, false_per_s=0.0,
                    on_grid_pct=0.0, jitter_us=0.0, trough_uv=float("nan"), noise_uv=float("nan"),
                    caught_ps=np.zeros(max(1, int(seconds))), false_ps=np.zeros(max(1, int(seconds))))
    t_ms = idx / rate * 1000
    period, real, jitter_us = on_sync_grid(t_ms)
    if seconds is None:
        seconds = (idx.max() - idx.min()) / rate if len(idx) > 1 else 1.0
    expected_per_s = 1000 / period
    sec = (idx - idx.min()) / rate
    return dict(seconds=seconds, period_ms=period, spikes_per_s=real.sum() / seconds,
                caught_pct=real.sum() / seconds / expected_per_s * 100,
                false_per_s=(~real).sum() / seconds, on_grid_pct=float(real.mean() * 100), jitter_us=jitter_us,
                trough_uv=float(-np.median(uv[real].min(1))) if real.any() else float("nan"),
                noise_uv=float(np.median(uv[:, :max(2, pre // 2)].std(1))) if len(uv) else float("nan"),
                caught_ps=per_second(sec, real, seconds) / expected_per_s * 100,
                false_ps=per_second(sec, ~real, seconds))
