# Project Log & Roadmap

> **Summary.** The living "where are we / what's next" page. Durable how/why lives
> in the topic docs ([architecture](system-architecture.md),
> [Intan reference](intan-rhd-reference.md)); this page is the chronological
> status and roadmap that points into them.

_Last updated: 2026-08-13._

## Status at a glance

| Area | State | Detail |
|------|-------|--------|
| **Real Intan RHD2164** | ✅ **bonded, powered, SPI-verified alive** | ROM reads `"INTAN"` — [project log below](#2026-08-13--real-intan-rhd2164-signal-path-validated-end-to-end-one-channel) |
| **Real signal path, one channel** | ✅ **validated end-to-end** | FG sine → real Intan → SPI → nRF54 → BLE → laptop, cross-checked two ways |
| BLE breaking point | ✅ actually found | ~1.05 Mbps / ~65,500 samples/s, proven by forcing real drops, not just observing 0 — see below |
| SPI ingestion ceiling | ✅ measured | 24 Mbit/s single-edge (Intan's 24 MHz cap) — [system-architecture.md](system-architecture.md#the-two-measured-ceilings-2026-07-31-ble-rate) |
| On-chip classifier / compression pipeline | ⬜ removed from repo, deferred | see [2026-08-13 entry](#2026-08-13--repo-stripped-to-hardware-bring-up-scope) |

## Log

### 2026-08-13 — Real Intan RHD2164 signal path validated end-to-end, one channel

The hardware work moved from emulation to a genuine bonded RHD2164. Headline:
a real function-generator sine, through the real chip, over SPI, over BLE,
live-plotted on the laptop — validated two independent ways.

**Bring-up.** A freshly-soldered RHD2164 initially drew zero current. Isolated
via voltage-at-decoupling-caps and continuity checks to unreflowed BGA power
balls — reflowed, current draw confirmed. `LVDS_en` also needed to be tied to
GND to force CMOS mode (it defaults to LVDS via an internal pull-up); without
that, the nRF's single-ended SPI physically cannot talk to the chip's
differential inputs. Once powered and in CMOS mode, `board-bring-up/` (a
minimal ROM-read-only firmware, no BLE, no config writes) confirmed the chip
alive: `ROM 40-44 = 'INTAN'`.

**Signal path.** `signal-path-intan/master/` configures the real amplifier
(10 Hz–10 kHz, all amps on, CALIBRATE) and streams ch0. First attempt railed
hard with nothing connected — a floating high-impedance input (~1.3 GΩ) acts
as an antenna. Fix: ground **both** `in0` and the reference input at the same
time (either alone floating rails the amplifier, since it measures
`in0 − reference`). Confirmed via a standalone raw-SPI print tool before
trusting the full BLE pipeline.

**Sampling correctness.** The first BLE-connected version sampled in fast
bursts separated by BLE-transmit gaps — looked like noise at low frequencies
(a burst only captures a fraction of a slow cycle). Fixed with a timer-paced
sampler thread + ring buffer, decoupling acquisition rate from BLE transmit
rate — uniform sampling at a known, fixed rate.

**Validated, not just observed.** FG on/off and waveform shape (sine/square/
triangle) visibly track the live plot. Quantitatively: sample rate ÷ FG
frequency correctly predicts the on-screen cycle spacing; amplitude
cross-checks between the raw-SPI print and the full BLE-relayed plot agree.

### 2026-08-13 — Repo stripped to hardware-bring-up scope

Removed the on-chip classifier / spike-sorting pipeline (`dataset/`, `model/`,
`sim/`, `firmware/classifiers`, `firmware/pipeline`, the two-DK Intan
emulation) from the working tree (commit `8b83a89`). Kept only
`board-bring-up/`, `signal-path-intan/`, `ble-rate/`. The classifier work
(logreg/CNN/ResNet on-chip, cross-day generalization, the full
raw→classify→BLE chain, all previously demonstrated end-to-end on two DKs) is
preserved in git history, not deleted — it's just no longer part of the active
build or documentation. Reason: focus shifted to proving the physical signal
chain on real hardware before returning to the compression/classification
question.

### 2026-08-05 — BLE breaking point actually found, not just a sustainable rate

Every prior BLE test showed 0 drops — proof of "at or below the ceiling,"
never proof of *finding* it, since Zephyr's `bt_gatt_notify` back-pressures
(blocks) rather than dropping when the radio can't keep up. Fix: a
free-running producer (its own timebase, doesn't wait for BLE) writing into a
bounded ring buffer — when BLE can't drain fast enough, the *buffer*
overflows, and that's a real, countable drop. This finally exercises the
actual ceiling: **~1.05 Mbps / ~65,500 sixteen-bit values/sec**, confirmed by
pushing the offered rate well past it (drops appear, tracking the overrun
almost exactly) and backing off to find the 0-drop knee.

### 2026-07-31 — Both data-rate ceilings measured; SPI is the harder wall

Documented in
[system-architecture.md](system-architecture.md#the-two-measured-ceilings-2026-07-31-ble-rate).
Headlines:
- **BLE egress ceiling = ~1.05 Mbps**, proven. BLE back-pressures, it does not
  drop — "0 drops" never meant "at the max" until the fix above.
- **SPI ingestion is the tighter wall.** SPI clock ≈ bit rate; Intan caps SCLK
  at 24 MHz → 24 Mbit/s single-edge < 30.7 Mbit/s needed for 64 ch. DDR is
  throughput-mandatory, not just a channel-capture nicety.
- **nRF SAADC ≠ Intan:** on-chip ADC is 14-bit, 8 ch, no gain stage — the real
  reason Intan exists is the per-channel amplifier (×192) before the ADC.

### 2026-07-24 — Intan datasheet reference added

Read the RHD2000-series and RHD2164 datasheets in full and distilled them into
a page-cited reference: [intan-rhd-reference.md](intan-rhd-reference.md).
Durable — grounded in the datasheet, not tied to any specific firmware, so it
survived the later repo cleanup intact.

## Roadmap

- [ ] **Push `signal-path-intan` toward its real ceiling** — currently well
  under both the SPI and BLE limits; find where one channel actually breaks.
- [ ] **Multi-channel on the real chip** — round-robin CONVERT across more than
  ch0, still on standard single-edge SPI (32 ch reachable without DDR).
- [ ] **The channel-count fork** — full 64 ch needs DDR (fragile FPGA-free
  trick or a hardware DDR receiver) vs. 32 ch on one clean lane vs. lower
  sample rate to fit more channels. See
  [intan-rhd-reference.md](intan-rhd-reference.md) §6.
- [ ] **Bring the classifier/compression work back**, now against real
  (not emulated) Intan data, once the signal path above is solid.
