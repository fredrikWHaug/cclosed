"""
Stream and 'scope' a RAW Intan .rhd file — the signal exactly as it leaves the
chip (16-bit codes -> microvolts), with zero third-party readers.

Everything is parsed here from the documented RHD format (struct + numpy): the
header, the data-block layout, and the amplifier de-interleaving. Verified
correct by signal autocorrelation (a real neural channel is smooth; a wrong
de-interleaving is white noise) — see the dev notes in the repo history.

This is the metal: `microvolts = 0.195 * (adc_code - 32768)`.

Knobs at the bottom. Optional 300-3000 Hz bandpass (needs scipy) makes spikes
pop out of the raw wideband; leave it off to see the true raw signal.

Run:  python sim/stream_rhd.py
"""
import struct
import numpy as np


def parse_header(f):
    """Read an RHD header; return the fields needed to locate amplifier samples."""
    def r(fmt): return struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))
    def qstr():
        (n,) = r('I')
        return "" if n == 0xFFFFFFFF else f.read(n).decode('utf-16-le', 'replace')

    assert r('I')[0] == 0xC6912702, "not an RHD file"
    vmaj, vmin = r('hh')
    fs = r('f')[0]
    r('h'); r('6f'); r('h'); r('2f')            # filter/notch/impedance params
    qstr(); qstr(); qstr()                       # notes
    num_temp = r('h')[0] if (vmaj, vmin) >= (1, 1) else 0
    if (vmaj, vmin) >= (1, 3): r('h')            # board mode
    if (vmaj, vmin) >= (2, 0): qstr()            # reference channel
    ngroups = r('h')[0]

    counts = {}                                  # enabled channels per signal_type
    for _ in range(ngroups):
        qstr(); qstr()
        _, nchan, _ = r('hhh')
        for _ in range(nchan):
            qstr(); qstr()
            _, _, stype, en = r('4h'); r('6h'); r('2f')
            if en:
                counts[stype] = counts.get(stype, 0) + 1

    block = 128 if (vmaj, vmin) >= (2, 0) else 60
    n_amp, n_aux, n_adc = counts.get(0, 0), counts.get(1, 0), counts.get(3, 0)
    # bytes per data block: timestamps + amp + aux(1/4 rate) + supply + temp + adc
    bpb = (block * 4 + n_amp * block * 2 + n_aux * (block // 4) * 2
           + counts.get(2, 0) * 2 + num_temp * 2 + n_adc * block * 2)
    return dict(fs=fs, n_amp=n_amp, block=block, bpb=bpb, header_end=f.tell())


def read_amplifier(path, channel, seconds):
    """Return `seconds` of one amplifier channel, in microvolts (channel-major)."""
    with open(path, "rb") as f:
        h = parse_header(f)
        nblocks = int(seconds * h["fs"] / h["block"])
        f.seek(h["header_end"])
        raw = f.read(nblocks * h["bpb"])
    out = np.empty(nblocks * h["block"], np.float32)
    for b in range(nblocks):
        amp = np.frombuffer(raw, '<u2', count=h["n_amp"] * h["block"],
                            offset=b * h["bpb"] + h["block"] * 4).reshape(h["n_amp"], h["block"])
        out[b * h["block"]:(b + 1) * h["block"]] = 0.195 * (amp[channel].astype(np.int32) - 32768)
    return out, h["fs"]


def bandpass(x, fs, lo=300, hi=3000):
    """300-3000 Hz filter to reveal spikes. scipy Butterworth if present, else a
    numpy FFT brick-wall (no dependency)."""
    try:
        from scipy.signal import butter, filtfilt
        b, a = butter(3, [lo / (fs / 2), hi / (fs / 2)], btype="band")
        return filtfilt(b, a, x).astype(np.float32)
    except ImportError:
        X = np.fft.rfft(x)
        fr = np.fft.rfftfreq(x.size, 1 / fs)
        X[(fr < lo) | (fr > hi)] = 0
        return np.fft.irfft(X, n=x.size).astype(np.float32)


if __name__ == "__main__":
    from pathlib import Path
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    ROOT = Path(__file__).resolve().parent.parent          # repo root, regardless of cwd
    FILE = ROOT / "raw-data/MA1_260413_131912/MA1_260413_131912.rhd"
    CHANNEL = 64        # try any 0-79
    SECONDS = 60        # how much to load and loop
    WIN_MS = 500        # scrolling window width
    SPEED = 1        # 1.0 = real time, 0.05 = 20x slow-mo
    FPS = 30
    FILTER = True      # bandpass 300-3000 Hz so spikes pop out of the raw signal

    signal, fs = read_amplifier(FILE, CHANNEL, SECONDS)
    if FILTER:
        signal = bandpass(signal, fs)
    WIN = int(WIN_MS / 1000 * fs)

    fig, ax = plt.subplots(figsize=(10, 3))
    (line,) = ax.plot(np.arange(WIN) / fs * 1000, signal[:WIN], lw=0.5, color="blue")
    ax.set_xlabel("time (ms)"); ax.set_ylabel("µV")
    ax.set_title(f"RAW Intan .rhd — channel {CHANNEL}" + (" (300-3000 Hz)" if FILTER else " (wideband)"))
    ax.set_ylim(signal.min() * 1.1, signal.max() * 1.1)

    step = max(1, int(SPEED * fs / FPS))
    def update(frame):
        i = (frame * step) % (signal.size - WIN)
        line.set_ydata(signal[i:i + WIN])
        return (line,)

    ani = FuncAnimation(fig, update, interval=1000 / FPS, blit=True, cache_frame_data=False)
    plt.tight_layout(); plt.show()
