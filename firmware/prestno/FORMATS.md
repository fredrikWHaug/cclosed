# Two firmwares, two packet formats

The headstage can run two kinds of firmware. They advertise under the same BLE name, use the same service, go through the same `theo-central` relay and the same serial port, so from the Mac they look identical until you parse the bytes. Every plotting and logging script expects one format or the other, and a script given the wrong one either shows garbage or crashes. This is what happened when `streamplot.py` was pointed at a `prestno` headstage on 2026-10-29: "buffer size must be a multiple of element size".

## What each firmware sends

| | raw streaming | spike events |
|---|---|---|
| firmware | `theo`, or `prestno` built with `RAW_STREAM 1` | `prestno` (default) and `spike` |
| what is sent | every sample | only a 2 ms window around each detected spike |
| one notification | `seq u16` then 120 samples as `u16` little-endian, offset-binary codes (0.195 µV per code, 32768 = 0 V); 242 bytes | one or two events back to back, 101 bytes each at 30 kS/s |
| one event | | `seq u16`, `channel u8`, `n_samples u8`, `pre u8`, `trough_index u32`, then `n_samples` 12-bit two's-complement values packed two per 3 bytes, 3.12 µV per step |
| channel order | sample k belongs to channel k mod N_CH | each event carries its channel |
| time base | packet counter only | `trough_index` is the channel's own sample counter, so spike times are exact |
| data rate at 1 ch x 30 kS/s | 484 kbit/s, 250 notifications/s | about 95 events/s in SYNC, 77 kbit/s |
| data rate at 4 ch x 30 kS/s | 1.9 Mbit/s, does not fit the radio | about 380 events/s in SYNC, 310 kbit/s |
| sequence counter | per packet | per event |

The relay forwards each notification as `A5 5A | length u16 | payload` at 921600 baud without caring about the format. Its status line does care: since 2026-10-28 it counts events and sequence gaps assuming the event format, so with raw packets the `events/s` and `ble_drops` columns are garbage (ble_drops runs into the hundreds of millions). Only `pkts/s` and `uart_drops` mean anything in raw mode, and a reset of the central clears the counter. In raw mode the headstage runs theo's loop and prints `[prestno raw] N packets sent` every 1000 packets instead of the per-second status line, since the detector does not run. `log.py` and theo's `log_stream.py` both write `wall time f64 | length u16 | payload` per notification, so a capture file is also format-blind until parsed.

## Which script needs which format

| script | expects | behaviour on the other format |
|---|---|---|
| `prestno/log.py` | either | records bytes, counts raw and event packets separately |
| `prestno/live.py` | either | switches its display on the packet length |
| `prestno/compare.py` | one raw file and one event file | tells them apart by packet length |
| `theo/stream_plot.py`, `theo/noise_meter.py`, `theo/score_capture.py`, `sorting/*.py` | raw | 101-byte events are an odd length, `np.frombuffer` raises, or values are silently wrong |
| `spike/events.py`, `spike/check_sync.py`, `spike/spike_events.py` | events | a 242-byte raw packet parses as nonsense events |

## How to tell which one the headstage is running

- The boot line on the headstage console. `prestno` prints `prestno spike detector, N ch x R S/s, window 20+41 samples` and, with `RAW_STREAM 1`, still prints that line but then sends raw packets. theo prints `streaming N channels interleaved`.
- The relay's status line. Raw at 1 ch x 30 kS/s is a steady 250 pkts/s. Events in SYNC are about 48 to 95 pkts/s per channel and vary.
- Notification length. 242 bytes is raw. 101 or 202 is events.

## Rules that follow

1. To look at the continuous signal, build `prestno` with `RAW_STREAM 1`. Only up to about 30,000 conversions per second fit the radio this way.
2. For every detection test, `RAW_STREAM 0`. `live.py` and `log.py` work in both modes; `compare.py` needs one capture of each.
3. Never run a theo-era script on a `prestno` capture or the other way round without checking the notification length first.
4. `spike` is the development copy of the event firmware and is frozen. `prestno` is the clean one. `theo` is frozen raw-streaming firmware and is no longer needed once `RAW_STREAM` exists.
