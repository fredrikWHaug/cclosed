#!/usr/bin/env python3
"""
Phase-2 diagnostic: how many real units feed our channel-56 detections?

Cross-references the spikes we detect on ch56 against the 73 ground-truth neuron
spike-time files — purely by TIME (both are 10 kHz indices into intan_combined),
so no channel-map needed. Tells us whether the 44% discard is structural (more
sources than the 4 cluster slots) or a parameter/quality problem.
"""
import glob
from pathlib import Path
import numpy as np
import prep   # reuse bandpass() + detect() + constants

NEURON_DIR = prep.ROOT / "raw-data" / "all_result_260414_141929" / "waveforms"
CH = 56
MINUTES = 5.0
TOL = 3       # samples; a detection "is" a GT spike if within TOL


def main():
    raw = np.load(prep.DATA, mmap_mode="r")
    nsamp = int(MINUTES * 60 * prep.FS)
    x = prep.bandpass(raw[CH, :nsamp].astype(np.float32))
    det, _, _ = prep.detect(x)
    det = np.sort(np.asarray(det))
    print(f"ch{CH}: {len(det)} detections in {MINUTES:.0f} min\n")

    # for each neuron, how many of its spikes coincide with one of our detections
    rows = []
    for nf in sorted(glob.glob(str(NEURON_DIR / "neuron_*_time_indices.npy"))):
        gt = np.load(nf)
        gt = np.sort(gt[gt < nsamp])
        if len(gt) == 0:
            continue
        idx = np.clip(np.searchsorted(det, gt), 1, len(det) - 1)
        mind = np.minimum(np.abs(det[idx] - gt), np.abs(det[idx - 1] - gt))
        coinc = int(np.sum(mind <= TOL))
        rows.append((Path(nf).stem.replace("_time_indices", ""), len(gt), coinc))

    rows.sort(key=lambda r: -r[2])
    print(f"{'neuron':>10} {'gt_spikes':>10} {'on_ch56':>8} {'frac_gt':>8}")
    total_explained = 0
    n_real = 0
    for name, ng, co in rows:
        if co < 20:
            continue
        frac = co / ng
        total_explained += co
        n_real += 1
        print(f"{name:>10} {ng:>10} {co:>8} {frac:>8.2f}")

    print(f"\nunits contributing >20 detections to ch56: {n_real}")
    print(f"detections explained by those units: {total_explained} / {len(det)} "
          f"({100*total_explained/len(det):.0f}%)")


if __name__ == "__main__":
    main()
