"""Gather every capture in data/ into one table and two figures.

    python sweep.py                  reads data/*.bin, writes sweep.md, sweep_rate.png, sweep_channels.png

File names carry the setup:   raw_1ch_10000_a.bin   ev_4ch_30000_b.bin
                              ^mode ^channels ^rate ^run
raw files are judged by raw_metrics (the yardstick), ev files by event_metrics (the device). Runs of the same setup
are listed side by side; the confidence interval is across the seconds of each run.
"""
import glob, re
import numpy as np
import matplotlib.pyplot as plt
from formats import read_log, is_raw, raw_samples, events
from metrics import raw_metrics, event_metrics, ci95

NAME = re.compile(r"(raw|ev)_(\d+)ch_(\d+)_([a-z])\.bin$")
BLUE, PINK, GREY = "#2c6fad", "#c76bae", "0.6"


def parse(path):
    m = NAME.search(path)
    return (m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)) if m else None


rows = []                                   # (mode, channels, rate, run, channel, metrics)
for path in sorted(glob.glob("data/*.bin")):
    tag = parse(path)
    if tag is None:
        print("skipping", path, "(name does not follow mode_Nch_RATE_run.bin)"); continue
    mode, n_ch, rate, run = tag
    recs = read_log(path)
    if mode == "raw":
        x = np.concatenate([raw_samples(p)[1] for _, p in recs if is_raw(p)])
        if n_ch > 1:
            x = x[: len(x) // n_ch * n_ch].reshape(-1, n_ch)[:, 0]          # channel 0 of an interleaved stream
        rows.append((mode, n_ch, rate, run, 0, raw_metrics(x, rate)))
    else:
        ev = [e for _, p in recs if not is_raw(p) for e in events(p)]
        ch = np.array([e[1] for e in ev]); idx = np.array([e[3] for e in ev], dtype=np.int64)
        uv = np.array([e[4] for e in ev]); pre = ev[0][2]
        wall = [t for t, p in recs if not is_raw(p)]; seconds = wall[-1] - wall[0]
        for c in range(n_ch):                                   # every converted channel, even one that sent nothing
            sel = ch == c; order = np.argsort(idx[sel])
            rows.append((mode, n_ch, rate, run, c, event_metrics(idx[sel][order], uv[sel][order], rate, pre, seconds)))

if not rows:
    raise SystemExit("no captures in data/")

# ---- the table
lines = ["| mode | channels | rate | run | ch | caught % | false /s | jitter us | trough uV | noise uV | spike-to-noise | 60 Hz hum uV |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for mode, n_ch, rate, run, c, m in rows:
    caught, half = ci95(m["caught_ps"])
    snr = f"{m['snr']:.1f} (device {m['dev_snr']:.1f})" if mode == "raw" else ""
    hum = f"{m['hum_uv']:.0f}" if mode == "raw" else ""
    lines.append(f"| {mode} | {n_ch} | {rate} | {run} | {c} | {caught:.0f} ± {half:.0f} | {m['false_per_s']:.1f} | "
                 f"{m['jitter_us']:.0f} | {m['trough_uv']:.0f} | {m['noise_uv']:.0f} | {snr} | {hum} |")
open("sweep.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

# ---- figure 1: everything at one channel against sample rate
one = [r for r in rows if r[1] == 1]
if one:
    rates = sorted(set(r[2] for r in one))
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    for mode, color, label in (("raw", BLUE, "raw stream, judged offline"), ("ev", PINK, "windows from the device")):
        pts = [(r[2], *ci95(r[5]["caught_ps"]), r[5]["false_per_s"]) for r in one if r[0] == mode]
        if pts:
            x_, y_, e_, f_ = map(np.array, zip(*pts))
            ax[0].errorbar(x_ / 1000, y_, yerr=e_, fmt="o", color=color, label=label, capsize=3)
            ax[1].plot(x_ / 1000, f_, "o", color=color, label=label)
    raw = [r for r in one if r[0] == "raw"]
    if raw:
        x_ = np.array([r[2] for r in raw]) / 1000
        ax[2].plot(x_, [r[5]["snr"] for r in raw], "o", color=BLUE, label="offline band")
        ax[2].plot(x_, [r[5]["dev_snr"] for r in raw], "s", color=GREY, label="device's causal filter")
    ax[0].set(xlabel="sample rate (kS/s)", ylabel="% of SYNC spikes caught", ylim=(0, 105), title="spikes caught")
    ax[1].set(xlabel="sample rate (kS/s)", ylabel="false detections / s", title="false detections", ylim=(0, None))
    ax[2].set(xlabel="sample rate (kS/s)", ylabel="spike trough / noise", title="spike-to-noise, one channel", ylim=(0, None))
    for a in ax:
        a.set_xticks([r / 1000 for r in rates]); a.legend(frameon=False, fontsize=8); a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig("sweep_rate.png", dpi=150); print("saved sweep_rate.png")

    # the one-panel version for slides: spikes caught against rate, device vs offline
    fig, a = plt.subplots(figsize=(7, 4.2))
    for mode, color, marker, label in (("raw", BLUE, "o", "raw stream, judged offline"), ("ev", PINK, "o", "spike windows sent by the device")):
        pts = [(r[2] / 1000, ci95(r[5]["caught_ps"])[0]) for r in one if r[0] == mode]
        if pts:
            x_, y_ = map(np.array, zip(*pts))
            a.plot(x_, y_, marker, color=color, ms=9, label=label)
    a.axhline(100, color="0.85", lw=1)
    a.set(xlabel="sample rate (kS/s)", ylabel="% of the FB128's spikes caught", ylim=(0, 105), xticks=[r / 1000 for r in rates],
          title="one channel, 60 s per point, two runs per rate")
    a.legend(frameon=False, loc="lower right"); a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig("sweep_caught.png", dpi=200); print("saved sweep_caught.png")

# ---- figure 1b: the spike itself at every rate, device windows (pink) on the offline-detected raw spikes (blue), same axes
raw_one = {r[2]: r for r in one if r[0] == "raw" and r[3] == "a"}
ev_one = {r[2]: r for r in one if r[0] == "ev" and r[3] == "a"}
if raw_one and ev_one:
    from metrics import bandpass, find_troughs
    rates_both = sorted(set(raw_one) & set(ev_one))
    fig, axes = plt.subplots(1, len(rates_both), figsize=(3.2 * len(rates_both), 3.6), sharey=True)
    for a, rate in zip(np.atleast_1d(axes), rates_both):
        raw_path = next(p for p in sorted(glob.glob("data/raw_1ch_*_a.bin")) if parse(p)[2] == rate)
        ev_path = next(p for p in sorted(glob.glob("data/ev_1ch_*_a.bin")) if parse(p)[2] == rate)
        x = np.concatenate([raw_samples(p)[1] for _, p in read_log(raw_path) if is_raw(p)])
        y = bandpass(x, rate); tr = find_troughs(y[rate:], rate) + rate
        pre, post = int(rate * 2 // 3000), int(rate * 41 // 30000)
        tr = tr[(tr > pre) & (tr < len(x) - post)]
        raw_win = np.array([x[t - pre:t + post] for t in tr]); raw_win -= np.median(raw_win[:, :max(2, pre // 2)], axis=1, keepdims=True)
        ev = [e for _, p in read_log(ev_path) if not is_raw(p) for e in events(p)]
        ev_win = np.array([e[4] for e in ev]); ev_win -= np.median(ev_win[:, :max(2, pre // 2)], axis=1, keepdims=True)
        ms = (np.arange(pre + post) - pre) / rate * 1000
        a.fill_between(ms, raw_win.mean(0) - raw_win.std(0), raw_win.mean(0) + raw_win.std(0), color=BLUE, alpha=0.15)
        a.plot(ms, raw_win.mean(0), color=BLUE, lw=2)
        a.fill_between(ms, ev_win.mean(0) - ev_win.std(0), ev_win.mean(0) + ev_win.std(0), color=PINK, alpha=0.2)
        a.plot(ms, ev_win.mean(0), color=PINK, lw=2)
        caught = ci95(ev_one[rate][5]["caught_ps"])[0]
        a.set(title=f"{rate / 1000:g} kS/s: device caught {caught:.0f}%", xlabel="ms from trough")
        a.spines[["top", "right"]].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("uV, DC removed")
    fig.suptitle("mean spike with one-sigma band: raw stream (blue) and the device's windows (pink), one channel", y=1.02)
    fig.tight_layout(); fig.savefig("sweep_spikes.png", dpi=170, bbox_inches="tight"); print("saved sweep_spikes.png")

# ---- figure 2: the device against channel count. Wired channels only (in0..in7 carry FB128 outputs); every wired
# channel of every run is one dot, the short bar is the mean per channel count.
WIRED = 8
multi = [r for r in rows if r[0] == "ev"]
rates_multi = sorted({r[2] for r in multi if len({q[1] for q in multi if q[2] == r[2]}) > 1})
plt.rcParams.update({"font.family": "Helvetica", "font.size": 11})
for rate in rates_multi:
    pts = [(r[1], ci95(r[5]["caught_ps"])[0], r[5]["noise_uv"]) for r in multi if r[2] == rate and r[4] < WIRED]
    n_ = np.array([p[0] for p in pts]); caught_ = np.array([p[1] for p in pts]); noise_ = np.array([p[2] for p in pts])
    counts = np.array(sorted(set(n_)))
    jit = np.random.default_rng(0).uniform(-0.05, 0.05, len(n_))
    fig, (a_c, a_n) = plt.subplots(1, 2, figsize=(11, 4.2))
    for a, y, ylabel, title in ((a_c, caught_, "% of SYNC spikes caught, per channel", "detection"),
                                (a_n, noise_, "noise before each spike (uV)", "noise")):
        a.scatter(n_ * (1 + jit), y, s=46, color=PINK, alpha=0.55, edgecolor="white", linewidth=0.8, zorder=3)
        for n in counts:
            m = np.nanmean(y[n_ == n])
            a.plot([n / 1.12, n * 1.12], [m, m], color="0.25", lw=2, zorder=4)
            if a is a_c:
                a.annotate(f"{m:.0f}%", (n, m), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color="0.25")
        a.set(xscale="log", xticks=counts, xticklabels=counts, xlabel="channels, each at %g kS/s" % (rate / 1000),
              ylabel=ylabel, title=title)
        a.minorticks_off(); a.spines[["top", "right"]].set_visible(False); a.grid(axis="y", color="0.92", zorder=0)
    a_c.set_ylim(-3, 103)
    base = np.nanmean(noise_[n_ == counts.min()])
    a_n.plot(counts, base * np.sqrt(counts / counts.min()), "--", color="0.55", lw=1.2, label="grows as the square root of channel count", zorder=2)
    a_n.set_ylim(0, None); a_n.legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(f"FB128 SYNC, {rate / 1000:g} kS/s per channel, 60 s x 2 runs, one dot per wired channel", y=1.02)
    fig.tight_layout(); fig.savefig("sweep_channels.png", dpi=200, bbox_inches="tight"); print("saved sweep_channels.png")

# ---- figure 2b: the spike itself as channels are added, device windows on wired channels, run a, same axes.
# Real spikes (on the SYNC grid) in pink with their one-sigma band; where fewer than 20 real spikes exist the
# detections are noise crossings and are drawn in grey instead.
from metrics import on_sync_grid
for rate in rates_multi:
    counts = [n for n in sorted({r[1] for r in multi if r[2] == rate}) if n in (1, 2, 4, 8)]
    fig, axes = plt.subplots(1, len(counts), figsize=(3.4 * len(counts), 3.8), sharey=True)
    for a, n_ch in zip(np.atleast_1d(axes), counts):
        path = next((p for p in sorted(glob.glob(f"data/ev_{n_ch}ch_{rate}_a.bin"))), None)
        if path is None:
            continue
        ev = [e for _, p in read_log(path) if not is_raw(p) for e in events(p)]
        ch = np.array([e[1] for e in ev]); idx = np.array([e[3] for e in ev], dtype=np.int64)
        uv = np.array([e[4] for e in ev]); pre = ev[0][2]
        real = np.zeros(len(ev), bool)
        for c in range(min(n_ch, WIRED)):
            sel = np.where(ch == c)[0]; order = sel[np.argsort(idx[sel])]
            real[order] = on_sync_grid(idx[order] / rate * 1000)[1]
        wired = ch < WIRED
        W = uv[wired] - np.median(uv[wired][:, :max(2, pre // 2)], axis=1, keepdims=True)
        ms = (np.arange(W.shape[1]) - pre) / rate * 1000
        caught = np.mean([ci95(r[5]["caught_ps"])[0] for r in multi if r[2] == rate and r[1] == n_ch and r[4] < WIRED])
        if real[wired].sum() >= 20:
            S = W[real[wired]]
            a.fill_between(ms, S.mean(0) - S.std(0), S.mean(0) + S.std(0), color=PINK, alpha=0.2)
            a.plot(ms, S.mean(0), color=PINK, lw=2)
            a.set_title(f"{n_ch} ch: caught {caught:.0f}%\n{real[wired].sum()} real spikes")
        else:
            a.fill_between(ms, W.mean(0) - W.std(0), W.mean(0) + W.std(0), color="0.7", alpha=0.3)
            a.plot(ms, W.mean(0), color="0.4", lw=2)
            a.set_title(f"{n_ch} ch: caught {caught:.0f}%\nonly noise crossings sent")
        a.set(xlabel="ms from trough", ylim=(-900, 700)); a.spines[["top", "right"]].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("uV, DC removed")
    fig.suptitle(f"mean spike with one-sigma band, as sent by the device at {rate / 1000:g} kS/s per channel", y=1.03)
    fig.tight_layout(); fig.savefig(f"sweep_channel_spikes_{rate}.png", dpi=170, bbox_inches="tight")
    print(f"saved sweep_channel_spikes_{rate}.png")
