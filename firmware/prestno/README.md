# prestno

Goal: as many reliable channels of windowed spikes over the BLE link as the current bench allows. The two knobs are
the sample rate and the channel count; the yardstick is the FB128 in SYNC mode, one identical spike every 10.533 ms
on every channel.

## Files

| file | job |
|---|---|
| `src/main.c` | firmware. `N_CH`, `CH_RATE_HZ`, and `RAW_STREAM` (1 = every sample, 0 = spike windows only) |
| `log.py OUT.bin SECONDS` | record whatever the relay forwards |
| `live.py` / `filtered_live.py` | look at the raw stream, plain or through the device's filter, before recording |
| `verdict.py RAW.bin [RATE]` | judge a raw capture offline, no device detector involved; prints numbers with 95% CI, saves the plot |
| `score.py EVENTS.bin [RATE]` | judge the device's windows against the SYNC truth, per channel, with 95% CI |
| `sweep.py` | every capture in `data/` into one table (`sweep.md`) and two figures |
| `metrics.py`, `formats.py` | the measurements and the packet formats, shared |
| `tests/` | `python -m pytest tests` checks the formats against the firmware's byte layout and the metrics against synthetic truth |
| `BENCH.md` | wiring and power record; every capture belongs to a bench revision |
| `table.py` | a slide-ready table image of chosen results |

`source .venv/bin/activate` once per terminal. Hand off the FB128 for every capture.

## File names carry the setup

`data/raw_1ch_10000_a.bin`: raw stream, 1 channel, 10000 S/s, run a. `data/ev_4ch_30000_b.bin`: events, 4 channels,
30000 S/s, run b. `sweep.py` reads the setup from the name, so stick to it.

## Experiment 1: sample rate, one channel

For each rate in 30000, 20000, 15000, 10000, 6000:

1. `CH_RATE_HZ` to the rate, `N_CH 1`, `RAW_STREAM 1`. Build, flash, reset the central, wait for `subscribed`.
   `python log.py data/raw_1ch_<rate>_a.bin 20`, then the same as `_b`.
2. `RAW_STREAM 0`, build, flash, reset the central. Copy three `[prestno]` lines.
   `python log.py data/ev_1ch_<rate>_a.bin 20`, then `_b`.

Then `python sweep.py`. The figure `sweep_rate.png` shows, against rate: spikes caught (raw judged offline and device),
false detections, and spike-to-noise both in the offline band and through the device's own filter. The best rate is
the one where the device catches the most with the fewest false detections.

## Experiment 2: channel count, at the best rate

`N_CH` 1, 2, 4, 8 with `RAW_STREAM 0`, two runs each: `data/ev_<N>ch_<rate>_a.bin`, `_b`. Three `[prestno]` lines per
run; `dropped/s` there is the radio's limit. `sweep.py` adds `sweep_channels.png`.

## Reading the numbers

- **caught**: share of the SYNC spikes a channel fires that were detected and sent, with a 95% confidence interval
  across the seconds of the capture. Two runs of one setup should overlap.
- **false /s**: detections that do not sit on the SYNC grid. About 8% of false detections pass as real by chance.
- **spike-to-noise**: trough depth over the noise between spikes. The device catches nearly everything above about 6.5
  at its 4 sigma threshold, and falls off quickly below 5.
- **dropped /s** (status line): events the radio could not send. Zero until the link is full.

## Predictions, written before Experiment 1

From the captures made so far on bench revision A: at 30 kS/s the device catches about 77%, at 6 kS/s about 65%.
If 10 kS/s is best, as the live view suggested, it is because the analog band drops to 3 kHz there and removes noise
faster than it removes spike. The sweep will show whether the spike-to-noise ratio peaks between 6 and 15 kS/s.
