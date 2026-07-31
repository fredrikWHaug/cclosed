# Project Log & Roadmap

> **Summary.** The living "where are we / what's next" page. Durable how/why lives
> in the topic docs ([architecture](system-architecture.md),
> [SPI link](spi-acquisition-link.md), [classifiers](on-chip-classifiers.md),
> [cross-day](cross-day-generalization.md)); this page is the chronological status
> and roadmap that points into them.

_Last updated: 2026-07-21._

## Status at a glance

| Area | State | Detail |
|------|-------|--------|
| **End-to-end on-chip chain** | ✅ **demonstrated on hardware** | raw `.rhd` → SPI → nRF54 (biquad/CMR/decimate/detect/classify) → BLE → host; 5.3× real-time, `real mismatches 0` |
| SPI acquisition link | ✅ working & understood | Real neural data transferred between two DKs, checksum-verified — [spi-acquisition-link.md](spi-acquisition-link.md) |
| On-chip classifiers | ✅ benchmarked on silicon | logreg / CNN / ResNet build & run; fidelity saturates at the cheap end — [on-chip-classifiers.md](on-chip-classifiers.md) |
| Cross-day generalization | 🟡 baseline done | Conservative host-side floor (no drift cost, but low-power) — [cross-day-generalization.md](cross-day-generalization.md) |
| Real Intan hardware | ⬜ not started | Open hardware questions in [system-architecture.md](system-architecture.md#open-hardware-questions) |

## Log

### 2026-07-31 — Both data-rate ceilings measured; SPI is the harder wall

Pushed the BLE link to its true breaking point and pinned the SPI budget with real
numbers. Documented in
[system-architecture.md](system-architecture.md#the-two-data-rate-ceilings-both-now-measured-2026-07-31).
Headlines:
- **BLE egress ceiling = ~1.05 Mbps**, proven — held against three attempts to
  raise it. BLE **back-pressures, it does not drop**, so "0 drops" never meant "at
  the max." Forcing loss needs a free-running producer + bounded buffer.
- **SPI ingestion is the *tighter* wall.** SPI clock ≈ bit rate; Intan caps SCLK at
  24 MHz → **24 Mbit/s single-edge < 30.7 Mbit/s** for 64 ch. So **DDR is
  throughput-mandatory**, and the nRF has only one SPI fast enough (HS ≤ 32 MHz; the
  six 8 MHz instances can't carry even 32 ch @ 30 kS/s). Fork sharpened: FPGA-free
  DDR (fragile) vs. 32 ch on one clean lane vs. drop to ~20 kS/s.
- **nRF SAADC ≠ Intan:** on-chip ADC is 14-bit, 8 ch (AIN0–7), *no gain stage* — the
  real reason Intan exists is the per-channel amplifier (×192) *before* the ADC, not
  the extra bits or channels.
- Added `offline-reference/peek_rhd.py` — dumps raw `uint16` ADC codes straight from
  any `.rhd` (raw codes on disk; the `0.195×(code−32768)` → µV conversion is
  software, post-load).

### 2026-07-24 — Intan datasheet reference added

Read the RHD2000-series (40 pp) and RHD2164 (16 pp) datasheets in full and distilled
them into a page-cited reference: [intan-rhd-reference.md](intan-rhd-reference.md).
Durable so future sessions (or fresh AI instances) don't re-derive from the PDFs.
Key takeaways now grounded, not assumed:
- **Sample rate is set by the controller's CONVERT cadence, not a chip register**
  (no internal clock); ceiling 30 kS/s/channel.
- **64 channels (RHD2164) needs DDR SPI** (both clock edges) — standard nRF SPI
  captures only 32 of 64. Open design fork: RHD2164+DDR vs 2×RHD2132.
- Manual CS-per-word is *required* by the chip (CS falling edge triggers the sample).
- Raw 64-ch rate ≈ 30.7 Mbit/s vs ~1.05 Mbps BLE → the ~30× gap is the thesis.
- Intan ships an STM32 SPI+DMA reference firmware worth reading before nRF work.

### 2026-07-24 — Serial monitor finalized (binary output, 80/20)

Closed out the bandwidth push with the single high-value change and stopped there:
the real streaming path is **BLE** (characterized separately — see
[ble_bitrate_plan.md](../firmware/ble-rate/ble_bitrate_plan.md), ~1.05 Mbps), so the
UART counter monitor only needs to be a solid **drop** tool, not hit 30 kHz.

**Done (Stage B — binary output):**
- slave: `printk("%u\n")` → raw 2-byte little-endian `uart_poll_out`. Removes the
  per-word ASCII formatting cost that was the actual bottleneck.
- `monitor.py`: reads the 2-byte stream, locks onto the counter ramp (skips the boot
  banner, resyncs one byte on slip). Rate is now **total ÷ wall-clock elapsed** — the
  old per-arrival rate was a burst-read artifact (it reported a bogus **1.5 MHz**
  because buffered serial timestamps values at *processing* time, not arrival).

**Measured on hardware (0 drops):** ~**4.1 kHz** sustained, clean ramp — ~1.8× the
old ~2.3 kHz ASCII path. Bottleneck is now the **master's SPI loop** (~240 µs/word
from the 100 µs CS busy-waits + SPIM overhead), not the slave; the slave's UART has
ample headroom. (The earlier ~8 kHz estimate was ~2× high — the board settled at 4.1.)

**Honest limitation:** true per-sample jitter is **not measurable** over buffered USB
serial — the OS delivers data in chunks, so any inter-arrival figure reflects host
buffering, not the link. Removed `monitor.py`'s jitter readout; the sequence-based
**drop** detection remains fully valid.

**Not done (deliberately):** reaching 30 kHz would need trimming the master's CS
busy-waits (option B) — low value now that BLE is the real transmit path.

### 2026-07-22 — Serial monitor + bandwidth push (`feature/monitor-limit-push`, Stage A)

**Context.** The counter test (`firmware/spi/{master,slave}` + `monitor.py`) is the
tool Dr. Oh asked for: master streams an increasing counter, slave echoes it to the
laptop over serial, `monitor.py` graphs it to expose **dropped words** (sequence
gaps) and **streaming delay/jitter** (inter-arrival time). Working and understood —
one counter at the source, Python checks each arrival is `last+1`; forward gap =
drop, backward jump = reorder (a reset). x-axis = # samples received since
`monitor.py` launched; y (sequence plot) = master's counter value; healthy stream =
slope-1 diagonal, and the vertical offset from `y=x` equals total drops.

**Goal of this branch.** Push the monitor's throughput from the ~2 kHz serial
ceiling up to the **real per-channel acquisition rate = 30 kHz** (`.rhd` `fs=30000`;
one channel = 30k × 16-bit = **60 KB/s**). The SPI link is not the limit — getting
values to the laptop is. Ladder: ASCII→binary (3×), 115200→1 Mbaud (~9×), and speed
up the master loop (it's capped ~8 kHz by the 100 µs per-word CS busy-waits).

**Stage A done (baud only, ASCII kept):**
- slave overlay: `&uart20 { current-speed = <1000000>; }` (console → 1 Mbaud)
- master: `SEND_PERIOD_US` via `k_usleep` (was `k_msleep`), pushed to run flat-out
- `monitor.py`: default baud → 1000000
- new `firmware/spi/serial_probe.py`: measures true bytes/sec + dumps raw bytes
- slave prints its compiled baud at boot (`DT_PROP(DT_CHOSEN(zephyr_console), current_speed)`)

**Where we are (the open thread).** Merged devicetree confirms the build IS at
1 Mbaud (`current-speed = <0xf4240>`). But `serial_probe.py` still reads ~13.7 KB/s
(~1953 values/s), clean, counting up by 2 (~50 % dropped). 13.7 KB/s slightly
*exceeds* the 115200 ceiling (11.5 KB/s), so the board is probably already faster —
meaning the bottleneck **moved from the UART to the slave's per-word ASCII `printk`**
(the master outruns the slave's produce loop). Ambiguous until the next test.

**NEXT STEP (do this first on resume):** read the *same* stream at 115200 —
`python firmware/spi/serial_probe.py --port <slave> --baud 115200`.
- **garbage** → board IS faster than 115200 → 1 Mbaud worked → bottleneck is the
  slave `printk`, so go to **Stage B**.
- **clean** → still 115200 at the link → investigate why.

**Stage B (planned):** replace the slave's ASCII `printk("%u\n")` with **raw binary**
(`uart_poll_out` of the 2 bytes) — fewer bytes AND a cheaper output path — and have
`monitor.py` read 2-byte values (needs start-up alignment on the monotonic counter).
Then trim the master's per-word CS busy-waits to break the ~8 kHz send cap, and dial
`SEND_PERIOD_US` toward 33 µs (30 kHz). Target: one channel at 30 kHz, 0 drops.

**Gotchas banked this session:** overlay/devicetree changes need a **pristine build**
(incremental skips them); `k_msleep` is integer-ms (use `k_usleep` for sub-ms —
`0.5` truncated to `0` = full speed); the debugger VCOM's baud dropdown caps at
256000 but takes a custom `1000000` (8-N-1, no flow control); the **200 Hz baseline
lives on `dev`**. Firmware changes for Stage A are stashed on this branch; this note
is committed so it survives.

### 2026-07-21
- **Full on-chip classification chain, end to end on two DKs** (`feature/end-to-end`).
  Built the honest pipeline from raw `.rhd`:
  - `dataset/build_onchip.py`: training set from raw ADC codes through the
    on-chip-*feasible* chain — causal biquad 300–3000 Hz + per-shank CMR + decimate
    30k→10k + trough realign — **not** the offline whitened recording (whitening
    can't run on-chip). Alignment verified corr 0.99; 64 ch = shanks [0,1,2,3,6,7,8,9].
  - `model/train_onchip.py`: per-shank logreg, forward-in-time split, **~0.98
    balanced** on shanks with distinct units; the over-split neuron (shank 1)
    correctly sits at chance (waveform corr +1.00).
  - On-chip pipeline (`firmware/classifiers/onchip`) verified **bit-for-bit** vs
    host: biquad → CMR → decimate → threshold-detect → classify.
  - Full chain (`firmware/pipeline/{slave,master}` + `sim/ble_receiver.py`): slave
    streams raw codes over SPI (**72000/72000 intact**) → master classifies
    (**57 ms for 300 ms of data = 5.3× real-time**) → BLE `(unit,timestamp)` to the Mac.
  - Honest caveat: host↔MCU disagreements occur only on genuine **near-tie** spikes
    (float boundary, host top-2 margin < 0.5); `real mismatches 0`.

### 2026-07-20
- **SPI link:** basic counter link + `monitor.py` (drop/jitter measurement); then
  `ndspi` — transferred a real 8-channel spike snippet master↔slave and
  checksum-verified it. Key lesson: per-word framing duplicated samples; fixed
  with **one transaction per frame**. Details:
  [spi-acquisition-link.md](spi-acquisition-link.md).
- **Cross-day data landed:** two consecutive MA1 sessions sorted, plus
  `MA1_match_dict_final.json` for cross-day identity. Decoded the match schema and
  verified 4 neurons tracked across both days (template corr 0.95–0.99).
- **Cross-day baseline committed** (`a8ef437`): logreg on peak-channel waveforms,
  train day 1 / test day 2 → balanced accuracy 0.66 → 0.68 (no drift cost).
  Documented as a conservative floor. Details:
  [cross-day-generalization.md](cross-day-generalization.md).
- **Docs unified** into this `documentation/` set with a README landing page.

## Roadmap (each its own feature branch)

- [ ] **Same-shank 8-channel detection** — the cross-day version with real
  discriminative power: full footprint, distractors on the *same* shank so
  location can't be exploited. Vary one axis at a time (within-day single-channel
  vs. across-day 8-channel) to separate "drift cost" from "channel cost."
- [ ] **CNN** on that footprint task — capacity helps only where spatial
  information exists, not on the near-identical single-channel task.
- [x] **Close the on-chip loop** — DONE (`feature/end-to-end`): the full
  raw → SPI → classify → BLE chain runs on two DKs, verified bit-for-bit and
  faster than real time.
- [ ] **Original thesis experiment** — offline compression-vs-fidelity on existing
  recordings: place fields + decoding error under each compression scheme (see the
  [spectrum](system-architecture.md#compression-vs-fidelity-spectrum)) to find the
  minimum viable representation.
- [ ] **Multi-session-per-day pairs** (some mice have them) for a shorter-interval
  drift comparison, once that data is local.

## Literature thread

High bar — skeptical of hype / synthetic-only / uncited claims. Working takeaways:

- Real "on-implant real-time *full* spike sorting" is largely aspirational. Most
  working BMIs use **threshold crossings**, not sorting. Surveys (e.g. Zhang 2023)
  assert the need but cite efficiency/offline architectures, not demonstrations.
- The online per-spike step is **template matching / classification**, not spike
  sorting — clustering stays offline (see design decision 4 in
  [system-architecture.md](system-architecture.md#key-design-decisions)).
- **SpikeForest** + **MEArec / SpikeInterface** are the rigorous
  fidelity-measurement tools, aligned with the thesis framing.

_Fredrik found new literature recently — may shift the roadmap; to be folded in._
