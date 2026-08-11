
import asyncio
import collections
import threading
import time
import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-sigpath"
CHR = "12345678-1234-5678-1234-56789abcdef1"
WINDOW = 200                    
UV_PER_CODE = 0.195

samples = collections.deque(maxlen=WINDOW)
st = {"pkts": 0, "drops": 0, "win_bytes": 0, "win_samples": 0,
      "last_seq": None, "t0": time.monotonic(), "sps": 0.0}


def on_notify(_, data: bytearray):
    seq = data[0] | (data[1] << 8)
    if st["last_seq"] is not None:
        gap = (seq - st["last_seq"] - 1) & 0xFFFF
        if gap != 0 and gap < 0x8000:
            st["drops"] += gap
    st["last_seq"] = seq

    vals = np.frombuffer(data, dtype="<u2", offset=2).astype(np.float64)
    samples.extend((vals - 32768.0) * UV_PER_CODE)     

    st["pkts"] += 1
    st["win_bytes"] += len(data)
    st["win_samples"] += len(vals)


async def reporter():
    while True:
        await asyncio.sleep(2.0)
        now = time.monotonic()
        dt = now - st["t0"]
        st["t0"] = now
        st["sps"] = st["win_samples"] / dt if dt else 0.0
        kbps = st["win_bytes"] * 8 / 1000.0 / dt if dt else 0.0
        st["win_bytes"] = 0
        st["win_samples"] = 0
        print(f"{kbps:7.1f} kbit/s   ~{st['sps']:.0f} S/s   "
              f"pkts {st['pkts']}   dropped pkts {st['drops']}")


async def ble_task():
    print(f"scanning for '{NAME}'...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=30)
    if dev is None:
        print("not found - is the master advertising?")
        return
    async with BleakClient(dev) as client:
        print(f"connected to {dev.address} - subscribing")
        await client.start_notify(CHR, on_notify)
        await reporter()


threading.Thread(target=lambda: asyncio.run(ble_task()), daemon=True).start()

fig, ax = plt.subplots(figsize=(11, 4))
(line,) = ax.plot([], [], lw=1)
ax.set_xlim(0, WINDOW)
ax.set_ylim(-3250, 3250)
ax.set_xlabel("sample index")
ax.set_ylabel("uV (electrode-referred)")
ax.grid(True, alpha=0.3)


def update(_):
    y = np.asarray(samples)
    line.set_data(np.arange(len(y)), y)
    ax.set_title(f"ch0  |  ~{st['sps']:.0f} S/s  |  pkts {st['pkts']}  dropped {st['drops']}")
    return (line,)


anim = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.show()
