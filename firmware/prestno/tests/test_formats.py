"""The packet formats decode exactly what the firmware encodes, and the filter is the firmware's filter."""
import struct, sys, os
import numpy as np
from scipy.signal import butter, sosfilt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from formats import events, raw_samples, is_raw, detector_filter, butter2, analog_band_hz, UV_PER_CODE


def pack_event(seq, ch, pre, trough, codes):
    """emit() in src/main.c, byte for byte: 9-byte header, then (code >> 4) as 12-bit two's complement, two per 3 bytes."""
    vals = [((int(c) >> 4) & 0xFFF) for c in codes]            # arithmetic shift of the int16 code, then 12 bits
    out = bytearray(struct.pack("<HBBBI", seq, ch, len(vals), pre, trough))
    for k in range(0, len(vals), 2):
        a = vals[k]; b = vals[k + 1] if k + 1 < len(vals) else 0
        out.append(a & 0xFF); out.append(((a >> 8) & 0x0F) | ((b & 0x0F) << 4))
        if k + 1 < len(vals):
            out.append((b >> 4) & 0xFF)
    return bytes(out)


def test_event_roundtrip_all_lengths_and_extremes():
    rng = np.random.default_rng(1)
    for n in list(range(1, 76)):
        codes = rng.integers(-32768, 32767, n, dtype=np.int16)
        codes[:5] = [-32768, -1, 0, 1, 32767][:min(5, n)]
        payload = pack_event(1234, 3, 20, 987654321, codes) + pack_event(1235, 4, 20, 5, codes[::-1])
        decoded = events(payload)
        assert [(e[0], e[1], e[2], e[3]) for e in decoded] == [(1234, 3, 20, 987654321), (1235, 4, 20, 5)]
        expect = (codes.astype(np.int64) >> 4) * 16 * UV_PER_CODE
        assert np.allclose(decoded[0][4], expect)
        assert np.allclose(decoded[1][4], expect[::-1])


def test_truncated_tail_is_dropped_not_misread():
    codes = np.arange(-30, 31, dtype=np.int16)
    good = pack_event(7, 0, 20, 100, codes)
    assert len(events(good + good[:40])) == 1


def test_raw_packet_decodes_to_microvolts():
    codes = np.array([32768, 32768 + 1000, 32768 - 1000] + [32768] * 117, dtype="<u2")
    payload = struct.pack("<H", 42) + codes.tobytes()
    assert is_raw(payload)
    seq, uv = raw_samples(payload)
    assert seq == 42 and np.allclose(uv[:3], [0, 195, -195])


def test_detector_filter_matches_scipy_and_the_band_rule():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 50, 20000)
    for rate in (30000, 20000, 10000, 6000):
        sos = [butter(2, 300, "highpass", fs=rate, output="sos")]
        if analog_band_hz(rate) > 6000:
            sos.append(butter(2, 6000, "lowpass", fs=rate, output="sos"))
        ref = x
        for s in sos:
            ref = sosfilt(s, ref)
        assert np.allclose(detector_filter(x, rate), ref, atol=1e-6)
    assert analog_band_hz(30000) == 10000 and analog_band_hz(10000) == 3000 and analog_band_hz(6000) == 2000
