# Handoff: wireless neural headstage (cclosed), for building its interactive documentation

You are helping Fredrik Willumsen Haug build an interactive documentation website for his Harvard ES100 senior
thesis (Bioengineering; he is applying to EE PhD programs, aiming to become an analog/mixed-signal IC designer). The
site should explain the system, let a visitor explore how data moves through it, and show the measured results. It
lives in a separate repo from the system's source (`cclosed`). Everything below was established on the bench; numbers
are measured unless marked "on paper".

## How to work with Fredrik

- Keep replies short and give one step at a time. Long multi-topic answers frustrate him.
- Don't write code before he approves the plan. Never build or flash firmware; he does that.
- Say plainly when you don't know something, and don't present guesses as findings.
- Refer to bench results by capture file or build stage, never by date.
- No `Co-Authored-By: Claude` trailers on commits in his personal repos.
- He likes ASCII Input → Process → Output block diagrams.

## The one-paragraph story

A neural headstage digitizes extracellular signals with an Intan RHD2164 amplifier chip, reads it over SPI from a
Nordic nRF54LM20B microcontroller, and sends the data over Bluetooth Low Energy. Raw streaming saturates BLE at about
one channel at 30 kS/s, so the thesis question is: **how many channels can be carried reliably if the microcontroller
detects spikes on-chip and sends only short windows around each spike?** His advisor, Dr. Saehyuck Oh, gets 16
channels with high fidelity on a different MCU with a near-identical bench, and our MCU is more capable, so the goal is
to beat 16. The transport already carries 12 channels losslessly; what blocks it is **noise on the analog side that
rises with the total number of conversions per second**, which drowns the spikes as soon as more than one channel is
sampled at a useful rate. Finding and removing that noise is the current thesis problem.

## Signal chain

```
FB128 neural simulator (TDT)            ground truth: known spikes on every channel
   │  jumper wires to in0..in7
   ▼
Intan RHD2164 board                     64 amplifiers, 16-bit ADC, 0.195 µV per code
   │  SPI: SCLK P2.01, MOSI P2.02, MISO P2.04, CS P2.05 (16 MHz, CMOS signalling, jumper wires)
   ▼
nRF54LM20B DK ("headstage")             timer + DPPI trigger SPI in hardware; detect spikes or stream raw
   │  BLE 2M PHY, 7.5 ms interval, 244-byte notifications
   ▼
nRF54LM20B DK ("theo-central" relay)    BLE central; forwards each notification over UART
   │  921600 baud, framed A5 5A | len u16 | payload
   ▼
Mac (Python)                            live plots, logging, offline scoring, spike sorting
```

Power: the Mac powers the headstage DK over USB; the DK's VDD header pin (3.3 V from its regulator) powers the Intan
board; Intan REF and FB128 ground go to DK ground.

## Hardware

| Part | Role | Key facts |
|---|---|---|
| Intan RHD2164 | amplifier + ADC | 64 channels, max 1.05 MS/s total per 32-channel half; analog band set to 10 Hz to 7.5 kHz (or 10 kHz) |
| Intan board (his PCB) | carries the chip | decoupling caps at the chip, 100 Ω LVDS terminations fitted, LVDS_en tied to GND (CMOS mode): LVDS-ready if DK-side transceivers are added |
| nRF54LM20B DK ×2 | headstage + relay | Zephyr / nRF Connect SDK; SPIM00 driven directly through nrfx |
| TDT FB128 | simulator | modes SYNC (one identical spike every 10.50 ms, 95.2 Hz, about 350 to 550 µV trough), NORMAL (3 to 4 sortable units), HASH, TETRODE, TONE |
| Tektronix TBS2204B | scope | used to verify SPI timing against the datasheet |

## Firmware apps (`cclosed/firmware/`)

| App | What it does |
|---|---|
| `theo` | raw streaming: every sample, channels interleaved. Frozen reference |
| `prestno` | the clean main firmware: on-chip spike detection, sends windows (`RAW_STREAM 0`) or raw (`RAW_STREAM 1`) |
| `spike` | development copy of the event firmware, frozen |
| `theo-central` | the relay DK |
| `debug` | copy of theo for experiments (burst SPI timing, see below) |
| `legacy/` | summer proofs: BLE rate tests, on-chip classification pilot |

### How acquisition works (the interesting engineering)

- A hardware timer fires at the conversion rate and triggers the SPI peripheral through DPPI; the CPU never times a
  sample. The SPI DMA walks a long TX list of 16-bit CONVERT commands and an RX list, so sampling runs with no CPU
  involvement. Timing jitter fell from 23.7 µs (software-paced) to 0.38 µs (hardware-timed).
- The Intan pipeline returns each result two commands late, so the TX list is offset by two.
- When the RX region fills (about every 1.7 s), acquisition restarts cleanly so every packet starts on channel 0.
- Bugs found and fixed along the way are good documentation material: a **stale-read bug** (DMA pointer advances when
  a conversion starts, so reading up to it returned last pass's sample; fingerprint: 15 to 18% of samples identical to
  the sample 36,864 earlier; it faked "noise" and shrank spikes 10%); a **restart-path bug** (SPI left in list mode
  corrupted data after restarts); a **relay UART bug** (byte-at-a-time FIFO fills lost 40% of frames).

### On-chip spike detection (prestno)

300 Hz high-pass biquad (plus 6 kHz low-pass only when the analog band exceeds it), running noise estimate, 4σ
threshold, 3 ms dead time, window aligned on the raw trough, 61 samples at 30 kS/s (Kilosort default). Each event
carries its channel and its own sample index, so spike times are exact.

### Packet formats

| | Raw | Event |
|---|---|---|
| Notification | `seq u16` + 120 samples u16 LE, offset binary (32768 = 0 V), 242 bytes | one or two events, 101 bytes each at 30 kS/s |
| Event | | `seq u16, channel u8, n_samples u8, pre u8, trough_index u32`, then 12-bit samples packed two per 3 bytes (3.12 µV per step) |
| Channel order | sample k is channel k mod N_CH | in each event |
| Rate, 1 ch × 30 kS/s | 484 kbit/s | about 77 kbit/s in SYNC |

## Throughput budgets

| Link | Ceiling |
|---|---|
| SPI (one-edge read) | about 770k conversions/s, on paper |
| BLE to an nRF relay | about 1.05 Mbit/s |
| BLE straight to a Mac | about 450 to 470 kbit/s at best; the Mac accepts few packets per connection event and has dropped to about 210 kbit/s |
| Relay UART at 921600 | about 737 kbit/s payload |

Raw streaming fits about one channel at 30 kS/s. Event streaming carried 12 channels × 20 kS/s with zero drops; relay
UART drops start at 14 channels.

## Results to showcase

**Validation of the chain.** FB128 tone measured at 761 Hz (spec about 763), confirming the 0.195 µV/code calibration;
zero lost packets in 28,112; SYNC capture locked at 10.50 ms with essentially 100% detection.

**Experiment 1, sample rate at one channel** (device detections vs SYNC truth): 30k 77%, 20k 94%, 15k 86%, 10k 89%,
6k 73%; 0 lost packets; 19 to 29 µs jitter. 20 kS/s is the best rate.

**Experiment 2, channel count at 20 kS/s:** detection collapses: 1 ch 94%, 2 ch about 23%, 4 ch about 1%, 6+ ch about
0%. Device noise estimate rises about as √N: 86 → 124 → 158 → 183 → 208 → 232 µV for 1, 2, 4, 6, 8, 10 channels.
Transport stayed lossless the whole way. This is the central figure of the thesis problem.

**Offline spike sorting** (`sorting/`): bandpass 300 to 4000 Hz, threshold, trough alignment, PCA(3), HDBSCAN. A
5-minute NORMAL capture (`fredrik_questioning.bin`, 1 ch, 10 kS/s) gives 4 clean units plus a weak fifth. An earlier
offline classifier (nearest template) matched the sorter 98 to 100% on held-out data.

## The noise investigation (the detective story)

- Noise depends on **total conversions per second** (channels × rate), not on channels or rate alone.
- With the input shorted to the Intan reference, noise is still about 300 µV per sample at 160k conversions/s (spec:
  2.4 µV), so it is made at conversion, not picked up by input wires, and the bits read back correctly.
- Intan datasheet p.12, "Increased Noise Levels with Standard CMOS Signaling": CMOS SPI at high ADC rates raises
  amplifier noise, worse with long high-capacitance wires; CMOS recommended only up to 175 kS/s total; LVDS otherwise.
- A 100 Ω series resistor on MISO at the Intan end cut fast noise 2 to 3×: strong evidence the switching of the SPI
  lines couples into the chip, though not proof it is the whole cause.
- Ruled out: CPU load, multiplexer switching, ADC bias settings, grounding variants, SPI bit errors.
- **Scope work:** all SPI timing meets the RHD2164 datasheet with wide margin at 1 and 2 channels (16 clocks per frame,
  about 62 ns clock period, CS-to-clock about 170 ns, clock-to-CS about 270 ns; CS period 83 µs at 1 ch × 12 kS/s,
  41 µs at 2 ch). Apparent clock overshoot (−1.4 V to +5.3 V) was shown to be a probing artifact: CS is clean when the
  clock probe is removed.
- **Dr. Oh's diagnosis, being tested:** his system sends all channels' conversions as a back-to-back burst (about
  100 ns between frames) once per sample period; ours spreads them evenly. `firmware/debug` now has a burst mode
  (`BURST_STEP_NS`) to test whether this changes the noise. Result pending.
- Open paths: LVDS transceivers on the DK side, shorter wires, or a custom PCB (Intan + regulator + nRF54 on one board).

## Mac-side tools (`cclosed/firmware/theo`, `firmware/prestno`, `sorting/`)

`stream_plot.py` (live plot, 300 Hz high-pass, space bar pauses; `--serial PORT` for the relay or direct BLE without
it), `log_stream.py` / `log.py` (record), `verdict.py` (judge a raw capture), `score.py` (judge device events against
SYNC truth), `sweep.py` (all captures into tables and figures), `single_channel_spike_sorting.py`. Existing figures
worth reusing live in `firmware/prestno/` (`sweep_rate.png`, `sweep_channels.png`, `sweep_caught.png`,
`benchmark_table.png`) and `sorting/out/`.

## Ideas for the site's interactive parts

- Click-through signal chain: each block expands into its hardware, firmware and numbers.
- SPI timing explorer: a frame drawn to scale (CS, SCLK, MOSI, MISO with DDR), with datasheet limits overlaid and the
  even-spacing vs burst scheduling toggle.
- Throughput calculator: channels × rate × format → bits/s against each ceiling (SPI, BLE to relay, BLE to Mac, UART).
- Noise vs conversions/s plot with the experiment points, and detection rate vs channel count.
- Packet inspector: paste or load bytes, see them decoded in either format.
- Spike-sorting gallery: units, waveforms, PCA clusters.
