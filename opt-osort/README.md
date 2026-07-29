# opt-OSort feasibility profiling

**Question:** is real-time, unsupervised spike *sorting* (not just classification
against fixed templates) feasible on the nRF54 — so that we can track units as they
drift instead of betting last session's sort still holds?

**Reference:** Wu et al. 2023, *J. Neural Eng.* **20** 066015 — "An unsupervised
real-time spike sorting system based on optimized OSort" (opt-OSort). It replaces
OSort's unbounded transient clusters with a **fixed number of cluster slots** and
swaps Euclidean distance for the **correlation coefficient (CC)** — solving the two
things that made textbook OSort infeasible on an MCU (memory + drift). Their FPGA
hits **0.68 µs/spike** with 4 slots; here we measure what the *same algorithm in C*
costs, to map it onto the nRF54's cycle/RAM budget.

## What this is (and isn't)

- **C, not Python** — the profiled artifact is the code that would eventually run on
  the MCU, so we measure the real thing. Python is used *only* for one-time data prep.
- **Sorting-only** — we feed pre-detected spike snippets, exactly as the paper does
  ("we assume the spikes have been detected"). Detection is cheap and already exists
  in the pipeline.
- **Single channel** — matches opt-OSort's single-channel configuration (4–6 slots).
  Multi-channel/shank is a later extension.
- **Phase 1 = cost** (ops/spike + memory → % CPU / % RAM). Phase 2 = accuracy
  (score the C clusters against the 73 ground-truth neurons). This is Phase 1.

## Run

```
source ../venv/bin/activate
python prep.py            # extract 1 channel of real data -> snippets.bin
make                      # build the C profiler
./opt_osort snippets.bin  # sort + report cost
```

## Pieces

| File | Role |
|------|------|
| `prep.py` | one-time: pick a channel from `raw-data/.../intan_combined.npy`, causal bandpass (300–3000 Hz @ 10 kHz), threshold-detect, cut 40-sample snippets → `snippets.bin` |
| `opt_osort.c` | the profiled artifact: opt-OSort (4 slots, CC criterion, 2 loop-checks), instrumented for float ops/spike + fixed memory |
| `snippets.bin` | generated: `int32 n, int32 k, then n×k float32` (the "stream") |
| `labels.txt` | generated: per-spike cluster id, for Phase-2 accuracy scoring |

## Reference: `osort_ref.py` — faithful port of REAL OSort (unvalidated)

Our `opt_osort.c` was reimplemented from the opt-OSort *paper's flowchart* — we have
no way to know it matches what the authors actually built. opt-OSort itself has **no
public code**. So we went to the base algorithm it's built on: **OSort**, whose source
IS public.

- Source: **official OSort v4.1**, Ueli Rutishauser (`urut.ch/downloads/osort/osort-v4.1-code.zip`).
  (A GitHub mirror `alexwickstrom/OSort` exists but is NOT authoritative — use the official.)
- `osort_ref.py` ports `sortSpikesOnline.m` (thresholdMethod 1) block-for-block, with
  every deviation from the MATLAB documented in the file header.
- **Status: UNVALIDATED.** It runs and reproduces OSort's signature behaviour (many
  transient clusters + a dominant cluster + noise), but that's a smoke test. Next step:
  validate on a ground-truth benchmark (synthetic 3-neuron data, or OSort's own
  simulated set) and confirm it recovers the units before trusting it or comparing
  opt-OSort against it.
- Real OSort details our C *missed* (found by reading the source): noise-derived
  threshold `std²·n·1.2` (1.2 = burst factor), squared-Euclidean on optionally-whitened
  spikes, edge-zeroed samples, recursive merging, periodic pruning.

**Cost result — plain OSort on the nRF54 (from `osort_ref.py`, ch56 real data):**

| | real OSort | opt-OSort |
|---|---|---|
| peak live clusters | **855** | 4 (fixed) |
| distances/spike | 531 | 4 |
| est. cost | ~498 µs/spike | ~8 µs/spike |
| memory, 64 ch | **8.3 MB** | 88 KB |
| fits 512 KB RAM? | **NO (16× over)** | yes |

**Plain OSort does not fit the nRF54** — unbounded transient clusters blow both RAM
(~16×) and compute (~60×). opt-OSort's fixed-slot design is the enabler. Caveats: the
855 count is inflated by our junk detector, but the paper measured 40–1192 transient
clusters on *clean* data, so the unbounded-memory conclusion is robust; and this is a
**cost** result — `osort_ref.py` sorting *quality* is still unvalidated.

## Cost model & honesty notes

- We count **float ops only** (mul/add/sqrt/div). Integer/compare ops are ignored —
  negligible and cheap on the M33.
- MCU cycle estimate assumes **~128 MHz Cortex-M33 + FPU**, VMUL/VADD ≈ 1 cycle,
  VSQRT/VDIV ≈ 14 cycles. These are standard M33 figures, not measured on our part.
- Laptop C timing is **not** MCU timing (x86 is far faster) — we use **op counts**,
  which are portable, and map them through the cycle model. True MCU timing comes
  later by flashing the same C (as we did for the pipeline's 5.3× real-time number).

## Results

**Phase 1 (cost), first pass — channel 56, 7293 spikes over 300 s (24.3 Hz):**

| Metric | Measured | Verdict |
|--------|----------|---------|
| ops/spike | 648 float ops (249 mul, 370 add, 2 sqrt, 28 div) | — |
| est. cost | ~1033 cycles → **~8 µs/spike** @ 128 MHz | feasible |
| memory | 1408 B/ch → **88 KB for 64 ch** (~17% of 512 KB) | fits easily |
| CPU load | **~1–5%** at 1k–6k spikes/s aggregate | feasible |

- **Cost is not a blocker** — online sorting fits the nRF54 with margin. The measured
  8 µs/spike is ~12× the paper's FPGA (0.68 µs), the expected software-vs-hardware gap.
- **Headroom:** the center-update uses K divides (~380 of 1033 cycles); one reciprocal
  + K muls ~halves it → ~4 µs/spike.
- **⚠ Quality unvalidated:** 3195/7293 spikes (44%) were **discarded** at default
  params. Cost numbers are valid regardless, but sort *quality* is poor here — Phase 2
  (accuracy vs. the 73 ground-truth neurons + parameter tuning) is required before
  claiming it sorts *well*, not just *cheaply*.

**Phase 2 (quality), diagnostic — `diagnose.py`:**

Cross-referenced the ch56 detections against the 73 ground-truth neurons *by time*
(no channel map needed — both are 10 kHz indices into `intan_combined`):

- **Only 31% (2242/7293) of our detections match any real sorted neuron.** The other
  **69% is junk** — noise/artifact/hash the offline sorter rejected but our crude
  4.5×MAD threshold detector grabbed.
- ch56 is essentially a **one-unit channel**: neuron_54 dominates (1826 detections);
  the other 4 "contributors" are 22–199-spike leakage from neighbours.

**Reinterpretation of the 44% discard:** it was **not** opt-OSort failing — it was
opt-OSort *correctly rejecting the junk* we fed it (the CC criterion working as
intended). It's **not structural** (nowhere near >4 units), and **not really an
opt-OSort parameter problem**. The weak link is **upstream detection quality**. This
is itself a thesis-relevant lever: offline curation vs. a crude on-chip threshold.

→ To fairly test the *sorter* (not the detector), Phase 2 next feeds opt-OSort
**real spikes at ground-truth times** and scores its clusters against true labels.

**Phase 2 (quality), ground-truth-fed sorter test — `prep_gt.py` + `score.py`:**

Fed opt-OSort real spikes at the offline sorter's spike times (units peaking on ch56
per `templates_average.npy`; row N ↔ neuron_N verified), scored via Hungarian
cluster→unit assignment (discards = errors).

- **The channel is effectively single-unit** — neuron_54 has 22,871 spikes; the other
  two that "peak" on ch56 (neuron_53: 113, neuron_20: 27) are near-empty. So this is a
  *fragmentation* test, not a *separation* test.
- **opt-OSort over-splits neuron_54** into multiple clusters. `rho_thr` sweep
  (discards / accuracy): **0.70 → 4066 / 31.5%**, **0.60 → 1737 / 45.0%**,
  **0.50 → 724 / 39.4%** (0.5 starts over-merging). Best is ~45% — poor.
- **Root cause (decisive diagnostic):** neuron_54's within-unit CC to its *own* mean
  template has **median ~0.80**, only **75% above 0.7**. So a quarter of the unit's own
  spikes fail the 0.7 threshold and fragment. That low within-unit CC is partly real
  variability, partly our **crude bandpass + single-sample trough alignment**.

**Honest verdict: cost is feasible (proven); sort quality is UNRESOLVED on this data.**
We cannot claim opt-OSort sorts well or badly here, because (a) no genuinely
multi-unit, well-populated test channel exists in this session, (b) snippet quality
(within-unit CC ~0.8) caps separability, and (c) our opt-OSort may not fully replicate
the paper's transient-cluster convergence.

**For a real Phase-2 verdict (future work):** a channel with ≥3 well-populated,
separable units; better preprocessing (sub-sample alignment, maybe whitening) to lift
within-unit CC toward the paper's regime; and validating the C against opt-OSort's
reference behaviour. The paper's own ~90%+ agreement says the algorithm *can* do it —
our first pass just doesn't reproduce it yet.
