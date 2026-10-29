# prestno

One question, one channel at 30 kS/s: does the headstage's windowed spike path reproduce the raw signal?

The headstage detects spikes on the nRF54LM20 and sends only the 2 ms window around each one. To trust that, we record the same bench twice, once as the raw stream and once as windows, and compare them against the FB128's SYNC ground truth of one identical spike every 10.50 ms.

## Files

| file | job |
|---|---|
| `src/main.c` | the firmware. `RAW_STREAM 1` sends every sample, `RAW_STREAM 0` sends spike windows. `N_CH 1`, `CH_RATE_HZ 30000`. |
| `log.py OUT.bin SECONDS` | records whatever the relay forwards |
| `live.py` | live view of the raw trace, raw firmware only; check the bench with it before the raw capture |
| `compare.py RAW.bin EVENTS.bin` | the answer: one table, one figure |
| `verdict.py RAW.bin [RATE_HZ]` | the verdict plot for one raw capture: 50 ms of trace and every spike overlaid, plus trough, noise and spike-to-noise |
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
