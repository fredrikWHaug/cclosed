"""Live view of one spike at a time: the raw samples of the most recent spike window, as the headstage sent them.

    python trace.py [RATE_HZ] [PORT]    defaults: 30000 and the relay port found automatically

Top: the newest window in blue with its samples marked, the five before it in grey.
Bottom: the same windows through the detector's filter (300 Hz high-pass, 6 kHz low-pass, causal, as in the firmware),
which is the signal the threshold is applied to.
In SYNC 100 Hz mode every window should show the same shape. Space pauses and resumes the drawing, Ctrl+C stops.
"""
import sys, time
from collections import deque
import numpy as np
import serial
import matplotlib.pyplot as plt
from check import events_in, find_relay_port, detector_filter

rate = float(sys.argv[1]) if len(sys.argv) > 1 else 30000.0
port = sys.argv[2] if len(sys.argv) > 2 else find_relay_port()
print(f"listening on {port}, time axis assumes {rate:.0f} S/s")
ser = serial.Serial(port, 921600, timeout=0.05)
buf = bytearray()
recent = deque(maxlen=6)                      # (channel, pre, microvolts)
count = 0

paused = False
def on_key(event):
    global paused
    if event.key == " ":
        paused = not paused
        print("paused" if paused else "running")

plt.ion()
fig, (ax, ax_f) = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
fig.canvas.mpl_connect("key_press_event", on_key)
t0 = time.time(); last_draw = 0
try:
    while True:
        buf += ser.read(4096)
        while True:
            i = buf.find(b"\xa5\x5a")
            if i < 0 or len(buf) < i + 4:
                break
            length = buf[i + 2] | (buf[i + 3] << 8)
            if length > 512:
                del buf[:i + 2]; continue
            if len(buf) < i + 4 + length:
                break
            for s, c, n, p, trough, w in events_in(bytes(buf[i + 4:i + 4 + length])):
                recent.append((c, p, w)); count += 1
            del buf[:i + 4 + length]
        now = time.time() - t0
        if now - last_draw > 0.3 and recent and not paused:
            last_draw = now
            ax.cla(); ax_f.cla()
            for k, (c, p, w) in enumerate(recent):
                ms = (np.arange(len(w)) - p) / rate * 1000
                newest = k == len(recent) - 1
                style = dict(color="#2c6fad", lw=1.5, ms=3) if newest else dict(color="0.75", lw=0.8)
                ax.plot(ms, w, "-o" if newest else "-", **style)
                ax_f.plot(ms, detector_filter(w, rate), "-o" if newest else "-", **style)
                if newest:
                    ax.set_title(f"in{c}, spike {count}, {len(w)} samples at {rate / 1000:g} kS/s, {count / max(now, 1):.0f} spikes/s so far")
            for a in (ax, ax_f):
                a.axhline(0, color="0.85", lw=0.5)
            ax.set(ylabel="uV, raw")
            ax_f.set(xlabel="ms from trough", ylabel="uV, detector filter 300 Hz to 6 kHz")
            fig.tight_layout(); fig.canvas.draw(); fig.canvas.flush_events()
        plt.pause(0.01)
except KeyboardInterrupt:
    print(f"\n{count} spikes seen in {time.time() - t0:.0f} s")
