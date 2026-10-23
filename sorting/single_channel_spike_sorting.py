from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, sosfiltfilt
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA

# 1. Settings.
recording_file = Path(__file__).parent / "data" / "normal_30k_5min.bin"
figure_folder = Path(__file__).parent / "out"
sampling_rate = 30000  # must equal CH_RATE_HZ in the firmware
band_hz = (300, 6000)  # top edge must stay below sampling_rate / 2
threshold_in_noise_units = 4
ms_before_trough, ms_after_trough = 1.0, 1.5
min_cluster_size, min_samples = 20, 3
view_start_s, view_length_s = 1.0, 1.0

# 2. Read the recording (one 252-byte record per Bluetooth packet) and convert to microvolts.
packets = np.fromfile(recording_file, dtype=[("time", "<f8"), ("size", "<u2"), ("count", "<u2"), ("codes", "<u2", (120,))])
raw_uv = (packets["codes"].ravel().astype(float) - 32768) * 0.195
restart_samples = (np.flatnonzero(np.diff(packets["count"].astype(int)) < 0) + 1) * 120
seconds = np.arange(len(raw_uv)) / sampling_rate

# 3. Bandpass filter to remove slow drift and fast noise.
filtered_uv = sosfiltfilt(butter(3, band_hz, "bandpass", fs=sampling_rate, output="sos"), raw_uv)

# 4. Detect spikes: dip below a multiple of the noise, take the lowest point, skip the glitch at the start and each restart.
noise_uv = np.median(np.abs(filtered_uv)) / 0.6745
threshold_uv = -threshold_in_noise_units * noise_uv
below = filtered_uv < threshold_uv
crossings = np.flatnonzero(below[1:] & ~below[:-1]) + 1
troughs = np.unique([c + filtered_uv[c : c + round(sampling_rate / 1000)].argmin() for c in crossings])
n_before, n_after = round(ms_before_trough * sampling_rate / 1000), round(ms_after_trough * sampling_rate / 1000)
glitches = [(r - 6, r + 12) for r in [0, *restart_samples]]
troughs = troughs[[not any(a <= t < b for a, b in glitches) for t in troughs]]
troughs = troughs[(troughs >= n_before) & (troughs < len(filtered_uv) - n_after)]

# 5. Cut a waveform around each trough, squeeze it to 3 numbers with PCA, and group similar shapes with HDBSCAN.
waveforms_uv = np.array([filtered_uv[t - n_before : t + n_after] for t in troughs])
features = PCA(n_components=3).fit_transform(waveforms_uv)
labels = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples, copy=True).fit_predict(features)
n_units = labels.max() + 1
print(f"{len(troughs)} spikes in {seconds[-1]:.1f} s ({len(troughs) / seconds[-1]:.0f}/s), noise {noise_uv:.0f} uV, {n_units} unit(s):")
for unit in range(n_units):
    print(f"  unit {unit}: {np.sum(labels == unit)} spikes, mean trough {waveforms_uv[labels == unit].mean(0).min():.0f} uV")

# 6. Draw three separate figures: the trace, the spike shapes, and the clusters.
plt.rcParams.update({"font.family": "Helvetica", "axes.spines.top": False, "axes.spines.right": False})
blue, magenta, palette = "#2c6fad", "#c76bae", ["#2c6fad", "#c76bae", "#e0a030", "#4f9d69", "#7b5ea7"]
color_of = lambda label: "0.7" if label < 0 else palette[label % len(palette)]
figure_folder.mkdir(exist_ok=True)

view = slice(int(view_start_s * sampling_rate), int((view_start_s + view_length_s) * sampling_rate))
in_view = (troughs >= view.start) & (troughs < view.stop)
fig, (raw_axes, filtered_axes) = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
raw_axes.plot(seconds[view], raw_uv[view], lw=0.8, color="0.35")
raw_axes.set_title("raw: the spikes ride on the slow wobble", loc="left")
filtered_axes.plot(seconds[view], filtered_uv[view], lw=0.8, color=blue)
filtered_axes.axhline(threshold_uv, ls="--", lw=1, color=magenta)
filtered_axes.scatter(seconds[troughs[in_view]], filtered_uv[troughs[in_view]], c=[color_of(l) for l in labels[in_view]], s=30, zorder=3)
filtered_axes.set_title(f"filtered {band_hz[0]}-{band_hz[1]} Hz: {in_view.sum()} spikes in this {view_length_s * 1000:.0f} ms window (dashed = threshold)", loc="left")
filtered_axes.set_xlabel("seconds")
for axes in (raw_axes, filtered_axes):
    axes.set_ylabel("µV")
fig.tight_layout()
fig.savefig(figure_folder / "1_trace.png", dpi=150)

fig, axes = plt.subplots(figsize=(6, 4.5))
milliseconds = np.arange(-n_before, n_after) / sampling_rate * 1000
for waveform, label in zip(waveforms_uv, labels):
    axes.plot(milliseconds, waveform, lw=0.6, color=color_of(label), alpha=0.2)
for unit in range(n_units):
    axes.plot(milliseconds, waveforms_uv[labels == unit].mean(0), lw=2.5, color=color_of(unit), label=f"unit {unit} ({np.sum(labels == unit)} spikes)")
axes.set(xlabel="milliseconds from trough", ylabel="µV", title=f"all {len(labels)} spike shapes")
axes.legend(frameon=False)
fig.tight_layout()
fig.savefig(figure_folder / "2_spike_shapes.png", dpi=150)

fig, axes = plt.subplots(figsize=(5.5, 5))
axes.scatter(features[:, 0], features[:, 1], c=[color_of(l) for l in labels], s=14, alpha=0.7)
axes.set(xlabel="PC 1", ylabel="PC 2", title=f"{n_units} cluster(s) from {len(labels)} spikes")
fig.tight_layout()
fig.savefig(figure_folder / "3_clusters.png", dpi=150)
plt.show()
