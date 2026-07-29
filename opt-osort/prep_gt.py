#!/usr/bin/env python3
"""
Ground-truth-fed snippet stream (Phase 2 sorter test).

Instead of our crude detector, this feeds opt-OSort REAL spikes at the offline
sorter's spike times — for the units that peak on a given channel (from
templates_average.npy) — each snippet carrying its true unit label. Time-ordered
to mimic streaming. This isolates the SORTER's quality from detection quality.

    python prep_gt.py --channel 56
    ./opt_osort snippets.bin        # -> labels.txt (predicted clusters)
    python score.py                 # true_labels.txt vs labels.txt

Assumes templates row N == neuron_N (verified: row 54 peaks ch56, neuron_54 dominant).
"""
import argparse
import struct
from pathlib import Path
import numpy as np
import prep

WF = prep.ROOT / "raw-data" / "all_result_260414_141929" / "waveforms"
ALIGN = 5   # search +/- this many samples around the GT time for the trough


def units_on_channel(ch):
    tmpl = np.load(WF / "templates_average.npy")        # (units, samples, channels)
    peak = np.ptp(tmpl, axis=1).argmax(axis=1)
    return np.where(peak == ch)[0].tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", type=int, default=56)
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--min-spikes", type=int, default=50)
    args = ap.parse_args()

    raw = np.load(prep.DATA, mmap_mode="r")
    nsamp = int(args.minutes * 60 * prep.FS)
    x = prep.bandpass(raw[args.channel, :nsamp].astype(np.float32))

    units = units_on_channel(args.channel)
    print(f"ch{args.channel}: units peaking here (templates): {units}")

    lo_ok, hi_ok = prep.PRE + ALIGN, nsamp - (prep.K - prep.PRE) - ALIGN
    stream, kept = [], []
    for u in units:
        gt = np.load(WF / f"neuron_{u}_time_indices.npy")
        gt = gt[(gt >= lo_ok) & (gt < hi_ok)]
        if len(gt) < args.min_spikes:
            continue
        for t in gt:
            c = (t - ALIGN) + int(np.argmin(x[t - ALIGN:t + ALIGN + 1]))   # local trough
            stream.append((c, x[c - prep.PRE:c - prep.PRE + prep.K].astype(np.float32), u))
        kept.append((int(u), int(len(gt))))
    print("units kept (>= min-spikes):", kept)

    stream.sort(key=lambda z: z[0])                    # time order == streaming order
    snips = np.stack([s for _, s, _ in stream]).astype(np.float32)
    labels = [l for _, _, l in stream]

    with open("snippets.bin", "wb") as f:
        f.write(struct.pack("<ii", len(snips), prep.K))
        f.write(snips.tobytes())
    with open("true_labels.txt", "w") as f:
        f.write("\n".join(str(l) for l in labels) + "\n")
    print(f"wrote snippets.bin + true_labels.txt: {len(snips)} spikes, {len(set(labels))} true units")


if __name__ == "__main__":
    main()
