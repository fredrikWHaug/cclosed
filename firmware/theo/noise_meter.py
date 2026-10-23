"""Live noise floor of the relayed stream, once per second: python noise_meter.py /dev/tty.usbmodemXXXX"""
import sys, time
import numpy as np
from scipy.signal import butter, sosfilt
from serial_source import frames

RATE = 30000
sos = butter(3, (300, 6000), "bandpass", fs=RATE, output="sos")
chunk, t0 = [], time.time()
print("noise sigma in the 300-6000 Hz band (lower is better; 50 uV = today's unaided bench)")
for payload in frames(sys.argv[1]):
    chunk.append(np.frombuffer(payload[2:], dtype="<u2"))
    if time.time() - t0 >= 1.0:
        uv = (np.concatenate(chunk).astype(float) - 32768) * 0.195
        filtered = sosfilt(sos, uv - uv.mean())[RATE // 10:]          # drop the filter's warm-up
        sigma = np.median(np.abs(filtered)) / 0.6745
        print(f"  {sigma:5.1f} uV   " + "#" * int(sigma / 2), flush=True)
        chunk, t0 = [], time.time()
