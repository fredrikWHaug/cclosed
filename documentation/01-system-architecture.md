# System Architecture

> **Summary.** The long-run scientific question is **compression vs. fidelity**:
> how far can neural data be squeezed *on the chip* before it stops being
> scientifically useful. That work (spike classifiers, on-chip pipeline) was
> deliberately set aside — see [03-project-log.md](03-project-log.md) — to first prove
> the physical signal chain end-to-end on real hardware. **This doc now describes
> only what's currently real and in the repo.**

Related: [02-intan-rhd-reference.md](02-intan-rhd-reference.md) · [03-project-log.md](03-project-log.md)

## Current hardware

| Component | Detail |
|-----------|--------|
| **MCU** | nRF54LM20B — 128 MHz Cortex-M33, 2 MB NVM, 512 KB RAM, BLE |
| **Dev kit** | nRF54LM20 DK (PCA10184), target `nrf54lm20dk/nrf54lm20b/cpuapp` |
| **Analog frontend** | A real, bonded **Intan RHD2164** (64-ch, BGA) on a custom board — bring-up complete, SPI-verified alive (ROM reads `"INTAN"`) |
| **Toolchain** | nRF Connect SDK v3.3.1 (Zephyr), VS Code extension, J-Link |

The RHD2164 is real silicon now, not an emulation — getting it powered, wired,
and talking took a genuinely hard bring-up (BGA reflow, LVDS_en mode select,
grounding both `in0` and the reference input). See [03-project-log.md](03-project-log.md)
for that story.

## What's actually running (3 firmware projects, `firmware/`)

| Dir | What it does |
|-----|---------------|
| `board-bring-up/` | Minimal SPI ROM read — proves the Intan is powered and talking. No BLE, no config writes. |
| `signal-path-intan/master/` | Configures the real Intan (10 Hz–10 kHz band, amps on, calibrated), samples **channel 0 at a fixed rate**, streams over BLE. `receiver.py` plots it live on the laptop. **Currently one channel, validated end-to-end with a real function-generator sine** — cross-checked two independent ways (raw SPI print vs. BLE-relayed plot; both agree on amplitude and cycle timing). |
| `ble-rate/` | Pure BLE throughput characterization (master/slave/central), independent of the Intan — where the two ceilings below were measured. |

Everything else that used to live here — spike classifiers, the on-chip
detect/classify pipeline, the two-DK Intan emulation, cross-day generalization —
was intentionally removed from the working tree (commit `8b83a89`, "everything
but board bring up, signal path intan, and ble-rate for backup"). It's in git
history if it's ever needed again; it is **not** part of the current build and
nothing below describes it.

## The current signal path (real, one channel)

```
function generator (sine, mV-scale)
    │
    ▼
Intan RHD2164 (real chip)     amplify (gain 192) + digitize ch0; SPI SLAVE
    │  16-bit ADC code, one per CONVERT(0) command
    ▼
nRF54LM20B                    SPI MASTER: timer-paced sampling, ring buffer
    │  packed BLE notification (121 samples + seq, 244 bytes)
    ▼
BLE  ──►  laptop (receiver.py, live plot)
```

Confirmed working: a real analog sine, through a real Intan, over a real SPI
link, over a real BLE connection, plotted live — with the plotted amplitude and
cycle spacing matching independent hand-calculated predictions.

## The two measured ceilings (2026-07-31, `ble-rate/`)

**SPI ingestion — the harder ceiling.** SPI clock ≈ raw bit rate (one bit per
clock, no framing overhead). The Intan RHD2164 caps SCLK at 24 MHz →
**24 Mbit/s single-edge**. A full 64 ch @ 30 kS/s needs 30.7 Mbit/s — more than
that ceiling — which is *why* the RHD2164 uses DDR (both clock edges) for full
channel count. The nRF has exactly one SPI fast enough to matter (one HS-SPI
≤ 32 MHz; the rest cap at 8 MHz, too slow for even one 32-ch chip at 30 kS/s).

**BLE egress — the softer ceiling.** **~1.05 Mbps** (2M PHY, 7.5 ms interval,
244-byte notifications), held firm against every attempt to raise it. BLE
**back-pressures rather than silently dropping** — Zephyr's `bt_gatt_notify`
blocks when the radio can't keep up, so "0 drops" only ever meant "at or below
capacity," never "found the ceiling." Forcing real loss requires a free-running
producer with a bounded buffer (mirrors how the real Intan would overrun a
too-slow reader). Fat packets matter: 244-byte notifications hit ~1.05 Mbps;
tiny packets hit a higher packet rate but a tiny fraction of the byte rate —
batch many samples/events per packet, always.

## Open questions (current, not aspirational)

- **Push `signal-path-intan` toward its real ceiling** — currently sampling
  well under both the SPI and BLE limits above; next step is finding where it
  actually breaks for one channel.
- **Channel count fork** (unchanged from the datasheet-level analysis): full
  64 ch @ 30 kS/s needs DDR (fragile, FPGA-free trick or a hardware DDR
  receiver) vs. scoping to 32 ch on one clean SPI lane vs. dropping sample rate
  to fit more channels — see [02-intan-rhd-reference.md](02-intan-rhd-reference.md) §6.
- **Multi-channel on the current real chip** — `signal-path-intan` only reads
  channel 0 today; round-robin CONVERT across more channels is the natural
  next step once single-channel throughput is understood.

## The deferred thesis question

The original scientific goal — how much can neural data be compressed on-chip
(raw voltage → threshold crossings → embeddings → sorted unit IDs) before it
stops being useful — is unchanged as the eventual target, but the classifier
work that explored it was removed from the repo to focus on hardware first (see
[03-project-log.md](03-project-log.md)). It will come back once the real signal path
is solid enough to feed it real, not emulated, data.
