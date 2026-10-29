"""Live view of the raw trace. Needs the firmware built with RAW_STREAM 1.

    python live.py [RATE_HZ] [PORT]     defaults: 30000 and the relay port found automatically

Shows the last 50 ms. In SYNC you see 4 to 5 identical spikes 10.5 ms apart. Space pauses, Ctrl+C stops.
"""
import sys, time
from collections import deque
import numpy as np
import serial
import matplotlib.pyplot as plt
from formats import find_relay_port, frames, is_raw, raw_samples

rate = float(sys.argv[1]) if len(sys.argv) > 1 else 30000.0
port = sys.argv[2] if len(sys.argv) > 2 else find_relay_port()
print(f"listening on {port}, time axis assumes {rate:.0f} S/s")
ser = serial.Serial(port, 921600, timeout=0.05)
buf = bytearray()
trace = deque(maxlen=int(0.05 * rate))
paused = False

def on_key(event):
    global paused
    if event.key == " ":
        paused = not paused

plt.ion()
fig, ax = plt.subplots(figsize=(10, 5))
fig.canvas.mpl_connect("key_press_event", on_key)
last_draw = 0
try:
    while True:
        for payload in frames(ser, buf):
            if not is_raw(payload):
                raise SystemExit("the headstage is sending spike windows, not the raw stream; rebuild with RAW_STREAM 1")
            trace.extend(raw_samples(payload)[1])
        if time.time() - last_draw < 0.3 or paused or not trace:
            plt.pause(0.01); continue
        last_draw = time.time()
        y = np.array(trace)
        ax.cla()
        ax.plot(np.arange(len(y)) / rate * 1000, y, color="#2c6fad", lw=0.8)
        ax.axhline(0, color="0.85", lw=0.5)
        ax.set(xlabel="ms", ylabel="uV", title="raw stream, last 50 ms")
        fig.tight_layout(); fig.canvas.draw(); fig.canvas.flush_events()
        plt.pause(0.01)
except KeyboardInterrupt:
    pass
