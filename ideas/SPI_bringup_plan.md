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

## 3.5 Chip-select mechanism & SPIM instance — RESOLVED (2026-09-01)

This is the concrete answer to what §2 hand-waved as "a DMA-driven SPI pipeline." Two
independent methods **converged** on the key numbers: (a) a direct read of the
**nRF54LM20B datasheet §11.19 (SPIM Electrical specification)** — primary source; and
(b) an adversarially-verified research workflow (12/12 central claims corroborated
across Nordic product spec, nrfx HAL, and Zephyr driver sources). The load-bearing
frequency figures from the workflow match the datasheet reading exactly.

### The silicon ceiling (datasheet §11.19, verbatim values)
- `fSPIM` (standard instances): **8 Mbps** max.
- `fSPIM,HS` (high-speed): **32 Mbps** max — footnote: *"For SPIM00 using GPIO port P2."*
- `tSPIM,CSCK` (SCK period): **31.25 ns** min → confirms 32 MHz on the HS instance.
- `tSPIM,START` (START task → transmission started): **1 µs** — a per-transfer startup latency (matters below).

**Instances:** SPIM00 (high-speed, MCU domain), SPIM20–24 (standard), SPIM30 (low-power).
**The old `spi22` is a standard 8 Mbps instance.** Consequence: `spi22` **physically cannot**
do 32 ch × 30 kHz — 8 Mbps ÷ 16 bit ÷ 32 ch ≈ **15 kHz/ch max**. **SPIM00 (32 MHz, on port
P2, extra-high-drive pins) is required for the scaling path.** This supersedes §2's
"~17–20 MHz on `spi22`" — 20 MHz is reachable *only* on SPIM00.

### The chip-select landscape (four mechanisms)
1. **Zephyr `cs-gpios` = software CS.** `spi_nrfx_spim.c` toggles a plain GPIO via
   `spi_context_cs_control()` around each transfer and leaves nrfx `.ss_pin` unused, so
   `PSEL.CSN` is never programmed. Correct, but CPU-bound and one-transfer-per-call →
   **does not scale.** (Effectively what the old `xfer()` did.)
2. **Silicon hardware CSN** (`PSEL.CSN` + `CSNPOL` + `IFTIMING.CSNDUR`). The peripheral
   pulses CSN per **transaction** (asserts at START, deasserts at END). Set **MAXCNT = 2
   bytes → one 16-bit word per transaction → CSN pulses per word in silicon** — exactly
   the Intan requirement. Gated by the nrfx feature `NRF_SPIM_HAS_HW_CSN`; **whether
   SPIM00 specifically carries it is UNCONFIRMED** (on nRF52 only SPIM3/4 had it).
3. **nrfx_spim direct.** Exposes `nrf_spim_csn_configure()`, `use_hw_ss`, and **array-list
   mode**. **Required**, because Zephyr's generic SPI API issues one transfer at a time
   and has no property to enable hardware CSN.
4. **EasyDMA array-list + SHORTS `END_START` / DPPI chaining.** DMA walks a list of
   per-word buffers; `END_START` (or a DPPI channel) re-arms the next transaction in
   hardware, CSN pulsing between each — **zero CPU per word.**

### Decision (fast now AND rewrite-proof)
Build acquisition on **nrfx_spim + hardware CSN on SPIM00**, driven by **EasyDMA
array-list transactions (MAXCNT = 2) chained via `END_START`/DPPI** — from the start,
**even for the ≥3-channel minimum.**
- *Why not the `cs-gpios` software path even for the minimum:* it's a dead end (8 MHz
  cap, CPU-toggled CS, one transfer per call). Nothing about it survives the jump to 32
  channels, so building on it is throwaway work.
- *Why this scales:* the same nrfx primitive goes from 1 word to a 32-channel list —
  scaling is a list-length + SCLK change, **not a rewrite.**
- *Concretely:* retarget **`spi22`/P3 → SPIM00/P2** (extra-high-drive); configure CSN in
  nrfx, **not** via devicetree `cs-gpios` (which would re-engage the software path — and
  on P2 may fail outright, since that port reportedly lacks GPIOTE on related nRF54L parts).

### The governing ceiling is the per-word restart cadence, NOT SCLK
The Intan mandates CS-high between every 16-bit word, so **each word is an irreducible
transaction — you cannot batch words into one long DMA transfer.** The only figure found
for per-word restart/turnaround is **~1 µs** (single DevZone thread, unverified) →
~1 M words/s → **right at the 960 k words/s requirement, essentially no margin.** This
cadence, not the 32 MHz SCLK, is what decides whether 32 ch × 30 kHz is reachable.

### Fallback ladder (if the primary path can't sustain 960 k words/s)
1. **PRIMARY:** SPIM00 @ ~20 MHz, nrfx, silicon CSN, array-list MAXCNT=2 chained via `END_START`/DPPI.
2. **If SPIM00 lacks HW-CSN:** keep SPIM00 @ 20 MHz, generate the per-word CS pulse with a
   **GPIOTE pin driven by DPPI off the SPIM END/START events** — still hardware-timed,
   zero CPU per word. (Requires checking P2 GPIOTE availability.)
3. **If restart cadence caps below 960 k words/s:** drop to **20–25 kS/s/ch** (640–800 k
   words/s) — no architecture change, only a sample-rate constant. (This is the design
   point already recommended in §1.)
4. **Last resort (real rewrite):** external SPI master (CPLD/FPGA) generating the
   CS-per-word framing, or a different host part.

### The one bench measurement that decides it
On SPIM00 with array-list + `END_START`/DPPI + hardware CSN engaged, scope the **sustained
per-word cadence** — CSN rising edge of one word to first SCLK edge of the next, over a
long run — and confirm CSN is actually toggling in silicon. This simultaneously proves
(a) SPIM00 has *usable* HW-CSN (the single most load-bearing unknown) and (b) the real
throughput ceiling. Under ~1.04 µs/word → 32-channel headroom; otherwise → rung 3.

### Devicetree's limited role
The overlay can bring SPIM00 up on its P2 pins, but the `nordic,nrf-spim` binding has **no
property to enable silicon CSN**, and adding `cs-gpios` forces the software-CS path back
on. So the overlay reserves the instance + pins only; CSN is configured in **nrfx C**
(`nrf_spim_csn_configure` + `CSNPOL` + `IFTIMING.CSNDUR`), deliberately not in devicetree.
Pin numbers, the `spi00` node label, the drive-mode token, and the max `clock-frequency`
the binding accepts must be checked against the SoC dtsi / pin map (unverified here).

---

## 4. Open questions (need verification, not assumption)

1. ~~What SCLK frequency does `spi22` sustain?~~ **ANSWERED (§3.5, 2026-09-01):** `spi22` is a standard **8 Mbps** instance and cannot do 32 ch × 30 kHz (~15 kHz/ch max). **SPIM00 (32 MHz, port P2) is required** for the scaling path. Remaining sub-question: the *achievable* per-word restart cadence on SPIM00 (the real ceiling) — bench-measure per §3.5.
2. Does the nRF54LM20B have native LVDS-capable I/O, or does LVDS require an external translator chip? → **Partially checked (2026-08-27):** the Nordic product page lists three packages (CSP98 3.67×3.85 mm / 98-ball / 0.35 mm pitch / 66 GPIO; CSP61 3.02×2.43 mm / 61-ball; QFN52 6×6 mm / 52-pin / 32 GPIO), 128 MHz Cortex-M33, 512 KB RAM, 2 MB flash — but it says **nothing about an LVDS I/O standard**. No confirmation of native LVDS support was found; the working assumption is therefore **an external LVDS↔CMOS translator chip would be needed** if LVDS is required. Still needs datasheet-level (not product-page) confirmation before deciding.
3. At the recommended 20–25 kS/s/ch design point, is CMOS signaling's noise penalty actually tolerable for spike detection, or does LVDS become necessary regardless of raw speed? (5 kS/s/ch CMOS-safe threshold from the Intan datasheet still applies even at the lower design point — 20–25 kS/s/ch is still 4–5× over it.)

## 5. Recommended sequencing

1. **Firmware first, at low channel count.** Get DMA-driven SPI acquisition working correctly (right data, right pipeline-offset handling) at a modest rate (e.g. 1 channel, current 1 MHz SCLK) before touching clock speed — isolate correctness from throughput.
2. **Push SCLK up on the bench**, measuring for bit errors, using `board-bring-up` as the probe — answers open question 1.
3. **Decide the CMOS-vs-LVDS question** based on measured noise at the target sample rate, not the datasheet's worst-case number alone — answers open questions 2–3.
4. **Scale channel count** only once single-channel acquisition is solid at the target rate with acceptable noise.

---

## Status / decision log

- **2026-09-17 — THE BENCH MEASUREMENT IS DONE (§3.5 answered).** SPIM00 @ 21.33 MHz + silicon HW CSN (CSNDUR 20) + END_START free-run, cadence counted in hardware (TIMER00←DPPI←SPIM.END): **757,741 words/s sustained (~1.32 µs/word), with data validity confirmed at full speed** (ROM reads "INTAN" at 21.33 MHz). → 32 ch = **23.7 kS/s/ch: inside the 20–25 kS/s design point (rung 3)**; 5-ch minimum has 5× headroom; 960 k (32×30k) not reachable. Bring-up gotchas found and fixed, in order: (1) shared ground missing; (2) DK board controller defaults P2.00–05 to the onboard mx25 flash — must disable "External memory" in Board Configurator to route to headers (also removes flash-opcode-aliasing hazard); (3) SPIM00 is bonded to dedicated pads only (SCK P2.01, SDO P2.02, SDI P2.04, CSN P2.05 — datasheet p.1222); (4) **IFTIMING.RXDELAY default (2 ticks = 15.6 ns) samples MISO one bit early** given the ~25–30 ns chip+DK-switch round trip — RXDELAY 4–7 read clean at both 4 and 21.33 MHz; operating point RXDELAY=5. Note: each RXDELAY tick lengthens the word by 7.8 ns (END waits for the delayed sample).

- **2026-08-27** — Document created. Captures the firmware/hardware split identified while drafting the "embedded development" help-ask for Dr. Moyer's advisor-search email. Design point set at 20–25 kS/s/ch (not the 30 kHz stretch case) pending the CMOS/LVDS decision.
- **2026-09-14** — **Biggest unknown RESOLVED from the MDK on disk** (`nrf54lm20b_application_peripherals.h`, NCS v3.3.1): `SPIM00_FEATURE_HARDWARE_CSN_PRESENT = 1` — SPIM00 **has silicon hardware CSN**; rung 1 of the ladder stands, no GPIOTE workaround needed. Also confirmed: SPIM00 core = 128 MHz with even prescaler 4–126 → **max legal SCLK under the Intan cap = 21.33 MHz (÷6)**; `IFTIMING.CSNDUR` is in 128 MHz cycles and, **with SHORTS.END_START, is exactly the inter-word CSN-high time** (types header) → CSNDUR 20 = 156 ns ≥ Intan's 154 ns; RXDELAY present (0–7, default 2) for the t_MISO margin; pins from the DK devicetree: SCK P2.01 / MOSI P2.02 / MISO P2.04 / CSN P2.05 (external-flash header, mx25 disabled). **Firmware written and compile-verified** (`firmware/theo`): nrfx_spim (API v4) + hardware CSN + END_START free-run, cadence counted in hardware by TIMER00 ← DPPIC00 ← SPIM00.END. Theoretical best: 750 ns + 156 ns ≈ **906 ns/word ≈ 1.10 M words/s** vs the 960 k target — margin exists only if the END→START restart adds ≈ nothing, which is what the flashed test measures. Bench: confirm CSN toggling per word on P2.05 with a scope.
- **2026-09-01** — Added §3.5: chip-select mechanism & SPIM-instance decision. Method: direct read of nRF54LM20B datasheet §11.19 (primary source) + an adversarially-verified research workflow (12/12 claims corroborated); the two converged. **Key results:** the old `spi22` (8 Mbps) cannot scale to 32 ch; **SPIM00 (32 MHz, port P2) is required**; the path forward is **nrfx_spim + silicon hardware CSN + EasyDMA array-list chained via `END_START`/DPPI**, adopted from the start (not `cs-gpios`, which is a non-scaling software-CS dead end). The real ceiling is the **per-word transaction restart cadence** (~1 µs unverified, ~no margin), not SCLK — one bench measurement (§3.5) decides it. Biggest unconfirmed fact: whether SPIM00 specifically carries the HW-CSN feature.
