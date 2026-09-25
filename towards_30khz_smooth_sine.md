# Toward 30 kS/s with a smooth sine — parked state & next steps

Parked on 2026-09-24, mid-bench, to pivot to the FB128 signal. Everything
below is ready to resume without re-derivation.

## Where we stand (all verified today)

- **Hardware-timed acquisition engine works**: TIMER00 (128 MHz/6400) → DPPI
  ch 7 → SPIM00 START; RX ArrayList DMA into an 80 KB region; timer-paused
  pointer rewind every 32,768 samples; byte-swap on drain (DMA stores wire
  order). Stable for minutes: no overruns, no faults, wraps metronomic
  (3.66/6 s as predicted), 0 lost packets.
- **Regularity measured (the deliverable):** before σ = 23.67 µs (0.7% within
  ±10%) → after **σ = 0.38 µs (100.0% within ±10%)**, 62× improvement, over
  ~12.8 k scope-measured CSN intervals each. Artifacts:
  `firmware/theo/measurements/before_sw_paced_20k/` and `after_hw_timed_20k/`.
- Clean 997 Hz sine at 20 dots/period over BLE to the Mac at 20 kS/s.

## Parked item 1 — the trough zigzag (do FIRST when resuming)

Symptom: adjacent-sample zigzag of ±400–500 µV near sine troughs (e.g.
−250/−800/−280/−700), far above analog noise, not explainable by the 20.06
samples/period phase precession (monotonic sine segments can't zigzag).

Suspicion: **marginal MISO bit errors at 21.33 MHz on dynamic data** —
±400/±800 µV ≈ single flips of bit 11/12 (2048/4096 codes × 0.195 µV). The
RXDELAY=5 choice was validated on static ROM bytes only; real ADC words
toggle many bits, electrically harder.

Experiment (one variable): drop SCLK 21.33 MHz → **8 MHz** at 20 kS/s
(single-channel needs only ~30 k words/s; 21.33 MHz is for the future 32-ch
case). If zigzag vanishes → confirmed; note that the 32-channel build must
revalidate RXDELAY against dynamic data. Optional tooling: add a
sample-to-sample delta histogram to `analyze.py` (bit errors show as discrete
±2^n spikes; analog noise is Gaussian).

## Parked item 2 — 30 kS/s single-channel (plan A1, everything prebuilt)

Sampling side is trivial (engine ceiling 757 k words/s; 30 k uses 4%):
`RATE_HZ 20000 → 30000` in `firmware/theo/src/main.c` and `RATE` in
`stream_plot.py` (CC = 4267 → 29.998 kS/s, ±70 ppm rounding — note in
writeup). The blocker is delivery: 480 kbps > macOS's ~26–28 kS/s ceiling
(15 ms interval). Path: **second DK flashed with `firmware/theo-central`**
(built; connects at 7.5 ms, relays to VCOM1 serial @ 921600), then
`python stream_plot.py --serial /dev/tty.usbmodemXXXX`. Steps:
1. Fix zigzag first (item 1) so 30 k inherits clean data.
2. Flash second DK with theo-central (pick its J-Link serial in the dialog);
   kill Mac-side stream_plot so the relay wins the connection.
3. Flip both rate constants, rebuild, reflash peripheral.
4. Verify: relay console `[relay] ~250 pkts/s ... ble_drops 0`; plot shows
   **30.0 dots/period**; log 5 min (`--log`), run `analyze.py`.
5. Scope after-capture at 33.3 µs nominal (same procedure, 5M pts) →
   `analyze_csn_csv.py <csv> 30000` → archive as
   `measurements/after_hw_timed_30k/`.

## Parked item 3 — small notes for the writeup

- Mean interval read 49.83 µs (+0.34%): the 128 MHz HSFLL timer clock is not
  crystal-exact and wanders slightly (also the ±1 µs band thickness). Fine
  for spike detection; state it. Crystal-locked timer source is the knob if
  exactness ever matters.
- The single ~53.4 µs outlier per capture = the wrap's timer pause (once per
  1.64 s, by design). Put it in the figure caption, don't hide it.
- Raw scope CSVs (~96 MB each) still on the USB stick only — archive
  somewhere off-repo if reproducibility matters.
- 32-channel round-robin (plan A2) builds on this same engine: TX becomes a
  command list, plus the two-command pipeline lag across channels, plus
  dynamic-data RXDELAY revalidation at 21.33 MHz (see item 1).
