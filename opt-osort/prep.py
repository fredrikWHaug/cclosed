#!/usr/bin/env python3
"""
opt-OSort profiling — DATA PREP (one-time, off the critical path).

Pulls one channel of real recorded data out of the MA1 session, causal-bandpasses
it, threshold-detects spikes, and cuts fixed-length snippets. Dumps the snippet
stream to a plain binary file that the C profiler (opt_osort.c) reads back as if
it were streaming off the SPI bus.

This is *only* data prep. The thing being profiled — opt-OSort itself — is in C,
because that's the artifact that eventually runs on the nRF54.

    python opt-osort/prep.py                 # auto-pick the most active channel
    python opt-osort/prep.py --channel 40    # force a channel

Output: opt-osort/snippets.bin   (int32 n_spikes, int32 k, then n_spikes*k float32)
"""
import argparse
import struct
import numpy as np
from pathlib import Path
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "raw-data" / "MA1_260414_141929" / "intan_combined.npy"
OUT = Path(__file__).resolve().parent / "snippets.bin"

FS = 10000              # intan_combined is the 30k->10k decimated data
BAND = (300, 3000)      # spike band; Nyquist at 10 kHz is 5 kHz, so this is safe
THR_MAD = 4.5           # detection threshold in units of noise MAD (negative-going)
REFRAC = 15             # samples (~1.5 ms) minimum between spikes
K = 40                  # snippet length (matches the on-chip pipeline SNIP_LEN)
PRE = 15                # samples before the trough (post = K - PRE)


def bandpass(x):
    sos = signal.butter(2, BAND, "bandpass", fs=FS, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)   # causal, matches on-chip


def detect(x):
    """Negative-threshold detection with refractory + trough alignment."""
    sigma = np.median(np.abs(x)) / 0.6745              # robust noise estimate
    thr = -THR_MAD * sigma
    below = x < thr
    troughs = []
    i, n = PRE, len(x) - (K - PRE)
    while i < n:
        if below[i]:
            j = i + np.argmin(x[i:i + REFRAC])         # local minimum = trough
            troughs.append(j)
            i = j + REFRAC
        else:
            i += 1
    return np.array(troughs, dtype=int), thr, sigma


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", type=int, default=-1, help="-1 = auto-pick most active")
    ap.add_argument("--minutes", type=float, default=5.0, help="how much recording to use")
    args = ap.parse_args()

    raw = np.load(DATA, mmap_mode="r")                 # (80, 27.2M) float16
    nsamp = min(int(args.minutes * 60 * FS), raw.shape[1])
    print(f"data {raw.shape} @ {FS} Hz | using first {nsamp/FS:.0f} s")

    if args.channel < 0:
        # quick scan: bandpass a short window on each channel, count crossings
        win = min(60 * FS, nsamp)
        counts = []
        for c in range(raw.shape[0]):
            t, _, _ = detect(bandpass(raw[c, :win].astype(np.float32)))
            counts.append(len(t))
        ch = int(np.argmax(counts))
        print(f"auto-picked channel {ch} ({counts[ch]} spikes in {win/FS:.0f} s scan)")
    else:
        ch = args.channel

    x = bandpass(raw[ch, :nsamp].astype(np.float32))
    troughs, thr, sigma = detect(x)
    snips = np.stack([x[t - PRE:t - PRE + K] for t in troughs]).astype(np.float32)

    dur = nsamp / FS
    print(f"channel {ch}: sigma={sigma:.1f}  thr={thr:.1f}  "
          f"{len(snips)} spikes over {dur:.0f}s = {len(snips)/dur:.1f} Hz")

    with open(OUT, "wb") as f:
        f.write(struct.pack("<ii", len(snips), K))
        f.write(snips.tobytes())
    print(f"wrote {OUT}  ({len(snips)} x {K} float32)")


if __name__ == "__main__":
    main()
