"""Read a spike-event capture written by log_stream.py (one record per BLE notification).

Each notification holds one or more events back to back:
    seq u16 | channel u8 | n_samples u8 | pre u8 | trough_index u32 | n_samples x 12-bit two's complement
12-bit samples are (code - 32768) / 16, packed two per 3 bytes: a[7:0] | b[3:0] a[11:8] | b[11:4].
"""
import struct
import numpy as np

UV_PER_12BIT = 0.195 * 16
HDR = 9


def unpack12(buf, n):
    """n 12-bit signed values from buf -> int array."""
    out = np.empty(n, dtype=np.int32)
    j = 0
    for k in range(0, n, 2):
        a = buf[j] | ((buf[j + 1] & 0x0F) << 8)
        out[k] = a - 4096 if a >= 2048 else a
        if k + 1 < n:
            b = (buf[j + 1] >> 4) | (buf[j + 2] << 4)
            out[k + 1] = b - 4096 if b >= 2048 else b
            j += 3
        else:
            j += 2
    return out


def read_events(path):
    """-> dict of arrays: wall (s), seq, ch, pre, idx (per-channel sample index of the trough), uv (events x n_samples)."""
    data = open(path, "rb").read()
    wall, seq, ch, pre, idx, uv = [], [], [], [], [], []
    i = 0
    while i + 10 <= len(data):
        t, n_bytes = struct.unpack_from("<dH", data, i); i += 10
        pkt = data[i:i + n_bytes]; i += n_bytes
        if len(pkt) >= 10 and len(pkt) == 10 + 2 * pkt[3]:        # old format (before 2026-10-28): one int16 event per notification
            s, c, n, _, _, trough = struct.unpack_from("<HBBBBI", pkt, 0)
            wall.append(t); seq.append(s); ch.append(c); pre.append(n * 2 // 5); idx.append(trough)
            uv.append(np.frombuffer(pkt[10:10 + 2 * n], dtype="<i2").astype(float) * 0.195)
            continue
        o = 0
        while o + HDR <= len(pkt):
            s, c, n, p, trough = struct.unpack_from("<HBBBI", pkt, o); o += HDR
            packed = (n * 3 + 1) // 2
            if n == 0 or o + packed > len(pkt):
                break                                      # truncated tail, stop at this notification
            wall.append(t); seq.append(s); ch.append(c); pre.append(p); idx.append(trough)
            uv.append(unpack12(pkt[o:o + packed], n) * UV_PER_12BIT); o += packed
    if not seq:
        raise SystemExit(f"no events in {path}")
    return dict(wall=np.array(wall), seq=np.array(seq), ch=np.array(ch), pre=np.array(pre),
                idx=np.array(idx, dtype=np.int64), uv=np.array(uv))


def lost_packets(seq):
    """events skipped according to the 16-bit sequence counter."""
    return int(((np.diff(seq.astype(np.int64)) % 65536) - 1).sum())
