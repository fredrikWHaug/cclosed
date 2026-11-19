"""What the headstage sends, and how to read it. Shared by log.py, live.py and compare.py.

Raw packets  (RAW_STREAM 1):  seq u16 | 120 x u16 little-endian codes, 0.195 uV per code, 32768 = 0 V.  242 bytes.
Event packets (RAW_STREAM 0):  one or more events back to back, each
                               seq u16 | ch u8 | n u8 | pre u8 | trough_index u32 | n x 12-bit two's complement,
                               value = (code - 32768) / 16, packed two per 3 bytes.  101 bytes per event at 30 kS/s.
The relay wraps every packet as  A5 5A | length u16 | payload.  log.py stores  wall time f64 | length u16 | payload.
"""
import glob, struct
import numpy as np

UV_PER_CODE = 0.195
RAW_BYTES = 242


def find_relay_port():
    """the USB serial port carrying A5 5A frames, i.e. the relay's data port."""
    import serial
    for port in sorted(glob.glob("/dev/tty.usbmodem*")):
        try:
            with serial.Serial(port, 921600, timeout=0.2) as ser:
                data = b"".join(ser.read(4096) for _ in range(6))
            if b"\xa5\x5a" in data:
                return port
            with serial.Serial(port, 115200):          # a console port: leave it at its usual baud
                pass
        except (serial.SerialException, OSError):
            pass
    raise SystemExit("no relay port found; is theo-central connected and subscribed?")


def frames(ser, buf):
    """pull complete relay frames out of buf (a bytearray fed from ser); yields payloads."""
    buf += ser.read(4096)
    while True:
        i = buf.find(b"\xa5\x5a")
        if i < 0 or len(buf) < i + 4:
            return
        length = buf[i + 2] | (buf[i + 3] << 8)
        if length > 512:
            del buf[:i + 2]
            continue
        if len(buf) < i + 4 + length:
            return
        yield bytes(buf[i + 4:i + 4 + length])
        del buf[:i + 4 + length]


def is_raw(payload):
    return len(payload) == RAW_BYTES


def raw_samples(payload):
    """-> (seq, microvolts[120])"""
    seq = payload[0] | (payload[1] << 8)
    return seq, (np.frombuffer(payload[2:], dtype="<u2").astype(float) - 32768) * UV_PER_CODE


def events(payload):
    """-> list of (seq, ch, pre, trough_index, microvolts[n])"""
    out, o = [], 0
    while o + 9 <= len(payload):
        seq, ch, n, pre, trough = struct.unpack_from("<HBBBI", payload, o); o += 9
        packed = (3 * n + 1) // 2
        if n == 0 or o + packed > len(payload):
            break
        b = payload[o:o + packed]; o += packed
        vals = np.empty(n, dtype=np.int32)
        for k in range(0, n, 2):
            j = k // 2 * 3
            a = b[j] | ((b[j + 1] & 0x0F) << 8)
            vals[k] = a - 4096 if a >= 2048 else a
            if k + 1 < n:
                v = (b[j + 1] >> 4) | (b[j + 2] << 4)
                vals[k + 1] = v - 4096 if v >= 2048 else v
        out.append((seq, ch, pre, trough, vals * 16 * UV_PER_CODE))
    return out


def read_log(path):
    """every (wall time, payload) record in a log.py file."""
    data = open(path, "rb").read()
    i, out = 0, []
    while i + 10 <= len(data):
        t, length = struct.unpack_from("<dH", data, i); i += 10
        out.append((t, data[i:i + length])); i += length
    return out


# ---- the detector's filter, written the same way as detector_init() and process() in src/main.c ----

def butter2(f_hz, rate, highpass):
    k = np.tan(np.pi * f_hz / rate)
    norm = 1 / (1 + np.sqrt(2) * k + k * k)
    b0 = norm if highpass else k * k * norm
    b1 = -2 * b0 if highpass else 2 * b0
    return b0, b1, b0, 2 * (k * k - 1) * norm, (1 - np.sqrt(2) * k + k * k) * norm


def biquad(x, coef):
    b0, b1, b2, a1, a2 = coef
    out = np.empty(len(x)); x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        out[i] = o
    return out


def analog_band_hz(rate):
    """the Intan upper cutoff the firmware selects for this rate (FH_HZ in src/main.c)."""
    for floor, fh in ((25000, 10000), (18750, 7500), (12500, 5000), (7500, 3000), (6250, 2500), (5000, 2000)):
        if rate >= floor:
            return fh
    return 1500


def detector_filter(x, rate):
    """the device's chain, causal: 300 Hz high-pass, then a 6 kHz low-pass only when the analog band is wider than 6 kHz."""
    y = biquad(np.asarray(x, dtype=float), butter2(300, rate, True))
    if analog_band_hz(rate) > 6000:
        y = biquad(y, butter2(6000, rate, False))
    return y
