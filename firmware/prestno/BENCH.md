# Bench record

Fill this in once, by hand, before the benchmark table is recorded. Every capture is labelled with the revision
below. If anything on this page changes, bump the revision and start a new table.

**Bench revision:** A  (date: ______)

## Signal source

| item | value |
|---|---|
| FB128 mode | SYNC 100 Hz |
| FB128 power | ______ (USB from the Mac / wall adapter / battery) |
| FB128 output pins used | in0 ← pin ____, in1 ← ____, in2 ← ____, in3 ← ____, in4 ← ____, in5 ← ____, in6 ← ____, in7 ← ____ |
| FB128 ground → | ______ (which board, which pin) |
| FB128 reference → | ______ |

## Intan board

| item | value |
|---|---|
| board | ______ (Intan RHD2164 headstage / other) |
| VDD ← | DK header ____ pin ____ |
| GND ← | DK header ____ pin ____ |
| REF → | ______ |
| SPI jumpers (SCLK, MOSI, MISO, CS) | DK P__ ____ ; length ≈ ____ cm |
| anything on a breadboard | ______ (ideally: nothing) |

## Headstage DK and relay

| item | value |
|---|---|
| headstage DK serial | ______ |
| central DK serial, data port | /dev/tty.usbmodem______ |
| Mac power | battery / charger |
| hand on FB128 | no |

## Firmware and scripts

| item | value |
|---|---|
| `prestno` commit | ______ |
| `theo-central` commit | ______ |
| detector | 4 sigma, 300 Hz high-pass, 6 kHz low-pass only when the analog band exceeds 6 kHz, 3 ms dead time |

## Notes

Anything unusual during the session (re-plugged a cable, moved the boards, changed rooms).
