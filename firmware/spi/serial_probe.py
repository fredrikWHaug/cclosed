"""
Measure the ACTUAL serial throughput and dump raw bytes — tells us the true baud
end-to-end (independent of the plot). Paste the text output.

Close monitor.py first (only one process can hold the serial port).

Usage:  python firmware/spi/serial_probe.py --port <slave_port> [--baud 1000000]
  ~11,500 bytes/s  -> link is effectively 115200
  ~100,000 bytes/s -> link is effectively 1 Mbaud
  garbage bytes    -> baud MISMATCH (host and board disagree)
"""
import argparse
import time
import serial

ap = argparse.ArgumentParser()
ap.add_argument("--port", required=True)
ap.add_argument("--baud", type=int, default=1000000)
args = ap.parse_args()

ser = serial.Serial(args.port, args.baud, timeout=1)
print(f"opened {args.port} @ {args.baud} baud")
ser.reset_input_buffer()

t0 = time.perf_counter()
n = 0
while time.perf_counter() - t0 < 2.0:
    n += len(ser.read(4096))
dt = time.perf_counter() - t0

print(f"throughput: {n/dt:,.0f} bytes/sec over {dt:.1f}s "
      f"(115200 baud ~= 11,500 B/s ; 1 Mbaud ~= 100,000 B/s)")
print(f"first 80 bytes: {ser.read(80)!r}")
ser.close()
