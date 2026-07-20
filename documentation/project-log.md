# Project Log & Roadmap

> **Summary.** The living "where are we / what's next" page. Durable how/why lives
> in the topic docs ([architecture](system-architecture.md),
> [SPI link](spi-acquisition-link.md), [classifiers](on-chip-classifiers.md),
> [cross-day](cross-day-generalization.md)); this page is the chronological status
> and roadmap that points into them.

_Last updated: 2026-07-20._

## Status at a glance

| Area | State | Detail |
|------|-------|--------|
| SPI acquisition link | ✅ working & understood | Real neural data transferred between two DKs, checksum-verified — [spi-acquisition-link.md](spi-acquisition-link.md) |
| On-chip classifiers | ✅ benchmarked on silicon | logreg / CNN / ResNet build & run; fidelity saturates at the cheap end — [on-chip-classifiers.md](on-chip-classifiers.md) |
| Cross-day generalization | 🟡 baseline done | Conservative host-side floor (no drift cost, but low-power) — [cross-day-generalization.md](cross-day-generalization.md) |
| Real Intan hardware | ⬜ not started | Open hardware questions in [system-architecture.md](system-architecture.md#open-hardware-questions) |

## Log

### 2026-07-20
- **SPI link:** basic counter link + `monitor.py` (drop/jitter measurement); then
  `ndspi` — transferred a real 8-channel spike snippet master↔slave and
  checksum-verified it. Key lesson: per-word framing duplicated samples; fixed
  with **one transaction per frame**. Details:
  [spi-acquisition-link.md](spi-acquisition-link.md).
- **Cross-day data landed:** two consecutive MA1 sessions sorted, plus
  `MA1_match_dict_final.json` for cross-day identity. Decoded the match schema and
  verified 4 neurons tracked across both days (template corr 0.95–0.99).
- **Cross-day baseline committed** (`a8ef437`): logreg on peak-channel waveforms,
  train day 1 / test day 2 → balanced accuracy 0.66 → 0.68 (no drift cost).
  Documented as a conservative floor. Details:
  [cross-day-generalization.md](cross-day-generalization.md).
- **Docs unified** into this `documentation/` set with a README landing page.

## Roadmap (each its own feature branch)

- [ ] **Same-shank 8-channel detection** — the cross-day version with real
  discriminative power: full footprint, distractors on the *same* shank so
  location can't be exploited. Vary one axis at a time (within-day single-channel
  vs. across-day 8-channel) to separate "drift cost" from "channel cost."
- [ ] **CNN** on that footprint task — capacity helps only where spatial
  information exists, not on the near-identical single-channel task.
- [ ] **Close the on-chip loop** — export day-1 logreg weights to C
  (`model/export_logreg_to_c.py`) → flash `firmware/classifiers/logreg` → verify
  on-chip predictions match the host. Logreg trivially fits (~160 MACs/spike); the
  open item is *verifying*, not whether it runs.
- [ ] **Original thesis experiment** — offline compression-vs-fidelity on existing
  recordings: place fields + decoding error under each compression scheme (see the
  [spectrum](system-architecture.md#compression-vs-fidelity-spectrum)) to find the
  minimum viable representation.
- [ ] **Multi-session-per-day pairs** (some mice have them) for a shorter-interval
  drift comparison, once that data is local.

## Literature thread

High bar — skeptical of hype / synthetic-only / uncited claims. Working takeaways:

- Real "on-implant real-time *full* spike sorting" is largely aspirational. Most
  working BMIs use **threshold crossings**, not sorting. Surveys (e.g. Zhang 2023)
  assert the need but cite efficiency/offline architectures, not demonstrations.
- The online per-spike step is **template matching / classification**, not spike
  sorting — clustering stays offline (see design decision 4 in
  [system-architecture.md](system-architecture.md#key-design-decisions)).
- **SpikeForest** + **MEArec / SpikeInterface** are the rigorous
  fidelity-measurement tools, aligned with the thesis framing.

_Fredrik found new literature recently — may shift the roadmap; to be folded in._
