# prestno

One question, one channel at 30 kS/s: does the headstage's windowed spike path reproduce the raw signal?

The headstage detects spikes on the nRF54LM20 and sends only the 2 ms window around each one. To trust that, we record the same bench twice, once as the raw stream and once as windows, and compare them against the FB128's SYNC ground truth of one identical spike every 10.50 ms.

## Files

| file | job |
|---|---|
| `src/main.c` | the firmware. `RAW_STREAM 1` sends every sample, `RAW_STREAM 0` sends spike windows. `N_CH 1`, `CH_RATE_HZ 30000`. |
| `log.py OUT.bin SECONDS` | records whatever the relay forwards |
| `live.py` | live view of the raw trace, raw firmware only; check the bench with it before the raw capture |
| `score.py EVENTS.bin [RATE_HZ]` | any channel count: per channel, % of SYNC spikes caught, false detections/s, jitter, trough, noise |
| `compare.py RAW.bin EVENTS.bin` | one channel: the device's windows against its own detector replayed on the raw stream |
| `verdict.py RAW.bin [RATE_HZ]` | the frozen yardstick: zero-phase analysis of a raw capture, never sees the device's algorithm |
| `BENCH.md` | the wiring and power record every capture is labelled with |
| `formats.py` | the two packet formats and the device's filter, shared by the scripts |
| `FORMATS.md` | why the two formats exist and which tool needs which |
| `../theo-central` | the relay on the second DK, unchanged |

`source .venv/bin/activate` once per terminal.

## Bench

FB128 in SYNC 100 Hz, one output on in0, FB128 ground and Intan REF on the DK ground, hand off. Before the raw capture, run `live.py` and look: 4 to 5 identical spikes in 50 ms, 10.5 ms apart. Anything else means the FB128 is not in SYNC.

## Procedure

1. `RAW_STREAM 1`, build, flash headstage, reset central, wait for `subscribed`. `python live.py`, confirm, Ctrl+C. `python log.py raw_1ch_30k.bin 20`.
2. `RAW_STREAM 0`, build, flash, reset central, wait for `subscribed`. `python log.py events_1ch_30k.bin 20`. Copy three `[prestno]` lines; in SYNC the noise column should read the same as the floor you see in NORMAL, about 85 uV.
3. `python compare.py raw_1ch_30k.bin events_1ch_30k.bin`.

## Reading the result

The table has two rows, the raw stream with the detector run offline and the windows the device sent. The windowed path is proven when the rows agree: about 95 spikes/s each, on grid above 85%, jitter under 100 µs, the same trough amplitude and spread, the same noise, and zero lost. The figure shows the two mean waveforms with their spread on top of each other, the gap histograms, and the amplitude histograms. Any disagreement between the rows is the thing to chase next.

Afterwards the same three steps at `CH_RATE_HZ 6000u`, with `6000` as the third argument to `compare.py` and the first to `live.py`, show what the lower rate does to the waveform.

## The benchmark table

Bench revision A, FB128 in SYNC, hand off, firmware frozen. One cell = one 20 s event capture, scored with `score.py`.
Every cell is recorded twice back to back; the two must agree within 5 points of "caught", else a third run and a note.
Each session opens and closes with the control: 1 channel, 30 kS/s, `RAW_STREAM 1`, 20 s, `verdict.py`. If the two
controls differ by more than 5 points, the session's cells are flagged.

| channels | 30 kS/s: caught / false per s / dropped per s | 6 kS/s: caught / false per s / dropped per s |
|---|---|---|
| 1 | | |
| 2 | | |
| 4 | | |
| 8 | radio-limited in SYNC (615 kbit/s), read dropped first | |

Run sheet per cell:

1. `N_CH`, `CH_RATE_HZ`, `RAW_STREAM 0` in `src/main.c`. Build, flash, reset the central, wait for `subscribed`.
2. Copy three `[prestno]` lines (noise, detected, dropped).
3. `python log.py <cell>_<run>.bin 20`, e.g. `ev_4ch_30k_a.bin`.
4. `python score.py <file> [6000]`. Write caught, false/s and dropped/s into the table.

Prediction before recording, from the one-channel measurements: at 30 kS/s about 73% caught and 4 false/s per channel;
at 6 kS/s about 65% and 1 false/s. Channel count should not change these unless the noise rises with it.
