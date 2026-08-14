# Wireless Ephys on nRF54LM20B — Documentation

The long-run scientific question is **compression vs. fidelity**: how far can
neural data be squeezed *on the chip* — from raw voltage down to spike
identities — before it stops being scientifically useful. That work is
currently **paused** (see [project-log.md](project-log.md)) while the physical
signal chain gets proven on real hardware — a real, bonded Intan RHD2164 chip,
not an emulation.

This folder is the durable reference for the project. The topic docs describe
how things work and why; the [project log](project-log.md) is the
chronological status and roadmap.

## The current signal path — real, one channel, validated

```
  function generator  ─►  Intan RHD2164  ─►  nRF54LM20B  ─►  BLE  ─►  laptop
  (sine, mV-scale)        (real chip,        (SPI master:                  live plot
                           amp + ADC,          timer-paced sample,
                           SPI slave)          ring buffer, notify)
```

Confirmed working end-to-end: a real analog sine, through the real chip, over
SPI, over BLE, live-plotted — cross-checked two independent ways (a raw-SPI
diagnostic print vs. the full BLE-relayed plot agree on amplitude and timing).

## Document map

| Document | What's inside |
|----------|---------------|
| [system-architecture.md](system-architecture.md) | Current hardware, the 3 active firmware projects, the real signal path, and the two measured throughput ceilings. Start here. |
| [intan-rhd-reference.md](intan-rhd-reference.md) | **The Intan front-end, distilled from the datasheets** (page-cited): sampling, SPI protocol, register map, the 64-channel DDR constraint, power. Read before any real-chip work. |
| [project-log.md](project-log.md) | The living status + roadmap: the hardware bring-up story, what's done, what's next. Chronological. |

## Status at a glance

- **Real Intan RHD2164**: bonded, powered, SPI-verified alive (`board-bring-up/`).
- **Real signal path, one channel**: validated end-to-end — `signal-path-intan/`.
- **BLE ceiling**: ~1.05 Mbps / ~65,500 samples/s, actually found (not just
  "0 drops observed") — `ble-rate/`.
- **On-chip classifier / compression work**: removed from the working tree,
  preserved in git history, deferred until the signal path above is solid.

## Conventions

- Board target: `nrf54lm20dk/nrf54lm20b/cpuapp`, nRF Connect SDK v3.3.1.
- Firmware is built and flashed by Fredrik via the VS Code Nordic extension.
