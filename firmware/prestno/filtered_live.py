"""Live view of the raw trace after the device's own filter. Needs the firmware built with RAW_STREAM 1.

    python filtered_live.py [RATE_HZ] [PORT]     defaults: 30000 and the relay port found automatically

The filter is the one the detector uses on the device: 300 Hz high-pass, then a 6 kHz low-pass when the analog band
is wider than 6 kHz. It runs continuously across packets, so what you see is what the detector sees.
Shows the last 50 ms, raw in grey behind the filtered trace. Space pauses, Ctrl+C stops.
"""
import sys, time
from collections import deque
import numpy as np
import serial
import matplotlib.pyplot as plt
from formats import find_relay_port, frames, is_raw, raw_samples, butter2, analog_band_hz


class Biquad:
    """one filter section whose state carries over from packet to packet."""
    def __init__(self, coef):
        self.b0, self.b1, self.b2, self.a1, self.a2 = coef
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def run(self, x):
        out = np.empty(len(x))
        for i, v in enumerate(x):
            y = self.b0 * v + self.b1 * self.x1 + self.b2 * self.x2 - self.a1 * self.y1 - self.a2 * self.y2
            self.x2, self.x1, self.y2, self.y1 = self.x1, v, self.y1, y
            out[i] = y
        return out


rate = float(sys.argv[1]) if len(sys.argv) > 1 else 30000.0
port = sys.argv[2] if len(sys.argv) > 2 else find_relay_port()
print(f"listening on {port}, time axis assumes {rate:.0f} S/s")
ser = serial.Serial(port, 921600, timeout=0.05)
buf = bytearray()

sections = [Biquad(butter2(300, rate, True))]
if analog_band_hz(rate) > 6000:
    sections.append(Biquad(butter2(6000, rate, False)))
band = f"300 Hz to {'6 kHz' if len(sections) == 2 else f'{analog_band_hz(rate) / 1000:g} kHz analog'}"

n_show = int(0.05 * rate)
raw = deque(maxlen=n_show)
filtered = deque(maxlen=n_show)
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
            x = raw_samples(payload)[1]
            y = x
            for s in sections:
                y = s.run(y)
            raw.extend(x)
            filtered.extend(y)
        if time.time() - last_draw < 0.3 or paused or not filtered:
            plt.pause(0.01); continue
        last_draw = time.time()
        r = np.array(raw); f = np.array(filtered)
        ms = np.arange(len(f)) / rate * 1000
        ax.cla()
        ax.plot(ms, r - np.median(r), color="0.85", lw=0.6)
        ax.plot(ms, f, color="#2c6fad", lw=1.0)
        ax.axhline(0, color="0.85", lw=0.5)
        ax.set(xlabel="ms", ylabel="uV", title=f"last 50 ms, filtered {band} (grey: raw)")
        fig.tight_layout(); fig.canvas.draw(); fig.canvas.flush_events()
        plt.pause(0.01)
except KeyboardInterrupt:
    pass
