"""Live viewer for the Intan-mechanics chain: FG -> RHD-emulating slave -> command-paced SPI -> master -> BLE.

Same plot as signal_path_viewer.py, but tuned to the emulation's numbers:
ch0 rate = (1 / WORD_PERIOD_US) / N_SLOTS = 1 kword/s / 8 = 125 S/s, and
samples arrive as 16-bit offset-binary-ish codes (14-bit SAADC << 2).

pip install bleak matplotlib numpy
python sim/intan_emu_viewer.py
"""
import asyncio
import collections
import threading

import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-intan"
CHR = "12345678-1234-5678-1234-56789abcdef1"
FS = 125                        # ch0 samples/s (1 kword/s over 8 MUX slots)
WINDOW = 1000                   # samples shown = 8 s
MV_PER_CODE = 1800.0 / 65536.0  # 14-bit SAADC code << 2

samples = collections.deque(maxlen=WINDOW)
stats = {"pkts": 0, "seq_gaps": 0, "last": None}


def on_notify(_, data: bytearray):
    seq = data[0] | (data[1] << 8)
    half = data[2]
    if stats["last"] is not None:
        expect = (stats["last"] + (1 if half == 0 else 0)) & 0xFFFF
        if half == 0 and seq != expect:
            stats["seq_gaps"] += 1
    if half == 1:
        stats["last"] = seq
    stats["pkts"] += 1
    vals = np.frombuffer(data, dtype="<u2", offset=4).astype(np.float64)
    samples.extend(vals * MV_PER_CODE)


async def ble_task():
    print(f"scanning for '{NAME}'...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=30)
    if dev is None:
        print("device not found - is master-intan advertising?")
        return
    async with BleakClient(dev) as client:
        print("connected, subscribing")
        await client.start_notify(CHR, on_notify)
        while True:
            await asyncio.sleep(1)


threading.Thread(target=lambda: asyncio.run(ble_task()), daemon=True).start()

fig, ax = plt.subplots(figsize=(10, 4))
(line,) = ax.plot([], [], lw=1)
ax.set_xlim(0, WINDOW / FS * 1000)
ax.set_ylim(0, 1800)
ax.set_xlabel("ms")
ax.set_ylabel("mV")


def update(_):
    y = np.asarray(samples)
    line.set_data(np.arange(len(y)) / FS * 1000, y)
    ax.set_title(f"intan-mechanics live  |  pkts {stats['pkts']}  seq gaps {stats['seq_gaps']}")
    return (line,)


anim = animation.FuncAnimation(fig, update, interval=100)
plt.show()
