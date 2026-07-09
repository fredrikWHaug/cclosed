# Lessons Learned: Two-Board SPI Between nRF54LM20B DKs

## Goal

Prove SPI master/slave communication between two chips, using two nRF54LM20 DKs
as a stand-in for the eventual **nRF54 (master) ↔ Intan (slave)** link. One DK
runs an SPI master, the other an SPI slave, wired together with jumpers.

**Final working setup:** master = `spi22`, slave = `spi21`, PORT3 pins
(P3.00 MOSI, P3.01 MISO, P3.02 CS, P3.03 SCK), wired same-pin-to-same-pin
between the boards plus a shared GND, at 250 kHz. Verified fully bidirectional
and reliable — no dropped bytes.

## The Hurdles (in the order we hit them)

### 1. Board-target gotcha: overlays silently ignored
Adding a build configuration sometimes defaulted the target to
`nrf54lm20dk/nrf54lm20**a**/cpuapp`. Our overlays are named for the **`b`**
variant, so on an `a` build they were silently skipped — the SPI peripheral
never got enabled and nothing worked, with no obvious error.
**Fix:** always confirm the build log shows `qualifiers: nrf54lm20b/cpuapp`.

### 2. SPIS devicetree properties don't match the SPIM defaults
The SoC devicetree defines each SPI node as a master (`nordic,nrf-spim`) with
`rx-delay` / `rx-delay-supported` properties. Re-declaring the node as a slave
(`nordic,nrf-spis`) fails to build because those properties aren't in the SPIS
binding, and the slave needs an explicit `SPIS_CSN` pin in pinctrl.
**Fix:** in the slave overlay, `/delete-property/ rx-delay;` and
`rx-delay-supported;`, and add `SPIS_SCK/MOSI/MISO/CSN` to a dedicated pinctrl
group. (Nordic's own `spi_controller_peripheral` test overlay was the reference.)

### 3. The big red herring: "SPIS arming / coordination"
The slave only reacted to reset glitches and physical unplugs, never the
master's real transactions. This *looked* like the well-known nRF SPIS
arming-latency problem (the DMA-based slave must be armed before the master
clocks; four-wire SPI has no "wait, I'm not ready" channel). We spent a long
time here — slowing the clock, adding CS setup delay, toggling PM device-runtime
settings, swapping SPI instances. **None of it helped**, because this was not
actually the problem.

### 4. Isolating the layers (what finally created traction)
Instead of more tweaking, we verified each layer independently:
- **Master SPIM works** — a MOSI→MISO loopback returned the sent bytes.
- **Slave SPIS works** — Nordic's `spi_controller_peripheral` test (master +
  slave on one board) passed 100% on this exact silicon.
- **Physical link is perfect** — a plain-GPIO test drove all four PORT3 pins as
  a 4-bit counter on one board and read them on the other; the reader tracked
  0→15 exactly, every bit correct. Wiring and ground were ruled out completely.

So: both peripherals work, the wires are perfect — yet two-board SPI fails.

### 5. The actual root cause: CS never toggled
We measured instead of guessing. A GPIO **edge-counter** on the slave watched
P3.02 (CS) and P3.03 (SCK) with interrupts while the master ran normally:

```
CS edges = 0        (CS now = 1, forever)
SCK edges = climbing
```

The clock was pulsing, but **the master's chip-select never went low — not
once.** An SPI slave does nothing until CS asserts, so the slave never saw a
transaction begin, captured nothing, and the master read `0xFF` back. The
Zephyr SPIM driver simply was not toggling the `cs-gpios` pin we handed it.

### 6. The fix: drive CS manually
Stop relying on the driver for chip-select. Remove `cs-gpios` from the master
overlay and control P3.02 as a plain GPIO in `main.c`:

```
idle high  →  pull low  →  ~50 µs setup  →  spi_transceive()  →  ~50 µs hold  →  release high
```

The setup delay after CS-low also gives the slave's SPIS margin to be armed.
This fixed it immediately: clean, continuous, bidirectional communication.

## Key Takeaways

- **Measure before tweaking.** Hours went into config changes against a theory
  (arming latency) that was wrong. A ten-minute edge-counter found the real,
  mundane bug (CS not toggling). When stuck, instrument the actual signals.
- **Isolate each layer.** Peripheral, physical link, and protocol are separate
  failure domains — prove each one independently before debugging their
  interaction.
- **Use the vendor's passing test as ground truth.** Nordic's
  `spi_controller_peripheral` test proved the silicon and gave the correct
  overlay/pin reference; we should have started there.
- **Hardware slave vs DMA slave.** A textbook SPI slave (shift register) is
  always ready. The nRF SPIS is DMA-based and needs arming. The **Intan is a
  hardware slave**, and in the real system the **nRF is the master** — so the
  hardest part of this exercise (nRF-as-slave) won't exist in the actual
  product. This two-DK test was only an Intan stand-in.

## Relevance Going Forward
For the real acquisition path the nRF54 is the SPI **master** talking to the
Intan (an always-ready hardware slave), so the arming/coordination difficulty
disappears. What carries over is a working, understood master — including how to
frame a transaction with an explicit chip-select if the driver's automatic CS
ever misbehaves again.
