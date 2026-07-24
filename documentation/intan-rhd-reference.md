# Intan RHD2000 / RHD2164 — chip reference

> **Why this file exists.** The Intan RHD is the analog front-end + ADC of this
> whole project — it's where sampling actually happens. This is a distilled,
> **page-cited** reference so no future session (you or a fresh AI instance) has to
> re-derive it from the PDFs. Every non-obvious claim cites a page.
>
> **Sources** (local PDFs, not in the repo):
> - `Intan_RHD2000_series_datasheet.pdf` — the general part (RHD2216/2132). Cited **[DS p_N_]**.
> - `Intan_RHD2164_datasheet.pdf` — the 64-channel variant. Cited **[2164 p_N_]**.
>
> Verified against both datasheets on 2026-07-24.

---

## TL;DR — the ten things that matter

1. **The sample rate is NOT a chip register — the controller (our nRF54) sets it** by how fast it issues `CONVERT` commands. The chip has no internal clock. [DS p35, p37]
2. **Ceiling = 30 kS/s per channel** (1.05 MS/s aggregate ÷ 35 multiplexed slots). [DS p7, p15]
3. Amplifier **gain is fixed at 192**; ADC step **V_LSB = 0.195 µV** at the electrode. [DS p6]
4. **Analog bandwidth IS configurable** in registers: upper cutoff f_H (100 Hz–20 kHz) and lower cutoff f_L (0.1–500 Hz). [DS p6, p25–26]
5. An **on-chip DSP high-pass** (Reg 4) does offset removal — the same job as the biquad high-pass in our pipeline. [DS p33]
6. **SPI is mode 0, 16-bit MSB-first, and CS must pulse high between *every* word** — the CS falling edge is what triggers each ADC sample. Our manual-CS firmware is *required*, not a workaround. [DS p15]
7. Protocol is **pipelined**: a `CONVERT` result comes back **two commands later**. [DS p16]
8. **64 channels (RHD2164) needs double-data-rate (DDR) SPI** — sampling MISO on *both* clock edges. Standard SPI (one edge) gets you **32 of the 64 channels**. This is the key nRF constraint. [2164 p9–11]
9. **Raw data rate is enormous**: 64 ch × 30 kS/s × 16 bit = **30.7 Mbit/s**. Our BLE ceiling is ~1.05 Mbps → a **~30× gap**. That gap *is* the compression thesis.
10. **Intan ships reference MCU firmware** (STM32, SPI + DMA, ≤20 kHz/ch) — read it before writing much nRF code. [DS p37]

---

## 1. The family

| Device | Amps | Inputs | Package | Chip ID (Reg 63) |
|--------|------|--------|---------|------------------|
| RHD2216 | 16 | 16 × differential (bipolar) | 8×8 mm 56-QFN | 2 |
| RHD2132 | 32 | 32 unipolar + 1 common ref | 8×8 mm 56-QFN | 1 |
| **RHD2164** | **64** | 64 unipolar + 1 common ref | 9×7 mm 104-BGA | **4** |

[DS p2; 2164 p2, p14]. Our recorded `.rhd` data is RHD2132-class (32 unipolar + shared `ref_elec`). The 64-channel rig implies the **RHD2164** — see §6 for why that matters.

---

## 2. Signal chain (one channel)

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

---

## 3. Sampling rate — set by the controller, not a register  ← the headline

The datasheet is blunt about this, twice:

> "The rate and timing of SPI commands sent to the chip determines the ADC sampling rate; sample times are set by the falling edge of CS." [DS p35]
>
> "The RHD2000 chips have no internal clock. The ADC sampling rate is entirely set by the rate at which CONVERT commands are sent over the SPI bus." [DS p37]

**How you set it:** run the round-robin `CONVERT(0), CONVERT(1) … CONVERT(31)` (+ a few aux slots) and **repeat the whole sequence at the desired per-channel rate R**. [DS p35]

- **Ceiling: 30 kS/s per channel.** Max MUX rate f_MUX = 1.05 MHz [DS p7]; total cycle time t_CYCLE ≥ 950 ns [DS p15] → 1.05 MS/s aggregate ÷ 35 multiplexed slots (32 amps + 3 aux) = 30 kS/s each. Continuously settable *below* that — nothing forces 30 k.
- **Two registers must match the rate you pick:** ADC **buffer bias** (Reg 1) and **MUX bias** (Reg 2) have optimum values that depend on total ADC rate — lookup table at [DS p27]. (e.g. ≤120 kS/s total → buffer bias 32 / MUX bias 40; ≥700 kS/s → 2 / 4.)
- **Anti-aliasing couples rate and bandwidth:** f_H is the anti-alias filter, so set f_H below Nyquist (R/2). Wideband neural uses R = 30 kS/s with f_H ≈ 10 kHz. [DS p7 Fig 7, p24]

---

## 4. Analog bandwidth & on-chip DSP (the real register config)

- **Upper cutoff f_H** (low-pass, 3rd-order Butterworth): Registers 8–11 (RH1/RH2 DACs). On-chip range **100 Hz–20 kHz**; exact register values tabulated at [DS p25]. [DS p22, p24]
- **Lower cutoff f_L** (high-pass, 1st-order): Registers 12–13 (RL DACs). On-chip range **0.1–500 Hz**; values at [DS p26]. [DS p22, p24]
- **On-chip DSP high-pass** (Reg 4 `DSPen` + `DSP cutoff freq[3:0]`): a 1st-order IIR high-pass on every channel for residual-offset removal; cutoff f_c = k_freq · f_sample [DS p33]. **This is the on-chip equivalent of the causal biquad high-pass we run on the nRF** — it could be offloaded to the chip.
- **Output format** (Reg 4): `twoscomp` (signed vs offset-binary) and `absmode` (on-chip full-wave rectification — useful for threshold/energy detectors). [DS p20, p33]
- **Per-amplifier power** (Reg 14–21): power down unused channels; each amp draws ≈ 7.6 µA/kHz of f_H. [DS p22]

---

## 5. SPI protocol (exact)

- **4 wires**: CS (active low), SCLK (base 0), MOSI (to chip), MISO (from chip). Chip is **always the SPI slave**. **16-bit words, MSB first.** [DS p15]
- **Mode 0** (CPOL = 0, CPHA = 0): MOSI sampled on SCLK **rising**; master samples MISO on SCLK **rising**; MISO changes on SCLK **falling**. [DS p15]
- **CS falling edge triggers the ADC sample**, and **CS must pulse high between every 16-bit transfer** — even for non-convert commands. [DS p15] → this is *why* our firmware toggles CS per word.
- **Timing**: t_SCLK ≥ 40 ns → **SCLK max 25 MHz** (RHD2132/2216) / **24 MHz** (RHD2164); t_CYCLE ≥ 950 ns between ADC samples. [DS p15; 2164 p11]
- **Pipelined**: each command's 16-bit result returns **two commands later**. [DS p16]

**Command words** (bit 15 = MSB) [DS p16–18]:

| Command | Encoding (16 bits) | Result |
|---------|--------------------|--------|
| `CONVERT(C)` | `00 C[5:0] 0000000 H` | ADC result of channel C (2 cmds later). `H`=1 resets that channel's DSP HP. |
| `CALIBRATE` | `0101010100000000` | Must be followed by **9 dummy commands**; run once after config. |
| `CLEAR` | `0110101000000000` | Clears ADC calibration (rarely needed). |
| `WRITE(R,D)` | `10 R[5:0] D[7:0]` | Upper byte all 1s, lower byte echoes D. |
| `READ(R)` | `11 R[5:0] 00000000` | Lower byte = register contents. |

- Channels **0–31** are amplifiers; **32–34** aux inputs; **48** supply sensor; **49** temp sensor. `CONVERT(63)` **auto-increments** the MUX to the next channel. [DS p16, p20]
- 18 RAM registers (0–17) on RHD2132/2216; RHD2164 adds **18–21** (amp power for ch 32–63). ROM registers 40–44 spell "INTAN"; 60–63 = die rev / unipolar flag / #amps / chip ID. [DS p19, p23; 2164 p13–14]

---

## 6. The 64-channel problem: RHD2164 + DDR  ← key design constraint

The RHD2164 is **two 32-channel cores in parallel** (module A = ch 0–31, module B = ch 32–63), each with its own ADC. A single `CONVERT(X)` converts channel **X on A and X+32 on B simultaneously**. [2164 p9]

The two 16-bit results are merged onto one MISO line by a **double-data-rate (DDR) multiplexer**: the master must sample MISO on **both the rising and falling edges of SCLK** (one module per edge). [2164 p10]

> "This DDR technique is a non-standard mode of SPI communication and will likely require an FPGA to implement." [2164 p10]

**Implication for the nRF54:** a standard SPI peripheral samples one edge only → you capture **one module = 32 of the 64 channels** (this is exactly the "standard SPI only covers the first 32 channels" from the advisor meeting). SCLK max 24 MHz. [2164 p10–11]

**The design fork for the 64-channel rig:**
1. **RHD2164 + solve DDR** — capture both SCLK edges on the nRF (non-trivial: needs a both-edge sampling trick, a small CPLD/logic shim, or a clever peripheral use). One chip, tightest footprint.
2. **2 × RHD2132** — 32 ch each, plain single-edge SPI, one MISO line per chip, both driven by the same commands. Sidesteps DDR entirely; costs a second chip + a second MISO line. [DS p13–14]

*(Open question for the thesis build — not yet decided.)*

---

## 7. Signaling: LVDS vs standard CMOS

- `LVDS_en` pin selects **LVDS** (differential pairs, terminated) or **standard CMOS** SPI. [DS p5]
- **CMOS is only recommended for low rates / short wires**: noise rises with CMOS at high ADC rates — Intan recommends CMOS only for **≤175 kS/s (16 amps)** or **≤5 kS/s/channel (32 amps)**; use **LVDS** above that or over long cables. [DS p12]
- Our two-DK bench runs **standard CMOS at 1 MHz SCLK** — well inside the safe zone. The real headstage over a cable will likely want LVDS.

---

## 8. Register cheat-sheet

| Reg | Field(s) | Purpose | Page |
|-----|----------|---------|------|
| 0 | ADC ref BW(=3), amp fast settle, amp Vref en, ADC comparator bias(=3)/select(=2) | ADC config + fast-settle | [DS p19] |
| 1 | VDD sense en, **ADC buffer bias[5:0]** | must match sample rate | [DS p19, p27] |
| 2 | **MUX bias[5:0]** | must match sample rate | [DS p20, p27] |
| 3 | MUX load(=0), tempS2/S1, tempen, digout HiZ, digout | temp sensor + aux digital out | [DS p20] |
| 4 | weak MISO, twoscomp, absmode, **DSPen**, DSP cutoff[3:0] | output format + on-chip HP filter | [DS p20, p33] |
| 5–7 | Zcheck… | electrode impedance test | [DS p21] |
| 8–11 | RH1/RH2 DACs | **upper bandwidth f_H** | [DS p22, p25] |
| 12–13 | RL DACs | **lower bandwidth f_L** | [DS p22, p26] |
| 14–17 | apwr[0:31] | per-amp power (ch 0–31) | [DS p22] |
| 18–21 | apwr[32:63] | per-amp power (ch 32–63, **RHD2164 only**) | [2164 p13] |
| 40–44 | "INTAN" | ROM, SPI-integrity check | [DS p23] |
| 60–63 | die rev / unipolar / #amps / **chip ID** | ROM identity | [DS p23; 2164 p14] |

---

## 9. Canonical init sequence (32 ch @ 30 kS/s, from [DS p36])

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

---

## 10. Power (implant budget)

| Config | Total | Page |
|--------|-------|------|
| RHD2132, 32 ch @ 30 kS/s, f_H = 10 kHz (wideband max) | 11.3 mA → **37.3 mW** | [DS p34] |
| RHD2164, 64 ch @ 30 kS/s, f_H = 10 kHz | 16.1 mA → **53.1 mW** | [2164 p15] |
| RHD2164, 64 ch @ 20 kS/s, f_H = 7.5 kHz | 13.3 mA → 43.9 mW | [2164 p15] |
| RHD2132, ECoG 32 ch @ 2 kS/s, f_H = 1 kHz | 1.33 mA → 4.4 mW | [DS p34] |

Levers: lower sample rate, lower f_H (7.6 µA/kHz per amp), power down unused channels, turn off temp/impedance/LVDS.

---

## 11. Data rate → why compression is mandatory

| Source | Raw rate |
|--------|----------|
| 1 amplifier @ 30 kS/s × 16 bit | 480 kbit/s |
| 32 ch (RHD2132) | 15.4 Mbit/s |
| **64 ch (RHD2164)** | **30.7 Mbit/s** |
| single-chip ADC max (1.05 MS/s × 16) | 16.8 Mbit/s [DS p11] |
| **— our measured BLE ceiling —** | **~1.05 Mbit/s** |

The gap between ~30 Mbit/s in and ~1 Mbit/s out is **~30×**. That is exactly the on-chip compression / spike-detection problem this project characterizes. See [ble_bitrate_plan.md](../firmware/ble-rate/ble_bitrate_plan.md) for the measured transmit ceiling.

---

## 12. Reference implementations worth reading first

- **Intan STM32 firmware** (released Dec 2023): open-source C driving RHD2132/2216 over **SPI + DMA**, steady rates up to **20 kHz/channel**, on a NUCLEO-U5A5ZJ-Q. Closest existing analog to our nRF task (but 32-ch, non-DDR). [DS p37] — `intantech.com/downloads.html?tabSelect=Firmware`
- **Rhythm** (RHD2000 USB/FPGA interface): Verilog that captures the DDR SPI and compensates cable delay — the reference for the 64-ch DDR problem. [2164 p10]

---

## 13. How this maps to *our* build

- **Manual CS per word** in `firmware/spi/*` and `firmware/pipeline/master` is not a Zephyr quirk — the Intan *requires* CS pulsed each word, and the CS falling edge triggers the sample. [DS p15] See [spi-acquisition-link.md](spi-acquisition-link.md).
- **The nRF's on-chip biquad high-pass** duplicates the Intan's DSP HP (Reg 4). On the real chip we could offload it — a compression-vs-fidelity design lever.
- **Decimate 30 k → 10 k** in the pipeline assumes 30 kS/s acquisition — which is the chip's ceiling, set by our CONVERT cadence, not a chip setting.
- **8 shanks × 8 = 64 channels** → RHD2164 → the DDR decision in §6 is the next real hardware question. Tracked in [system-architecture.md](system-architecture.md#open-hardware-questions).
