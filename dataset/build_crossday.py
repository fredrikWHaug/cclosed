"""
Build the cross-day dataset for the representational-drift / generalization test.

Two consecutive MA1 sessions (same probe, same mouse):
    day 1 = 260413_131912   (universal session index 2, group "0" position 2)
    day 2 = 260414_141929   (universal session index 3, group "0" position 3)

MA1_match_dict_final.json tracks neuron identity across sessions. We keep every
tracked neuron that appears on BOTH our days, pool its (possibly split) local
units under the tracked ID, and extract — for each spike — the PEAK-CHANNEL
40-sample waveform only.

Peak channel, not the 8-channel shank snippet, is deliberate: the 4 tracked
neurons sit on 4 different shanks, so a multi-channel input would let a model
separate them by *which shank is active* (a location fingerprint that is stable
across days and would hide drift). One channel forces the classifier to rely on
spike SHAPE alone — the honest test of whether a day-1 model survives to day 2.

Selection effect to keep in mind: only neurons match_dict could TRACK across
both days are included. Trackable implies stable, so this subset under-represents
drift by construction — it is a floor, not a measure of drift magnitude.

Output: dataset/crossday.npz
    waveforms  (N, 40)  float32 — peak-channel snippet, microvolts
    labels     (N,)     int32   — tracked neuron ID
    sessions   (N,)     int8    — 0 = day 1, 1 = day 2
    times      (N,)     int64   — sample index within that day's recording

Usage:
    python dataset/build_crossday.py
"""

import json
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent.parent / "raw-data"
OUT = Path(__file__).parent / "crossday.npz"

DAY1 = "260413_131912"
DAY2 = "260414_141929"
GROUP = "0"          # match-group these two sessions share
POS1, POS2 = "2", "3"  # their positions within that group (from runsheet)

SAMPLES_BEFORE = 20  # 2 ms at 10 kHz
SAMPLES_AFTER = 20
SNIPPET_LEN = SAMPLES_BEFORE + SAMPLES_AFTER  # 40


def load_recording(day: str) -> np.ndarray:
    rec = BASE / f"all_result_{day}" / "recordings"
    meta = json.load(open(rec / "binary.json"))["kwargs"]
    dtype = np.dtype(meta["dtype"])
    n_ch = len(meta["channel_ids"])
    data = np.memmap(rec / "traces_cached_seg0.raw", dtype=dtype, mode="r")
    return data.reshape(-1, n_ch)


def load_sorting(day: str):
    f = np.load(BASE / f"all_result_{day}" / "sorting" / "sorter_output" / "firings.npz")
    return f["spike_indexes_seg0"], f["spike_labels_seg0"]


def peak_channel(day: str, unit: int) -> int:
    """Channel (0..79) of largest negative deflection in this unit's template."""
    t = np.load(BASE / f"all_result_{day}" / "waveforms" / "templates_average.npy")
    return int(np.argmin(t[unit - 1].min(axis=0)))


def as_list(v):
    return v if isinstance(v, list) else [v]


def tracked_pairs():
    """From match_dict: {tracked_id: (day1_local_units, day2_local_units)}."""
    md = json.load(open(BASE / "MA1_match_dict_final.json"))
    pairs = {}
    for tid, groups in md.items():
        g = groups.get(GROUP, {})
        if POS1 in g and POS2 in g:
            pairs[int(tid)] = (as_list(g[POS1]), as_list(g[POS2]))
    return pairs


def extract_day(day: str, units, tracked_id, peak_ch):
    """Peak-channel snippet for every spike of `units` on `day`."""
    rec = load_recording(day)
    n = rec.shape[0]
    times, labels = load_sorting(day)
    keep = np.isin(labels, units)
    out_wf, out_t = [], []
    for t in times[keep]:
        if t < SAMPLES_BEFORE or t + SAMPLES_AFTER > n:
            continue
        out_wf.append(rec[t - SAMPLES_BEFORE:t + SAMPLES_AFTER, peak_ch].astype(np.float32))
        out_t.append(int(t))
    return out_wf, out_t


def main():
    pairs = tracked_pairs()
    print(f"Tracked neurons on both days: {sorted(pairs)}")

    waveforms, labels, sessions, times = [], [], [], []
    for tid, (u1, u2) in sorted(pairs.items()):
        # peak channel is stable across a neuron's units + across days (verified)
        pch = peak_channel(DAY1, u1[0])
        assert all(peak_channel(DAY1, u) == pch for u in u1)
        assert all(peak_channel(DAY2, u) == pch for u in u2)

        for day, units, sess in [(DAY1, u1, 0), (DAY2, u2, 1)]:
            wf, tt = extract_day(day, units, tid, pch)
            waveforms += wf
            times += tt
            labels += [tid] * len(wf)
            sessions += [sess] * len(wf)
            print(f"  tracked {tid:>3}  peak-ch {pch:>2}  day{sess+1}  units {units} -> {len(wf)} spikes")

    waveforms = np.array(waveforms, dtype=np.float32)
    labels = np.array(labels, dtype=np.int32)
    sessions = np.array(sessions, dtype=np.int8)
    times = np.array(times, dtype=np.int64)

    print(f"\nTotal snippets: {len(waveforms)}  shape {waveforms.shape}")
    for s, name in [(0, "day1"), (1, "day2")]:
        m = sessions == s
        print(f"  {name}: {m.sum()} spikes, classes {sorted(np.unique(labels[m]))}")

    np.savez_compressed(OUT, waveforms=waveforms, labels=labels,
                        sessions=sessions, times=times)
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
