# On-device spike classification — options & test ladder

**Purpose.** A living reference for the classification methods we might run *on the nRF54LM20B* after offline spike sorting. We build this ladder from the **most bare-bones method up**, testing each against the same ground truth before adding complexity. Add a method only when the one below it is understood, tested, and found wanting.

**Scope.** This document is about *classification* (given a detected spike snippet, which unit fired?), not *detection* (was there a spike at all?) and not *sorting* (the offline clustering that produces our labels). Detection and sorting are upstream; see the pipeline note below.

---

## Where classification sits in the pipeline

```
1. wired recording            → raw multichannel data
2. offline spike sorting      → labeled (waveform, unit_id) pairs   ← our ground truth / training set
3. offline: fit a classifier  → parameters (thresholds / templates / centroids)
4. quantize + flash to nRF54  → integer params + integer inference code
5. real-time on device:
     detect spike → extract snippet → CLASSIFY → emit (unit_id, timestamp)
```

Everything in this document is step 3 (fit) and step 5 (run). The offline sort in step 2 is treated as truth — we are trying to *reproduce its labels* on-device, cheaply, in real time.

---

## The shared skeleton (why the ladder is coherent)

Every method here, from the crudest to the fanciest, is the same three-line shape:

```
INPUT   : one detected spike snippet  (~40 int16 samples from the ring buffer)
PROCESS : reduce snippet → score it against K stored prototypes → argmax/threshold
OUTPUT  : unit_id  (+ timestamp, stamped at classification time)
```

What changes as we climb the ladder is **only two things**:

1. **What we reduce the snippet to** (a single scalar → a few features → the whole waveform).
2. **What we store per unit** (a few cutoffs → a centroid → a full template).

The classification *logic* (compare, pick winner) barely changes. That's the point — it makes the data-structure differences the whole lesson.

---

## Tier 0 — Single-feature threshold  ← **START HERE (most bare-bones)**

The crudest thing that still counts as a learned classifier. No vectors, no distances, no matrix math. One scalar per spike, compared against learned cutoffs.

**Feature.** Peak-to-trough amplitude of the snippet:
`amp = max(window) - min(window)` — one subtraction of two int16 values. (Baseline-invariant, which is why peak-to-trough beats using the raw trough depth alone — though trough-only is an even-cheaper variant if we want to go there.)

**Fit (offline).** For every sorted spike, compute `amp`. Histogram `amp` per unit. If the units separate along this one axis, pick threshold(s) at the valleys between clusters. K units → K−1 thresholds.

**Data structure on device.**

```c
int16_t thresholds[K-1];   // sorted ascending
uint8_t bin_unit[K];       // which unit_id each amplitude bin maps to
```

That's the entire model. Bytes: `2*(K-1) + K`. For K=3 units: 8 bytes.

**Inference (on device).**

```
amp = max(window) - min(window)
find the bin: first i where amp < thresholds[i]   (linear or binary search)
unit_id = bin_unit[i]
```

**IPO.**

```
INPUT   : int16 window[40]
PROCESS : amp = max-min ; walk thresholds → bin index
OUTPUT  : unit_id
```

**Quantization.** None needed — it's already integer comparisons on raw int16 ADC values. This is the whole appeal of starting here.

**When it works / when it breaks.**

- ✅ Works when units on a channel differ mainly in *size* (common for 2 well-separated units).
- ❌ Breaks when two units have similar amplitude but different *shape* (same height, different width/polarity) — one scalar can't separate those.
- ❌ No notion of "this doesn't look like any unit" (noise/collision rejection) unless we add an outer detect threshold and an upper bound.

**Cheapest possible variant if even this is too much:** single trough depth `min(window)` instead of peak-to-trough — saves the `max()`. Less robust to baseline drift.

---

## Tier 1 — Nearest-centroid on 2 hand-picked features

If one scalar can't separate the units, add a second axis before reaching for anything heavy.

**Features.** Two cheap scalars, e.g. peak-to-trough amplitude + trough-to-peak width (samples between min and max). Now each spike is a 2-D point.

**Fit.** Mean (centroid) of each unit's points in the 2-D plane.

**Data structure.**

```c
int16_t centroid[K][2];    // (amp, width) per unit
```

**Inference.** Compute the 2 features, pick the nearest centroid by squared Euclidean distance (`da² + dw²` — no sqrt needed for argmin). Integer math throughout.

**vs Tier 0:** adds one feature axis and turns "which bin" into "nearest of K points." First appearance of the distance-to-prototype pattern that Tiers 2–3 reuse.

---

## Tier 2 — Nearest-template (matched filter) on the raw waveform

The method you named. No feature reduction at all — compare the whole snippet to a stored mean waveform per unit.

**Fit.** Per unit, average all its (aligned) snippets → one template waveform of ~40 samples.

**Data structure.**

```c
int16_t template[K][40];   // full mean waveform per unit
```

**Inference.** Score the snippet against each template; argmax/argmin.

- **Metric decision (open):** SSD (`Σ(x−t)²`) vs normalized cross-correlation (`Σ x·t` / magnitudes). Default **SSD** — no division, easiest to quantize; cross-corr is more robust to amplitude drift. Test both.

**vs Tier 1:** same "nearest prototype" logic, but the prototype is the full waveform in raw 40-D sample space. Biggest data structure so far (`K*40*2` bytes), most shape information retained.

**This is the on-chip workhorse.** Nearest-template with Euclidean distance is exactly the core of **Osort** — the clustering algorithm inside most fabricated on-chip sorters (Chen 2023/2026, Jiang 2026, L-Sort). The difference: real chips run Osort *online and adaptive* — templates update as spikes arrive (`T' = (N·T + s)/(N+1)`) and new clusters spawn when a spike matches nothing. Our version is the **static** case: templates fixed from offline training, no adaptation. For a train-offline / infer-on-device thesis that's the right simplification — but Osort is the live cousin, and worth naming that way when you present it.

---

## Tier 3 — Nearest-centroid in a reduced feature space (PCA *or* FSDE)

Compress the Tier-2 waveform to a few features first, then classify in that small space. Two ways to get the features — and the literature says the cheaper one is the one real chips actually use.

**Option 3a — PCA features.** Reuses the PCA work from the MountainSort-from-scratch pipeline directly.

- **Fit (offline).** Top-`d` principal components of the training snippets (d≈2–5). Store the `d×40` projection matrix. Project each unit's mean → centroid.
- **Data structure.**

```c
int16_t proj[d][40];       // PCA projection matrix (the expensive part)
int16_t centroid[K][d];    // one centroid per unit in feature space
```

- **Inference.** Project snippet (`d` dot products of length 40) → nearest centroid.

**Option 3b — FSDE features (first & second derivative extrema).** ← **what fabricated chips actually use.** Instead of a learned projection, extract a few hand-defined scalars: peak amplitude, trough amplitude, and the max/min of the first and second derivatives of the snippet. Chen 2026 and Jiang 2026 both use exactly this (they call it FSDE / pFSDE) because it's far cheaper than PCA — no projection matrix to store or multiply, just a handful of differences and max/min over the window.

- **Data structure.**

```c
int16_t centroid[K][d];    // d≈4-6 FSDE features per unit — NO projection matrix
```

- **Inference.** Compute the FSDE scalars directly from the snippet → nearest centroid. Cheaper than 3a (no `d×40` matrix-vector product).

**vs Tier 2:** same classification logic in a *reduced* space. The Tier 2 (store full waveforms, compare directly) vs Tier 3 (reduce first, then compare) contrast is the core data-structure lesson. **PCA vs FSDE is the sub-decision within Tier 3:** PCA is what you already understand; FSDE is what the hardware community defaults to. Worth testing both — if FSDE matches PCA's accuracy, it's the better on-device choice by a wide margin.

---

## Beyond the ladder (not yet)

- **Linear / LDA classifier:** weight matrix `W`, compute `W·x`, argmax. The canonical quantized on-device classifier (int8 MACs, NPU-friendly). Natural next rung after Tier 3.
- **Quantization-aware training:** only if post-training quantization drops accuracy too much. Fallback, not default.
- **Collision handling:** two units overlapping in <1 ms → superimposed waveform. Open problem, out of scope until the single-unit case works.

---

## What real fabricated on-chip sorters actually use (2013–2026)

Grounding the ladder against measured silicon (see `literature_review.md` for the full survey). This validates the ladder's *direction* and pins down two decisions.

| Chip                          | Features                 | Classifier / clustering                                    |
| ----------------------------- | ------------------------ | ---------------------------------------------------------- |
| Karkare 2013 (16-ch)          | —                       | unsupervised clustering                                    |
| Do 2019 (128-ch)              | —                       | improved**K-means**                                  |
| Hao 2021 (analog)             | —                       | analog**K-means**                                    |
| Chen 2023 / 2026 (384/128-ch) | **FSDE** + spatial | **Osort** (online nearest-template, Euclidean)       |
| Akhoundi 2025 (1024-ch)       | spatial                  | **SOM** (self-organizing map)                        |
| Jiang 2026 (1024-ch)          | **FSDE**           | **Osort** (firing-rate variant), Euclidean templates |
| Lukito 2026 (32-ch)           | analog autoencoder       | **L1 K-means**                                       |

**Three things this tells us:**

1. **Our ladder is the right shape.** Every one of these is either K-means (≈ our nearest-centroid, Tiers 1/3) or Osort (≈ our nearest-template, Tier 2). Nobody uses anything exotic for the *classifier* — the exotic part is always the *feature extraction*, not the decision rule.
2. **FSDE beats PCA for on-device.** The two strongest recent full sorters (Chen, Jiang) use FSDE, not PCA — because it needs no projection matrix. That's why Tier 3b exists.
3. **We're in the *hard* regime, and should own it.** All the high-accuracy chips lean on **spatial features** (which channel has the biggest peak) from dense multi-channel probes. On a **single channel** we have **temporal features only** — the same regime as the Quiroga benchmark, which Chen 2026 explicitly flags as where their spatial tricks *don't* apply and accuracy is hardest to get. Our one-channel pilot is a legitimate, well-defined slice — not a shortcut — but expect single-channel temporal-only accuracy to sit below the headline multi-channel numbers.

---

## Test / evaluation plan (same for every tier)

Run each method offline first, on held-out real data, *before* flashing anything.

- **Data:** real MA8 recordings we already have; offline-sort labels = ground truth. Train/test split.
- **Primary metric:** classification accuracy vs offline labels + **confusion matrix**.
- **The "don't miss a neuron" metric:** per-unit **recall** (fraction of a unit's true spikes correctly assigned). Misses matter more than misclassifications here.
- **Cost metrics (for the on-device story):** model size (bytes), inference ops per spike, worst-case latency.
- **Rule:** only climb to the next tier when the current tier's confusion matrix shows a failure the next tier could plausibly fix. Document *why* we climbed.

---

## Status / decision log

- **2026-08-26** — Document created. Decision: **start at Tier 0 (single-feature amplitude threshold)**, the most bare-bones learned classifier, and only climb when the confusion matrix demands it. Metric choice for Tier 2 (SSD vs cross-correlation) deferred until we get there.
- **2026-08-26 (update)** — Cross-checked the ladder against fabricated on-chip sorters (4 primary papers + verified deep-research pass; see `literature_review.md`). Findings folded in: (a) added the "what real chips use" section — ladder shape confirmed (everyone uses K-means or Osort; the variety is all in features); (b) added **FSDE** as Tier 3b, the hardware-community default that beats PCA on cost; (c) named **Osort** as the online/adaptive cousin of our static Tier 2; (d) flagged that our single-channel pilot is the harder **temporal-features-only** regime (no spatial features). No change to the start-at-Tier-0 decision.
