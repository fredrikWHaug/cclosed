"""Live view of the spike events coming through the relay.

    python live.py [RATE_HZ] [PORT]     defaults: 30000 and the relay port found automatically

Top: one second of spike times per channel, with a grey line every 10.5 ms (the SYNC period) so you can see the
95 spikes a second land on the grid. Middle: the last 100 ms with the spike windows drawn where they happened,
9 or 10 spikes and the silence between them. Bottom: the last 100 spike windows overlaid.
Times come from the headstage's own sample counter, so radio jitter does not move them.
Space pauses and resumes the drawing, Ctrl+C stops.
"""
import sys, time
import numpy as np
import serial
import matplotlib.pyplot as plt
from check import events_in, find_relay_port, COLORS, SYNC_RATE

rate = float(sys.argv[1]) if len(sys.argv) > 1 else 30000.0
port = sys.argv[2] if len(sys.argv) > 2 else find_relay_port()
print(f"listening on {port}, waveform axis assumes {rate:.0f} S/s")
ser = serial.Serial(port, 921600, timeout=0.05)
buf = bytearray()
times, chans, waves, pre = [], [], [], None          # times in headstage seconds (trough sample / rate)

paused = False
def on_key(event):
    global paused
    if event.key == " ":
        paused = not paused
        print("paused" if paused else "running")

plt.ion()
fig, (ax_t, ax_s, ax_w) = plt.subplots(3, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [1, 1, 1.3]})
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
                times.append(trough / rate); chans.append(c); waves.append(w); pre = p
            del buf[:i + 4 + length]
        now = time.time() - t0
        if now - last_draw > 0.5 and times and not paused:
            last_draw = now
            t = np.array(times); c = np.array(chans); latest = t[-1]
            ax_t.cla(); ax_s.cla(); ax_w.cla()
            for g in np.arange(latest, latest - 1.0, -0.0105):                  # the SYNC grid, anchored on the newest spike
                ax_t.axvline(g, color="0.88", lw=0.5, zorder=0)
            for k in sorted(set(c)):
                sel = (c == k) & (t > latest - 1.0)
                ax_t.vlines(t[sel], k - 0.4, k + 0.4, color=COLORS[k % 8], lw=1)
                ax_t.text(latest - 1.0, k + 0.45, f"in{k}: {sel.sum()} in the last second (SYNC {SYNC_RATE})",
                          fontsize=8, color=COLORS[k % 8])
            ax_t.set(xlim=(latest - 1.0, latest), ylabel="channel", xlabel="headstage time (s)",
                     title="one second of spike times; grey lines every 10.5 ms")
            ms = (np.arange(len(waves[-1])) - pre) / rate * 1000
            for ti, k, w in zip(t[-12:], c[-12:], waves[-12:]):                  # last 100 ms, windows at their real times
                if ti > latest - 0.1:
                    ax_s.plot(ti * 1000 + ms, w, color=COLORS[k % 8], lw=0.8)
            ax_s.set(xlim=((latest - 0.1) * 1000, latest * 1000 + 1.5), xlabel="headstage time (ms)", ylabel="uV",
                     title="last 100 ms: the spike windows where they happened")
            W = np.array(waves[-100:])
            for w, k in zip(W, chans[-100:]):
                ax_w.plot(ms, w, color=COLORS[k % 8], lw=0.5, alpha=0.4)
            lo, hi = np.percentile(W, [1, 99])                       # ignore the few wild windows
            ax_w.set(xlabel="ms from trough", ylabel="uV", title="last 100 spike windows",
                     xlim=(-0.4, 0.9), ylim=(lo - 0.1 * (hi - lo), hi + 0.1 * (hi - lo)))
            fig.tight_layout(); fig.canvas.draw(); fig.canvas.flush_events()
        plt.pause(0.01)
except KeyboardInterrupt:
    print(f"\n{len(times)} events seen in {time.time() - t0:.0f} s")
