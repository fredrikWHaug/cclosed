"""Read packets relayed by theo-central over the DK's VCOM1: frames of A5 5A len_lo len_hi payload."""
import glob
import serial

BAUD = 921600


def list_ports():
    return sorted(glob.glob("/dev/tty.usbmodem*"))


def frames(port):
    """Yield each relayed BLE packet (seq + samples) as bytes, resyncing on the A5 5A marker."""
    link = serial.Serial(port, BAUD, timeout=1)
    buf = b""
    while True:
        buf += link.read(4096)
        while True:
            start = buf.find(b"\xa5\x5a")
            if start < 0:
                buf = buf[-1:]
                break
            if len(buf) < start + 4:
                buf = buf[start:]
                break
            length = buf[start + 2] | (buf[start + 3] << 8)
            if length > 512:                       # corrupt length, skip this marker
                buf = buf[start + 2:]
                continue
            if len(buf) < start + 4 + length:
                buf = buf[start:]
                break
            yield buf[start + 4:start + 4 + length]
            buf = buf[start + 4 + length:]
