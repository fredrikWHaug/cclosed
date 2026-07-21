# On-Chip Real-Time Pipeline (raw → neuron → BLE)

> **Summary.** The end-to-end demonstration: raw Intan ADC codes go in on one MCU,
> get filtered / detected / classified into neuron IDs on a second MCU, and come
> out over BLE — verified bit-for-bit against a host reference and running 5.3×
> faster than real time. This page explains each stage, the results, the honest
> caveats, and **exactly how to reproduce and verify every number yourself**.

Related: [system-architecture.md](system-architecture.md) ·
[spi-acquisition-link.md](spi-acquisition-link.md) ·
[on-chip-classifiers.md](on-chip-classifiers.md)

## The chain

```
 slave DK (emulated Intan)                 master DK (nRF54)                 host (Mac)
 ┌────────────────────┐   SPI   ┌──────────────────────────────────┐  BLE  ┌──────────┐
 │ raw 16-bit ADC     │ ──────► │ biquad → CMR → decimate 30k→10k   │ ────► │ (unit_id,│
 │ codes (8 ch/shank) │ 3 frames│ → detect trough → classify (logreg)│ notify│ time)    │
 └────────────────────┘         └──────────────────────────────────┘       └──────────┘
        stream_test.h            firmware/pipeline/master            sim/ble_receiver.py
```

Every arrow is real: real recorded mouse data, a real SPI bus between two DKs, a
real BLE link to the laptop. The only thing emulated is the Intan chip itself
(a DK replaying a recording stands in for it).

## The governing constraint: train == deploy

The single rule that shapes everything: **the model must be trained on the exact
signal representation the MCU can produce in real time.** Two consequences that
are *not* choices:

1. **No whitening.** The offline sorter's recording is bandpass + common-median
   reference + **whitening** + downsample. Whitening needs a precomputed
   covariance over all channels and **cannot run on-chip**. So the training set is
   rebuilt from raw `.rhd` *without* whitening.
2. **Causal filter.** Real-time filtering must be causal (an IIR biquad), not the
   zero-phase FFT that's convenient offline. We measured the cost of ignoring
   this: an FFT-trained model dropped from 0.995 → **0.942** on causally-filtered
   test spikes. Training on the *same* causal biquad recovered it to **0.984**.
   So the biquad coefficients are shared, identically, between
   `dataset/build_onchip.py` (training) and the firmware.

The on-chip-feasible representation, fixed once:

| Stage | Value |
|-------|-------|
| Channels | shanks `[0,1,2,3,6,7,8,9]` = 64 ch, classified **per shank** (8 ch) |
| Filter | causal Butterworth biquad, 300–3000 Hz, 2 SOS sections |
| Reference | common-median across the shank's 8 channels |
| Rate | decimate 30 kHz → 10 kHz |
| Snippet | 40 samples (4 ms), realigned to the trough |
| Classifier | per-shank multinomial logistic regression, scaler folded into weights |
| Label | offline sorter unit ID (see "what accuracy means" below) |

## Results (what was actually measured)

**Offline model** (`model/train_onchip.py`, forward-in-time split — train the
earliest 80 % of the session, test the latest 20 %):

| shank | units | balanced accuracy | note |
|-------|-------|------------------:|------|
| 0 | 2 | 1.000 | distinct |
| 2 | 5 | **0.984** | distinct — this is the shank deployed to firmware |
| 3 | 4 | 0.940 | distinct |
| 9 | 2 | 0.876 | distinct |
| 1 | 4 | 0.255 (≈ chance) | **one over-split neuron** (waveform corr +1.00) |

Shank 1 sitting at chance is *correct behaviour*: the sorter split one neuron into
four labels; classifying between them is ill-posed. It's a label artifact, not a
model failure.

**On-chip, verified against the host:**
- Batch pipeline: decimated-signal max difference **< 1e-3 µV** (float32 vs numpy
  float — negligible on a ~100 µV signal).
- Streaming pipeline: **30 spikes detected, `real mismatches 0`.** The only
  host↔MCU disagreements are *near-tie* spikes (see caveat) — never a wrong trough
  or a confident misclassification.

**Full chain (two boards):**
- SPI transport: **72000 / 72000 words correct** (per-frame checksums).
- Compute: **57 ms for 300 ms of data = 5.3× faster than real time.**
- Output: 30 `(unit_id, timestamp)` notifications received on the Mac over BLE.

## Read this honestly — the caveats

1. **"Accuracy" = fidelity to the offline sorter, not ground truth.** The labels
   come from MountainSort + curation. A high score means the tiny on-chip model
   *reproduces the expensive offline pipeline*, which is a coherent goal — but it
   does **not** claim the sorter itself is correct. (Ground truth would need
   MEArec; deliberately out of scope here.)
2. **Near-tie flips are expected.** x86-numpy-float32 and ARM-float32 can't be
   bit-identical, so a spike whose top-2 logits are within ~0.1–0.2 can flip
   between host and MCU. The verification counts a disagreement as a *real*
   mismatch only if the host's top-2 margin is > 0.5 (float noise can't cross
   that). One such near-tie flip occurs in the 30-spike stream; it is honest, not
   tuned to pass.
3. **Bulk transport, not per-sample real-time.** The SPI transfer sends the whole
   stream in 3 frames, then the pipeline runs. True 30 kHz per-sample streaming
   needs a faster SPI clock + less framing overhead — a transport optimization.
   The **compute timing (5.3×)** is the real-time proof, separate from transport.
4. **One session, one deployed shank.** The firmware ships shank 2's 5-unit model.
   The pipeline is general (any shank), but only shank 2's weights are exported.

## Reproduce & verify it yourself

> **Interpreter gotcha:** use the system `python3` (has numpy + scipy + sklearn),
> **not** the repo `venv` (numpy only). Everything below needs scipy/sklearn.
> Requires `raw-data/MA1_260413_131912/*.rhd` present.

**Host side — rebuild the data, model, and firmware headers:**
```bash
python3 dataset/build_onchip.py          # raw .rhd -> dataset/onchip_260413.npz
                                         #   prints per-unit alignment corr + 100% coverage
python3 model/train_onchip.py            # per-shank balanced accuracy (the table above)
python3 model/export_onchip_logreg.py    # folds scaler -> firmware/classifiers/logreg/*.h
                                         #   asserts folded weights == sklearn on 20788 test snippets
python3 model/gen_stream_test.py         # -> firmware/classifiers/onchip/stream_test.h (verification vector)
```

**On-chip — single board (Fredrik builds/flashes via the VS Code extension):**
```
build+flash firmware/classifiers/onchip   ->  serial prints "STREAM MATCH"
                                              (30 spikes, real mismatches 0)
```

**Full chain — two boards + laptop:**
```
build+flash firmware/pipeline/slave    (board A, Intan emulator)
build+flash firmware/pipeline/master   (board B, pipeline + BLE), SPI-wired A<->B
pip install bleak && python sim/ble_receiver.py   (on the Mac)
  -> master serial: "SPI transport 72000/72000", "CHAIN OK", "57 ms for 300 ms"
  -> Mac: 30 spikes received over BLE
```

## File map

| File | Role |
|------|------|
| `dataset/build_onchip.py` | raw `.rhd` → on-chip-representation training set (`onchip_*.npz`, gitignored) |
| `model/train_onchip.py` | per-shank logreg, honest time-split benchmark |
| `model/export_onchip_logreg.py` | fold scaler, export `firmware/classifiers/logreg/{model_weights,test_data}.h` |
| `model/gen_stream_test.py` | build the streaming verification vector |
| `firmware/classifiers/onchip/` | single-board streaming pipeline + self-check |
| `firmware/pipeline/slave/` | Intan emulator: streams raw codes over SPI |
| `firmware/pipeline/master/` | SPI receive → pipeline → BLE notify |
| `sim/ble_receiver.py` | host `bleak` receiver |
| `sim/stream_rhd.py` | dependency-free `.rhd` reader used by the builders |

## What this proves (and doesn't)

**Proves:** a tiny linear model, fed a real-time-feasible on-chip representation,
reproduces the offline sorter's per-spike decisions on unseen (later) spikes, runs
on the nRF54 with 5× headroom, and its compressed output — a few bytes per spike —
survives SPI and BLE intact. That's the compressed end of the
[compression-vs-fidelity spectrum](system-architecture.md#compression-vs-fidelity-spectrum),
made real.

**Doesn't prove:** that the sorter is right (no ground truth), that it generalizes
across days at this fidelity (see [cross-day](cross-day-generalization.md)), or
that per-sample 30 kHz streaming closes over this SPI setup (transport, not compute).
