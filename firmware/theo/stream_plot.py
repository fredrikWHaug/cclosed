"""Live plot of the Theo 30 kS/s ch0 stream; prints samples-per-period.

pip install bleak matplotlib numpy
"""
import asyncio, threading, collections, sys, glob, os
import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-theo"
CHR  = "12345678-1234-5678-1234-56789abcdef1"
RATE = 20000
UV_PER_CODE = 0.195

buf = collections.deque(maxlen=RATE)          # last 1 s of samples (uV)
stats = {"pkts": 0, "drops": 0, "last_seq": None}

log_fh = None
if "--log" in sys.argv:
    import time, struct
    _p = sys.argv[sys.argv.index("--log") + 1]
    log_fh = open(_p, "ab")
    print(f"logging packets to {_p}")

def on_notify(_, data: bytearray):
    if log_fh is not None:
        import time, struct
        log_fh.write(struct.pack("<dH", time.time(), len(data)) + bytes(data))
    seq = int.from_bytes(data[:2], "little")
    if stats["last_seq"] is not None:
        stats["drops"] += (seq - stats["last_seq"] - 1) & 0xFFFF
    stats["last_seq"] = seq
    stats["pkts"] += 1
    codes = np.frombuffer(bytes(data[2:]), dtype="<u2").astype(float)
    buf.extend((codes - 32768.0) * UV_PER_CODE)

async def ble():
    dev = await BleakScanner.find_device_by_name(NAME, timeout=15)
    if dev is None:
        raise SystemExit(f"'{NAME}' not found - is the DK advertising?")
    async with BleakClient(dev) as client:
        await client.start_notify(CHR, on_notify)
        print("subscribed - streaming")
        while True:
            await asyncio.sleep(1)
            print(f"pkts/s={stats['pkts']:4d}  samples/s={stats['pkts']*120:6d}  "
                  f"lost_pkts={stats['drops']}")
            stats["pkts"] = 0

def serial_reader(port):
    import serial
    ser = serial.Serial(port, 921600, timeout=1)
    print(f"reading frames from {port}")
    buf_bytes = b""
    while True:
        buf_bytes += ser.read(4096)
        while True:
            i = buf_bytes.find(b"\xa5\x5a")
            if i < 0 or len(buf_bytes) < i + 4:
                buf_bytes = buf_bytes[-1:] if i < 0 else buf_bytes[i:]
                break
            ln = buf_bytes[i+2] | (buf_bytes[i+3] << 8)
            if ln > 512:                       # corrupt length: resync
                buf_bytes = buf_bytes[i+2:]
                continue
            if len(buf_bytes) < i + 4 + ln:
                buf_bytes = buf_bytes[i:]
                break
            on_notify(None, bytearray(buf_bytes[i+4:i+4+ln]))
            buf_bytes = buf_bytes[i+4+ln:]

def stats_printer():
    import time
    while True:
        time.sleep(1)
        print(f"pkts/s={stats['pkts']:4d}  samples/s={stats['pkts']*120:6d}  "
              f"lost_pkts={stats['drops']}")
        stats["pkts"] = 0

if "--serial" in sys.argv:
    idx = sys.argv.index("--serial")
    port = sys.argv[idx+1] if len(sys.argv) > idx+1 else None
    if port is None:
        cands = sorted(glob.glob("/dev/tty.usbmodem*"))
        print("candidate ports:", cands)
        if not cands:
            raise SystemExit("no usbmodem ports found")
        port = cands[-1]
        print(f"auto-picked {port} (pass the port explicitly if wrong: "
              f"python stream_plot.py --serial /dev/tty.usbmodemXXXX)")
    threading.Thread(target=serial_reader, args=(port,), daemon=True).start()
    threading.Thread(target=stats_printer, daemon=True).start()
else:
    threading.Thread(target=lambda: asyncio.run(ble()), daemon=True).start()

fig, ax = plt.subplots(figsize=(10, 4))
paused = [False]
def on_key(ev):
    if ev.key == " ":
        paused[0] = not paused[0]
        fig.canvas.manager.set_window_title("PAUSED (space to resume)" if paused[0] else "live")
fig.canvas.mpl_connect("key_press_event", on_key)
(line,) = ax.plot([], [], "-", lw=1)
ax.set_xlabel("sample"); ax.set_ylabel("uV")

def update(_):
    if paused[0]:
        return (line,)
    y = np.array(buf)[-5000:]                   # ~3 periods: countable dots
    if len(y) < 10:
        return (line,)
    line.set_data(np.arange(len(y)), y)
    ax.relim(); ax.autoscale_view()
    # samples per period via FFT peak: robust against noise double-crossings
    full = np.array(buf) - np.mean(buf)
    if len(full) >= RATE // 2:
        spec = np.abs(np.fft.rfft(full))
        spec[0] = 0
        f = np.fft.rfftfreq(len(full), d=1.0 / RATE)
        fpk = f[int(np.argmax(spec))]
        if fpk > 0:
            ax.set_title(f"Spikes")
    return (line,)

ani = animation.FuncAnimation(fig, update, interval=200, blit=False, cache_frame_data=False)
try:
    plt.tight_layout()
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    # flush the log before the hard exit below, which skips interpreter teardown
    if log_fh is not None:
        log_fh.flush()
        log_fh.close()
    plt.close("all")
    os._exit(0)
