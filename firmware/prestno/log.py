"""Record what the relay forwards, raw or events alike.

    python log.py OUT.bin SECONDS [PORT]        e.g.  python log.py raw_1ch_30k.bin 20
"""
import struct, sys, time
import serial
from formats import find_relay_port, frames, is_raw

out, seconds = sys.argv[1], float(sys.argv[2])
port = sys.argv[3] if len(sys.argv) > 3 else find_relay_port()
print(f"recording {seconds:.0f} s from {port}")

ser = serial.Serial(port, 921600, timeout=0.1)
buf = bytearray()
n_raw = n_ev = 0
t_end = time.time() + seconds
with open(out, "wb") as f:
    while time.time() < t_end:
        for payload in frames(ser, buf):
            f.write(struct.pack("<dH", time.time(), len(payload)) + payload)
            if is_raw(payload):
                n_raw += 1
            else:
                n_ev += 1
print(f"wrote {n_raw} raw packets and {n_ev} event packets to {out}")
