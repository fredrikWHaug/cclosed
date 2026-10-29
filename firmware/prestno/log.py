"""Record spike events arriving from the theo-central relay over USB serial.

    python log.py OUT.bin SECONDS [PORT]        e.g.  python log.py a_1ch_30k.bin 20

The relay frames each BLE notification as  A5 5A | length u16 | payload.
Each frame is written as  wall time f64 | length u16 | payload  (the same record format check.py reads).
"""
import struct, sys, time
import serial
from check import find_relay_port

out, seconds = sys.argv[1], float(sys.argv[2])
port = sys.argv[3] if len(sys.argv) > 3 else find_relay_port()
print(f"recording {seconds:.0f} s from {port}")

ser = serial.Serial(port, 921600, timeout=0.1)
buf = bytearray()
n = 0
t_end = time.time() + seconds
with open(out, "wb") as f:
    while time.time() < t_end:
        buf += ser.read(4096)
        while True:
            i = buf.find(b"\xa5\x5a")
            if i < 0 or len(buf) < i + 4:
                break
            length = buf[i + 2] | (buf[i + 3] << 8)
            if length > 512:                       # not a real header, resync
                del buf[:i + 2]
                continue
            if len(buf) < i + 4 + length:
                break
            payload = bytes(buf[i + 4:i + 4 + length])
            f.write(struct.pack("<dH", time.time(), length) + payload)
            n += 1
            del buf[:i + 4 + length]
print(f"wrote {n} notifications to {out}")
