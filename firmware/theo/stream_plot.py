"""Live plot of in0 voltage vs time from the Theo BLE stream."""
import asyncio, threading, collections, os
import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-theo"
CHR = "12345678-1234-5678-1234-56789abcdef1"
RATE = 20000
UV_PER_CODE = 0.195
WINDOW = 1000                                  # samples shown (50 ms)

buf = collections.deque(maxlen=WINDOW)

def on_notify(_, data: bytearray):
    codes = np.frombuffer(bytes(data[2:]), dtype="<u2").astype(float)
    buf.extend((codes - 32768.0) * UV_PER_CODE)

async def ble():
    dev = await BleakScanner.find_device_by_name(NAME, timeout=15)
    if dev is None:
        raise SystemExit(f"'{NAME}' not found - is the DK advertising?")
    async with BleakClient(dev) as client:
        await client.start_notify(CHR, on_notify)
        while True:
            await asyncio.sleep(1)

threading.Thread(target=lambda: asyncio.run(ble()), daemon=True).start()

fig, ax = plt.subplots(figsize=(10, 4))
(line,) = ax.plot([], [], lw=1)
ax.set_xlabel("time (ms)"); ax.set_ylabel("voltage (uV)")

def update(_):
    y = np.array(buf)
    line.set_data(np.arange(len(y)) / RATE * 1000, y)
    ax.relim(); ax.autoscale_view()
    return (line,)

ani = animation.FuncAnimation(fig, update, interval=200, cache_frame_data=False)
try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    os._exit(0)
