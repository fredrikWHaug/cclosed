"""Check one capture against the FB128 SYNC ground truth and draw it.

    python check.py CAPTURE.bin [RATE_HZ]      rate defaults to 30000; pass 6000 for the 6 kS/s test

Ground truth in SYNC 100 Hz mode: every channel fires one fixed-shape spike every 10.50 ms (95.2/s).
Prints per channel: events/s, share of the 95.2 caught, share of gaps on the 10.5 ms grid, noise before the spike.
Saves CAPTURE_check.png: spike times against the grid, gap histogram, waveforms, summary.
"""
import glob, struct, sys, time
import numpy as np
import matplotlib.pyplot as plt

SYNC_MS, SYNC_RATE = 10.5, 95.2
COLORS = ["#2c6fad", "#c76bae", "#e0a030", "#4f9d69", "#7b5ea7", "#d2553d", "#3aa6a6", "#8c8c4a"]


def find_relay_port():
    """the USB serial port that carries A5 5A frames, i.e. the relay's data port."""
    import serial
    for port in sorted(glob.glob("/dev/tty.usbmodem*")):
        try:
            with serial.Serial(port, 921600, timeout=0.2) as ser:
                data = b"".join(ser.read(4096) for _ in range(6))      # ~1.2 s
            if b"\xa5\x5a" in data:
                return port
            with serial.Serial(port, 115200):                           # a console port: leave it at its usual baud
                pass
        except (serial.SerialException, OSError):
            pass
    raise SystemExit("no relay port found; is theo-central connected and subscribed?")


def butter2(f_hz, rate, highpass):
    """2nd-order Butterworth section, bilinear transform, same coefficients as detector_init() in main.c."""
    k = np.tan(np.pi * f_hz / rate)
    norm = 1 / (1 + np.sqrt(2) * k + k * k)
    b0 = norm if highpass else k * k * norm
    b1 = -2 * b0 if highpass else 2 * b0
    return b0, b1, b0, 2 * (k * k - 1) * norm, (1 - np.sqrt(2) * k + k * k) * norm


def biquad(x, coef, x_rest, y_rest):
    """run one section over x, starting from a resting input x_rest and resting output y_rest."""
    b0, b1, b2, a1, a2 = coef
    out = np.empty(len(x)); x1 = x2 = x_rest; y1 = y2 = y_rest
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        out[i] = o
    return out


def detector_filter(x, rate):
    """x through the firmware's chain, causal: high-pass 300 Hz, then low-pass 6 kHz (0.4 x rate below 15 kS/s).
    Each section starts at rest on the window's first sample so a 2 ms window does not ring at the start."""
    lp_hz = 6000 if rate >= 15000 else 0.4 * rate
    y = np.asarray(x, dtype=float)
    y = biquad(y, butter2(300, rate, True), x_rest=y[0], y_rest=0.0)      # high-pass blocks DC: resting output is 0
    y = biquad(y, butter2(lp_hz, rate, False), x_rest=y[0], y_rest=y[0])  # low-pass passes DC: rests at the first value
    return y


def events_in(pkt):
    """events packed in one notification -> list of (seq, ch, n, pre, trough_index, microvolts).
    Event = seq u16 | ch u8 | n u8 | pre u8 | trough u32 | n x 12-bit two's complement, two per 3 bytes."""
    out, o = [], 0
    while o + 9 <= len(pkt):
        s, c, n, p, trough = struct.unpack_from("<HBBBI", pkt, o); o += 9
        packed = (3 * n + 1) // 2
        if n == 0 or o + packed > len(pkt):
            break
        b = pkt[o:o + packed]; o += packed
        vals = np.empty(n, dtype=np.int32)
        for k in range(0, n, 2):
            j = k // 2 * 3
            a = b[j] | ((b[j + 1] & 0x0F) << 8)
            vals[k] = a - 4096 if a >= 2048 else a
            if k + 1 < n:
                v = (b[j + 1] >> 4) | (b[j + 2] << 4)
                vals[k + 1] = v - 4096 if v >= 2048 else v
        out.append((s, c, n, p, trough, vals * 16 * 0.195))      # 12-bit -> 16-bit code -> microvolts
    return out


def read(path):
    """all events in a log.py file -> dict of arrays."""
    data = open(path, "rb").read()
    wall, seq, ch, pre, idx, uv = [], [], [], [], [], []
    i = 0
    while i + 10 <= len(data):
        t, length = struct.unpack_from("<dH", data, i); i += 10
        for s, c, n, p, trough, w in events_in(data[i:i + length]):
            wall.append(t); seq.append(s); ch.append(c); pre.append(p); idx.append(trough); uv.append(w)
        i += length
    if not seq:
        raise SystemExit(f"no events in {path}")
    return dict(wall=np.array(wall), seq=np.array(seq), ch=np.array(ch), pre=np.array(pre),
                idx=np.array(idx, dtype=np.int64), uv=np.array(uv))


if __name__ == "__main__":
    path = sys.argv[1]
    rate = float(sys.argv[2]) if len(sys.argv) > 2 else 30000.0
    ev = read(path)
    seconds = ev["wall"][-1] - ev["wall"][0]
    lost = int(((np.diff(ev["seq"].astype(int)) % 65536) - 1).sum())
    channels = sorted(set(ev["ch"]))
    pre = int(ev["pre"][0])

    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    print(f"{path}: {len(ev['seq'])} events in {seconds:.1f} s, lost {lost}, {len(channels)} channels at {rate:.0f} S/s")
    for k, c in enumerate(channels):
        sel = ev["ch"] == c
        t_ms = ev["idx"][sel] / rate * 1000
        gaps = np.diff(t_ms)
        slots = np.round(gaps / SYNC_MS)
        on_grid = np.mean(np.abs(gaps - slots * SYNC_MS) < 0.6) * 100          # gaps that are a whole number of SYNC periods
        w = ev["uv"][sel]
        noise = np.median(w[:, :max(3, pre // 2)].std(1))                       # raw noise in the half-window before the spike
        print(f"  in{c}: {sel.sum() / seconds:5.1f} events/s = {sel.sum() / seconds / SYNC_RATE * 100:3.0f}% of SYNC,"
              f"  on grid {on_grid:3.0f}%,  noise before spike {noise:4.0f} uV")
        start = t_ms[len(t_ms) // 2]
        view = t_ms[(t_ms >= start) & (t_ms < start + 1000)] - start
        ax[0, 0].vlines(view, c - 0.4, c + 0.4, color=COLORS[k % 8], lw=1)
        ax[0, 1].hist(gaps, bins=np.arange(0, 60, 0.25), color=COLORS[k % 8], alpha=0.6)
        ms = (np.arange(w.shape[1]) - pre) / rate * 1000
        ax[1, 0].plot(ms, w[:150].T, color=COLORS[k % 8], lw=0.3, alpha=0.15)
        ax[1, 0].plot(ms, w.mean(0), color=COLORS[k % 8], lw=2)

    for g in range(1, 96):
        ax[0, 0].axvline(view[0] + g * SYNC_MS, color="0.85", lw=0.5, zorder=0)
    ax[0, 0].set(title="1 s of spike times; grey lines every 10.5 ms", xlabel="ms", yticks=channels, ylabel="channel")
    ax[0, 1].axvline(SYNC_MS, color="0.3", lw=1, ls="--")
    ax[0, 1].set(title="gap between consecutive spikes (truth 10.5 ms)", xlabel="ms", ylabel="count", xlim=(0, 60))
    ax[1, 0].set(title="received spike windows and their means", xlabel="ms from trough", ylabel="uV")
    ax[1, 1].axis("off")
    ax[1, 1].text(0, 0.9, f"{path}\n{len(channels)} ch x {rate:.0f} S/s = {len(channels) * rate:.0f} conversions/s\n"
                          f"{len(ev['seq']) / seconds / len(channels):.1f} events/s per channel  (truth {SYNC_RATE})\n"
                          f"lost events {lost}", va="top", fontsize=12, family="monospace")
    fig.tight_layout()
    out = path.rsplit(".", 1)[0] + "_check.png"
    fig.savefig(out, dpi=150); print("saved", out)
    plt.show()
