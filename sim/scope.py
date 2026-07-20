"""
Live 'oscilloscope' for a synthetic extracellular neural signal.

Scrolls a real-time voltage trace in matplotlib so a spike actually looks like a
spike. Same idea as firmware/spi/monitor.py, but the samples come from a
generator here instead of the serial port. Swap `signal` for a real .rhd channel
or a MEArec recording to stream those instead — the plotting loop is unchanged.

Run:  python sim/scope.py       (close the window or Ctrl-C to stop)
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

FS = 30_000        # sample rate (Hz) — real extracellular rate
WIN_MS = 500       # width of the scrolling window (ms)
SPEED = 0.05       # playback speed: 1.0 = real time, 0.05 = 20x slow-mo (see shape)
FPS = 30

WIN = int(WIN_MS / 1000 * FS)
rng = np.random.default_rng(0)

# biphasic extracellular spike template (~2 ms): sharp negative trough + rebound
tt = (np.arange(-30, 30) / FS) * 1000                                  # ms
spike = -100 * np.exp(-(tt ** 2) / 0.02) + 35 * np.exp(-((tt - 0.4) ** 2) / 0.05)  # µV

# 20 s of baseline noise with ~5 Hz Poisson-timed spikes
N = 20 * FS
signal = rng.normal(0, 8, N)                                          # 8 µV RMS noise
for t0 in np.where(rng.random(N) < 5 / FS)[0]:
    signal[t0:t0 + spike.size] += spike[:N - t0]

fig, ax = plt.subplots(figsize=(10, 3))
(line,) = ax.plot(np.arange(WIN) / FS * 1000, signal[:WIN], lw=0.6, color="blue")
ax.set_xlabel("time (ms)"); ax.set_ylabel("µV"); ax.set_ylim(-140, 70)
ax.set_title("synthetic extracellular stream (scrolling)")

step = max(1, int(SPEED * FS / FPS))
def update(frame):
    i = (frame * step) % (N - WIN)
    line.set_ydata(signal[i:i + WIN])
    return (line,)

ani = FuncAnimation(fig, update, interval=1000 / FPS, blit=True, cache_frame_data=False)
plt.tight_layout(); plt.show()
