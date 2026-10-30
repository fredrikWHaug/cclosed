# Bench record

Every capture is labelled with the revision below. If anything on this page changes, bump the revision and start a
new table.

**Bench revision:** A

## Power and ground

The Mac powers the headstage DK over USB. The DK powers the Intan board. Ground is the DK ground: the Intan board's
GND and the FB128's ground are both wired to DK GND pins, nothing through a breadboard. The central DK is on a second
USB cable to the same Mac.

## Signal source

| item | value |
|---|---|
| FB128 mode | SYNC 100 Hz |
| FB128 power | battery |
| FB128 outputs | eight of the unnumbered outputs, one each on in0 to in7 |
| FB128 ground and reference | shorted together on the FB128, both wired to DK GND pins |

## Intan board

| item | value |
|---|---|
| board | Intan RHD2164 headstage PCB |
| VDD ← | DK P4 (PORT2) VDD pin |
| GND ← | DK P4 (PORT2) GND pin, the same header as the SPI lines |
| REF → | DK GND |
| SPI | SCLK P2.01, MOSI P2.02, MISO P2.04, CS P2.05, jumper wires |

## Headstage DK and relay

| item | value |
|---|---|
| headstage DK | nRF54LM20 DK, console /dev/tty.usbmodem…845658 |
| central DK | nRF54LM20 DK running theo-central, data port /dev/tty.usbmodem0010518186261 |
| Mac power | battery |
| Mac Bluetooth | connected to a mouse and AirPods during captures |
| hand on FB128 | no |

## Firmware and scripts

| item | value |
|---|---|
| `prestno` commit | ed298fb |
| `theo-central` commit | d9257eb |
| detector | 4 sigma, 300 Hz high-pass, 6 kHz low-pass only when the analog band exceeds 6 kHz, 3 ms dead time |

## Notes

Anything unusual during a session (re-plugged a cable, moved the boards, changed rooms).
