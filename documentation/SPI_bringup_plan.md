# SPI bring-up plan — getting acquisition to 32-channel speed

**Purpose.** "Get SPI up to speed" is actually **two separate problems wearing one name** — a firmware problem and a hardware/signal-integrity problem. This doc pins down both, with the numbers behind them, so neither gets silently dropped and so each can be handed to the right kind of help (embedded-dev mentorship vs. PCB/mixed-signal mentorship).

**Why this matters now.** The discrete detect-then-classify architecture (see `classification_options.md`, `design_considerations.md`) only works at 32 channels if acquisition can actually sustain the required throughput. Detection, classification, and BLE egress all have comfortable headroom at 32 ch — **acquisition is the one gate**, and it's not solved by the current code.

---

## 1. The target, in numbers

- **32 channels × 30 kS/s/ch = 960 kS/s aggregate**, vs. the RHD2164's rated ceiling of **1.05 MS/s** — ✅ fits, but at ~91% of max, essentially no headroom.
- That requires one Intan SPI conversion every **~950 ns**, i.e. an SPI clock (`SCLK`) around **17–20 MHz**, driven continuously.
- **Recommended design point, not the stretch case:** 20–25 kS/s/ch (640–800 kS/s aggregate) — still fine for spike detection, gives real margin on both the ADC ceiling and the SCLK requirement. Treat 30 kHz/ch as the edge case to reach for later, not the first target.

## 2. Problem A — firmware (the software half)

**Current code cannot do this.** `xfer()` (in `board-bring-up`, `signal-path-intan`, `classification-pilot`) runs `SCLK` at 1 MHz with **manual GPIO chip-select** and `k_busy_wait(2)` padding around every single transfer — roughly ~20 µs per conversion. At that rate, sustaining 960 k conversions/s would require ~19 seconds of SPI time per second of real time. Not close to possible.

**What's actually needed:**
- Replace manual-CS / busy-wait with a **DMA-driven SPI pipeline** — queue conversions, let the peripheral run at ~17–20 MHz `SCLK` without the CPU busy-waiting on each transfer.
- This has to run **concurrently** with the rest of the real-time pipeline (detection, classification, BLE notify) without blocking any of them — a Zephyr RTOS concurrency question (threads/interrupts/queues), not just a raw-throughput one.
- The **two-command pipeline lag** (Intan datasheet, p.16: *"each command sent over the MOSI line generates a 16-bit result that is transmitted over the MISO line two commands later"*) still has to be handled correctly at this speed — this is a correctness detail on top of the throughput problem, not a substitute for it.

**This is the "embedded development" help-ask** — see the email draft context: DMA-driven peripheral drivers + Zephyr concurrency primitives for sustained multichannel acquisition into the ring buffer without drops.

## 3. Problem B — hardware / signal integrity (the electrical half)

**Firmware alone cannot guarantee this works**, because at ~17–20 MHz the timing margins get tight. From the Intan datasheet's own SPI Bus Timing Specifications (p.15):

| Parameter | Spec | Consequence at high SCLK |
|---|---|---|
| `t_SCLK` (SCLK period) | min 40 ns → 25 MHz absolute ceiling | at 20 MHz (50 ns period) there's very little slack left |
| `t_MOSI` (data-valid-before-sample setup) | min 10 ns | real wiring/propagation delay eats into this margin |
| `t_MISO` (clock-edge-to-data-valid) | max 12 ns | if the line hasn't settled by the sampling edge, you sample the wrong bit |

At 1 MHz (1000 ns period), these margins were enormous and invisible. At 17–20 MHz, board wiring (trace length, capacitance) becomes a real threat to correct sampling — this is a **layout/signal-integrity problem**, not something fixable by changing C code.

**The separate, and arguably bigger, issue: CMOS vs. LVDS signaling.** The board is currently forced into **CMOS signaling** (`LVDS_en` tied to GND, a fix from the BGA bring-up saga). The datasheet (p.12) is explicit:

> "Operating the ADC at 1.05 MS/s with standard CMOS signaling will increase amplifier noise by at least 30%... standard CMOS signaling is recommended only for ADC sampling rates of 175 kS/s or less (i.e., ... **5 kS/s/channel or less with 32 amplifiers**)."

Our 20–30 kS/s/ch target is **4–6× above** that CMOS-safe threshold. The mechanism (also datasheet, p.11): CMOS's full-swing switching pulls bursty current from a power supply *shared with the ultra-sensitive analog amplifiers* (2.4 µVrms input-referred noise), injecting high-frequency noise into the recording. LVDS avoids this because it steers a **constant** current instead of switching a full voltage swing, so it doesn't jolt the shared rail.

**If LVDS is required, what changes:**
- `LVDS_en` → tied to VDD instead of GND (board/hardware change, not firmware).
- 100 Ω termination resistors near the chip on each differential pair (board change).
- Either the nRF54's SPI peripheral has native LVDS-capable I/O for the relevant pins (**unconfirmed — needs checking against the nRF54LM20B datasheet**), or an external LVDS↔CMOS translator chip is added (the Intan datasheet's own suggested path for controllers lacking native LVDS I/O).
- **Important, and reassuring:** none of this touches the application-level code. `xfer()`, the `CMD_*` macros, the pipeline handling, the ring buffer — all identical either way. LVDS is a physical-layer change, not a protocol change.

**This is the "PCB design / mixed-signal" help-ask**, not embedded development: confirming reliable SCLK at the required throughput given real trace/wiring signal integrity, and evaluating whether LVDS is needed to hit the speed and noise targets simultaneously.

## 4. Open questions (need verification, not assumption)

1. What SCLK frequency does the nRF54LM20B's `spi22` instance actually sustain reliably on our real bonded-Intan wiring? (Datasheet ceiling is 25 MHz; achievable-in-practice is unverified.) → probe with `board-bring-up`.
2. Does the nRF54LM20B have native LVDS-capable I/O, or does LVDS require an external translator chip? → **Partially checked (2026-08-27):** the Nordic product page lists three packages (CSP98 3.67×3.85 mm / 98-ball / 0.35 mm pitch / 66 GPIO; CSP61 3.02×2.43 mm / 61-ball; QFN52 6×6 mm / 52-pin / 32 GPIO), 128 MHz Cortex-M33, 512 KB RAM, 2 MB flash — but it says **nothing about an LVDS I/O standard**. No confirmation of native LVDS support was found; the working assumption is therefore **an external LVDS↔CMOS translator chip would be needed** if LVDS is required. Still needs datasheet-level (not product-page) confirmation before deciding.
3. At the recommended 20–25 kS/s/ch design point, is CMOS signaling's noise penalty actually tolerable for spike detection, or does LVDS become necessary regardless of raw speed? (5 kS/s/ch CMOS-safe threshold from the Intan datasheet still applies even at the lower design point — 20–25 kS/s/ch is still 4–5× over it.)

## 5. Recommended sequencing

1. **Firmware first, at low channel count.** Get DMA-driven SPI acquisition working correctly (right data, right pipeline-offset handling) at a modest rate (e.g. 1 channel, current 1 MHz SCLK) before touching clock speed — isolate correctness from throughput.
2. **Push SCLK up on the bench**, measuring for bit errors, using `board-bring-up` as the probe — answers open question 1.
3. **Decide the CMOS-vs-LVDS question** based on measured noise at the target sample rate, not the datasheet's worst-case number alone — answers open questions 2–3.
4. **Scale channel count** only once single-channel acquisition is solid at the target rate with acceptable noise.

---

## Status / decision log

- **2026-08-27** — Document created. Captures the firmware/hardware split identified while drafting the "embedded development" help-ask for Dr. Moyer's advisor-search email. Design point set at 20–25 kS/s/ch (not the 30 kHz stretch case) pending the CMOS/LVDS decision.
