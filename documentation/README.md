# Wireless Ephys on nRF54LM20B — Documentation

On-chip neural-data compression for a wireless electrophysiology implant.
The scientific question is **compression vs. fidelity**: how far can neural data
be squeezed *on the chip* — from raw voltage down to spike identities — before it
stops being scientifically useful?

This folder is the durable reference for the project. The topic docs describe how
things work and why; the [project log](project-log.md) is the chronological
status and roadmap.

## The system in one diagram

```
  mouse  ─►  80-ch mesh probe  ─►  Intan RHD  ─►  nRF54LM20B  ─►  BLE  ─►  host
             (10 shanks × 8)      (amp + ADC,     (SPI master:
                                   SPI slave)      detect, classify,
                                                   compress)
             ── raw µV ──►    ── 16-bit ADC ──►   ── unit IDs + ──►
                                 samples             timestamps
```

The Intan is a dumb amplifier + ADC that streams **raw voltage**; every bit of
compression intelligence (spike detection, classification) runs on the
**nRF54**. That boundary is the whole thesis.

## Document map

| Document | What's inside |
|----------|---------------|
| [system-architecture.md](system-architecture.md) | Hardware, the full acquisition path, the compression-vs-fidelity spectrum, and the key design decisions. Start here. |
| [spi-acquisition-link.md](spi-acquisition-link.md) | The Intan ↔ nRF54 SPI link: protocol, the two-DK bench emulation, whole-frame neural-data transfer, wiring/config, and the hard-won debugging lessons. |
| [on-chip-classifiers.md](on-chip-classifiers.md) | The three on-chip classifiers (logreg / CNN / ResNet) benchmarked on real silicon — accuracy vs. flash / RAM / latency. The compression-vs-fidelity curve, measured. |
| [cross-day-generalization.md](cross-day-generalization.md) | Does a classifier trained on one recording day still work the next day? The representational-drift experiment, its honest result, and its caveats. |
| [project-log.md](project-log.md) | The living status + roadmap: what's done, what's next, and the literature thread. Chronological; points into the topic docs. |

## Status at a glance

- **SPI link**: working and understood — two DKs stand in for Intan ↔ nRF54,
  real recorded neural data transferred and checksum-verified.
- **On-chip classifiers**: all three build and run on the `nrf54lm20b/cpuapp`
  target; within-day accuracy saturates at the linear/CNN end of the curve.
- **Cross-day generalization**: a conservative host-side baseline exists
  (logreg, peak-channel); next is same-shank 8-channel detection and closing the
  on-chip loop.

## Conventions

- Board target: `nrf54lm20dk/nrf54lm20b/cpuapp`, nRF Connect SDK v3.3.1.
- Git: `main` + `dev` only; feature branches cut from `dev`, rebased back,
  ff-merged, deleted. Linear history.
- Firmware is built and flashed by Fredrik via the VS Code Nordic extension.
