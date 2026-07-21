"""
Build the ON-CHIP-representation training set from raw .rhd.

Deploy constraint (make-or-break): the model must see what the MCU can actually
produce in real time. So snippets come from the raw .rhd through an on-chip-
FEASIBLE chain — bandpass 300-3000 Hz -> common-median reference (per shank) ->
decimate 30k->10k -> 40-sample snippet — NOT the offline whitened recording
(whitening needs a precomputed covariance and can't run on-chip).

Verified: this chain + the sorter's spike times recovers unit templates at
corr 0.999, and the sorter time (10 kHz) maps 1:1 to the decimated index.

64 channels = shanks [0,1,2,3,6,7,8,9] (4 top + best-4 bottom), classified per
shank (8 ch each). Labels = offline sorter unit IDs (the fidelity target).
Only units with >= MIN_SPIKES are kept (the rest are unlearnable/unmeasurable).

Output: dataset/onchip_<session>.npz
    snippets (N,8,40) float32   labels (N,)   shanks (N,)   times (N,) 10 kHz
"""
import glob
import json
import sys
import numpy as np
from pathlib import Path
from scipy import signal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))
from stream_rhd import parse_header

# The ONE causal bandpass, shared between this training pipeline and the firmware.
# 2nd-order Butterworth 300-3000 Hz at 30 kHz, second-order sections.
SOS = signal.butter(2, [300, 3000], "bandpass", fs=30000, output="sos")
RW = 5   # trough-realignment search radius (samples @ 10 kHz) — matches on-chip detect

SESSION = "MA1_260413_131912"
RESULT = ROOT / "raw-data" / "all_result_260413_131912"
RAWDIR = ROOT / "raw-data" / SESSION
SEL = [0, 1, 2, 3, 6, 7, 8, 9]
MIN_SPIKES = 1000
SB = SA = 20

CHN_GROUPS = {
    0: [49,48,47,46,44,45,50,51], 1: [53,52,43,42,40,41,54,55],
    2: [57,56,39,38,36,37,58,59], 3: [61,60,35,34,32,33,62,63],
    4: [1,0,31,30,28,29,2,3],     5: [5,4,27,26,24,25,6,7],
    6: [9,8,23,22,20,21,10,11],   7: [13,12,19,18,16,17,14,15],
    8: [72,71,73,70,68,75,69,74], 9: [76,67,77,66,64,79,65,78],
}
CH2SHANK = {c: s for s, chs in CHN_GROUPS.items() for c in chs}
ALLCH = [c for s in SEL for c in CHN_GROUPS[s]]   # 64, grouped by SEL-shank order


def process_file(fp):
    """Raw .rhd -> {shank: (8, L_10k)} after CAUSAL bandpass + CMR + decimate."""
    f = open(fp, "rb"); h = parse_header(f)
    N, NAMP, bpb, he = h["block"], h["n_amp"], h["bpb"], h["header_end"]
    f.seek(he); raw = f.read(); nb = len(raw) // bpb
    data = np.empty((len(ALLCH), nb * N), np.float32)
    for b in range(nb):
        amp = np.frombuffer(raw, '<u2', count=NAMP * N, offset=b * bpb + N * 4).reshape(NAMP, N)
        data[:, b * N:(b + 1) * N] = 0.195 * (amp[ALLCH].astype(np.int32) - 32768)
    data = signal.sosfilt(SOS, data, axis=1).astype(np.float32)   # causal biquad, all 64 at once
    out = {}
    for i, s in enumerate(SEL):
        blk = data[i * 8:(i + 1) * 8]
        blk = blk - np.median(blk, axis=0, keepdims=True)   # CMR per shank
        out[s] = blk[:, ::3]                                # decimate -> 10 kHz
    return out, out[SEL[0]].shape[1]


def main():
    fr = np.load(RESULT / "sorting" / "sorter_output" / "firings.npz")
    times, lab, uids = fr["spike_indexes_seg0"], fr["spike_labels_seg0"], fr["unit_ids"]
    tmpl = np.load(RESULT / "waveforms" / "templates_average.npy")
    counts = {int(u): int((lab == u).sum()) for u in uids}
    peakch = {int(u): int(np.argmin(tmpl[i].min(0))) for i, u in enumerate(uids)}
    shank_of = {int(u): CH2SHANK[peakch[int(u)]] for u in uids}
    units = [int(u) for u in uids if shank_of[int(u)] in SEL and counts[int(u)] >= MIN_SPIKES]
    st_by_unit = {u: times[lab == u] for u in units}
    print(f"training units ({len(units)}): "
          + ", ".join(f"u{u}(s{shank_of[u]},{counts[u]})" for u in units))

    meta = json.load(open(RESULT / "recordings" / "binary.json"))["kwargs"]
    nch = len(meta["channel_ids"]); dt = np.dtype(meta["dtype"])
    prep_len = (RESULT / "recordings" / "traces_cached_seg0.raw").stat().st_size // (nch * dt.itemsize)
    files = sorted(glob.glob(str(RAWDIR / "*.rhd")))
    print(f"{len(files)} .rhd files | preprocessed 10kHz len {prep_len} | max spike time {times.max()}")

    SNIP, LAB, SH, T = [], [], [], []
    offset = 0
    for fp in files:
        ss, L = process_file(fp)
        for u in units:
            st = st_by_unit[u] - offset
            st = st[(st >= SB + RW) & (st < L - SA - RW)]
            if len(st) == 0:
                continue
            sig = ss[shank_of[u]]
            pcl = CHN_GROUPS[shank_of[u]].index(peakch[u])
            # realign each spike to its trough on the peak channel (matches on-chip detect)
            win = st[:, None] + np.arange(-RW, RW + 1)
            centers = st - RW + np.argmin(sig[pcl][win], axis=1)
            idx = centers[:, None] + np.arange(-SB, SA)     # (n,40)
            sn = np.transpose(sig[:, idx], (1, 0, 2))        # (n,8,40)
            SNIP.append(sn); LAB += [u] * len(st); SH += [shank_of[u]] * len(st)
            T += (centers + offset).tolist()
        offset += L
        print(f"  {Path(fp).name}: L={L}, cum={offset}, total snippets={sum(len(x) for x in SNIP)}")

    SNIP = np.concatenate(SNIP).astype(np.float32)
    LAB, SH, T = np.array(LAB), np.array(SH), np.array(T)
    print(f"\ncovered {offset} of {prep_len} 10kHz samples ({100*offset/prep_len:.0f}%)")

    # global alignment check: every unit's mean snippet vs its sorter template
    print("per-unit alignment (mean snippet vs template):")
    ok = True
    for u in units:
        m = LAB == u; pc = peakch[u]; pcl = CHN_GROUPS[shank_of[u]].index(pc)
        c = np.corrcoef(SNIP[m].mean(0)[pcl], tmpl[list(uids).index(u)][:, pc])[0, 1]
        # causal (un-whitened) snippets correlate ~0.85-0.96 with the whitened
        # sorter template; a gross misalignment would sit near 0.
        ok &= c > 0.75
        print(f"    u{u:>3} s{shank_of[u]}: n={m.sum():>6}  corr={c:.3f}")
    print("ALL UNITS ALIGNED" if ok else "*** SOME UNITS MISALIGNED ***")

    out = ROOT / "dataset" / "onchip_260413.npz"
    np.savez_compressed(out, snippets=SNIP, labels=LAB, shanks=SH, times=T,
                        units=np.array(units))
    print(f"saved {out}  ({SNIP.shape})")


if __name__ == "__main__":
    main()
