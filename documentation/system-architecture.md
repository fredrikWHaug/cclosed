# System Architecture

> **Summary.** Extracellular signals from a mouse are amplified and digitized by
> an Intan RHD chip, streamed over SPI to an nRF54LM20B, which detects and
> classifies spikes on-chip and sends a compressed representation out over BLE.
> The design question is where on the compression-vs-fidelity spectrum to
> operate.

Related: [spi-acquisition-link.md](spi-acquisition-link.md) ·
[on-chip-classifiers.md](on-chip-classifiers.md) ·
[cross-day-generalization.md](cross-day-generalization.md)

## The core problem

| Quantity | Value |
|----------|-------|
| Raw data rate | 80 ch × 30 kHz × 16-bit ≈ **38 Mbps** |
| BLE throughput (measured) | **~1.05 Mbps** (2M PHY, 7.5 ms) — proven ceiling, see below |
| SPI ingest ceiling | **24 Mbit/s** single-edge @ Intan's 24 MHz cap — *below* one chip's output, see below |
| Compression needed | **~20–40×**, without losing scientific utility |
| Science use case | place-cell remapping, decoding, encoding models (CA3–CA1 hippocampus) |

The implant cannot send raw voltage — the radio is ~20–40× too slow. Something
on the chip has to reduce the data first. *How much* it reduces, and *what it
throws away*, is the compression-vs-fidelity tradeoff this project characterizes.

## Hardware

| Component | Detail |
|-----------|--------|
| **MCU** | nRF54LM20B — 128 MHz Cortex-M33 + RISC-V + Axon NPU, 2 MB NVM, 512 KB RAM, BLE |
| **Dev kit** | nRF54LM20 DK (PCA10184), target `nrf54lm20dk/nrf54lm20b/cpuapp` |
| **Probe** | 80-channel mesh probe, 10 shanks × 8 contacts (2 col × 4 row, 66 µm × 35 µm pitch) |
| **Analog frontend** | Intan RHD chip — per-channel amplifier + ADC, SPI slave |
| **Toolchain** | nRF Connect SDK v3.3.1 (Zephyr), VS Code extension, J-Link |

## The acquisition path

```
mouse extracellular electrodes (80-ch mesh probe)
    │  analog µV signals
    ▼
Intan RHD chip          amplify + digitize each channel; SPI SLAVE
    │  16-bit ADC samples, one per CONVERT(channel) command
    ▼
nRF54LM20B              SPI MASTER: read samples, detect + classify spikes
    │  compressed representation (unit IDs + timestamps, or embeddings)
    ▼
BLE  ──►  host
```

**Key clarification.** The Intan does **not** emit spikes. It emits *raw
continuous voltage*, all channels, digitized. Spike detection and classification
happen on the nRF54. The Intan is a dumb ADC frontend; all compression
intelligence lives on the MCU. That boundary is the thesis.

**This whole path now runs end-to-end** on two DKs (one emulating the Intan by
replaying a recording) — see [onchip-pipeline.md](onchip-pipeline.md). Only the
Intan silicon and the live mouse are still emulated; the MCU + SPI + BLE half is
real.

## The two data-rate ceilings (both now measured, 2026-07-31)

> **The most important thing clarified this session:** the tightest wall in the
> pipe is getting samples *in* over SPI, **not** getting them *out* over BLE. The
> SPI side is the one that forces a hard design fork.

### SPI ingestion — the *harder* ceiling

**SPI clock rate ≈ raw bit rate, literally.** SPI is a shift register: exactly one
bit crosses the wire per clock cycle (single-data-rate). So `24 MHz SCLK → 24
Mbit/s`, with *no* packet/framing overhead baked into that number (unlike BLE).
The link runs at the **slower** of the two devices, and the **Intan RHD2164 caps
SCLK at 24 MHz** — so the nRF's 32 MHz HS-SPI ceiling is irrelevant; the Intan
sets the pace at **24 Mbit/s single-edge**.

**That is less than one chip produces.** 64 ch × 30 kS/s × 16 bit = **30.7
Mbit/s**. Since `24 < 30.7`, a normal single-edge link — even maxed at the Intan's
own limit — **physically cannot carry all 64 channels.** This is *why* the RHD2164
uses **DDR** (a bit on both clock edges → ~48 Mbit/s effective at 24 MHz). DDR is
therefore **throughput-mandatory, not merely a channel-capture nicety** — the
earlier framing ("DDR so we don't miss half the channels") undersold it.

**The nRF has exactly one SPI fast enough to matter.** Datasheet: one HS-SPI ≤ 32
MHz, six SPI ≤ 8 MHz. The 8 MHz instances (8 Mbit/s) can't carry even one
32-channel chip at 30 kS/s (needs 15.4 Mbit/s), so parallelism across the slow
instances cannot rescue the budget. One fast lane, period.

**FPGA-free DDR on the nRF — the trick, and why it's risky.** Put two nRF SPI
peripherals on the *same* SCLK+MISO with opposite clock phase: the SPIM samples
the rising edge (module A), a SPIS samples the falling edge (module B), interleave
in software. This is the closest thing to "combining SPI blocks" and the only
FPGA-free route to full DDR. It is **fragile and unverified on this silicon** —
both peripherals must stay bit-aligned across the whole transfer, and the Intan's
**CS-pulse-per-word** rule adds dead time at ~1.9 M words/s. This is exactly the
difficulty the RHD2164 datasheet flags as "will likely require an FPGA."

**The fork (sharper than the old "which Intan part" question):**
- **A — Full 64 ch @ 30 kS/s:** needs FPGA-free DDR (fragile) or an actual
  CPLD/FPGA shim.
- **B — Scope to one clean HS-SPI:** a single 24 MHz single-edge lane cleanly
  ingests **32 ch @ 30 kS/s** (15.4 Mbit/s, comfortable) with no DDR at all.
- **Loosen the premise:** spikes live below ~6 kHz, so **20 kS/s is plenty**
  (Nyquist). At 20 kS/s: 64 ch = 20.5 Mbit/s, 32 ch = 10.2 Mbit/s. Lowering the
  rate is the cheapest way to fit more channels on one lane.

### BLE egress — the *softer* ceiling

Nailed down too: **~1.05 Mbps** (2M PHY, 7.5 ms interval, 244-byte notifications),
and it held firm against three separate attempts to raise it (removing sender
back-pressure, stretching the connection-event length to 20 ms, matching receive
buffers). Two things worth recording:

- **BLE back-pressures; it does not silently drop.** When the sender outruns the
  radio, Zephyr's `bt_gatt_notify` *blocks* (a 30 s buffer-alloc wait,
  `att.c:3128` → `BT_ATT_TIMEOUT`) rather than discarding. So **"0 drops" means
  "at or below capacity," never "we found the ceiling."** To *see* the ceiling you
  must add a free-running producer with a bounded buffer — loss then appears at the
  producer boundary, not on the air. (This mirrors the real Intan: a free-running
  source overruns a too-slow reader; that's where data is actually lost.)
- **Fat vs. tiny packets are two different ceilings.** Max *byte* rate (~1.05
  Mbps) needs 244-byte packets; max *packet* rate (~1600 pkt/s) comes from tiny
  packets but delivers ~1% of the bytes. Design consequence: **batch many spike
  events into one fat notification** — never one spike per packet — to amortize the
  fixed per-packet overhead (~16× more events/s).

## Compression-vs-fidelity spectrum

Ordered from most faithful (least compressed) to most compressed (highest risk):

1. **Threshold crossings only** — `(channel, time)` per spike. ~30–50×. Baseline.
2. **Compressed LFP** — downsample to 1 kHz. Good for SWR / ripple detection.
3. **Embeddings (clusterless)** — small learned feature vector per spike; cluster
   / decode offline.
4. **On-chip sorted IDs** — `(unit_id, timestamp)`. Maximum compression, maximum
   risk (an ID error is unrecoverable). **← built and demonstrated end-to-end
   ([onchip-pipeline.md](onchip-pipeline.md)).**
5. **Event-triggered** — high-fidelity raw only during detected events (e.g.
   ripples), nothing otherwise.

Level 4 is realized: the [on-chip pipeline](onchip-pipeline.md) emits
`(unit_id, timestamp)` over BLE. The [cross-day study](cross-day-generalization.md)
tests whether those IDs stay valid across days.

## Key design decisions

1. **Shank is the atom.** Each shank's 8 channels are an independent sorting
   group; one neuron's footprint is contained within one shank.
2. **Snippet shape.** 8 channels × 40 samples @ 10 kHz = a 4 ms window (the
   offline pipeline downsamples 30 kHz → 10 kHz).
3. **Label contract.** Per-session curated units (post-MountainSort4 + curation +
   merge) are the *training* labels. Universal cross-day identity is an
   *evaluation* yardstick only.
4. **On-chip sorting ≠ full sorting.** Only the *classify* step runs on-chip.
   Clustering / unit discovery stays offline. (An online per-spike classifier is
   *template matching*, not spike sorting.)
5. **Feature extractor freezes, templates adapt.** Train a similarity/embedding
   model once; per-session just recompute cluster centroids in embedding space.

## Existing offline pipeline (source of ground truth)

- **Sorter**: MountainSort4 (adjacency_radius 190, threshold 5, bandpass
  300–3000 Hz, common-median reference, whitening).
- **Curation**: ISI / amplitude auto-checks → LLM 3-vote agent → manual rescue →
  cosine merge → cross-day match.
- **Final artifact**: `M{mouse}_match_dict_final.json` — persistent neuron
  identity across sessions, used as the cross-day evaluation yardstick.

## Open hardware questions

These are *not yet decided* and should be pinned before calling this a hardware plan.
Chip facts below are grounded in [intan-rhd-reference.md](intan-rhd-reference.md).

- **The channels × rate × DDR fork.** Now quantified — see [The two data-rate
  ceilings](#the-two-data-rate-ceilings-both-now-measured-2026-07-31). One nRF
  single-edge SPI does **not** have the budget for 64 ch @ 30 kS/s (30.7 > 24
  Mbit/s), so the decision is real: **(A)** RHD2164 + fragile FPGA-free DDR (or a
  CPLD/FPGA shim), **(B)** scope to 32 ch on one clean HS-SPI, or **(C)** drop to
  ~20 kS/s to fit more channels per lane. *Still to decide — but now with numbers.*
- **On-link sampling rate**, and where the 30 kHz → 10 kHz decimation happens (on
  the MCU?). Note the rate is set by our **CONVERT cadence**, not a chip register —
  and it's now a *lever* in the fork above, not just a fidelity knob.
- **Continuous stream vs. on-demand CONVERT.** (Throughput budget question is
  resolved above — the answer is "no, not for 64 ch single-edge.")
- **Headstage**: how the mesh probe physically connects to the Intan.
