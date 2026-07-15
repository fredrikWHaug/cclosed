# On-Chip Model Comparison: Compression vs. Fidelity

## Goal
Classify a raw electrophysiology snippet from shank 0 — 8 channels × 40 samples
(4 ms @ 10 kHz) — into *which spike-sorted unit* fired, and run that classifier
**on the nRF54LM20B itself**. We deploy three models spanning ~94× in parameter
count to see how much on-chip cost buys how much accuracy. This is the core
compression-vs-fidelity question for the wireless-ephys thesis.

All three classify the **same** hardcoded test snippet (the first shank-0
sample of class 0, unit 29), so the on-device demos are directly comparable.

## The three models
| Model | What it is |
|-------|------------|
| **Logistic Regression** | One linear layer: `logits = W·x + b`. The floor. |
| **CNN** | 3× (Conv1d k3 + ReLU + MaxPool) → 2 FC layers. The working model. |
| **Small ResNet** | Conv stem → 3 residual blocks (64→128 ch) → 2 FC layers. The heavy ceiling. |

Shared inference primitives (`conv1d`, `maxpool1d`, `linear`, residual-add,
`argmax`) live in one header, `firmware/classifiers/nn.h`, so each model's
`main.c` reads like its PyTorch definition with no duplicated math. BatchNorm is
folded into the preceding conv at export time, so the C code is just
conv/relu/pool/linear.

## Results

Accuracy is from `model/compare_models.py` (all three trained on one identical
80/20 split, seed 42, 30 epochs). Flash/RAM are real figures from the
`nrf54lm20b/cpuapp` build. Parameters stored as float32.

| Model | Params | Val Acc | Flash | Flash % of 2 MB | RAM | On-chip latency |
|-------|-------:|--------:|------:|----------------:|----:|----------------:|
| Logistic Regression |   3,531 | 98.0% |   52 KB |  2.7% |  6.8 KB | **1 ms** (measured) |
| CNN                 |  40,939 | 97.8% |  197 KB | 10.2% | 26.8 KB | **44 ms** (measured) |
| Small ResNet        | 333,259 | 98.2% | **1,334 KB** | **68.8%** | 73.8 KB | **665 ms** (measured) |

The weight arrays dominate flash (≈ params × 4 bytes); the remaining ~40 KB is
the base Zephyr image.

## What this shows

**1. Fidelity saturates almost immediately.** A 3,531-parameter linear model is
within **0.2 points** of a 333,259-parameter ResNet (98.0% vs 98.2%). Spending
94× the parameters — 26× the flash, and **665× the on-chip compute (1 ms → 665
ms)** — buys essentially nothing in aggregate accuracy on this task. On real
silicon the cost spread is enormous while the accuracy spread is noise; for a
power- and bandwidth-constrained wireless implant, the linear/CNN end of the
curve is clearly the right operating point.

**2. The aggregate number hides class imbalance — read it honestly.** Per-unit
accuracy (from the same run) shows the val set is dominated by one unit:

| Unit | n | Logistic | CNN | ResNet |
|-----:|--:|---------:|----:|-------:|
| 46 | 5,572 | 99.9% | 99.8% | 99.9% |
| 29 | 10 | 0% | 20% | 30% |
| 49 | 259 | 88.4% | 92.3% | 93.1% |
| 47 | 58 | 89.7% | 77.6% | 82.8% |

Unit 46 alone is ~65% of the validation samples, so "98%" is largely "predict
46 well." The extra capacity of the CNN/ResNet mainly helps the **rare** units
(e.g. unit 29: 0% → 20% → 30%), which is where fidelity actually differs — but
those units contribute little to the headline number. A fairer future metric is
macro-averaged (per-unit) accuracy, not overall accuracy.

**3. ResNet fits, but only just.** At 68.8% of flash it is deployable on this
chip, yet leaves little room for the BLE stack, the acquisition/SPI path, and
buffers that the real product needs. Combined with (1), it is not a sensible
choice here — it is the useful *ceiling* that proves the cheaper models lose
nothing.

## Reproduce

```bash
# from repo root, with the venv active
# 1. train + export each model's C headers (weights + test snippet)
python model/export_logreg_to_c.py     # -> firmware/classifiers/logreg/*.h
python model/export_to_c.py            # -> firmware/classifiers/cnn/*.h   (uses checkpoints/shank0_best.pt)
python model/export_resnet_to_c.py     # -> firmware/classifiers/resnet/*.h (trains + saves checkpoint)

# 2. authoritative accuracy table (all three, identical split)
python model/compare_models.py

# 3. build a classifier for the board (repeat for logreg / cnn / resnet)
west build --build-dir firmware/classifiers/cnn/build --pristine \
    --board nrf54lm20dk/nrf54lm20b/cpuapp firmware/classifiers/cnn

# 4. flash, then open the serial terminal (115200 8N1) and reset the board.
#    Each firmware prints its prediction, correctness, and inference time in ms.
```

## Open items
- Fill the two _pending flash_ latencies by flashing logreg and resnet and
  reading the `Inference time: N ms` line (CNN is the 44 ms reference).
- The numeric correctness of every forward pass was checked offline against
  PyTorch before flashing (ResNet C-mirror matched to 1.7e-6); the on-chip run
  is the final confirmation.
