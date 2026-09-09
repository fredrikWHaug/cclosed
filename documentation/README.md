# On-Device Classification of Neural Action Potentials for Wireless Unit Transmission over Bluetooth Low Energy

# NB! Just started editind this but it's just a bunch of AI SLOP anyways so frankly, start over and build this shit the real way. I'm boutta start that right now.

The engineering problem at hand is optimizing fidelity as a function of compression:
how far can neural data for systems neuroscience be compressed on the headstage of a
rodent before it stops being scientifically useful.

This file contains the complete documentation reference for the project. It can also be found at website/documentation.

## Table of Contents

1. [System Architecture](#1-system-architecture) — current hardware, the active firmware, the real signal path, and the two measured throughput ceilings.
2. [Intan RHD Reference](#2-intan-rhd-reference) — the Intan front-end distilled from the datasheets: sampling, SPI protocol, register map, the 64-channel DDR constraint, power.
3. [Project Log and Roadmap](#3-project-log-and-roadmap) — the living status and roadmap: the hardware bring-up story, what's done, what's next.

- [Ideation and Planning](#ideation--planning) — deferred/forward-looking notes (classifier ladder, benchmark plan, PCB package, SPI scaling, research background).

## Status at a Glance

- **Intan RHD2164**: bonded, powered, SPI-verified alive (ROM reads `"INTAN"`).
- **Real signal path, one channel**: validated end-to-end — function-generator
  sine → real Intan → SPI → nRF54 → BLE → laptop, cross-checked two independent ways.
- **BLE ceiling**: ~1.05 Mbps / ~65,500 samples/s, actually found (not just
  "0 drops observed").
- **SPI ingestion ceiling**: 24 Mbit/s single-edge (Intan's 24 MHz cap) — the tighter wall.
- **On-chip classifier / compression work**: removed from the working tree,
  preserved in git history, deferred until the signal path above is solid.

## Conventions

- Board target: `nrf54lm20dk/nrf54lm20b/cpuapp`, nRF Connect SDK v3.3.1.
- Firmware is built and flashed via the VS Code Nordic extension.

---

## 1. System Architecture

> **Summary.** The long-run scientific question is **compression vs. fidelity**:
> how far can neural data be squeezed *on the chip* before it stops being
> scientifically useful. That work (spike classifiers, on-chip pipeline) was
> deliberately set aside — see the [Project Log](#3-project-log-and-roadmap) — to
> first prove the physical signal chain end-to-end on real hardware. **This
> section describes only what's currently real and in the repo.**

### Current hardware

| Component                 | Detail                                                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **MCU**             | nRF54LM20B — 128 MHz Cortex-M33, 2 MB NVM, 512 KB RAM, BLE                                                                           |
| **Dev kit**         | nRF54LM20 DK (PCA10184), target`nrf54lm20dk/nrf54lm20b/cpuapp`                                                                      |
| **Analog frontend** | A real, bonded**Intan RHD2164** (64-ch, BGA) on a custom board — bring-up complete, SPI-verified alive (ROM reads `"INTAN"`) |
| **Toolchain**       | nRF Connect SDK v3.3.1 (Zephyr), VS Code extension, J-Link                                                                            |

The RHD2164 is real silicon now, not an emulation — getting it powered, wired,
and talking took a genuinely hard bring-up (BGA reflow, LVDS_en mode select,
grounding both `in0` and the reference input). See the
[Project Log](#3-project-log-and-roadmap) for that story.

### What's actually running (3 firmware projects, `firmware/`)

| Dir                           | What it does                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `board-bring-up/`           | Minimal SPI ROM read — proves the Intan is powered and talking. No BLE, no config writes.                                                                                                                                                                                                                                                                                                      |
| `signal-path-intan/master/` | Configures the real Intan (10 Hz–10 kHz band, amps on, calibrated), samples**channel 0 at a fixed rate**, streams over BLE. `receiver.py` plots it live on the laptop. **Currently one channel, validated end-to-end with a real function-generator sine** — cross-checked two independent ways (raw SPI print vs. BLE-relayed plot; both agree on amplitude and cycle timing). |
| `ble-rate/`                 | Pure BLE throughput characterization (master/slave/central), independent of the Intan — where the two ceilings below were measured.                                                                                                                                                                                                                                                            |

Everything else that used to live here — spike classifiers, the on-chip
detect/classify pipeline, the two-DK Intan emulation, cross-day generalization —
was intentionally removed from the working tree (commit `8b83a89`, "everything
but board bring up, signal path intan, and ble-rate for backup"). It's in git
history if it's ever needed again; it is **not** part of the current build and
nothing below describes it.

### The current signal path (real, one channel)

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

Module and flow diagrams for this path:
[flow](signal-path-intan-master-flow.svg) ·
[modules](signal-path-intan-master-modules.svg).

### The Two Measured Ceilings (2026-07-31, `ble-rate/`)

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

### Open questions (current, not aspirational)

- **Push `signal-path-intan` toward its real ceiling** — currently sampling
  well under both the SPI and BLE limits above; next step is finding where it
  actually breaks for one channel.
- **Channel count fork** (unchanged from the datasheet-level analysis): full
  64 ch @ 30 kS/s needs DDR (fragile, FPGA-free trick or a hardware DDR
  receiver) vs. scoping to 32 ch on one clean SPI lane vs. dropping sample rate
  to fit more channels — see [Intan RHD Reference §6](#6-the-64-channel-problem-rhd2164-and-ddr).
- **Multi-channel on the current real chip** — `signal-path-intan` only reads
  channel 0 today; round-robin CONVERT across more channels is the natural
  next step once single-channel throughput is understood.

### The deferred thesis question

The original scientific goal — how much can neural data be compressed on-chip
(raw voltage → threshold crossings → embeddings → sorted unit IDs) before it
stops being useful — is unchanged as the eventual target, but the classifier
work that explored it was removed from the repo to focus on hardware first (see
the [Project Log](#3-project-log-and-roadmap)). It will come back once the real
signal path is solid enough to feed it real, not emulated, data.

---

## 2. Intan RHD Reference

> **Why this section exists.** The Intan RHD is the analog front-end + ADC of this
> whole project — it's where sampling actually happens. This is a distilled,
> **page-cited** reference so no future session (you or a fresh AI instance) has to
> re-derive it from the PDFs. Every non-obvious claim cites a page.
>
> **Sources** (local PDFs, not in the repo):
>
> - `Intan_RHD2000_series_datasheet.pdf` — the general part (RHD2216/2132). Cited **[DS p_N_]**.
> - `Intan_RHD2164_datasheet.pdf` — the 64-channel variant. Cited **[2164 p_N_]**.
>
> Verified against both datasheets on 2026-07-24.

### TL;DR — the ten things that matter

1. **The sample rate is NOT a chip register — the controller (our nRF54) sets it** by how fast it issues `CONVERT` commands. The chip has no internal clock. [DS p35, p37]
2. **Ceiling = 30 kS/s per channel** (1.05 MS/s aggregate ÷ 35 multiplexed slots). [DS p7, p15]
3. Amplifier **gain is fixed at 192**; ADC step **V_LSB = 0.195 µV** at the electrode. [DS p6]
4. **Analog bandwidth IS configurable** in registers: upper cutoff f_H (100 Hz–20 kHz) and lower cutoff f_L (0.1–500 Hz). [DS p6, p25–26]
5. An **on-chip DSP high-pass** (Reg 4) does offset removal on-chip, in hardware. [DS p33]
6. **SPI is mode 0, 16-bit MSB-first, and CS must pulse high between *every* word** — the CS falling edge is what triggers each ADC sample. Our manual-CS firmware is *required*, not a workaround. [DS p15]
7. Protocol is **pipelined**: a `CONVERT` result comes back **two commands later**. [DS p16]
8. **64 channels (RHD2164) needs double-data-rate (DDR) SPI** — sampling MISO on *both* clock edges. Standard SPI (one edge) gets you **32 of the 64 channels**. This is the key nRF constraint. [2164 p9–11]
9. **Raw data rate is enormous**: 64 ch × 30 kS/s × 16 bit = **30.7 Mbit/s**. Our BLE ceiling is ~1.05 Mbps → a **~30× gap**. That gap *is* the compression thesis.
10. **Intan ships reference MCU firmware** (STM32, SPI + DMA, ≤20 kHz/ch) — read it before writing much nRF code. [DS p37]

### 1. The family

| Device            | Amps         | Inputs                       | Package         | Chip ID (Reg 63) |
| ----------------- | ------------ | ---------------------------- | --------------- | ---------------- |
| RHD2216           | 16           | 16 × differential (bipolar) | 8×8 mm 56-QFN  | 2                |
| RHD2132           | 32           | 32 unipolar + 1 common ref   | 8×8 mm 56-QFN  | 1                |
| **RHD2164** | **64** | 64 unipolar + 1 common ref   | 9×7 mm 104-BGA | **4**      |

[DS p2; 2164 p2, p14]. The real chip now bonded and bring-up-verified on the bench is a **RHD2164** — see §6 for why 64 channels is a genuinely harder problem than 32.

### 2. Signal chain (one channel)

```
electrode ─► AC-coupled amp ─► programmable band-pass ─► MUX ─► 16-bit SAR ADC ─► SPI
             (gain 192,          f_L (high-pass)                  V_LSB = 0.195 µV
              DC rejected)        f_H (3rd-order LP,               @ electrode
                                  anti-alias)
```

- **Gain 192** (45.7 dB) in the mid-band; DC gain is 0 (internal caps fully reject electrode DC offset). [DS p6]
- **V_LSB = 0.195 µV** referred to the electrode (16-bit ADC over the amplifier gain). Aux inputs: 37.4 µV; supply sensor: 74.8 µV. [DS p6]
- **Input-referred noise 2.4 µV_rms**; linear input range **±5.0 mV**; tolerates **±0.4 V** electrode DC offset before the ESD diodes conduct. [DS p6–7]
- The `.rhd` code→µV conversion we use (`0.195 × (code − 32768)`) is exactly V_LSB with offset-binary centering. [DS p6, p20]

### 3. Sampling rate — set by the controller, not a register  ← the headline

The datasheet is blunt about this, twice:

> "The rate and timing of SPI commands sent to the chip determines the ADC sampling rate; sample times are set by the falling edge of CS." [DS p35]
>
> "The RHD2000 chips have no internal clock. The ADC sampling rate is entirely set by the rate at which CONVERT commands are sent over the SPI bus." [DS p37]

**How you set it:** run the round-robin `CONVERT(0), CONVERT(1) … CONVERT(31)` (+ a few aux slots) and **repeat the whole sequence at the desired per-channel rate R**. [DS p35]

- **Ceiling: 30 kS/s per channel.** Max MUX rate f_MUX = 1.05 MHz [DS p7]; total cycle time t_CYCLE ≥ 950 ns [DS p15] → 1.05 MS/s aggregate ÷ 35 multiplexed slots (32 amps + 3 aux) = 30 kS/s each. Continuously settable *below* that — nothing forces 30 k.
- **Two registers must match the rate you pick:** ADC **buffer bias** (Reg 1) and **MUX bias** (Reg 2) have optimum values that depend on total ADC rate — lookup table at [DS p27]. (e.g. ≤120 kS/s total → buffer bias 32 / MUX bias 40; ≥700 kS/s → 2 / 4.)
- **Anti-aliasing couples rate and bandwidth:** f_H is the anti-alias filter, so set f_H below Nyquist (R/2). Wideband neural uses R = 30 kS/s with f_H ≈ 10 kHz. [DS p7 Fig 7, p24]

### 4. Analog bandwidth & on-chip DSP (the real register config)

- **Upper cutoff f_H** (low-pass, 3rd-order Butterworth): Registers 8–11 (RH1/RH2 DACs). On-chip range **100 Hz–20 kHz**; exact register values tabulated at [DS p25]. [DS p22, p24]
- **Lower cutoff f_L** (high-pass, 1st-order): Registers 12–13 (RL DACs). On-chip range **0.1–500 Hz**; values at [DS p26]. [DS p22, p24]
- **On-chip DSP high-pass** (Reg 4 `DSPen` + `DSP cutoff freq[3:0]`): a 1st-order IIR high-pass on every channel for residual-offset removal; cutoff f_c = k_freq · f_sample [DS p33]. **This is the on-chip equivalent of the causal biquad high-pass we run on the nRF** — it could be offloaded to the chip.
- **Output format** (Reg 4): `twoscomp` (signed vs offset-binary) and `absmode` (on-chip full-wave rectification — useful for threshold/energy detectors). [DS p20, p33]
- **Per-amplifier power** (Reg 14–21): power down unused channels; each amp draws ≈ 7.6 µA/kHz of f_H. [DS p22]

### 5. SPI protocol (exact)

- **4 wires**: CS (active low), SCLK (base 0), MOSI (to chip), MISO (from chip). Chip is **always the SPI slave**. **16-bit words, MSB first.** [DS p15]
- **Mode 0** (CPOL = 0, CPHA = 0): MOSI sampled on SCLK **rising**; master samples MISO on SCLK **rising**; MISO changes on SCLK **falling**. [DS p15]
- **CS falling edge triggers the ADC sample**, and **CS must pulse high between every 16-bit transfer** — even for non-convert commands. [DS p15] → this is *why* our firmware toggles CS per word.
- **Timing**: t_SCLK ≥ 40 ns → **SCLK max 25 MHz** (RHD2132/2216) / **24 MHz** (RHD2164); t_CYCLE ≥ 950 ns between ADC samples. [DS p15; 2164 p11]
- **Pipelined**: each command's 16-bit result returns **two commands later**. [DS p16]

**Command words** (bit 15 = MSB) [DS p16–18]:

| Command        | Encoding (16 bits)      | Result                                                                       |
| -------------- | ----------------------- | ---------------------------------------------------------------------------- |
| `CONVERT(C)` | `00 C[5:0] 0000000 H` | ADC result of channel C (2 cmds later).`H`=1 resets that channel's DSP HP. |
| `CALIBRATE`  | `0101010100000000`    | Must be followed by**9 dummy commands**; run once after config.        |
| `CLEAR`      | `0110101000000000`    | Clears ADC calibration (rarely needed).                                      |
| `WRITE(R,D)` | `10 R[5:0] D[7:0]`    | Upper byte all 1s, lower byte echoes D.                                      |
| `READ(R)`    | `11 R[5:0] 00000000`  | Lower byte = register contents.                                              |

- Channels **0–31** are amplifiers; **32–34** aux inputs; **48** supply sensor; **49** temp sensor. `CONVERT(63)` **auto-increments** the MUX to the next channel. [DS p16, p20]
- 18 RAM registers (0–17) on RHD2132/2216; RHD2164 adds **18–21** (amp power for ch 32–63). ROM registers 40–44 spell "INTAN"; 60–63 = die rev / unipolar flag / #amps / chip ID. [DS p19, p23; 2164 p13–14]

### 6. The 64-channel problem: RHD2164 and DDR

The RHD2164 is **two 32-channel cores in parallel** (module A = ch 0–31, module B = ch 32–63), each with its own ADC. A single `CONVERT(X)` converts channel **X on A and X+32 on B simultaneously**. [2164 p9]

The two 16-bit results are merged onto one MISO line by a **double-data-rate (DDR) multiplexer**: the master must sample MISO on **both the rising and falling edges of SCLK** (one module per edge). [2164 p10]

> "This DDR technique is a non-standard mode of SPI communication and will likely require an FPGA to implement." [2164 p10]

**Implication for the nRF54:** a standard SPI peripheral samples one edge only → you capture **one module = 32 of the 64 channels** (this is exactly the "standard SPI only covers the first 32 channels" from the advisor meeting). SCLK max 24 MHz. [2164 p10–11]

**The design fork for the 64-channel rig:**

1. **RHD2164 + solve DDR** — capture both SCLK edges on the nRF (non-trivial: needs a both-edge sampling trick, a small CPLD/logic shim, or a clever peripheral use). One chip, tightest footprint.
2. **2 × RHD2132** — 32 ch each, plain single-edge SPI, one MISO line per chip, both driven by the same commands. Sidesteps DDR entirely; costs a second chip + a second MISO line. [DS p13–14]

*(Open question for the thesis build — not yet decided.)*

### 7. Signaling: LVDS vs standard CMOS

- `LVDS_en` pin selects **LVDS** (differential pairs, terminated) or **standard CMOS** SPI. [DS p5]
- **CMOS is only recommended for low rates / short wires**: noise rises with CMOS at high ADC rates — Intan recommends CMOS only for **≤175 kS/s (16 amps)** or **≤5 kS/s/channel (32 amps)**; use **LVDS** above that or over long cables. [DS p12]
- Our bench (nRF54 + real Intan) runs **standard CMOS at 1 MHz SCLK** — well inside the safe zone. The real headstage over a cable will likely want LVDS.

### 8. Register cheat-sheet

| Reg    | Field(s)                                                                         | Purpose                                          | Page               |
| ------ | -------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------ |
| 0      | ADC ref BW(=3), amp fast settle, amp Vref en, ADC comparator bias(=3)/select(=2) | ADC config + fast-settle                         | [DS p19]           |
| 1      | VDD sense en,**ADC buffer bias[5:0]**                                      | must match sample rate                           | [DS p19, p27]      |
| 2      | **MUX bias[5:0]**                                                          | must match sample rate                           | [DS p20, p27]      |
| 3      | MUX load(=0), tempS2/S1, tempen, digout HiZ, digout                              | temp sensor + aux digital out                    | [DS p20]           |
| 4      | weak MISO, twoscomp, absmode,**DSPen**, DSP cutoff[3:0]                    | output format + on-chip HP filter                | [DS p20, p33]      |
| 5–7   | Zcheck…                                                                         | electrode impedance test                         | [DS p21]           |
| 8–11  | RH1/RH2 DACs                                                                     | **upper bandwidth f_H**                    | [DS p22, p25]      |
| 12–13 | RL DACs                                                                          | **lower bandwidth f_L**                    | [DS p22, p26]      |
| 14–17 | apwr[0:31]                                                                       | per-amp power (ch 0–31)                         | [DS p22]           |
| 18–21 | apwr[32:63]                                                                      | per-amp power (ch 32–63,**RHD2164 only**) | [2164 p13]         |
| 40–44 | "INTAN"                                                                          | ROM, SPI-integrity check                         | [DS p23]           |
| 60–63 | die rev / unipolar /#amps / **chip ID**                                    | ROM identity                                     | [DS p23; 2164 p14] |

### 9. Canonical init sequence (32 ch @ 30 kS/s, from [DS p36])

```
READ(63), READ(63)          # dummy — put controller in known state
WRITE(0,  0xDE)             # ADC config, fast-settle off
WRITE(1,  0x42)             # ADC buffer bias  ┐ for 960 kS/s total
WRITE(2,  0x04)             # MUX bias         ┘ (= 32 ch × 30 kS/s)
WRITE(3,  0x00)             # temp sensor off, digout low
WRITE(4,  0x80)             # offset-binary out, DSP HP off  (0x9C = DSP HP on @ 1.17 Hz)
WRITE(5,  0x00)             # impedance check off  (0x40/6/0x80/7/0x00 to enable)
WRITE(6,  0x80)
WRITE(7,  0x00)
WRITE(8,  0x16), WRITE(9,  0x80), WRITE(10, 0x17), WRITE(11, 0x80)   # f_H = 7.5 kHz
WRITE(12, 0x2C), WRITE(13, 0x86)                                     # f_L = 1.0 Hz
WRITE(14..17, 0xFF)         # power up ch 0–31
WRITE(18..21, 0xFF)         # power up ch 32–63   (RHD2164 only)
CALIBRATE
READ(63) × 9               # 9 dummy cmds required after CALIBRATE
# then loop CONVERT(0..31) + 3 aux slots at rate R
```

For 30 kHz neural work you'd typically enable the DSP HP (`WRITE(4, 0x9C)` region) or set f_H ≈ 10 kHz — adjust f_H/f_L via the [DS p25–26] tables.

### 10. Power (implant budget)

| Config                                                | Total                       | Page       |
| ----------------------------------------------------- | --------------------------- | ---------- |
| RHD2132, 32 ch @ 30 kS/s, f_H = 10 kHz (wideband max) | 11.3 mA →**37.3 mW** | [DS p34]   |
| RHD2164, 64 ch @ 30 kS/s, f_H = 10 kHz                | 16.1 mA →**53.1 mW** | [2164 p15] |
| RHD2164, 64 ch @ 20 kS/s, f_H = 7.5 kHz               | 13.3 mA → 43.9 mW          | [2164 p15] |
| RHD2132, ECoG 32 ch @ 2 kS/s, f_H = 1 kHz             | 1.33 mA → 4.4 mW           | [DS p34]   |

Levers: lower sample rate, lower f_H (7.6 µA/kHz per amp), power down unused channels, turn off temp/impedance/LVDS.

### 11. Data rate → why compression is mandatory

| Source                                   | Raw rate               |
| ---------------------------------------- | ---------------------- |
| 1 amplifier @ 30 kS/s × 16 bit          | 480 kbit/s             |
| 32 ch (RHD2132)                          | 15.4 Mbit/s            |
| **64 ch (RHD2164)**                | **30.7 Mbit/s**  |
| single-chip ADC max (1.05 MS/s × 16)    | 16.8 Mbit/s [DS p11]   |
| **— our measured BLE ceiling —** | **~1.05 Mbit/s** |

The gap between ~30 Mbit/s in and ~1 Mbit/s out is **~30×**. That is exactly the on-chip compression / spike-detection problem this project characterizes. See [System Architecture → The Two Measured Ceilings](#the-two-measured-ceilings-2026-07-31-ble-rate) for the measured transmit ceiling.

### 12. Reference implementations worth reading first

- **Intan STM32 firmware** (released Dec 2023): open-source C driving RHD2132/2216 over **SPI + DMA**, steady rates up to **20 kHz/channel**, on a NUCLEO-U5A5ZJ-Q. Closest existing analog to our nRF task (but 32-ch, non-DDR). [DS p37] — `intantech.com/downloads.html?tabSelect=Firmware`
- **Rhythm** (RHD2000 USB/FPGA interface): Verilog that captures the DDR SPI and compensates cable delay — the reference for the 64-ch DDR problem. [2164 p10]

### 13. How this maps to *our* build

- **Manual CS per word** in `firmware/board-bring-up` and `firmware/signal-path-intan/master` is not a Zephyr quirk — the Intan *requires* CS pulsed each word, and the CS falling edge triggers the sample. [DS p15]
- **LVDS_en must be tied to GND** to get standard CMOS signaling — confirmed the hard way during real bring-up: left floating, the chip defaults to LVDS via an internal pull-up, and a single-ended nRF SPI simply cannot talk to a chip expecting differential inputs. See §7.
- **64 channels (RHD2164)** — the DDR decision in §6 is the next real hardware question once single-channel throughput is understood. Tracked in [System Architecture → Open questions](#open-questions-current-not-aspirational).

---

## 3. Project Log and Roadmap

> **Summary.** The living "where are we / what's next" page. Durable how/why lives
> in the topic sections above ([System Architecture](#1-system-architecture),
> [Intan RHD Reference](#2-intan-rhd-reference)); this section is the chronological
> status and roadmap that points into them.

_Last updated: 2026-08-13._

### Status at a Glance

| Area                                      | State                                         | Detail                                                                                                                |
| ----------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Real Intan RHD2164**              | **bonded, powered, SPI-verified alive** | ROM reads`"INTAN"`                                                                                                  |
| **Real signal path, one channel**   | **validated end-to-end**                | FG sine → real Intan → SPI → nRF54 → BLE → laptop, cross-checked two ways                                        |
| BLE breaking point                        | actually found                                | ~1.05 Mbps / ~65,500 samples/s, proven by forcing real drops, not just observing 0                                    |
| SPI ingestion ceiling                     | measured                                      | 24 Mbit/s single-edge (Intan's 24 MHz cap) — see[System Architecture](#the-two-measured-ceilings-2026-07-31-ble-rate) |
| On-chip classifier / compression pipeline | ⬜ removed from repo, deferred                | see the 2026-08-13 repo-strip entry below                                                                             |

### Log

#### 2026-08-13 — Real Intan RHD2164 signal path validated end-to-end, one channel

The hardware work moved from emulation to a genuine bonded RHD2164. Headline:
a real function-generator sine, through the real chip, over SPI, over BLE,
live-plotted on the laptop — validated two independent ways.

**Bring-up.** A freshly-soldered RHD2164 initially drew zero current. Isolated
via voltage-at-decoupling-caps and continuity checks to unreflowed BGA power
balls — reflowed, current draw confirmed. `LVDS_en` also needed to be tied to
GND to force CMOS mode (it defaults to LVDS via an internal pull-up); without
that, the nRF's single-ended SPI physically cannot talk to the chip's
differential inputs. Once powered and in CMOS mode, `board-bring-up/` (a
minimal ROM-read-only firmware, no BLE, no config writes) confirmed the chip
alive: `ROM 40-44 = 'INTAN'`.

**Signal path.** `signal-path-intan/master/` configures the real amplifier
(10 Hz–10 kHz, all amps on, CALIBRATE) and streams ch0. First attempt railed
hard with nothing connected — a floating high-impedance input (~1.3 GΩ) acts
as an antenna. Fix: ground **both** `in0` and the reference input at the same
time (either alone floating rails the amplifier, since it measures
`in0 − reference`). Confirmed via a standalone raw-SPI print tool before
trusting the full BLE pipeline.

**Sampling correctness.** The first BLE-connected version sampled in fast
bursts separated by BLE-transmit gaps — looked like noise at low frequencies
(a burst only captures a fraction of a slow cycle). Fixed with a timer-paced
sampler thread + ring buffer, decoupling acquisition rate from BLE transmit
rate — uniform sampling at a known, fixed rate.

**Validated, not just observed.** FG on/off and waveform shape (sine/square/
triangle) visibly track the live plot. Quantitatively: sample rate ÷ FG
frequency correctly predicts the on-screen cycle spacing; amplitude
cross-checks between the raw-SPI print and the full BLE-relayed plot agree.

#### 2026-08-13 — Repo stripped to hardware-bring-up scope

Removed the on-chip classifier / spike-sorting pipeline (`dataset/`, `model/`,
`sim/`, `firmware/classifiers`, `firmware/pipeline`, the two-DK Intan
emulation) from the working tree (commit `8b83a89`). Kept only
`board-bring-up/`, `signal-path-intan/`, `ble-rate/`. The classifier work
(logreg/CNN/ResNet on-chip, cross-day generalization, the full
raw→classify→BLE chain, all previously demonstrated end-to-end on two DKs) is
preserved in git history, not deleted — it's just no longer part of the active
build or documentation. Reason: focus shifted to proving the physical signal
chain on real hardware before returning to the compression/classification
question.

#### 2026-08-05 — BLE breaking point actually found, not just a sustainable rate

Every prior BLE test showed 0 drops — proof of "at or below the ceiling,"
never proof of *finding* it, since Zephyr's `bt_gatt_notify` back-pressures
(blocks) rather than dropping when the radio can't keep up. Fix: a
free-running producer (its own timebase, doesn't wait for BLE) writing into a
bounded ring buffer — when BLE can't drain fast enough, the *buffer*
overflows, and that's a real, countable drop. This finally exercises the
actual ceiling: **~1.05 Mbps / ~65,500 sixteen-bit values/sec**, confirmed by
pushing the offered rate well past it (drops appear, tracking the overrun
almost exactly) and backing off to find the 0-drop knee.

#### 2026-07-31 — Both data-rate ceilings measured; SPI is the harder wall

Documented in
[System Architecture → The Two Measured Ceilings](#the-two-measured-ceilings-2026-07-31-ble-rate).
Headlines:

- **BLE egress ceiling = ~1.05 Mbps**, proven. BLE back-pressures, it does not
  drop — "0 drops" never meant "at the max" until the fix above.
- **SPI ingestion is the tighter wall.** SPI clock ≈ bit rate; Intan caps SCLK
  at 24 MHz → 24 Mbit/s single-edge < 30.7 Mbit/s needed for 64 ch. DDR is
  throughput-mandatory, not just a channel-capture nicety.
- **nRF SAADC ≠ Intan:** on-chip ADC is 14-bit, 8 ch, no gain stage — the real
  reason Intan exists is the per-channel amplifier (×192) before the ADC.

#### 2026-07-24 — Intan datasheet reference added

Read the RHD2000-series and RHD2164 datasheets in full and distilled them into
a page-cited reference: [Intan RHD Reference](#2-intan-rhd-reference).
Durable — grounded in the datasheet, not tied to any specific firmware, so it
survived the later repo cleanup intact.

### Roadmap

- [ ] **Push `signal-path-intan` toward its real ceiling** — currently well
  under both the SPI and BLE limits; find where one channel actually breaks.
- [ ] **Multi-channel on the real chip** — round-robin CONVERT across more than
  ch0, still on standard single-edge SPI (32 ch reachable without DDR).
- [ ] **The channel-count fork** — full 64 ch needs DDR (fragile FPGA-free
  trick or a hardware DDR receiver) vs. 32 ch on one clean lane vs. lower
  sample rate to fit more channels. See
  [Intan RHD Reference §6](#6-the-64-channel-problem-rhd2164-and-ddr).
- [ ] **Bring the classifier/compression work back**, now against real
  (not emulated) Intan data, once the signal path above is solid.

---

## Ideation & Planning

Forward-looking plans, design options, and research notes — distinct from the
documentation of work already done above. These live under
[`ideas/`](ideas/):

- [`two-phase-architecture.md`](ideas/two-phase-architecture.md) — design spec for the deferred offline-supervised / online classifier split (Approach A).
- [`classification_options.md`](ideas/classification_options.md) — the Tier 0→3 on-device classifier ladder to test later.
- [`design_considerations.md`](ideas/design_considerations.md) — stored architecture dialogue on invariant "plumbing" + the swappable classifier seam.
- [`classification_benchmark.md`](ideas/classification_benchmark.md) — plan for validating classification accuracy against Kilosort ground truth.
- [`nrf54-package-selection.md`](ideas/nrf54-package-selection.md) — package decision (QFN52 / CSP61 / CSP98) for the not-yet-built custom PCB.
- [`SPI_bringup_plan.md`](ideas/SPI_bringup_plan.md) — plan for scaling SPI acquisition to 32 channels (firmware + signal-integrity halves; the CSN/SPIM00 decision).
- [`waveform_classification_backrgound.md`](ideas/waveform_classification_backrgound.md) — time-series ML research background + faculty notes.
