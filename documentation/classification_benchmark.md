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
