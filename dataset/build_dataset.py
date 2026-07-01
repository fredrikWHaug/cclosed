"""
Build training dataset from offline spike sorting results.

Takes the filtered continuous recording + MountainSort4 firings and produces
per-shank (input, label) pairs:
  - input: 8-channel x 40-sample snippet around each spike
  - label: unit ID from the sorter

Usage:
    python build_dataset.py --data_dir ../offline-reference
"""

import argparse
import json
import numpy as np
from pathlib import Path


# 10 shanks, 8 channels each, in hardware channel order
# (from the lab's generate_multi_shank + cal_probe_groups config)
CHN_GROUPS = {
    0: [49, 48, 47, 46, 44, 45, 50, 51],
    1: [53, 52, 43, 42, 40, 41, 54, 55],
    2: [57, 56, 39, 38, 36, 37, 58, 59],
    3: [61, 60, 35, 34, 32, 33, 62, 63],
    4: [1, 0, 31, 30, 28, 29, 2, 3],
    5: [5, 4, 27, 26, 24, 25, 6, 7],
    6: [9, 8, 23, 22, 20, 21, 10, 11],
    7: [13, 12, 19, 18, 16, 17, 14, 15],
    8: [72, 71, 73, 70, 68, 75, 69, 74],
    9: [76, 67, 77, 66, 64, 79, 65, 78],
}

SAMPLES_BEFORE = 20  # 2 ms at 10 kHz
SAMPLES_AFTER = 20   # 2 ms at 10 kHz
SNIPPET_LEN = SAMPLES_BEFORE + SAMPLES_AFTER  # 40 samples = 4 ms


def find_shank(channel_id: int) -> tuple[int, list[int]]:
    """Return (shank_index, list_of_8_channels) for a given channel."""
    for shank_id, channels in CHN_GROUPS.items():
        if channel_id in channels:
            return shank_id, channels
    raise ValueError(f"Channel {channel_id} not found in any shank group")


def load_recording(data_dir: Path) -> np.ndarray:
    """Load the filtered continuous recording. Returns (n_samples, 80) float16."""
    rec_dir = data_dir / "all_result_260422_130915" / "recordings"
    with open(rec_dir / "binary.json") as f:
        meta = json.load(f)

    kwargs = meta["kwargs"]
    dtype = np.dtype(kwargs["dtype"])
    n_channels = len(kwargs["channel_ids"])
    raw_path = rec_dir / "traces_cached_seg0.raw"

    data = np.memmap(raw_path, dtype=dtype, mode="r")
    n_samples = data.shape[0] // n_channels
    return data.reshape(n_samples, n_channels)


def load_sorting(data_dir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load firings.npz. Returns (spike_times, spike_labels, unit_ids)."""
    firings_path = data_dir / "all_result_260422_130915" / "sorting" / "sorter_output" / "firings.npz"
    firings = np.load(firings_path)
    return (
        firings["spike_indexes_seg0"],
        firings["spike_labels_seg0"],
        firings["unit_ids"],
    )


def load_templates(data_dir: Path) -> np.ndarray:
    """Load average templates (n_units, 40, 80) to find each unit's peak channel."""
    path = data_dir / "all_result_260422_130915" / "waveforms" / "templates_average.npy"
    return np.load(path)


def build_dataset(data_dir: Path, output_path: Path):
    print("Loading recording...")
    recording = load_recording(data_dir)
    n_samples = recording.shape[0]
    print(f"  Recording shape: {recording.shape}")

    print("Loading sorting results...")
    spike_times, spike_labels, unit_ids = load_sorting(data_dir)
    print(f"  {len(spike_times)} spikes, {len(unit_ids)} units")

    print("Loading templates to find peak channels...")
    templates = load_templates(data_dir)
    # Peak channel = channel with largest negative deflection per unit
    # templates shape: (n_units, 40, 80)
    peak_channels = {}
    for i, uid in enumerate(unit_ids):
        peak_ch = np.argmin(templates[i].min(axis=0))
        peak_channels[uid] = int(peak_ch)

    # Build snippets
    snippets = []
    labels = []
    shank_ids = []
    times = []
    skipped = 0

    print("Extracting snippets...")
    for spike_idx in range(len(spike_times)):
        t = spike_times[spike_idx]
        uid = spike_labels[spike_idx]

        # Boundary check
        if t < SAMPLES_BEFORE or t + SAMPLES_AFTER > n_samples:
            skipped += 1
            continue

        # Get this unit's shank
        peak_ch = peak_channels[uid]
        shank_id, shank_channels = find_shank(peak_ch)

        # Extract 8-channel snippet
        snippet = recording[t - SAMPLES_BEFORE : t + SAMPLES_AFTER, shank_channels]
        # snippet shape: (40, 8)

        snippets.append(snippet)
        labels.append(uid)
        shank_ids.append(shank_id)
        times.append(t)

    snippets = np.array(snippets, dtype=np.float32)  # (N, 40, 8)
    labels = np.array(labels, dtype=np.int32)
    shank_ids = np.array(shank_ids, dtype=np.int8)
    times = np.array(times, dtype=np.int64)

    print(f"  Extracted {len(snippets)} snippets ({skipped} skipped at boundaries)")
    print(f"  Snippet tensor shape: {snippets.shape}")
    print(f"  Unique units: {len(np.unique(labels))}")
    print(f"  Shanks used: {np.unique(shank_ids)}")

    # Per-shank stats
    for s in range(10):
        mask = shank_ids == s
        n = mask.sum()
        n_units = len(np.unique(labels[mask])) if n > 0 else 0
        print(f"    Shank {s}: {n} spikes, {n_units} units")

    print(f"Saving to {output_path}...")
    np.savez_compressed(
        output_path,
        snippets=snippets,      # (N, 40, 8) float32
        labels=labels,           # (N,) int32 — unit IDs
        shank_ids=shank_ids,     # (N,) int8 — which shank
        times=times,             # (N,) int64 — sample index in recording
        peak_channels=np.array(
            [(uid, ch) for uid, ch in peak_channels.items()],
            dtype=np.int32
        ),  # (n_units, 2) — [unit_id, peak_channel]
        chn_groups=np.array(
            [(k, *v) for k, v in CHN_GROUPS.items()],
            dtype=np.int32
        ),  # (10, 9) — [shank_id, ch0, ..., ch7]
    )
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build spike sorting training dataset")
    parser.add_argument(
        "--data_dir",
        type=Path,
        default=Path(__file__).parent.parent / "offline-reference",
        help="Path to offline-reference directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "dataset.npz",
        help="Output path for the dataset",
    )
    args = parser.parse_args()
    build_dataset(args.data_dir, args.output)
