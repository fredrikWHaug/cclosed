# SPI Acquisition Link

> **Summary.** The nRF54 reads digitized neural data from the Intan chip over
> SPI, with the nRF as master and the Intan as an always-ready hardware slave.
> Two nRF54LM20 DKs stand in for that link on the bench — one emulates the Intan
> — and we have transferred real recorded neural data across it, checksum-verified.

Related: [system-architecture.md](system-architecture.md) ·
[on-chip-classifiers.md](on-chip-classifiers.md)

## Role

In the real product the nRF54 is the SPI **master** talking to the Intan, an
always-ready hardware **slave**. On the bench we have no Intan, so a second DK
emulates it (nRF-as-slave). That emulation is *harder* than the real system —
the nRF SPIS is DMA-based and must be armed before the master clocks, whereas the
Intan (a shift-register slave) is always ready — so any nRF-as-slave difficulty
disappears in the actual product.

## Working setup

| Role | SPI instance | Pins (PORT3) |
|------|--------------|--------------|
| Master (nRF stand-in) | `spi22` | SCK P3.03, MOSI P3.00, MISO P3.01, CS P3.02 |
| Slave (Intan stand-in) | `spi21` | same pins, wired pin-to-pin + shared GND |

- Mode 0 (CPOL 0, CPHA 0), MSB first, 8-bit SPI words (a 16-bit value = 2 bytes).
- **Chip-select is driven manually** as a plain GPIO on P3.02 (see the debugging
  log below for why). Frame: `idle high → pull low → ~50 µs setup →
  spi_transceive() → ~50 µs hold → release high`.
- The `nrf54lm20b/cpuapp` overlays enable `spi22`/`spi21`; the slave overlay must
  `/delete-property/ rx-delay` and `rx-delay-supported` and declare a
  `SPIS_CSN` pin.

## Intan RHD protocol (what the master speaks)

- 16-bit words, MSB first, mode 0, one CS pulse per word.
- **CONVERT(channel)** command: bits [13:8] select the channel; the slave replies
  with that channel's 16-bit ADC sample.
- **2-command pipeline delay**: the reply to command *i* comes back at command
  *i+2*. The emulator reproduces this so the master firmware is exercised against
  the real timing.

## Bench firmware (`firmware/spi/`)

Two complementary demos, each a master + slave app plus a host tool:

### 1. Counter link — data-integrity / latency test
- Master streams `0, 1, 2, …` as 16-bit words; slave prints each received value.
- `monitor.py` reads the slave's serial output, live-plots the sequence, and
  flags **dropped / reordered** words and inter-arrival jitter — the honest
  loss/latency measurement of the link.

### 2. `ndspi/` — real neural-data transfer
- The slave emulates an Intan streaming a **real 8-channel spike snippet** (unit
  46 from `dataset.npz`, Q8 fixed-point microvolts).
- Frame: `[ SYNC=0x7FFF ][ 320 data words ][ checksum ]`. The master clocks the
  whole frame, reconstructs the snippet, verifies the checksum, and plots the
  peak channel — you watch a real spike cross the link and land intact.
- `gen_nd_data.py` regenerates the snippet header from `dataset.npz`.

### The whole-frame lesson (important)

The first `ndspi` version framed **one CS pulse per word**, which re-armed the
DMA-based SPIS between every 16-bit word. That re-arm raced the master's clock and
the preloaded word was sampled across **two** master transactions — every sample
came out **duplicated** and the frame de-aligned (checksum failed).

**Fix: one transaction per frame.** The slave preloads the entire 322-word frame
and the master clocks all of it under a single CS assertion. One arm per frame,
no per-word race, exact alignment (SYNC lands at word 0). This is the right mental
model for bulk SPI transfers, and it maps cleanly onto the real Intan use case
(burst-read many samples per CS, not one word per CS).

## Debugging log — two-board SPI (hard-won)

Getting the two-DK link working at all took a long detour. Recorded here because
the lessons generalize.

### The hurdles, in order

1. **Board-target gotcha.** Build configs sometimes defaulted to
   `nrf54lm20**a**/cpuapp`. Our overlays are named for the **`b`** variant, so on
   an `a` build they were *silently skipped* — SPI never enabled, no error.
   **Fix:** confirm the build log shows `qualifiers: nrf54lm20b/cpuapp`.
2. **SPIS devicetree mismatch.** The SoC defines each SPI node as a master
   (`nordic,nrf-spim`) with `rx-delay` properties. Redeclaring it as a slave
   (`nordic,nrf-spis`) fails to build because those properties aren't in the SPIS
   binding, and the slave needs an explicit `SPIS_CSN` pin. **Fix:**
   `/delete-property/` them and add `SPIS_SCK/MOSI/MISO/CSN` to a pinctrl group
   (Nordic's `spi_controller_peripheral` test overlay was the reference).
3. **The red herring: "SPIS arming latency."** The slave only reacted to reset
   glitches and unplugs, never real transactions. This *looked* like the known
   nRF SPIS arming problem, and a lot of time went into slowing the clock, CS
   setup delay, PM toggles, instance swaps — **none of it helped**.
4. **Isolating the layers** finally created traction: master SPIM verified by
   MOSI→MISO loopback; slave SPIS verified by Nordic's on-board
   `spi_controller_peripheral` test (100% pass on this silicon); physical link
   verified by a 4-bit GPIO counter driven across the wires and read back
   exactly. All three layers proven good in isolation — yet two-board SPI failed.
5. **The actual root cause: CS never toggled.** A GPIO edge-counter on the slave
   watching P3.02/P3.03 showed `SCK edges climbing, CS edges = 0`. The Zephyr
   SPIM driver simply wasn't toggling the `cs-gpios` pin, so the slave never saw
   a transaction begin and the master read `0xFF`.
6. **The fix: drive CS manually.** Remove `cs-gpios` from the master overlay and
   control P3.02 as a plain GPIO in `main.c` (idle-high → low → setup delay →
   transceive → hold → high). The setup delay also gives the SPIS arming margin.
   Fixed it immediately.

### Takeaways

- **Measure before tweaking.** Hours went into a wrong theory (arming latency); a
  ten-minute edge-counter found the mundane bug (CS not toggling). When stuck,
  instrument the actual signals.
- **Isolate each layer.** Peripheral, physical link, and protocol are separate
  failure domains — prove each independently before debugging their interaction.
- **Use the vendor's passing test as ground truth.** Nordic's
  `spi_controller_peripheral` proved the silicon and gave the correct overlay/pin
  reference; that's where to start.
- **Hardware slave vs DMA slave.** The nRF SPIS needs arming; the Intan is a
  shift-register slave that's always ready. In the real system the nRF is the
  *master*, so the hardest part of this exercise won't exist in the product.

### Multi-frame streaming (the full chain)

The whole-frame pattern scales up in `firmware/pipeline/` (see
[onchip-pipeline.md](onchip-pipeline.md)): a full 8-channel raw stream is too big
for one transfer, so it goes out in **3 frames** of 24000 words, each
`[frame_idx][SYNC][data][checksum]` under one CS. The `frame_idx` lets the master
place frames even if it starts reading mid-cycle, and each frame's checksum is
verified — the receive was **72000/72000 words correct**. This is bulk
transport-then-process; true per-sample 30 kHz streaming would need a faster clock
and less per-frame overhead (a transport optimization, not a correctness gap).

## Relevance going forward

For the real acquisition path the nRF54 is the SPI **master** talking to the
always-ready Intan, so the arming/coordination difficulty disappears. What
carries over: a working, understood master, an explicit manual-CS framing for
when the driver misbehaves, and the whole-frame burst-transfer pattern for
reading many samples per CS.
