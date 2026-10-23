"""Live plot of the Theo stream: python stream_plot.py [--serial /dev/tty.usbmodemXXXX]"""
import asyncio, threading, collections, os, sys
import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-theo"
CHR = "12345678-1234-5678-1234-56789abcdef1"
RATE = 30000                                   # per channel
UV_PER_CODE = 0.195
WINDOW = 5000                                  # samples shown per channel (167 ms)

N_CH = 1
bufs = [collections.deque(maxlen=WINDOW) for _ in range(N_CH)]

def on_notify(_, data: bytearray):
    codes = np.frombuffer(bytes(data[2:]), dtype="<u2").astype(float)
    uv = (codes - 32768.0) * UV_PER_CODE
    for i, buf in enumerate(bufs):             # sample k belongs to channel k % N_CH
        buf.extend(uv[i::N_CH])

async def ble():
    dev = await BleakScanner.find_device_by_name(NAME, timeout=15)
    if dev is None:
        raise SystemExit(f"'{NAME}' not found - is the DK advertising?")
    async with BleakClient(dev) as client:
        await client.start_notify(CHR, on_notify)
        while True:
            await asyncio.sleep(1)

def serial_relay(port):
    from serial_source import frames
    for payload in frames(port):
        on_notify(None, bytearray(payload))

if "--serial" in sys.argv:
    from serial_source import list_ports
    args = sys.argv[sys.argv.index("--serial") + 1:]
    if not args:
        raise SystemExit("give the relay DK's VCOM1 port, one of: " + ", ".join(list_ports()))
    threading.Thread(target=serial_relay, args=(args[0],), daemon=True).start()
else:
    threading.Thread(target=lambda: asyncio.run(ble()), daemon=True).start()

fig, axes = plt.subplots(N_CH, 1, figsize=(10, 2 + 1.5 * N_CH), sharex=True, squeeze=False)
axes = axes[:, 0]                              # always a list, even for one channel
lines = [ax.plot([], [], lw=1, color=f"C{i}")[0] for i, ax in enumerate(axes)]
for i, ax in enumerate(axes):
    ax.set_ylabel(f"in{i} (uV)")
axes[-1].set_xlabel("time (ms)")

def update(_):
    for line, buf, ax in zip(lines, bufs, axes):
        y = np.array(buf)
        line.set_data(np.arange(len(y)) / RATE * 1000, y)
        ax.relim(); ax.autoscale_view()
    return lines

ani = animation.FuncAnimation(fig, update, interval=200, cache_frame_data=False)
try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    os._exit(0)
