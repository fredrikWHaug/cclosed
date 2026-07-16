"""
Build a realistic single-channel spike TRACE for the SPI 'Intan' emulator.

Takes real recorded snippets from dataset.npz, picks a well-sampled unit and
its strongest channel, and strings a handful of real spikes together with
baseline gaps between them — so the slave streams something that looks like a
genuine extracellular recording (mostly flat, occasional sharp spikes).

Output: firmware/spi/slave/src/spike_data.h with the trace pre-converted to
16-bit offset-binary "ADC" samples (centre = 32768), so the firmware does no
float math.
"""
import numpy as np

SEED = 42
N_SPIKES = 6          # real spikes to string together
GAP = 24              # baseline samples between spikes
CENTRE = 32768        # 16-bit offset-binary midpoint (like a real ADC)
FILL = 0.80           # let the biggest spike use 80% of the ADC range

rng = np.random.default_rng(SEED)

d = np.load("dataset/dataset.npz")
snips = d["snippets"]          # (N, 40, 8)
labels = d["labels"]           # (N,)

# Pick the most-sampled unit so the spike shape is well-defined.
unit = np.bincount(labels[labels >= 0]).argmax()
idx = np.where(labels == unit)[0]

# Its strongest channel = largest peak-to-peak on the average snippet.
avg = snips[idx].mean(axis=0)                       # (40, 8)
ch = int((avg.max(axis=0) - avg.min(axis=0)).argmax())
print(f"unit {unit}: {len(idx)} snippets, strongest channel = {ch}")

# Baseline noise level estimated from the quiet edges of the snippets.
edges = np.concatenate([snips[idx, :5, ch], snips[idx, -5:, ch]], axis=1)
noise_std = float(edges.std())

# Build the trace: leading gap, then (spike, gap) x N, using distinct real spikes.
pick = rng.choice(idx, size=N_SPIKES, replace=False)
trace = [rng.normal(0.0, noise_std, GAP)]
for i in pick:
    trace.append(snips[i, :, ch])                   # a real 40-sample spike
    trace.append(rng.normal(0.0, noise_std, GAP))
trace = np.concatenate(trace).astype(np.float32)

# Convert to 16-bit offset-binary ADC codes.
scale = FILL * 32767.0 / np.max(np.abs(trace))
adc = np.clip(np.round(CENTRE + trace * scale), 0, 65535).astype(np.uint16)

with open("firmware/spi/slave/src/spike_data.h", "w") as f:
    f.write("#ifndef SPIKE_DATA_H\n#define SPIKE_DATA_H\n\n")
    f.write(f"/* Real spike trace: unit {unit}, channel {ch}, "
            f"{N_SPIKES} spikes + baseline. 16-bit offset-binary, centre={CENTRE}. */\n")
    f.write(f"#define SPIKE_CENTRE {CENTRE}\n")
    f.write(f"#define SPIKE_LEN {len(adc)}\n\n")
    f.write("static const unsigned short spike_stream[SPIKE_LEN] = {\n")
    for i in range(0, len(adc), 12):
        f.write("    " + ", ".join(str(v) for v in adc[i:i + 12]) + ",\n")
    f.write("};\n\n#endif\n")

print(f"wrote firmware/spi/slave/src/spike_data.h  ({len(adc)} samples, "
      f"range {adc.min()}..{adc.max()})")
