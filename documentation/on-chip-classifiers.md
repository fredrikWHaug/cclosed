# On-Chip Classifiers

> **Summary.** Three spike classifiers — logistic regression, a CNN, and a small
> ResNet — spanning ~94× in parameter count, all deployed on the nRF54LM20B and
> measured on real silicon. The headline: **fidelity saturates almost
> immediately**; the linear model is within 0.2 points of the ResNet at a
> fraction of the cost. This is the compression-vs-fidelity curve, measured.

Related: [system-architecture.md](system-architecture.md) ·
[cross-day-generalization.md](cross-day-generalization.md)

## Task

Classify a raw electrophysiology snippet from shank 0 — **8 channels × 40 samples
(4 ms @ 10 kHz)** — into *which spike-sorted unit* fired, and run that classifier
**on the nRF54 itself**. All three models classify the same hardcoded test
snippet (first shank-0 sample of class 0, unit 29) so the on-device demos are
directly comparable.

> **Scope note.** These are *within-day* numbers: train and test are an 80/20
> split of one recording session, and the input is the full 8-channel snippet
> (which includes spatial/location information). That makes the task relatively
> easy — see [cross-day-generalization.md](cross-day-generalization.md) for what
> happens when the day changes and the location cue is removed.

## The three models

| Model | What it is |
|-------|------------|
| **Logistic Regression** | One linear layer: `logits = W·x + b`. The floor. |
| **CNN** | 3× (Conv1d k3 + ReLU + MaxPool) → 2 FC layers. The working model. |
| **Small ResNet** | Conv stem → 3 residual blocks (64→128 ch) → 2 FC layers. The heavy ceiling. |

Shared inference primitives (`conv1d`, `maxpool1d`, `linear`, residual-add,
`argmax`) live in one header, `firmware/classifiers/nn.h`, so each model's
`main.c` reads like its PyTorch definition with no duplicated math. BatchNorm is
folded into the preceding conv at export time.

## Results (real silicon)

Accuracy from `model/compare_models.py` (all three trained on one identical 80/20
split, seed 42, 30 epochs). Flash/RAM are real figures from the
`nrf54lm20b/cpuapp` build; parameters stored as float32.

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
94× the parameters — 26× the flash and **665× the on-chip compute (1 ms → 665
ms)** — buys essentially nothing in aggregate accuracy. For a power- and
bandwidth-constrained implant, the linear/CNN end of the curve is clearly the
right operating point.

**2. The aggregate number hides class imbalance — read it honestly.** Per-unit
accuracy from the same run:

| Unit | n | Logistic | CNN | ResNet |
|-----:|--:|---------:|----:|-------:|
| 46 | 5,572 | 99.9% | 99.8% | 99.9% |
| 29 | 10 | 0% | 20% | 30% |
| 49 | 259 | 88.4% | 92.3% | 93.1% |
| 47 | 58 | 89.7% | 77.6% | 82.8% |

Unit 46 alone is ~65% of the validation samples, so "98%" is largely "predict 46
well." The extra capacity of the CNN/ResNet mainly helps the **rare** units (unit
29: 0% → 20% → 30%) — which contribute little to the headline number. A fairer
metric is macro-averaged (per-unit) accuracy, which the
[cross-day study](cross-day-generalization.md) adopts.

**3. ResNet fits, but only just.** At 68.8% of flash it is deployable, yet leaves
little room for the BLE stack, the SPI acquisition path, and buffers. Combined
with (1), it's not a sensible choice — it's the useful *ceiling* that proves the
cheaper models lose nothing.

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
#    — Fredrik builds/flashes via the VS Code Nordic extension.

# 4. open the serial terminal (115200 8N1) and reset the board.
#    Each firmware prints its prediction, correctness, and inference time in ms.
```

## Open items

- The numeric correctness of every forward pass was checked offline against
  PyTorch before flashing (ResNet C-mirror matched to 1.7e-6); the on-chip run is
  the final confirmation.
- **Cross-day** is the open frontier: these within-day numbers say nothing about
  whether a day-1 model survives to day 2. See
  [cross-day-generalization.md](cross-day-generalization.md).
