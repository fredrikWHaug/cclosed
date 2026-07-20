# Cross-Day Generalization

> **Summary.** Does a spike classifier trained on one recording day still work
> the next day, or does representational drift break it? A conservative host-side
> baseline (logistic regression, peak-channel waveform) shows **no drift cost**
> across two consecutive days — but the result is a deliberate *floor*, and this
> document is careful about what it does and does not prove.

Related: [on-chip-classifiers.md](on-chip-classifiers.md) ·
[system-architecture.md](system-architecture.md)

## Why it matters

For a chronic implant, you train the on-chip classifier once and the animal keeps
living. If neural representations drift, a day-1 classifier degrades over time.
Measuring that degradation is the practical question behind on-chip sorting —
and the natural next step after the within-day
[on-chip classifier benchmark](on-chip-classifiers.md).

## Data

Two consecutive MA1 sessions (same mouse, same probe), sorted with the standard
pipeline:

| Session | Date | Units | Spikes |
|---------|------|------:|-------:|
| day 1 | `260413_131912` | 65 | 186,765 |
| day 2 | `260414_141929` | 73 | 78,699 |

`MA1_match_dict_final.json` tracks neuron identity across sessions. Its schema is
`tracked_neuron → match_group → session_position → local_unit(s)`; our two days
are group `"0"`, positions 2 and 3.

**Four neurons are tracked across both days** (IDs 39, 43, 47, 68), on four
different shanks (0, 1, 2, 8). The matches were verified genuine — cross-day
template correlation **0.95–0.99**, identical peak channels. Some neurons *split*
across days (one tracked neuron → several local units on a day); we pool them
under the tracked ID, and the split is itself a drift signal.

## Method — and the "no shortcuts" rule

- **Input: the peak-channel 40-sample waveform only** — *not* the 8-channel
  snippet. Because the four neurons sit on four different shanks, a multi-channel
  input would let the model separate them by *which shank is active* — a location
  fingerprint that is stable across days and would make drift look artificially
  harmless. One channel forces the classifier onto spike **shape** alone.
- **Model**: multinomial logistic regression, balanced class weights (unit 47 has
  ~35k day-1 spikes, unit 68 only ~368).
- **Protocol**: train on 80% of day 1; evaluate on held-out day 1 (within-day
  ceiling) and all of day 2 (cross-day). `StandardScaler` fit on **day-1 train
  only** — no leakage.
- Code: `dataset/build_crossday.py` (→ `crossday.npz`), `model/eval_crossday.py`.

## Result

| Evaluation | Balanced accuracy |
|------------|------------------:|
| Day 1 held-out (within-day ceiling) | **0.66** |
| Day 2 (cross-day generalization) | **0.68** |

**No drift cost** — the day-1 classifier works just as well on day 2 (the +2
points is noise).

## Read this honestly — it is a floor, not a headline

1. **Host-side only.** Nothing here ran on the nRF54. On-chip portability
   (export → flash → verify predictions match) is a separate, unverified step.
2. **Selection effect.** We can only test neurons `match_dict` could *track*
   across days — and trackable ⇒ stable. Neurons that actually drifted are
   untrackable and excluded, so "a day-1 model still works on day 2" is close to
   tautological for this subset.
3. **Information floor.** The four neurons' single-channel waveforms correlate
   **0.97–1.00** (all the same canonical negative spike; only trough depth
   differs). So 66% is a shape/amplitude ceiling, *not* a model-capacity limit —
   a CNN would not help, because the information isn't in one channel.
4. **Not comparable to the 98% within-day benchmark.** That number was same-day +
   8-channel + per-shank; this is across-day + single-channel + pooled-4-neurons.
   Three axes changed at once, so the gap cannot be attributed to drift alone.

## Next steps

- **Same-shank 8-channel detection.** Give each tracked neuron the full footprint
  but pit it only against *other units on the same shank* — real discriminative
  power, no location shortcut. This is the version worth trusting.
- **Vary one axis at a time** (within-day single-channel vs. across-day
  8-channel) to separate "drift cost" from "channel cost."
- **CNN** on the footprint task, where spatial structure exists for it to exploit.
- **Close the on-chip loop**: export the day-1 logreg weights, flash, and confirm
  on-chip predictions match the host (logreg is ~160 MACs/spike — it trivially
  fits; the open item is *verifying*, not whether it runs).
