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
| BLE throughput | ~1–2 Mbps |
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

- **Which Intan part + the DDR fork.** The bench emulation uses an RHD2132 (32-ch).
  64 channels means the **RHD2164**, whose SPI is **double-data-rate** — the master
  must sample MISO on *both* clock edges, which a standard nRF SPI peripheral can't
  do (it would capture only 32 of 64). Decide: **RHD2164 + solve DDR** on the nRF, or
  **2 × RHD2132** on plain single-edge SPI (one MISO each). See reference §6.
- **On-link sampling rate**, and where the 30 kHz → 10 kHz decimation happens (on
  the MCU?). Note the rate is set by our **CONVERT cadence**, not a chip register.
- **Continuous stream vs. on-demand CONVERT**, and whether one SPI bus has the
  throughput budget for the raw rate (64 ch × 30 kS/s × 16 bit ≈ **30.7 Mbit/s**).
- **Headstage**: how the mesh probe physically connects to the Intan.
