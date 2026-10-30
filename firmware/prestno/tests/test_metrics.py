"""The measurements return the truth on synthetic SYNC data where the truth is known."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metrics import on_sync_grid, raw_metrics, event_metrics, ci95, SYNC_PERIOD_MS


def sync_times_ms(seconds, period=SYNC_PERIOD_MS, drop_every=None, seed=0):
    t = np.arange(0, seconds * 1000, period)
    if drop_every:
        t = np.delete(t, np.arange(drop_every, len(t), drop_every))
    return t


def test_grid_counts_real_and_false_with_missing_spikes():
    t = sync_times_ms(20, drop_every=4)                        # every 4th spike missing
    rng = np.random.default_rng(0)
    false = rng.uniform(0, 20000, 60)                          # 3 false detections per second
    allt = np.sort(np.r_[t, false])
    period, real, jitter = on_sync_grid(allt)
    assert abs(period - SYNC_PERIOD_MS) < 0.01
    # every real spike is kept (each has a neighbour 1 to 4 periods away); a random false event sits within 0.4 ms of
    # a grid multiple about 8% of the time (2 x 0.4 / 10.533), so a few false ones pass as real
    assert len(t) <= real.sum() <= len(t) + 0.15 * len(false)
    assert (~real).sum() >= 0.85 * len(false)


def test_grid_is_immune_to_clock_drift():
    t = sync_times_ms(20, period=SYNC_PERIOD_MS * 1.0005)      # a clock 0.05% slow
    period, real, jitter = on_sync_grid(t)
    assert real.all() and jitter < 5


def synth_raw(rate, seconds, amp_uv, noise_uv, seed=0):
    """one SYNC channel: biphasic spike every period on Gaussian noise, with a DC offset like the Intan's."""
    rng = np.random.default_rng(seed)
    n = int(rate * seconds)
    x = rng.normal(0, noise_uv, n) + 150
    tt = np.arange(0, 0.0025, 1 / rate)
    spike = -amp_uv * np.exp(-((tt - 0.0004) / 0.00012) ** 2) + 0.7 * amp_uv * np.exp(-((tt - 0.0009) / 0.0002) ** 2)
    for t0 in np.arange(0.3, seconds - 0.01, SYNC_PERIOD_MS / 1000):
        i = int(t0 * rate)
        x[i:i + len(spike)] += spike[: len(x) - i]
    return x


def test_raw_metrics_recover_amplitude_noise_and_recall():
    for rate in (30000, 10000):
        x = synth_raw(rate, 20, amp_uv=500, noise_uv=40)
        m = raw_metrics(x, rate)
        caught, half = ci95(m["caught_ps"])
        assert caught > 95 and m["false_per_s"] < 1
        assert 0.7 * 500 < m["trough_uv"] < 1.1 * 500           # band-limiting takes some amplitude; it must not invent any
        band = min(3000, 0.4 * rate) - 300                       # white noise keeps band / (rate / 2) of its power
        expect = 40 * np.sqrt(band / (rate / 2))
        assert 0.75 * expect < m["noise_uv"] < 1.25 * expect
        assert abs(m["period_ms"] - SYNC_PERIOD_MS) < 0.02


def test_event_metrics_match_a_known_recall():
    rate = 30000
    t = sync_times_ms(20, drop_every=5)                        # 80% recall by construction
    idx = np.round(t / 1000 * rate).astype(np.int64)
    uv = np.tile(np.r_[np.zeros(20), -400, np.zeros(40)], (len(idx), 1))
    m = event_metrics(idx, uv, rate, pre=20)
    caught, half = ci95(m["caught_ps"])
    assert 76 < caught < 84 and m["false_per_s"] == 0 and abs(m["trough_uv"] - 400) < 1


def test_ci95_is_the_textbook_interval():
    mean, half = ci95([10, 12, 11, 13, 9])
    assert abs(mean - 11) < 1e-9 and 1.9 < half < 2.0           # t(0.975, 4) * sd / sqrt(5) = 2.776 * 1.581 / 2.236
