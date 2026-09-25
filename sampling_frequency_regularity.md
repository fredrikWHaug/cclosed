# Sampling frequency & regularity — the plan (v2)

Two goals, one root fix:

- **A. Rate:** 30 kS/s per channel, toward 32 channels (Dr. Oh's target).
- **B. Regularity:** the time between samples, with statistics — measured, not
  assumed.

**v2 change:** the bench found the current sampler is *bursty*, and the cure —
hardware-timed sampling — becomes Step 0 that everything else builds on.
Tags: **[bench]** = you at the hardware, **[AI]** = code I write.

---

## Where we stand (measured)

| Fact | Value | How we know |
|---|---|---|
| Single-bus word ceiling (SPIM00 + HW CSN, pure silicon) | **757,741 words/s** (1.32 µs/word) | hardware-counted free-run; data-validated (INTAN clean at 21.33 MHz, RXDELAY 5) |
| → 32 ch on one bus | **23.7 kS/s/ch** | 757,741 / 32 |
| → channels at full 30 kS/s on one bus | **25 ch** | 757,741 / 30,000 |
| Streaming demo (1 ch → Mac BLE) | 20 kS/s, 5 min, **0 lost** of 50,464 pkts | `run1_report.txt` |
| Sampling regularity, software-paced (BEFORE) | σ = 23.67 µs, min 6.75 / max 325.8 µs, **0.7%** within ±10% | 12,800 scope-measured CSN intervals, `measurements/before_sw_paced_20k/` |
| **Sampling regularity, hardware-timed (AFTER, 2026-09-24)** | **σ = 0.38 µs, min 19.0(1 glitch) / max 53.4(1 wrap) µs, 100.0% within ±10%** — 62× better | 12,843 scope-measured CSN intervals, `measurements/after_hw_timed_20k/` |
| macOS BLE ceiling | ~26–28 kS/s (15 ms interval, non-negotiable) | measured |
| nRF↔nRF BLE ceiling | ~1.05 Mbps (≈65 kS/s of 16-bit) | ble-rate tests |

**Why the bursts:** the sampler is a software thread pacing itself against
deadlines. The BLE controller runs at interrupt priority and stalls it; on
waking, the thread finds several deadlines expired and fires those CONVERTs
back-to-back (catch-up burst). Average rate is preserved exactly — which is
why the 5-minute log (20,000.3 S/s, 0 lost) never saw it. Only the scope
could. No receiver-side statistic can detect or refute this; the samples
carry values and order, not times.

**Consequence:** regularity is not a measurement problem to bolt on — it is a
design defect to remove. Hence Step 0.

---

## Step 0 — hardware-timed sampling engine — **DONE (2026-09-24)**

Implemented, debugged (DMA pointer rewind requires pausing the timer; wrap
gates on the hardware write position; DMA byte order is wire-order, swap on
read), data-validated (clean 997 Hz sine, 20 dots/period, 0 lost packets),
and measured: σ = 0.38 µs. Residuals worth knowing: mean read 49.83 µs
(+0.34%) — the 128 MHz HSFLL timer clock, not crystal-exact; one ~53 µs
interval per 1.64 s (the wrap's timer pause); one glitch edge in 12,843.
Original design notes below.

Take the CPU out of the timing path: a hardware timer fires each SPI
transaction in silicon. The radio can stall a thread or an interrupt; it
cannot stall a DPPI task trigger.

**Design (verified against the SDK/datasheet):**
- **TIMER00** (same fast domain as SPIM00 — DPPIC00 path already proven in the
  free-run test) in timer mode, `COMPARE0` + compare-clear short → periodic.
- TIMER00 `PUBLISH_COMPARE[0]` → DPPI channel → SPIM00 `SUBSCRIBE_START`:
  one 16-bit CONVERT per timer tick, hardware CSN pulsing per transaction as
  already validated.
- **RX side is where the risk moves — handle it:** an END-interrupt copy can
  itself be radio-delayed. Use **RX array-list DMA** (hardware auto-advances
  the receive pointer per transaction) into a large region, so the CPU drains
  lazily in chunks and hundreds of µs of blocking costs nothing. TX stays a
  fixed 2-byte CONVERT buffer (no post-increment).
- Software's only jobs: drain region → ring → BLE packets. Fully off the
  timing-critical path.

**Steps:**
1. **[AI]** Rewrite the acquisition core of `firmware/theo/src/main.c` as
   above (timer-fired transactions, array-list RX, chunked drain). Keep BLE
   path unchanged. Build.
2. **[bench]** Re-validate **data** in the new mode: the RXDELAY=5 fix was
   proven through the driver's transfer path, and the timer-fired path
   bypasses it per-transfer — so first run must show a clean 1 kHz sine (and
   an INTAN check), not assume it.
3. **[bench]** The before/after money shot: scope on **P2.05**, falling-edge
   trigger, **infinite persistence**. Current build = smeared clusters (take
   this photo FIRST, before reflashing). New build = knife-edge comb at
   exactly the sample period. That pair of photos is the regularity
   deliverable for Dr. Oh — better than any stats table.

**Honesty notes for the writeup:** 20 kS/s divides the 128 MHz timer base
exactly (6400 ticks); 30 kS/s does not (4266.67 → 29.998 or 30.005 kS/s,
~±70 ppm — below crystal tolerance, but say so). Regularity in this mode is a
property of the crystal + timer, verified externally by the scope.

---

## A. Rate

### A1 — 30 kS/s single-channel over BLE (the "30 dots per period" shot)
macOS caps delivery at ~26–28 kS/s, so this runs through the already-built
nRF relay (`firmware/theo-central`: connects at 7.5 ms, forwards to VCOM1
serial @ 921600).
1. **[bench]** Flash second DK with `theo-central` (pick its J-Link serial in
   the dialog). Kill any Mac-side `stream_plot.py` so the relay wins the
   connection.
2. **[AI]** Set 30 kS/s in the (new, Step-0) firmware + `stream_plot.py`;
   rebuild.
3. **[bench]** Reflash peripheral; run
   `python stream_plot.py --serial /dev/tty.usbmodemXXXX` (relay's VCOM1);
   log ≥5 min; `analyze.py`.
   **Done when:** 30.00 samples/period on the 1 kHz sine, 0 lost packets,
   report + scope persistence shot at 33.3 µs pitch saved.

### A2 — 32-channel round-robin at the measured ceiling
Same Step-0 engine, TX becomes a command list.
1. **[AI]** TX array-list walking `CONVERT(0..31)`; handle the Intan's
   two-command pipeline lag across the rotation (result i ← command i−2);
   packets carry interleaved frames; plot streams a selectable channel.
2. **[bench]** 1 kHz sine on in0: ch0 shows ~23.4 dots/period (timer set near
   the 757 k words/s ceiling / 32), all channels counted, zero drops.
   **Done when:** sustained ≥ ~750 k words/s with valid ch0 data — the
   thesis's T1+T2 evidence at the design point.

### A3 — closing the gap to 30 × 32 (architecture, not firmware)
960 k words/s cannot fit one SPI bus of this SoC (silicon floor above).
Options for the Dr. Oh discussion, in order of realism:
1. **Dual front-end, dual bus on the custom PCB:** 2 × RHD2132; SPIM00 carries
   ≤25 ch @ 30 k, a standard 8 Mbps SPIM carries the remaining ≥7 (its ceiling
   ≈ 395 k words/s). Decision must land **before** PCB layout.
2. **Accept the design point** (23.7 kS/s/ch × 32) — already inside the
   proposal's 20–25 k commitment; spike band (300 Hz–6 kHz) fully captured.
3. Rejected for the record: 32 MHz SCLK (violates Intan's 24 MHz cap), odd
   prescalers (silicon), shorter CSN-high (at Intan minimum), batching words
   under one CS (forbidden by RHD2000 protocol).

---

## B. Regularity (post-Step-0 this is verification, not rescue)

- **Primary instrument — scope on CSN (P2.05):** falling-edge trigger;
  period readout must sit at the sample period; infinite persistence shows
  jitter as smear width. Capture at 20 k and 30 k. (This scope's 2000-point
  record can't accumulate deep statistics — the persistence photo + stable
  period readout is the deliverable; quantitative depth comes from the
  option below if wanted.)
- **Optional in-band timestamps, hardware-measured:** GPIOTE event on the CSN
  edge → DPPI → TIMER capture = per-sample timestamps taken by silicon.
  Stream a burst; compute mean/σ/min/max of Δt in Python — dots at *measured*
  positions, Dr. Oh's request verbatim. Build only if the scope evidence
  isn't deemed sufficient.
- Removed as obsolete: software "slip statistics" — in hardware-timed mode
  there is no software schedule left to slip.

---

## Order

1. **[bench]** BEFORE photo: persistence shot of today's bursty CSN (current
   build still flashed — do this first, it's the baseline evidence).
2. **Step 0** build → data re-validation → AFTER photo at 20 k.
3. **A1** relay + 30 k + logged run + scope shot at 33.3 µs.
4. **A2** 32-channel round-robin at the ceiling.
5. **A3** dual-bus decision with Dr. Oh — before PCB layout.
