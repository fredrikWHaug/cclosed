# Classification benchmark plan — validating accuracy against ground truth

**Purpose.** Pin down the minimum design requirement for the classification pipeline and work out exactly how to measure it — what "ground truth" means, how to get it, and how to align it in time with our on-device output.

---

## 1. The minimum design requirement

> The classification pipeline achieves classification accuracy **above chance** (note: chance varies with the size of the classification space — 50% for a 2-unit problem, lower for 3+ units) **benchmarked against post-recording Kilosort 4.0 sorting from concurrent tethered recordings.**

This is a deliberately low, achievable floor, not a stretch target — every fabricated on-chip sorter reviewed in `literature_review.md` clears 70–99% on comparable benchmarks (Chen 2026: 87–99%; Jiang 2026: 84.6–93.7% including replayed real mouse data vs. Kilosort; Lukito 2026: 91.5–94.5%). The value of setting the bar here is that it's a genuine pass/fail gate ("did the pipeline work at all"), not an aspirational number.

**Chance level depends on the number of classes.** For a 2-unit classification problem, chance = 50%. For 3 balanced units, chance ≈ 33%. For 5, ≈ 20%. The requirement should be read as "reliably above whatever chance is for the specific classification space being tested," not literally "> 50%" in all cases.

## 2. Methodological precedent — this is not a novel approach

This validation pattern — synthetic/replayed signal → real acquisition hardware → compare on-device output to offline-sorted ground truth — is the standard methodology used by the fabricated on-chip sorters already reviewed:
- **Jiang et al. 2026**: replays real pre-recorded in-vivo mouse data through their chip, compares to **Kilosort** ground truth (93.7%/85.1% agreement).
- **Russo et al. 2026**: feeds in-vivo pre-recorded rodent data through a DAC into their serializer ASIC for validation.

So using Kilosort 4.0 output as the ground-truth reference is directly precedented by top-venue prior art, not an invented approach.

## 3. Two signal-source options, and why they lead to different pipelines

### Option A — Fully synthetic, file-based (known a priori ground truth)
If the test signal is generated from a **known digital file** (e.g., programmed onto a general-purpose arbitrary waveform generator from a file we wrote), the ground truth already exists *before* playback — no separate ground-truth capture needed. Feed the same file to Kilosort 4.0 directly, or skip Kilosort entirely and compare against the a priori labels used to construct the file.
- **Pros:** simplest; no synchronization problem between two acquisition systems, since only one exists (ours).
- **Use for:** validating the classification pipeline's *logic* first, before tackling synchronization.

### Option B — TDT FB128 Neural Simulator (procedurally generated, no accessible ground-truth file)
**Correction to initial assumption:** the FB128 does **not** play back a known file. Per TDT's own spec page:
> "The FB128 generates simulated neurological waveforms rather than playing back pre-recorded spike trains... procedurally-generated spikes... eight unique spike waveform shapes depending on the operating mode."

This means **there is no pre-existing digital ground truth to hand to Kilosort** — the FB128 itself is the only source of the signal, generated live. Consequently, **Option A's shortcut does not apply**, and a genuine concurrent tethered reference recording is required to establish ground truth.

- **Device specs (verified from TDT docs):** ±10 mV output, up to 128 channels (96 unique), four ZIF-Clip connector variants, optional Omnetics connectors (FB128-OMN model). Modes include NORMAL (LFP + spikes), HASH, LFP ONLY, TETRODE, SYNC 100 Hz, and tone modes.
- **Open item:** the FB128-OMN's Omnetics connector may be intended for Intan-style headstage compatibility (Omnetics is Intan's typical connector family) — **not verified**, check exact pinout against the RHD2164 before assuming direct compatibility.
- **Open item:** the "SYNC 100 Hz" mode's exact function is undocumented on the page fetched — its name suggests it may be built for cross-system synchronization, but this needs to be looked up directly, not assumed.

## 4. Required architecture for Option B (and for the eventual real-animal experiment)

**Key realization:** this dual-tap-plus-sync architecture is not just a bench-test workaround — it is the same general architecture needed for the eventual real animal validation (one real signal, split into a tethered reference path and the wireless nRF54 path). Solving it now, with reproducible fake spikes, de-risks the synchronization mechanism before any animal is involved.

1. **Physically split the single analog signal** (FB128 output, or eventually a real electrode) into two simultaneous acquisition paths: our nRF54/Intan chain, and a separate standard tethered reference recording system.
2. **Run Kilosort 4.0 offline on the reference system's digitized recording** to produce ground-truth `(spike, unit_id)` labels — unavoidable for procedurally-generated or real signals, since no pre-existing ground-truth file exists.
3. **Align the two independently-clocked digital recordings** using a shared hardware sync signal (a TTL pulse or distinctive marker) recorded as an extra channel by both systems, giving a common time anchor. Do not assume the two systems' sample clocks stay perfectly aligned over the whole recording — clock drift between independent clocks is expected.
4. **Match spikes using a tolerance window (e.g., ±1–2 ms), not exact-sample alignment.** This is standard practice in spike-sorting-comparison frameworks (e.g., SpikeForest-style matching) — exact sample-level synchronization between two independent systems is not achievable in practice, and the field doesn't require it.

## 5. Recommended sequencing

1. **Validate pipeline logic first, using Option A** (fully synthetic, known ground truth, single acquisition system, no sync problem) — proves the classifier itself works before adding hardware complexity.
2. **Then validate the synchronization mechanism using Option B** (FB128 + tethered reference + Kilosort 4.0 + shared sync signal) — proves the dual-system, tolerance-window comparison methodology works with reproducible fake data.
3. **Only then move toward the real animal experiment**, reusing the exact synchronization architecture proven in step 2, with a live probe replacing the FB128.

This keeps each step isolated: pipeline correctness (step 1) is never confounded with synchronization correctness (step 2), and both are proven before any live-animal complexity is introduced — consistent with the ES100 no-animal-testing constraint on the proposal itself, since steps 1–2 require no animal at all.

---

## Status / decision log

- **2026-08-27** — Document created, capturing the minimum design requirement (accuracy above chance vs. Kilosort 4.0 on concurrent tethered recordings) and the FB128 investigation. Correction recorded: the FB128 procedurally generates spikes and does not expose a ground-truth file, ruling out the simpler file-based comparison for that specific device. Two open items flagged for verification: FB128-OMN/Intan RHD2164 connector compatibility, and the exact function of the FB128's "SYNC 100 Hz" mode.

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

# Design considerations — architecture dialogue (stored context)

> Verbatim transcript of the architecture discussion about keeping the firmware
> "plumbing" invariant while swapping classifiers, and an epistemic-honesty
> exchange about how confident that architecture advice actually is. Stored as
> important context for the classifier-pipeline architecture decision.

---

## Fredrik

Right. But these are design considerations that we will have to make. But are you saying we can keep the overarching architecture fairly consistent in terms of the plumbing as I call it, like what separate modules we have and how we interface between the different modules? This is the important thing I thing we need to decide upon now, and also consider whether this itself is a considerably variable concept that can be optimized or not.

## Claude

Yes — and this is the right thing to lock down now. My honest position: **the plumbing can be kept near-invariant, with the classifier as the single swappable module — but only if we adopt two conventions now.** Those two conventions *are* the decision. Let me lay out the invariant substrate, then the two forks that determine how invariant it really is, with my recommendation on each.

### The proposed invariant substrate

```
[SPI/Intan acquire] → [ring buffer] → [detect + align] → [classify] → [packetize + BLE]
        │                  │                │                 │              │
     invariant         invariant        invariant        SWAPPABLE      invariant
        │                  │                │                 │              │
   xfer/init          ring[N]          snippet out       classify.h      unit_id+ts
   (never             samples in,     ◄─ Contract A     ◄ Contract B ─►   out
    changes)          windows out      int16 snippet[N]  uint8 unit_id    fixed packet
```

Four of the five modules never change when you swap classifiers. The interfaces between them — **Contract A** (`int16 snippet[N]` in) and **Contract B** (`uint8 unit_id` + timestamp out) — are what you freeze once and never touch again.

### The two decisions that determine invariance

**Decision 1 — Where does feature extraction live?** This is the big one.
- **Option A (recommended): inside `classify()`.** Every classifier receives the *same raw `int16 snippet[N]`* and does its own feature work internally. Logistic-regression-on-FSDE computes FSDE inside its file; the CNN eats raw samples; Tier 0 takes max−min. **Plumbing stays 100% invariant** because the interface is always "raw snippet in."
- **Option B: feature extraction as its own pipeline stage** feeding a `feature[]` vector to `classify()`. But different classifiers want different features → the feature stage *and* the interface (how many features) become variable → the plumbing is no longer invariant.
- **My recommendation: Option A.** Freeze the contract at raw snippet. If two classifiers share a feature extractor (e.g. FSDE), factor it into a `features.c` helper they *choose* to call — shared code without it being a mandatory, interface-changing stage. This is the single most important convention for keeping the plumbing stable.

**Decision 2 — Where do detection and alignment live?**
- **Recommended: as a fixed upstream stage**, not inside `classify()`. Detection ("a spike occurred at index i") and alignment ("center the snippet on the peak") are logically independent of *which* classifier runs. Making them a fixed stage means every classifier receives a clean, peak-centered snippet and none of them re-implements detection. (Your pilot currently folds lag-search *into* `classify()` — that was fine for one method, but it's the thing to lift out to make the swap truly clean.)
- Consequence: `classify()` may assume its input is already aligned. That assumption becomes part of Contract A, documented in `classify.h`.

### Is the plumbing itself "considerably variable / optimizable"?

Honest answer: **within your paradigm, no — and that's the good news.** The *module structure and the two interfaces* should be frozen now; you nail them once and every classifier reuses them. What remains tunable is strictly *inside* modules and doesn't touch the interfaces:

- ring size, window length `N`, detection threshold/method, alignment method, packet batching — all internal knobs you can optimize freely later without breaking anything.

The plumbing only becomes genuinely *variable* if you leave the paradigm — and it's worth naming exactly when, so you know the boundaries of what you're freezing:
1. **Continuous/streaming classifiers** (an RNN or CNN that processes every sample with no discrete detection) — this removes the detect stage and changes Contract A from "a snippet" to "a sample stream." *Out of scope for your single-channel detect-then-classify thesis, but it's the one thing that would rearchitect the plumbing.*
2. **Multi-channel spatial classification** (multiple ring buffers + a spatial-feature stage, like the real chips) — future, not now.

So the discipline is: **freeze the module boundaries and Contracts A/B today; optimize inside modules forever; only revisit the plumbing if you deliberately switch paradigms.** Adopt Option A (features inside classify) + detection/alignment as a fixed upstream stage, and your plumbing is invariant across logistic regression, template matching, MLP, and snippet-based CNN/RNN — the entire realistic classifier space for the thesis — with `classify.c` as the one file that ever changes.

If you're good with those two conventions, that *is* the architecture, and we can freeze `classify.h` (the contract) as the first concrete artifact.

---

## Fredrik

Ok great but now let me ask you this: how do you know this? Or what makes you think you know this? Is this a battle-tested architecture for this kind of data streaming in terms of the interfaces? Or are you genuinely not sure since you have some kind of intuition? I'm not necessarily asking you to cite a book written about abstract system architectures for this kind of embedded streaming, I mean you could but I don't expect you to be able to. I just want to have an open dialog about this, because I have the best interest for myself in terms of my learning, this project, and my integrity. But I think it's unavoidable to have these kinds of discussions with AI these days, so I want to just ask you this question first: how do you know this, and how confidently are you that if we were to decide on this architecture, we wouldn't be wrong i.e. there exists a much better choice?

## Claude

Good question, and the honest answer has layers, because "how do I know this" is genuinely different at different levels of the claim. Let me separate what's battle-tested from what's my judgment, because they're not the same and you deserve to know which is which.

**What's canonical, not intuition.** The two load-bearing pieces are textbook, decades-old patterns that I'm recognizing, not inventing:
- **Producer-consumer via a ring buffer** — a single-producer/single-consumer ring is one of the most-studied concurrency primitives in existence (every RTOS, audio pipeline, DSP chain uses it). The claim "decouple acquisition from processing with a bounded ring" is as close to settled as embedded architecture gets.
- **A stable interface with a swappable implementation behind it** — this is just the strategy pattern / dependency inversion / hardware-abstraction-layer idea. "Freeze a header, vary the .c behind it" is bedrock C modularity.

These have names you can check independently of me: *SPSC ring buffer*, *strategy pattern*, *pipeline/dataflow architecture*, *HAL*. If I disappeared, you'd find all of them described the same way. At this level my confidence is very high, and it's not intuition — it's recognition of established patterns.

**What's my judgment, not canon.** The *specific decomposition* — exactly these five stages, features-inside-classify vs. features-as-a-stage, alignment upstream vs. inside — is me *instantiating* those patterns for your problem. That's informed (the fabricated-chip papers you just read literally diagram detect→feature→classify as stages, and your pilot already has the seam), but the exact boundary choices are defensible opinions, not theorems. Option B (features as their own stage) is a real alternative that some real pipelines prefer; I recommended A, but I can't prove A dominates B for your future. Here my confidence is *moderate* — good recommendation, genuinely contestable.

**The one thing that would make us "wrong."** The whole "invariant plumbing" claim is *conditional on the paradigm*: discrete detect-then-classify, single channel. That assumption is load-bearing. If the project's real trajectory turns out to be streaming neural nets (process every sample, no discrete detection) or multi-channel spatial sorting, the plumbing I described needs rework. I flagged that earlier, and it's the honest hedge: **the architecture is right *given the paradigm*, and the paradigm assumption is the thing most likely to be the actual mistake** — not the ring buffer, not the interface.

**And a failure mode you should hold me to.** AI architecture advice has two characteristic biases: it *over-engineers* (adds principled-sounding abstractions you don't need) and it *sounds more authoritative than the underlying confidence warrants*. I've tried to counter the first — I explicitly argued *against* splitting `ring.c`/`ble.c`/`spi.c`, kept it to the one split that serves your stated goal. But I can't fully self-certify that I'm not doing the second right now. I don't have reliable introspective access to distinguish "this is the canonical pattern" from "this pattern-completes to something that sounds right" — same caveat as when I botched those numeric comparisons earlier.

**So here's the integrity move, and it's better than trusting my confidence:** this architecture makes a *falsifiable* claim — "you can swap the classifier without touching `main.c`." Don't take that on faith. Test it cheaply and early: implement two *maximally different* classifiers behind the same `classify.h` — say, the Tier-0 threshold (integer, trivial) and template-matching (float, windowed) — and check whether `main.c` genuinely never changes. If it does, the abstraction leaked and we chose the boundary wrong, and you'll know in an afternoon rather than after building on it. That experiment tests the design harder than any amount of me asserting it's right — and it's the kind of thing that protects your integrity too, because then *you've* verified the claim, not outsourced it to me.

My net position: high confidence on the patterns, moderate on the specific boundaries, and the real risk isn't "a much better architecture exists for this paradigm" (this *is* the standard shape) — it's "the paradigm might shift." I'd commit to it *as a starting point designed to be cheaply falsified*, not as a thing to trust because I said so.

# SPI bring-up plan — getting acquisition to 32-channel speed

**Purpose.** "Get SPI up to speed" is actually **two separate problems wearing one name** — a firmware problem and a hardware/signal-integrity problem. This doc pins down both, with the numbers behind them, so neither gets silently dropped and so each can be handed to the right kind of help (embedded-dev mentorship vs. PCB/mixed-signal mentorship).

**Why this matters now.** The discrete detect-then-classify architecture (see `classification_options.md`, `design_considerations.md`) only works at 32 channels if acquisition can actually sustain the required throughput. Detection, classification, and BLE egress all have comfortable headroom at 32 ch — **acquisition is the one gate**, and it's not solved by the current code.

---

## 1. The target, in numbers

- **32 channels × 30 kS/s/ch = 960 kS/s aggregate**, vs. the RHD2164's rated ceiling of **1.05 MS/s** — ✅ fits, but at ~91% of max, essentially no headroom.
- That requires one Intan SPI conversion every **~950 ns**, i.e. an SPI clock (`SCLK`) around **17–20 MHz**, driven continuously.
- **Recommended design point, not the stretch case:** 20–25 kS/s/ch (640–800 kS/s aggregate) — still fine for spike detection, gives real margin on both the ADC ceiling and the SCLK requirement. Treat 30 kHz/ch as the edge case to reach for later, not the first target.

## 2. Problem A — firmware (the software half)

**Current code cannot do this.** `xfer()` (in `board-bring-up`, `signal-path-intan`, `classification-pilot`) runs `SCLK` at 1 MHz with **manual GPIO chip-select** and `k_busy_wait(2)` padding around every single transfer — roughly ~20 µs per conversion. At that rate, sustaining 960 k conversions/s would require ~19 seconds of SPI time per second of real time. Not close to possible.

**What's actually needed:**
- Replace manual-CS / busy-wait with a **DMA-driven SPI pipeline** — queue conversions, let the peripheral run at ~17–20 MHz `SCLK` without the CPU busy-waiting on each transfer.
- This has to run **concurrently** with the rest of the real-time pipeline (detection, classification, BLE notify) without blocking any of them — a Zephyr RTOS concurrency question (threads/interrupts/queues), not just a raw-throughput one.
- The **two-command pipeline lag** (Intan datasheet, p.16: *"each command sent over the MOSI line generates a 16-bit result that is transmitted over the MISO line two commands later"*) still has to be handled correctly at this speed — this is a correctness detail on top of the throughput problem, not a substitute for it.

**This is the "embedded development" help-ask** — see the email draft context: DMA-driven peripheral drivers + Zephyr concurrency primitives for sustained multichannel acquisition into the ring buffer without drops.

## 3. Problem B — hardware / signal integrity (the electrical half)

**Firmware alone cannot guarantee this works**, because at ~17–20 MHz the timing margins get tight. From the Intan datasheet's own SPI Bus Timing Specifications (p.15):

| Parameter | Spec | Consequence at high SCLK |
|---|---|---|
| `t_SCLK` (SCLK period) | min 40 ns → 25 MHz absolute ceiling | at 20 MHz (50 ns period) there's very little slack left |
| `t_MOSI` (data-valid-before-sample setup) | min 10 ns | real wiring/propagation delay eats into this margin |
| `t_MISO` (clock-edge-to-data-valid) | max 12 ns | if the line hasn't settled by the sampling edge, you sample the wrong bit |

At 1 MHz (1000 ns period), these margins were enormous and invisible. At 17–20 MHz, board wiring (trace length, capacitance) becomes a real threat to correct sampling — this is a **layout/signal-integrity problem**, not something fixable by changing C code.

**The separate, and arguably bigger, issue: CMOS vs. LVDS signaling.** The board is currently forced into **CMOS signaling** (`LVDS_en` tied to GND, a fix from the BGA bring-up saga). The datasheet (p.12) is explicit:

> "Operating the ADC at 1.05 MS/s with standard CMOS signaling will increase amplifier noise by at least 30%... standard CMOS signaling is recommended only for ADC sampling rates of 175 kS/s or less (i.e., ... **5 kS/s/channel or less with 32 amplifiers**)."

Our 20–30 kS/s/ch target is **4–6× above** that CMOS-safe threshold. The mechanism (also datasheet, p.11): CMOS's full-swing switching pulls bursty current from a power supply *shared with the ultra-sensitive analog amplifiers* (2.4 µVrms input-referred noise), injecting high-frequency noise into the recording. LVDS avoids this because it steers a **constant** current instead of switching a full voltage swing, so it doesn't jolt the shared rail.

**If LVDS is required, what changes:**
- `LVDS_en` → tied to VDD instead of GND (board/hardware change, not firmware).
- 100 Ω termination resistors near the chip on each differential pair (board change).
- Either the nRF54's SPI peripheral has native LVDS-capable I/O for the relevant pins (**unconfirmed — needs checking against the nRF54LM20B datasheet**), or an external LVDS↔CMOS translator chip is added (the Intan datasheet's own suggested path for controllers lacking native LVDS I/O).
- **Important, and reassuring:** none of this touches the application-level code. `xfer()`, the `CMD_*` macros, the pipeline handling, the ring buffer — all identical either way. LVDS is a physical-layer change, not a protocol change.

**This is the "PCB design / mixed-signal" help-ask**, not embedded development: confirming reliable SCLK at the required throughput given real trace/wiring signal integrity, and evaluating whether LVDS is needed to hit the speed and noise targets simultaneously.

## 3.5 Chip-select mechanism & SPIM instance — RESOLVED (2026-09-01)

This is the concrete answer to what §2 hand-waved as "a DMA-driven SPI pipeline." Two
independent methods **converged** on the key numbers: (a) a direct read of the
**nRF54LM20B datasheet §11.19 (SPIM Electrical specification)** — primary source; and
(b) an adversarially-verified research workflow (12/12 central claims corroborated
across Nordic product spec, nrfx HAL, and Zephyr driver sources). The load-bearing
frequency figures from the workflow match the datasheet reading exactly.

### The silicon ceiling (datasheet §11.19, verbatim values)
- `fSPIM` (standard instances): **8 Mbps** max.
- `fSPIM,HS` (high-speed): **32 Mbps** max — footnote: *"For SPIM00 using GPIO port P2."*
- `tSPIM,CSCK` (SCK period): **31.25 ns** min → confirms 32 MHz on the HS instance.
- `tSPIM,START` (START task → transmission started): **1 µs** — a per-transfer startup latency (matters below).

**Instances:** SPIM00 (high-speed, MCU domain), SPIM20–24 (standard), SPIM30 (low-power).
**The old `spi22` is a standard 8 Mbps instance.** Consequence: `spi22` **physically cannot**
do 32 ch × 30 kHz — 8 Mbps ÷ 16 bit ÷ 32 ch ≈ **15 kHz/ch max**. **SPIM00 (32 MHz, on port
P2, extra-high-drive pins) is required for the scaling path.** This supersedes §2's
"~17–20 MHz on `spi22`" — 20 MHz is reachable *only* on SPIM00.

### The chip-select landscape (four mechanisms)
1. **Zephyr `cs-gpios` = software CS.** `spi_nrfx_spim.c` toggles a plain GPIO via
   `spi_context_cs_control()` around each transfer and leaves nrfx `.ss_pin` unused, so
   `PSEL.CSN` is never programmed. Correct, but CPU-bound and one-transfer-per-call →
   **does not scale.** (Effectively what the old `xfer()` did.)
2. **Silicon hardware CSN** (`PSEL.CSN` + `CSNPOL` + `IFTIMING.CSNDUR`). The peripheral
   pulses CSN per **transaction** (asserts at START, deasserts at END). Set **MAXCNT = 2
   bytes → one 16-bit word per transaction → CSN pulses per word in silicon** — exactly
   the Intan requirement. Gated by the nrfx feature `NRF_SPIM_HAS_HW_CSN`; **whether
   SPIM00 specifically carries it is UNCONFIRMED** (on nRF52 only SPIM3/4 had it).
3. **nrfx_spim direct.** Exposes `nrf_spim_csn_configure()`, `use_hw_ss`, and **array-list
   mode**. **Required**, because Zephyr's generic SPI API issues one transfer at a time
   and has no property to enable hardware CSN.
4. **EasyDMA array-list + SHORTS `END_START` / DPPI chaining.** DMA walks a list of
   per-word buffers; `END_START` (or a DPPI channel) re-arms the next transaction in
   hardware, CSN pulsing between each — **zero CPU per word.**

### Decision (fast now AND rewrite-proof)
Build acquisition on **nrfx_spim + hardware CSN on SPIM00**, driven by **EasyDMA
array-list transactions (MAXCNT = 2) chained via `END_START`/DPPI** — from the start,
**even for the ≥3-channel minimum.**
- *Why not the `cs-gpios` software path even for the minimum:* it's a dead end (8 MHz
  cap, CPU-toggled CS, one transfer per call). Nothing about it survives the jump to 32
  channels, so building on it is throwaway work.
- *Why this scales:* the same nrfx primitive goes from 1 word to a 32-channel list —
  scaling is a list-length + SCLK change, **not a rewrite.**
- *Concretely:* retarget **`spi22`/P3 → SPIM00/P2** (extra-high-drive); configure CSN in
  nrfx, **not** via devicetree `cs-gpios` (which would re-engage the software path — and
  on P2 may fail outright, since that port reportedly lacks GPIOTE on related nRF54L parts).

### The governing ceiling is the per-word restart cadence, NOT SCLK
The Intan mandates CS-high between every 16-bit word, so **each word is an irreducible
transaction — you cannot batch words into one long DMA transfer.** The only figure found
for per-word restart/turnaround is **~1 µs** (single DevZone thread, unverified) →
~1 M words/s → **right at the 960 k words/s requirement, essentially no margin.** This
cadence, not the 32 MHz SCLK, is what decides whether 32 ch × 30 kHz is reachable.

### Fallback ladder (if the primary path can't sustain 960 k words/s)
1. **PRIMARY:** SPIM00 @ ~20 MHz, nrfx, silicon CSN, array-list MAXCNT=2 chained via `END_START`/DPPI.
2. **If SPIM00 lacks HW-CSN:** keep SPIM00 @ 20 MHz, generate the per-word CS pulse with a
   **GPIOTE pin driven by DPPI off the SPIM END/START events** — still hardware-timed,
   zero CPU per word. (Requires checking P2 GPIOTE availability.)
3. **If restart cadence caps below 960 k words/s:** drop to **20–25 kS/s/ch** (640–800 k
   words/s) — no architecture change, only a sample-rate constant. (This is the design
   point already recommended in §1.)
4. **Last resort (real rewrite):** external SPI master (CPLD/FPGA) generating the
   CS-per-word framing, or a different host part.

### The one bench measurement that decides it
On SPIM00 with array-list + `END_START`/DPPI + hardware CSN engaged, scope the **sustained
per-word cadence** — CSN rising edge of one word to first SCLK edge of the next, over a
long run — and confirm CSN is actually toggling in silicon. This simultaneously proves
(a) SPIM00 has *usable* HW-CSN (the single most load-bearing unknown) and (b) the real
throughput ceiling. Under ~1.04 µs/word → 32-channel headroom; otherwise → rung 3.

### Devicetree's limited role
The overlay can bring SPIM00 up on its P2 pins, but the `nordic,nrf-spim` binding has **no
property to enable silicon CSN**, and adding `cs-gpios` forces the software-CS path back
on. So the overlay reserves the instance + pins only; CSN is configured in **nrfx C**
(`nrf_spim_csn_configure` + `CSNPOL` + `IFTIMING.CSNDUR`), deliberately not in devicetree.
Pin numbers, the `spi00` node label, the drive-mode token, and the max `clock-frequency`
the binding accepts must be checked against the SoC dtsi / pin map (unverified here).

---

## 4. Open questions (need verification, not assumption)

1. ~~What SCLK frequency does `spi22` sustain?~~ **ANSWERED (§3.5, 2026-09-01):** `spi22` is a standard **8 Mbps** instance and cannot do 32 ch × 30 kHz (~15 kHz/ch max). **SPIM00 (32 MHz, port P2) is required** for the scaling path. Remaining sub-question: the *achievable* per-word restart cadence on SPIM00 (the real ceiling) — bench-measure per §3.5.
2. Does the nRF54LM20B have native LVDS-capable I/O, or does LVDS require an external translator chip? → **Partially checked (2026-08-27):** the Nordic product page lists three packages (CSP98 3.67×3.85 mm / 98-ball / 0.35 mm pitch / 66 GPIO; CSP61 3.02×2.43 mm / 61-ball; QFN52 6×6 mm / 52-pin / 32 GPIO), 128 MHz Cortex-M33, 512 KB RAM, 2 MB flash — but it says **nothing about an LVDS I/O standard**. No confirmation of native LVDS support was found; the working assumption is therefore **an external LVDS↔CMOS translator chip would be needed** if LVDS is required. Still needs datasheet-level (not product-page) confirmation before deciding.
3. At the recommended 20–25 kS/s/ch design point, is CMOS signaling's noise penalty actually tolerable for spike detection, or does LVDS become necessary regardless of raw speed? (5 kS/s/ch CMOS-safe threshold from the Intan datasheet still applies even at the lower design point — 20–25 kS/s/ch is still 4–5× over it.)

## 5. Recommended sequencing

1. **Firmware first, at low channel count.** Get DMA-driven SPI acquisition working correctly (right data, right pipeline-offset handling) at a modest rate (e.g. 1 channel, current 1 MHz SCLK) before touching clock speed — isolate correctness from throughput.
2. **Push SCLK up on the bench**, measuring for bit errors, using `board-bring-up` as the probe — answers open question 1.
3. **Decide the CMOS-vs-LVDS question** based on measured noise at the target sample rate, not the datasheet's worst-case number alone — answers open questions 2–3.
4. **Scale channel count** only once single-channel acquisition is solid at the target rate with acceptable noise.

---

## Status / decision log

- **2026-09-17 — THE BENCH MEASUREMENT IS DONE (§3.5 answered).** SPIM00 @ 21.33 MHz + silicon HW CSN (CSNDUR 20) + END_START free-run, cadence counted in hardware (TIMER00←DPPI←SPIM.END): **757,741 words/s sustained (~1.32 µs/word), with data validity confirmed at full speed** (ROM reads "INTAN" at 21.33 MHz). → 32 ch = **23.7 kS/s/ch: inside the 20–25 kS/s design point (rung 3)**; 5-ch minimum has 5× headroom; 960 k (32×30k) not reachable. Bring-up gotchas found and fixed, in order: (1) shared ground missing; (2) DK board controller defaults P2.00–05 to the onboard mx25 flash — must disable "External memory" in Board Configurator to route to headers (also removes flash-opcode-aliasing hazard); (3) SPIM00 is bonded to dedicated pads only (SCK P2.01, SDO P2.02, SDI P2.04, CSN P2.05 — datasheet p.1222); (4) **IFTIMING.RXDELAY default (2 ticks = 15.6 ns) samples MISO one bit early** given the ~25–30 ns chip+DK-switch round trip — RXDELAY 4–7 read clean at both 4 and 21.33 MHz; operating point RXDELAY=5. Note: each RXDELAY tick lengthens the word by 7.8 ns (END waits for the delayed sample).

- **2026-08-27** — Document created. Captures the firmware/hardware split identified while drafting the "embedded development" help-ask for Dr. Moyer's advisor-search email. Design point set at 20–25 kS/s/ch (not the 30 kHz stretch case) pending the CMOS/LVDS decision.
- **2026-09-14** — **Biggest unknown RESOLVED from the MDK on disk** (`nrf54lm20b_application_peripherals.h`, NCS v3.3.1): `SPIM00_FEATURE_HARDWARE_CSN_PRESENT = 1` — SPIM00 **has silicon hardware CSN**; rung 1 of the ladder stands, no GPIOTE workaround needed. Also confirmed: SPIM00 core = 128 MHz with even prescaler 4–126 → **max legal SCLK under the Intan cap = 21.33 MHz (÷6)**; `IFTIMING.CSNDUR` is in 128 MHz cycles and, **with SHORTS.END_START, is exactly the inter-word CSN-high time** (types header) → CSNDUR 20 = 156 ns ≥ Intan's 154 ns; RXDELAY present (0–7, default 2) for the t_MISO margin; pins from the DK devicetree: SCK P2.01 / MOSI P2.02 / MISO P2.04 / CSN P2.05 (external-flash header, mx25 disabled). **Firmware written and compile-verified** (`firmware/theo`): nrfx_spim (API v4) + hardware CSN + END_START free-run, cadence counted in hardware by TIMER00 ← DPPIC00 ← SPIM00.END. Theoretical best: 750 ns + 156 ns ≈ **906 ns/word ≈ 1.10 M words/s** vs the 960 k target — margin exists only if the END→START restart adds ≈ nothing, which is what the flashed test measures. Bench: confirm CSN toggling per word on P2.05 with a scope.
- **2026-09-01** — Added §3.5: chip-select mechanism & SPIM-instance decision. Method: direct read of nRF54LM20B datasheet §11.19 (primary source) + an adversarially-verified research workflow (12/12 claims corroborated); the two converged. **Key results:** the old `spi22` (8 Mbps) cannot scale to 32 ch; **SPIM00 (32 MHz, port P2) is required**; the path forward is **nrfx_spim + silicon hardware CSN + EasyDMA array-list chained via `END_START`/DPPI**, adopted from the start (not `cs-gpios`, which is a non-scaling software-CS dead end). The real ceiling is the **per-word transaction restart cadence** (~1 µs unverified, ~no margin), not SCLK — one bench measurement (§3.5) decides it. Biggest unconfirmed fact: whether SPIM00 specifically carries the HW-CSN feature.

# Two-phase system architecture

Authoritative description of the system's two-phase structure. Supersedes the
framing in `system-architecture.md` (which predates the offline/online split).
This is **design Approach A (offline-supervised)**; Approach B (online-unsupervised,
single-phase) is the alternative under consideration — see `classification_options.md`
and the proposal's Design section.

---

## Overview

The system runs in **two phases under different constraints**, and the online phase
does not exist without the offline phase.

```
   OFFLINE PHASE (workstation, once)                 ONLINE PHASE (nRF54 SoC, real time)
   ─────────────────────────────────                ────────────────────────────────────
   wired reference recording                         acquire → detect → (timestamp) →
        │                                                   classify → transmit
        ▼                                                        ▲
   spike sorting (unsupervised clustering)                       │  consumes
        │                                                        │
        ▼                                             ┌──────────┴───────────┐
   train + quantize classifier  ───────────────────► │ model + unit library │
        │                                             │   (the ARTIFACT)     │
        ▼                                             └──────────────────────┘
   model + unit library artifact
```

**The artifact is the interface between the two phases.** Offline produces it; online
consumes it at the classify step. Nothing else crosses the boundary.

---

## Offline phase (workstation, runs once, no device constraints)

- **Input:** a wired, tethered, high-fidelity reference recording.
- **Steps:**
  1. **Spike sorting** — unsupervised clustering (e.g. Kilosort / MountainSort) of the
     reference recording into labeled units. Produces `(waveform, unit_id)` training pairs.
  2. **Train** a supervised classifier on those pairs.
  3. **Quantize** the trained model for integer, on-device inference.
- **Output (artifact):** a **unit library + quantized classifier model**, flashed onto
  the device alongside the firmware (e.g. as `model.h`).
- **Constraints:** none of the device's. Runs on a workstation with the *full* data set
  available in advance. Not power-, latency-, memory-, or bandwidth-bound.

---

## Online phase (nRF54 SoC, real time, device-constrained)

Consumes the offline artifact and runs the real-time pipeline. Subject to the power,
latency (bounded, non-closed-loop), memory, and BLE-bandwidth constraints that motivate
the thesis.

**The five functional operations** (proposal-level view):
`acquire → detect → record time → classify → transmit`.

**The firmware decomposition** (implementation view) — five functions plus one shared
data structure. Four functions are invariant plumbing; `classify` is the swappable seam
(see `design_considerations.md` for the contracts and the swap discipline).

```
[SPI/Intan acquire] → [ring buffer] → [detect + align] → [classify] → [packetize + BLE]
       │                   │                │                 │              │
    invariant          invariant        invariant        SWAPPABLE       invariant
```

- `acquire_sample(ch)` — one Intan SPI conversion → one 16-bit sample. Built on
  `intan_transceive_word(cmd)` → Zephyr's `spi_transceive()`. Touches only SPI; knows
  nothing of the ring buffer.
- ring buffer — samples land here; snippets are cut from here. Exists so `extract` can
  reach *backward* in time to samples that arrived before a spike was confirmed.
- `detect(sample)` — returns true at the instant a spike is confirmed. **The timestamp is
  captured here, at detection**, and carried through to `emit` — so "record the time"
  (functional op 3) is folded into the detect→emit flow, not a separate stage.
- `extract_snippet(snippet)` — copies the peak-aligned window out of the ring (Contract A:
  `int16 snippet[N]` in).
- `classify(snippet)` — inference against the offline model → `unit_id` (Contract B out).
  The one file that changes between classifier designs.
- `emit_event(unit_id, timestamp)` — packetize + `bt_gatt_notify` over BLE.

**Contracts (frozen interfaces):**
- **Contract A** — `int16 snippet[N]` into `classify`.
- **Contract B** — `uint8 unit_id` (+ timestamp) out of `classify`.

**File structure (one firmware image):**
- `main.c` — the invariant plumbing (SPI, ring, detect, BLE).
- `classify.{c,h}` — the swappable classifier; `classify.h` is the contract.
- `model.h` — the offline artifact (generated, not hand-written).

---

## Cross-cutting properties (span the whole online pipeline, not one stage)

- **No-loss / keep-up** — no detected spike (or its source sample) dropped under sustained
  load. A drop anywhere in the chain compromises the result identically.
- **Timestamp fidelity** — stamped at detection, on a stable clock, at sufficient
  resolution; spans detect and transmit.

---

## Design-approach context

This two-phase structure **is a design decision**, not a requirement — it is the axis
along which the two candidate designs differ:

- **Approach A (this document):** offline-supervised, two-phase. Higher accuracy; requires
  offline calibration/training per subject.
- **Approach B:** online-unsupervised, single-phase (on-device Osort clustering). No offline
  phase, self-contained; expected lower sorted-unit stability/accuracy.

The functional and technical *requirements* are design-agnostic and satisfied by both; only
the realization differs.

---

## Related documents

- `design_considerations.md` — the plumbing/contracts and the swap discipline (dialogue + decisions).
- `classification_options.md` — the classifier tiers (what runs in the `classify` seam).
- `classification_benchmark.md` — how online output is validated against Kilosort ground truth.
- `SPI_bringup_plan.md` — scaling acquisition (the `acquire` throughput/LVDS work) to 32 channels.

# Waveform Classification — Background

> Research context for the sine/square/triangle classifier rehearsal
> (`classification.py`) and the deferred on-chip spike-classification thesis
> goal. Compiled 2026-08-17 via a multi-source research pass (deep-research
> workflow + a targeted faculty-search agent), claims adversarially verified
> against primary sources.

## 1. The field: two camps, one real tension

General time-series / raw-waveform classification with ML splits into two
approaches that have been competing since ~2019:

- **End-to-end deep learning on raw signal** — CNNs (ResNet, and especially
  **InceptionTime**, a cascaded-Inception 1D-CNN) that learn features
  directly from raw time series, no hand engineering. The pitch: eliminate
  manual feature design entirely — the network learns whatever
  discriminative structure exists in the raw window.
- **Fast kernel/feature-transform methods** — **ROCKET** (10,000 random 1D
  convolutional kernels → 20,000 summary features, max value + proportion-of-
  positive-values per kernel → linear classifier) and its much faster
  reformulation **MiniRocket** (up to 75× faster, essentially the same
  accuracy). Not hand-engineered in the classical sense (kernels are random,
  not designed) but not end-to-end learned either — a genuine third category
  between raw deep learning and classic feature engineering.

**The honest empirical finding:** an independent benchmark ("Bake off redux,"
Middlehurst et al.) found the leading deep model (InceptionTime) merely
*competitive with*, not superior to, ROCKET/HIVE-COTE on the standard
UCR/UEA benchmark archives — partly because those archives are too small
(median ~217 training examples per dataset) for deep learning's usual
data-hungry advantage to show up. A comprehensive 2023/2024 survey (Foumani
et al., arXiv:2302.02515 / ACM Computing Surveys) maps the taxonomy: MLPs,
CNNs, RNNs, GNNs, attention/transformer models, self-supervised learning,
and augmentation/transfer learning.

**Transformers for time series get more skepticism than hype.** A
widely-cited paper (Zeng, Chen, Zhang, Xu, AAAI 2023, arXiv:2205.13504)
showed a trivial one-layer linear model (DLinear) beats contemporary
Transformer forecasters on most long-horizon benchmarks — a caution against
reaching for attention-heavy architectures by default.

**On embedded/MCU deployment** (directly relevant to the eventual nRF54
target): one paper found 1D-CNNs match or beat LSTMs on microcontroller-class
hardware — comparable or higher accuracy (~95% vs ~89%) while using ~35%
less RAM and ~25% less flash. This is a concrete data point for how to shrink
whatever architecture wins on the laptop before porting it.

## 2. The raw-vs-engineered-features debate, applied to this project

The literature validates the plan already in motion for `classification.py`:
train on the **raw time-domain window** (Option A), not hand-picked
scalar features like crest factor (Option B). That's where the field's
energy and best results concentrate, and it's the version that actually
rehearses what a real spike classifier will have to do — learn shape from
raw samples, including tolerating unknown phase.

If a simple raw-window classifier (e.g. logistic regression) underperforms,
the well-precedented next step **before** reaching for a bigger neural net is
a **ROCKET-style random-kernel transform** — cheap, robust, and a legitimate
middle ground supported by strong primary-source results, not a hand-wavy
guess.

## 3. What actually counts as "a feature" here

The methods above differ not just in *architecture* but in **where the
boundary between "feature" and "model" sits** — this is a sliding scale, not
a binary:

| | What counts as "the feature"? | Who decided it? |
|---|---|---|
| **Hand-engineered** (e.g. crest factor = peak ÷ RMS) | One computed summary number, from a formula chosen using domain knowledge of what differs between shapes | A human |
| **ROCKET / MiniRocket** | Two numbers *per random kernel* — max response and % of the window where it fired — from thousands of random small pattern-detectors | Nobody picks the patterns (random); the *aggregation rule* (max, %-positive) is fixed by the method [^rocket] |
| **Raw window, end-to-end** (our plan for `classification.py`) | Literally the raw amplitude value at every sample point in the window (e.g. 80–120 numbers), z-scored | Nobody — the classifier decides what to do with them during training |

For the raw-window approach specifically, there is **no separate feature-
extraction step at all** — the thing fed to the model *is* the signal, and
"eliminating manual feature engineering" is exactly the framing the survey
literature uses for this end-to-end approach [^eliminate1] [^eliminate2].

**What a raw-window classifier plausibly keys on, mechanistically:** a
logistic regression over raw samples learns one weight per sample position —
it discovers *which* sample points, and combinations of them, separate the
classes, purely from labeled data. A small 1D-CNN is more structured: each
convolutional filter has a small receptive field (a handful of adjacent
samples) and slides across the window, and filters of this kind are known to
learn **discriminative local subsequence patterns — functionally similar to
"shapelets"** in the time-series literature, though a caveat is worth
stating precisely: one study found that *unregularized* CNN filters often
learn patterns that don't correspond to any real, human-recognizable piece
of an actual input series, even when they're discriminative [^shapelet].
That's a **softer claim than "filters become edge detectors,"** which is
well-supported for *image* CNNs [^zeiler] but which I could not find a
verified time-series-specific source for — flagging that so the analogy
doesn't get overstated.

[^rocket]: Dempster, Petitjean, Webb, "ROCKET: Exceptionally fast and accurate time series classification using random convolutional kernels," arXiv:1910.13051. Verified quotes: "For 10,000 kernels (the default), Rocket produces 20,000 features" and each kernel contributes "the maximum value... [and] the proportion of positive values."
[^eliminate1]: Foumani, Miller, Tan, Webb, Forestier, Salehi, "Deep Learning for Time Series Classification and Extrinsic Regression: A Current Survey," arXiv:2302.02515 / ACM Computing Surveys 56(9). Verified quote: "Deep learning can autonomously learn informative features from raw data, eliminating the need for manual feature engineering."
[^eliminate2]: Ismail Fawaz, Forestier, Weber, Idoumghar, Muller, "Deep learning for time series classification: a review," Data Mining and Knowledge Discovery 33 (2019), arXiv:1809.04356.
[^shapelet]: Wang, Yan, Oates, "Learning Interpretable Shapelets for Time Series Classification through Adversarial Regularization," arXiv:1906.00917. Finding: standard (unregularized) 1D-CNN filters do learn discriminative local sliding-window patterns functionally like shapelets, but these are "often different from actual pieces of a real series" without added regularization — i.e. they act as local pattern-matchers, not necessarily human-recognizable shapes.
[^zeiler]: Zeiler & Fergus, "Visualizing and Understanding Convolutional Networks," ECCV 2014, arXiv:1311.2901. Verified quote (image-domain CNNs, not time series): "Layer 2 responds to corners and other edge/color conjunctions," with deeper layers showing "compositionality, increasing invariance and class discrimination as we ascend the layers." Note: this paper grounds the *image*-CNN edge-detector intuition only — I could not verify an equivalent filter-level claim specifically for 1D time-series CNNs; see [^shapelet] for the closest, softer, time-series-specific finding.

## 4. Key methods, concretely

| Method | What it does | Result |
|---|---|---|
| **InceptionTime** | Cascaded-Inception 1D-CNN, end-to-end on raw signal | Accuracy on par with HIVE-COTE, ~100× faster to train |
| **ROCKET** | 10,000 random conv kernels → 20,000 features → linear classifier | Competitive with (statistically indistinguishable from) HIVE-COTE, TS-CHIEF, InceptionTime |
| **MiniRocket** | Near-deterministic reformulation of ROCKET | Up to 75× faster than ROCKET, same accuracy |
| **1D-CNN on MCU** | Same CNN family, sized down | ~95% acc vs ~89% for LSTM, using less RAM/flash — the embedded-deployment analogue |

## 5. Caveats on this research pass

- **Time-sensitivity:** the empirical leaderboard (ROCKET vs. InceptionTime
  vs. newer transformer variants) moves fast. The comparisons above are
  accurate as of their cited 2019–2024 papers; treat exact rankings as
  historically situated, not "current SOTA."
- **Source concentration:** most claims trace back to a small cluster of
  related papers (Foumani et al. survey, Fawaz et al. 2019 review, the
  Dempster/Schmidt/Webb ROCKET/MiniRocket papers) — strong within-paper
  verification, less independent triangulation across unrelated groups.
- **Not covered in depth:** pure transformer architectures for time series
  (PatchTST, TimesNet) beyond the taxonomy level, self-supervised
  pretraining, and MCU-specific quantization/latency benchmarks sized for
  a window as short as this project's — these are open threads if this
  ever needs a deeper second pass.

## 6. Harvard / MIT faculty — general time-series ML (not neuro/spike-sorting-specific)

Screened explicitly to exclude people whose center of gravity is
neuroscience, spike sorting, or clinical applications — that's a deliberate
exclusion, not an oversight, since the question was about the general ML
subfield.

1. **Devavrat Shah** — MIT EECS (Andrew & Erna Viterbi Professor), directs the
   MIT Statistics and Data Science Center; LIDS/IDSS. Matrix-estimation /
   nearest-neighbor theory for general time-series prediction (e.g. "Time
   Series Analysis via Matrix Estimation," tspDB). Strongest, most direct
   match. — https://devavrat.mit.edu/
2. **Munther A. Dahleh** — MIT EECS (William A. Coolidge Professor), founding
   director of MIT IDSS; LIDS. Learning linear/nonlinear dynamical systems
   and mixtures of dynamical systems from trajectory data — methodologically
   close to learning structure from raw signal windows. —
   https://dahleh.lids.mit.edu/
3. **Yoon Kim** — MIT EECS/CSAIL, MIT-IBM Watson AI Lab. General
   sequence-model architectures (state-space models, efficient/linear
   attention) — domain-general methods, mostly demonstrated on text so a
   moderate match on "waveform" specifically, strong on "sequence models." —
   https://www.eecs.mit.edu/people/yoon-kim/
4. **Pavlos Protopapas** — Harvard IACS, Scientific Program Director /
   Lecturer (note: not tenure-track professor rank). Deep learning for
   time-series classification directly (astronomical time series, GAN-based
   time-series augmentation), non-neuro. Teaches Harvard's CS109 — the most
   realistically approachable option for an undergraduate. —
   https://iacs.seas.harvard.edu/people/pavlos-protopapas

**Considered and excluded** (verified real but off-target for this specific
ask): Sasha Rakhlin (MIT, theory of online/sequential prediction — abstract,
not waveform methods); David Alvarez-Melis (Harvard SEAS — optimal
transport/data-centric ML, not time series); Sham Kakade (Harvard — current
focus is LLM/foundation-model theory); Kalyan Veeramachaneni (MIT LIDS —
excellent time-series-anomaly-detection work, but Principal Research
Scientist, not faculty); Demba Ba, Cengiz Pehlevan, Finale Doshi-Velez
(Harvard SEAS/Kempner — real time-series people, but center of gravity is
neuro/spike-sorting/clinical, the exact thing this search was scoped to
exclude).

**Bottom line:** MIT has 2–3 clean matches (Shah, Dahleh, Kim); Harvard's
best fit is IACS's Protopapas, with the title caveat. No Harvard
tenure-track professor was found whose primary research centers on general
time-series/waveform ML rather than neuroscience or a clinical application —
worth a second pass into Harvard Applied Math or Statistics specifically if
this becomes a priority.

# Sampling frequency & regularity — the plan (v2)

Two goals, one root fix:

- **A. Rate:** 30 kS/s per channel, toward 32 channels (Dr. Oh's target).
- **B. Regularity:** the time between samples, with statistics — measured, not
  assumed.

**v2 change:** the bench found the current sampler is *bursty*, and the cure —
hardware-timed sampling — becomes Step 0 that everything else builds on.
Tags: **[bench]** = you at the hardware, **[AI]** = code I write.

---

## Where we stand (measured)

| Fact | Value | How we know |
|---|---|---|
| Single-bus word ceiling (SPIM00 + HW CSN, pure silicon) | **757,741 words/s** (1.32 µs/word) | hardware-counted free-run; data-validated (INTAN clean at 21.33 MHz, RXDELAY 5) |
| → 32 ch on one bus | **23.7 kS/s/ch** | 757,741 / 32 |
| → channels at full 30 kS/s on one bus | **25 ch** | 757,741 / 30,000 |
| Streaming demo (1 ch → Mac BLE) | 20 kS/s, 5 min, **0 lost** of 50,464 pkts | `run1_report.txt` |
| Sampling regularity, software-paced (BEFORE) | σ = 23.67 µs, min 6.75 / max 325.8 µs, **0.7%** within ±10% | 12,800 scope-measured CSN intervals, `measurements/before_sw_paced_20k/` |
| **Sampling regularity, hardware-timed (AFTER, 2026-09-24)** | **σ = 0.38 µs, min 19.0(1 glitch) / max 53.4(1 wrap) µs, 100.0% within ±10%** — 62× better | 12,843 scope-measured CSN intervals, `measurements/after_hw_timed_20k/` |
| macOS BLE ceiling | ~26–28 kS/s (15 ms interval, non-negotiable) | measured |
| nRF↔nRF BLE ceiling | ~1.05 Mbps (≈65 kS/s of 16-bit) | ble-rate tests |

**Why the bursts:** the sampler is a software thread pacing itself against
deadlines. The BLE controller runs at interrupt priority and stalls it; on
waking, the thread finds several deadlines expired and fires those CONVERTs
back-to-back (catch-up burst). Average rate is preserved exactly — which is
why the 5-minute log (20,000.3 S/s, 0 lost) never saw it. Only the scope
could. No receiver-side statistic can detect or refute this; the samples
carry values and order, not times.

**Consequence:** regularity is not a measurement problem to bolt on — it is a
design defect to remove. Hence Step 0.

---

## Step 0 — hardware-timed sampling engine — **DONE (2026-09-24)**

Implemented, debugged (DMA pointer rewind requires pausing the timer; wrap
gates on the hardware write position; DMA byte order is wire-order, swap on
read), data-validated (clean 997 Hz sine, 20 dots/period, 0 lost packets),
and measured: σ = 0.38 µs. Residuals worth knowing: mean read 49.83 µs
(+0.34%) — the 128 MHz HSFLL timer clock, not crystal-exact; one ~53 µs
interval per 1.64 s (the wrap's timer pause); one glitch edge in 12,843.
Original design notes below.

Take the CPU out of the timing path: a hardware timer fires each SPI
transaction in silicon. The radio can stall a thread or an interrupt; it
cannot stall a DPPI task trigger.

**Design (verified against the SDK/datasheet):**
- **TIMER00** (same fast domain as SPIM00 — DPPIC00 path already proven in the
  free-run test) in timer mode, `COMPARE0` + compare-clear short → periodic.
- TIMER00 `PUBLISH_COMPARE[0]` → DPPI channel → SPIM00 `SUBSCRIBE_START`:
  one 16-bit CONVERT per timer tick, hardware CSN pulsing per transaction as
  already validated.
- **RX side is where the risk moves — handle it:** an END-interrupt copy can
  itself be radio-delayed. Use **RX array-list DMA** (hardware auto-advances
  the receive pointer per transaction) into a large region, so the CPU drains
  lazily in chunks and hundreds of µs of blocking costs nothing. TX stays a
  fixed 2-byte CONVERT buffer (no post-increment).
- Software's only jobs: drain region → ring → BLE packets. Fully off the
  timing-critical path.

**Steps:**
1. **[AI]** Rewrite the acquisition core of `firmware/theo/src/main.c` as
   above (timer-fired transactions, array-list RX, chunked drain). Keep BLE
   path unchanged. Build.
2. **[bench]** Re-validate **data** in the new mode: the RXDELAY=5 fix was
   proven through the driver's transfer path, and the timer-fired path
   bypasses it per-transfer — so first run must show a clean 1 kHz sine (and
   an INTAN check), not assume it.
3. **[bench]** The before/after money shot: scope on **P2.05**, falling-edge
   trigger, **infinite persistence**. Current build = smeared clusters (take
   this photo FIRST, before reflashing). New build = knife-edge comb at
   exactly the sample period. That pair of photos is the regularity
   deliverable for Dr. Oh — better than any stats table.

**Honesty notes for the writeup:** 20 kS/s divides the 128 MHz timer base
exactly (6400 ticks); 30 kS/s does not (4266.67 → 29.998 or 30.005 kS/s,
~±70 ppm — below crystal tolerance, but say so). Regularity in this mode is a
property of the crystal + timer, verified externally by the scope.

---

## A. Rate

### A1 — 30 kS/s single-channel over BLE (the "30 dots per period" shot)
macOS caps delivery at ~26–28 kS/s, so this runs through the already-built
nRF relay (`firmware/theo-central`: connects at 7.5 ms, forwards to VCOM1
serial @ 921600).
1. **[bench]** Flash second DK with `theo-central` (pick its J-Link serial in
   the dialog). Kill any Mac-side `stream_plot.py` so the relay wins the
   connection.
2. **[AI]** Set 30 kS/s in the (new, Step-0) firmware + `stream_plot.py`;
   rebuild.
3. **[bench]** Reflash peripheral; run
   `python stream_plot.py --serial /dev/tty.usbmodemXXXX` (relay's VCOM1);
   log ≥5 min; `analyze.py`.
   **Done when:** 30.00 samples/period on the 1 kHz sine, 0 lost packets,
   report + scope persistence shot at 33.3 µs pitch saved.

### A2 — 32-channel round-robin at the measured ceiling
Same Step-0 engine, TX becomes a command list.
1. **[AI]** TX array-list walking `CONVERT(0..31)`; handle the Intan's
   two-command pipeline lag across the rotation (result i ← command i−2);
   packets carry interleaved frames; plot streams a selectable channel.
2. **[bench]** 1 kHz sine on in0: ch0 shows ~23.4 dots/period (timer set near
   the 757 k words/s ceiling / 32), all channels counted, zero drops.
   **Done when:** sustained ≥ ~750 k words/s with valid ch0 data — the
   thesis's T1+T2 evidence at the design point.

### A3 — closing the gap to 30 × 32 (architecture, not firmware)
960 k words/s cannot fit one SPI bus of this SoC (silicon floor above).
Options for the Dr. Oh discussion, in order of realism:
1. **Dual front-end, dual bus on the custom PCB:** 2 × RHD2132; SPIM00 carries
   ≤25 ch @ 30 k, a standard 8 Mbps SPIM carries the remaining ≥7 (its ceiling
   ≈ 395 k words/s). Decision must land **before** PCB layout.
2. **Accept the design point** (23.7 kS/s/ch × 32) — already inside the
   proposal's 20–25 k commitment; spike band (300 Hz–6 kHz) fully captured.
3. Rejected for the record: 32 MHz SCLK (violates Intan's 24 MHz cap), odd
   prescalers (silicon), shorter CSN-high (at Intan minimum), batching words
   under one CS (forbidden by RHD2000 protocol).

---

## B. Regularity (post-Step-0 this is verification, not rescue)

- **Primary instrument — scope on CSN (P2.05):** falling-edge trigger;
  period readout must sit at the sample period; infinite persistence shows
  jitter as smear width. Capture at 20 k and 30 k. (This scope's 2000-point
  record can't accumulate deep statistics — the persistence photo + stable
  period readout is the deliverable; quantitative depth comes from the
  option below if wanted.)
- **Optional in-band timestamps, hardware-measured:** GPIOTE event on the CSN
  edge → DPPI → TIMER capture = per-sample timestamps taken by silicon.
  Stream a burst; compute mean/σ/min/max of Δt in Python — dots at *measured*
  positions, Dr. Oh's request verbatim. Build only if the scope evidence
  isn't deemed sufficient.
- Removed as obsolete: software "slip statistics" — in hardware-timed mode
  there is no software schedule left to slip.

---

## Order

1. **[bench]** BEFORE photo: persistence shot of today's bursty CSN (current
   build still flashed — do this first, it's the baseline evidence).
2. **Step 0** build → data re-validation → AFTER photo at 20 k.
3. **A1** relay + 30 k + logged run + scope shot at 33.3 µs.
4. **A2** 32-channel round-robin at the ceiling.
5. **A3** dual-bus decision with Dr. Oh — before PCB layout.

# Toward 30 kS/s with a smooth sine — parked state & next steps

Parked on 2026-09-24, mid-bench, to pivot to the FB128 signal. Everything
below is ready to resume without re-derivation.

---

## >>> IMMEDIATE NEXT STEP (do this first, nothing else) <<<
## Ground-truth the FB128 output by scoping it as well as possible

Context: with the FB128 in TONE 1000 Hz mode (sine, ±70 uV, actually ~763 Hz
per TDT's own docs), our chain received the tone — the plot's FFT read
760.0 Hz, TDT's documented quirk frequency, so timing/order/frequency are
validated end-to-end. But the tone is buried in ~±50–100 uV of scatter.
Established by logic, not assumption: the conversion math CANNOT cause
scatter (it is deterministic — same code in, same value out). The scatter is
either (a) real voltage at the Intan input (EMI pickup on the long
adapter-board + jumper chain) or (b) marginal SPI read bit-errors at
21.33 MHz (parked item 1 below). The FB128 signal is 35x smaller than the FG
sine was — the same absolute bench noise that was invisible at 5 mVpp now
rivals the signal. This is the real neural amplitude regime.

The session goal: measure what the FB128 ACTUALLY outputs, independently of
our chain, and localize where the signal gets dirty. All bench, no code:

1. **FB128 → TONE 30 Hz mode** (sine, ±700 uV — 10x bigger, scopeable;
   the ±70 uV tone is below the scope's own noise floor, which is why the
   earlier direct-scope attempt showed only "some periodic waveform").
2. **Scope + averaging at the SOURCE:** probe directly at the FB128 output
   pin (any channel — all carry the same tone), ground clip to the common
   ground. Scope: Acquire → **Average, 64 or 128 sweeps** — averaging a
   periodic signal crushes uncorrelated noise ~sqrt(N). Record amplitude,
   frequency, shape. This is the ground truth of the box itself.
3. **Same averaged measurement at the DESTINATION:** probe at the Intan
   input pin (in0), i.e. after the adapter boards and jumper chain. The
   difference between (2) and (3) IS the cabling's contribution, isolated.
4. **Then look at our own plot of the same TONE 30 Hz** (no code changes:
   the 60-sample window shows a smooth slow arc, ~667 samples/period; the
   FFT title should read ~30 Hz). At ±700 uV the tone should stand well
   clear of the noise.
5. Physical fixes to try while there: shorten the analog path, twist the
   signal wire with its ground return, route away from the DK/antenna/P2
   SCLK area.
6. **Free noise-floor measurement:** disconnect FB128, short in0 to ground,
   watch the plot for a minute — the residual scatter is the bench noise
   floor, quantified with zero code.

When the code freeze lifts, the two quantitative finishers:
- Add FFT **magnitude** readout at the tone peak to stream_plot.py → checks
  the 0.195 uV/LSB conversion against TDT's ±70/±700 uV spec (the only
  as-yet-unvalidated quantity is absolute amplitude).
- The 8 MHz SCLK build (parked item 1) → kills or convicts hypothesis (b).

Note on "transmit the ground truth digitized": there is no better digitizer
in the room — the scope resolves ~100 uV, the Intan resolves 0.195 uV. Our
chain IS the precision instrument; validation at this amplitude = agreement
between scope-averaged source measurement, TDT's published spec, and our
chain's FFT amplitude.

---

## Where we stand (all verified today)

- **Hardware-timed acquisition engine works**: TIMER00 (128 MHz/6400) → DPPI
  ch 7 → SPIM00 START; RX ArrayList DMA into an 80 KB region; timer-paused
  pointer rewind every 32,768 samples; byte-swap on drain (DMA stores wire
  order). Stable for minutes: no overruns, no faults, wraps metronomic
  (3.66/6 s as predicted), 0 lost packets.
- **Regularity measured (the deliverable):** before σ = 23.67 µs (0.7% within
  ±10%) → after **σ = 0.38 µs (100.0% within ±10%)**, 62× improvement, over
  ~12.8 k scope-measured CSN intervals each. Artifacts:
  `firmware/theo/measurements/before_sw_paced_20k/` and `after_hw_timed_20k/`.
- Clean 997 Hz sine at 20 dots/period over BLE to the Mac at 20 kS/s.

## Parked item 1 — the trough zigzag (do FIRST when resuming)

Symptom: adjacent-sample zigzag of ±400–500 µV near sine troughs (e.g.
−250/−800/−280/−700), far above analog noise, not explainable by the 20.06
samples/period phase precession (monotonic sine segments can't zigzag).

Suspicion: **marginal MISO bit errors at 21.33 MHz on dynamic data** —
±400/±800 µV ≈ single flips of bit 11/12 (2048/4096 codes × 0.195 µV). The
RXDELAY=5 choice was validated on static ROM bytes only; real ADC words
toggle many bits, electrically harder.

Experiment (one variable): drop SCLK 21.33 MHz → **8 MHz** at 20 kS/s
(single-channel needs only ~30 k words/s; 21.33 MHz is for the future 32-ch
case). If zigzag vanishes → confirmed; note that the 32-channel build must
revalidate RXDELAY against dynamic data. Optional tooling: add a
sample-to-sample delta histogram to `analyze.py` (bit errors show as discrete
±2^n spikes; analog noise is Gaussian).

## Parked item 2 — 30 kS/s single-channel (plan A1, everything prebuilt)

Sampling side is trivial (engine ceiling 757 k words/s; 30 k uses 4%):
`RATE_HZ 20000 → 30000` in `firmware/theo/src/main.c` and `RATE` in
`stream_plot.py` (CC = 4267 → 29.998 kS/s, ±70 ppm rounding — note in
writeup). The blocker is delivery: 480 kbps > macOS's ~26–28 kS/s ceiling
(15 ms interval). Path: **second DK flashed with `firmware/theo-central`**
(built; connects at 7.5 ms, relays to VCOM1 serial @ 921600), then
`python stream_plot.py --serial /dev/tty.usbmodemXXXX`. Steps:
1. Fix zigzag first (item 1) so 30 k inherits clean data.
2. Flash second DK with theo-central (pick its J-Link serial in the dialog);
   kill Mac-side stream_plot so the relay wins the connection.
3. Flip both rate constants, rebuild, reflash peripheral.
4. Verify: relay console `[relay] ~250 pkts/s ... ble_drops 0`; plot shows
   **30.0 dots/period**; log 5 min (`--log`), run `analyze.py`.
5. Scope after-capture at 33.3 µs nominal (same procedure, 5M pts) →
   `analyze_csn_csv.py <csv> 30000` → archive as
   `measurements/after_hw_timed_30k/`.

## Parked item 3 — small notes for the writeup

- Mean interval read 49.83 µs (+0.34%): the 128 MHz HSFLL timer clock is not
  crystal-exact and wanders slightly (also the ±1 µs band thickness). Fine
  for spike detection; state it. Crystal-locked timer source is the knob if
  exactness ever matters.
- The single ~53.4 µs outlier per capture = the wrap's timer pause (once per
  1.64 s, by design). Put it in the figure caption, don't hide it.
- Raw scope CSVs (~96 MB each) still on the USB stick only — archive
  somewhere off-repo if reproducibility matters.
- 32-channel round-robin (plan A2) builds on this same engine: TX becomes a
  command list, plus the two-command pipeline lag across channels, plus
  dynamic-data RXDELAY revalidation at 21.33 MHz (see item 1).
