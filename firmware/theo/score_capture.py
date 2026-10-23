"""Score a Theo .bin capture: python score_capture.py FILE.bin N_CH [WIRED] [--rate HZ]

N_CH   channels interleaved in the stream (must match the firmware's N_CH)
WIRED  how many of them carry the FB128 SYNC signal (default 4, channels 0..WIRED-1)

Reports radio throughput (delivered fraction, clean-segment lengths) and data
integrity (SYNC 10.5 ms grid per wired channel, cross-channel alignment).
"""
import struct, sys
import numpy as np
from scipy import signal as sig

args = [a for a in sys.argv[1:] if not a.startswith("--")]
path, n_ch = args[0], int(args[1])
wired = int(args[2]) if len(args) > 2 else 4
RATE = float(sys.argv[sys.argv.index("--rate") + 1]) if "--rate" in sys.argv else 6000.0   # per channel

data = open(path, "rb").read()
seqs, times, pls = [], [], []
i = 0
while i + 10 <= len(data):
    t, ln = struct.unpack_from("<dH", data, i); i += 10
    if i + ln > len(data): break
    pkt = data[i:i+ln]; i += ln
    seqs.append(pkt[0] | (pkt[1] << 8)); times.append(t)
    pls.append(np.frombuffer(pkt[2:], dtype="<u2"))
seqs = np.array(seqs); n = len(seqs)
wall = times[-1] - times[0]

# firmware resets seq to 0 at every restart, so a seq drop marks a seam;
# a lone out-of-sequence header (legacy overrun corruption) is also excluded
d = np.diff(seqs.astype(np.int64))
seam = [k + 1 for k in np.flatnonzero(d < 0)]
corrupt = [k for k in range(1, n-1) if seqs[k] != seqs[k-1]+1 and seqs[k+1] == seqs[k-1]+2]
keep = [p for k, p in enumerate(pls) if k not in set(corrupt)]
uv = (np.concatenate(keep).astype(np.float64) - 32768.0) * 0.195
per_ch = len(uv) // n_ch
delivered_s = per_ch / RATE
bounds = [0] + seam + [n]
seg_s = np.array([(b1 - b0) * 120 / n_ch / RATE for b0, b1 in zip(bounds[:-1], bounds[1:])])

print(f"{path}: {n_ch} channels, {n} packets, {wall:.1f} s wall")
print(f"  delivered   {delivered_s:5.1f} s of signal = {100*delivered_s/wall:4.0f}% of wall clock")
print(f"  seams       {len(seam)} restarts; clean segments median {np.median(seg_s):.2f} s, min {seg_s.min():.2f} s; corrupt headers {len(corrupt)} (must be 0 on fixed firmware)")

b, a = sig.butter(3, [300/(RATE/2), min(6000, 0.45*RATE)/(RATE/2)], "bandpass")
events = []
print(f"  {'ch':>4} {'spikes/s':>9} {'ISI med':>8} {'on-grid':>8} {'sd uV':>6}")
for c in range(wired):
    x = uv[c::n_ch][:per_ch]; x -= np.median(x)
    y = sig.filtfilt(b, a, x)
    thr = 4 * np.median(np.abs(y)) / 0.6745
    above = (-y) > thr
    on = np.flatnonzero(above[1:] & ~above[:-1])
    ev, last = [], -1e9
    for o in on:
        if o - last > 0.002 * RATE: ev.append(o); last = o
    ev = np.array(ev); events.append(ev)
    isi = np.diff(ev) / RATE * 1000
    grid = 100 * np.mean(np.abs(isi - 10.5) < 0.6) if len(isi) else 0
    print(f"  {c:>4} {len(ev)/delivered_s:9.1f} {np.median(isi) if len(isi) else 0:8.2f} {grid:7.0f}% {x.std():6.0f}")
for c in range(1, wired):
    d = np.abs(events[c][:, None] - events[0][None, :]).min(axis=1) / RATE * 1000
    print(f"  ch{c} vs ch0: {100*np.mean(d < 1.0):.0f}% of spikes coincide within 1 ms")
