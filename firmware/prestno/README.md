# prestno

Headstage firmware that detects spikes on the nRF54LM20 and sends only the windows around them over BLE. Clean copy of `spike` with the diagnostics removed. The question it answers: at which channel count and sampling rate does on-device threshold detection still catch the FB128's SYNC spikes.

## Parts

| what | where | you change |
|---|---|---|
| headstage firmware | `src/main.c` | `N_CH` and `CH_RATE_HZ` at the top; `RAW_STREAM 1` only to look at the raw signal |
| relay (unchanged) | `../theo-central` | nothing |
| record a capture | `log.py OUT.bin SECONDS` | file name |
| watch live, all channels | `live.py` (add `6000` for the 6 kS/s test) | |
| watch one spike at a time | `trace.py` (same optional rate) | |
| watch the raw trace | `streamplot.py --serial PORT`, needs the firmware built with `RAW_STREAM 1` | |
| check one capture | `check.py CAPTURE.bin` (add `6000` for the 6 kS/s test) | |
| the problem in one figure | `compare.py a.bin:30000 b.bin:6000 c.bin:30000` | |

Python: `source .venv/bin/activate` once per terminal (numpy, matplotlib, pyserial are installed there).

## Bench

FB128 in SYNC 100 Hz. Every channel the firmware converts needs a FB128 output wired to it. FB128 ground, Intan REF and DK ground on one net. Hand off the FB128.

## Run

1. Set `N_CH` and `CH_RATE_HZ`, build, flash the headstage. Flash `theo-central` on the other DK once.
2. Reset headstage, then central, wait for `subscribed` on the headstage console.
3. Copy three `[prestno]` status lines. Then `python log.py NAME.bin 20` (the relay's port is found automatically).
4. `python check.py NAME.bin` (add `6000` after the file name for the 6 kS/s test).

## The three tests

| test | N_CH | CH_RATE_HZ | conversions/s | file | expected |
|---|---|---|---|---|---|
| A | 1 | 30000 | 30k | `a_1ch_30k.bin` | about 95 events/s, noise near 80 uV, on grid > 85% |
| B | 4 | 6000 | 24k | `b_4ch_6k.bin` | about 95 events/s per channel, noise near 60 uV |
| C | 4 | 30000 | 120k | `c_4ch_30k.bin` | noise 150 uV or more, most spikes missed |

Then `python compare.py a_1ch_30k.bin:30000 b_4ch_6k.bin:6000 c_4ch_30k.bin:30000`.

## Status line

`[prestno] S/s drained | lag | ch0 noise uV | detected/s sent/s dropped/s | queued | restarts`

drained should equal N_CH x CH_RATE_HZ. lag is how many samples the detector trails the DMA; thousands is fine, tens of thousands means the CPU is behind. dropped above zero means the radio could not keep up.
