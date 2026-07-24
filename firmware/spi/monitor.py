#!/usr/bin/env python3
"""
SPI stream monitor — reads the slave's raw 16-bit counter over serial,
automatically detects dropped / reordered words, and live-plots the stream.

The slave streams each received word as 2 raw bytes (little-endian) — binary,
not ASCII, so the monitor keeps up at the master's full ~8 kHz instead of the
~2 kHz the old printf path capped at. This reads what the slave ACTUALLY got, so:
  - a gap in the sequence  = dropped data
  - inter-arrival timing   = streaming rate + jitter (the honest latency signal)

Usage:
    python firmware/spi/monitor.py --list                  # list serial ports
    python firmware/spi/monitor.py --port /dev/tty.usbmodemXXXX
    python firmware/spi/monitor.py --port <slave> --no-plot   # terminal stats only

Pick the SLAVE board's port (the one streaming numbers). If you open the master's
port you'll only see the banner and no data — the script warns you if so.
"""
import argparse
import sys
import threading
import time
from collections import deque

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial not installed. In your venv:  pip install pyserial")

WRAP = 65536      # counter wraps here (16-bit)
HIST = 600        # samples shown in the scrolling plots


class Monitor:
    """Thread-safe accumulator: a reader thread feeds it, the UI reads snapshots."""

    def __init__(self):
        self.lock = threading.Lock()
        self.total = 0
        self.dropped = 0            # count of missing values
        self.reordered = 0          # backward jumps (dup / out-of-order)
        self.prev = None
        self.last_t = None
        self.t_start = None                 # wall-clock of first value (for true rate)
        self.seq_idx = deque(maxlen=HIST)   # x-axis: running received count
        self.seq_val = deque(maxlen=HIST)   # received value (the ramp)
        self.dt_ms = deque(maxlen=HIST)     # inter-arrival time (ms)
        self.drops_xy = deque(maxlen=HIST)  # (received count, cumulative dropped)

    def feed(self, val, t):
        with self.lock:
            if self.t_start is None:
                self.t_start = t
            self.total += 1
            if self.prev is not None:
                expected = (self.prev + 1) % WRAP
                diff = val - expected
                if diff > WRAP // 2:
                    diff -= WRAP
                elif diff < -WRAP // 2:
                    diff += WRAP
                if diff > 0:
                    self.dropped += diff        # 'diff' values went missing
                elif diff < 0:
                    self.reordered += 1
            self.prev = val

            self.seq_idx.append(self.total)
            self.seq_val.append(val)
            self.dt_ms.append((t - self.last_t) * 1000.0 if self.last_t else 0.0)
            self.last_t = t
            self.drops_xy.append((self.total, self.dropped))

    def snapshot(self):
        with self.lock:
            # True throughput = total values / wall-clock span they arrived over.
            # (Per-value inter-arrival is meaningless here: the OS delivers serial
            # data in bursts, so we measure aggregate rate, not per-sample timing.)
            rate = 0.0
            if self.t_start is not None and self.last_t is not None and self.last_t > self.t_start:
                rate = self.total / (self.last_t - self.t_start)
            return {
                "total": self.total, "dropped": self.dropped,
                "reordered": self.reordered, "rate": rate,
                "idx": list(self.seq_idx), "val": list(self.seq_val),
                "dt": list(self.dt_ms), "drops": list(self.drops_xy),
            }


def reader_thread(ser, mon, stop):
    """Parse the slave's raw 16-bit LE counter stream.

    The bytes have no framing, so we first LOCK onto the stream by requiring a
    short run of +1 increments (this skips the plain-text boot banner and any
    mid-word start). Once locked we feed every value; if we ever slip by a byte
    (e.g. after a UART byte drop) a single +1 shift re-aligns us. Genuine gaps
    pass straight through to mon.feed(), which counts them as drops.
    """
    buf = bytearray()
    last = None
    locked = False
    run = 0
    while not stop.is_set():
        try:
            chunk = ser.read(4096)
        except serial.SerialException:
            break
        if not chunk:
            continue
        buf.extend(chunk)
        i, n = 0, len(buf)
        while i + 2 <= n:
            val = buf[i] | (buf[i + 1] << 8)
            cont = last is not None and val == (last + 1) % WRAP
            if not locked:
                if last is not None and not cont:
                    last = val                  # not a ramp yet: slide one byte
                    i += 1
                    run = 0
                    continue
                run = run + 1 if last is not None else 0
                last = val
                i += 2
                if run >= 4:                     # 4 clean increments = aligned
                    locked = True
                    mon.feed(val, time.perf_counter())
                continue
            # locked: resync a single byte only if that cleanly restores the ramp
            if not cont and i + 3 <= n and (buf[i + 1] | (buf[i + 2] << 8)) == (last + 1) % WRAP:
                i += 1
                continue
            mon.feed(val, time.perf_counter())
            last = val
            i += 2
        del buf[:i]


def summary_line(st):
    pct = (100.0 * st["dropped"] / st["total"]) if st["total"] else 0.0
    return (f"Received {st['total']:>8}  Dropped {st['dropped']:>5} ({pct:5.2f}%)  "
            f"Reordered {st['reordered']:>4}  Rate {st['rate']:8.0f} Hz")


def list_serial_ports():
    ports = list_ports.comports()
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}    {p.description}")


def run_terminal(mon, stop):
    try:
        while not stop.is_set():
            print("\r" + summary_line(mon.snapshot()), end="", flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    print()


def run_plot(mon, stop):
    try:
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
    except ImportError:
        print("matplotlib not installed — falling back to terminal mode.")
        print("For graphs:  pip install matplotlib\n")
        run_terminal(mon, stop)
        return

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(9, 7.5))
    fig.suptitle("SPI stream monitor", fontweight="bold")
    (l1,) = ax1.plot([], [], lw=1.0)
    (l2,) = ax2.plot([], [], lw=0.8)
    (l3,) = ax3.plot([], [], lw=1.5, color="crimson")
    ax1.set_ylabel("received value")
    ax1.set_title("Master counter / Monitor Counter", fontsize=9)
    ax2.set_ylabel("inter-arrival (ms)")
    ax2.set_title("inter-arrival (host-buffered — not true link jitter)", fontsize=9)
    ax3.set_ylabel("cumulative drops")
    ax3.set_title("dropped words over time", fontsize=9)
    txt = fig.text(0.5, 0.965, "", ha="center", va="top", fontsize=9, family="monospace")
    fig.subplots_adjust(hspace=0.5, top=0.9)

    def update(_):
        st = mon.snapshot()
        txt.set_text(summary_line(st))
        if st["val"]:
            l1.set_data(st["idx"], st["val"])
            l2.set_data(st["idx"], st["dt"])
            if st["drops"]:
                xs = [x for x, _ in st["drops"]]
                ys = [y for _, y in st["drops"]]
                l3.set_data(xs, ys)
            for ax in (ax1, ax2, ax3):
                ax.relim()
                ax.autoscale_view()
        return l1, l2, l3, txt

    ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    try:
        plt.show()
    finally:
        stop.set()
    _ = ani  # keep a reference so it isn't garbage-collected


def main():
    ap = argparse.ArgumentParser(description="Monitor the SPI sequence-number stream.")
    ap.add_argument("--port", help="serial device of the SLAVE board")
    ap.add_argument("--baud", type=int, default=1000000)   # Stage A: 1 Mbaud console
    ap.add_argument("--list", action="store_true", help="list serial ports and exit")
    ap.add_argument("--no-plot", action="store_true", help="terminal stats only")
    args = ap.parse_args()

    if args.list:
        list_serial_ports()
        return
    if not args.port:
        print("No --port given.\n")
        list_serial_ports()
        print("\nRe-run with:  python firmware/spi/monitor.py --port <SLAVE device>")
        return

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
    except serial.SerialException as e:
        sys.exit(f"Could not open {args.port}: {e}\n"
                 f"(Is a serial terminal still holding the port open? Close it first.)")

    mon = Monitor()
    stop = threading.Event()
    t = threading.Thread(target=reader_thread, args=(ser, mon, stop), daemon=True)
    t.start()

    # Sanity check: are we on the right board?
    time.sleep(2.0)
    if mon.snapshot()["total"] == 0:
        print(f"No numbers arriving on {args.port} after 2 s.")
        print("This is probably the MASTER port (banner only). Try the other port.\n")

    print(f"Monitoring {args.port} @ {args.baud}.  Ctrl-C to stop.\n")
    if args.no_plot:
        run_terminal(mon, stop)
    else:
        run_plot(mon, stop)

    stop.set()
    ser.close()


if __name__ == "__main__":
    main()
