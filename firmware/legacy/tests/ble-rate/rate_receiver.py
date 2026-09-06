#!/usr/bin/env python3
"""Laptop BLE receiver for the ble-rate throughput test.

The laptop-side twin of the nRF54 `central` firmware: connects to the ble-rate
`master` ('cclosed-blerate'), subscribes to the rate characteristic, unpacks the
16-bit counter stream, and prints throughput + drops once per second using the
SAME wrap-safe gap math as the DK central -- so the two receivers' numbers are
directly comparable.

Two receivers, two ceilings:
  - DK central   : ~1.05 Mbps   (the DK controls the connection interval)
  - this laptop  : ~200-234 kbit/s on macOS (CoreBluetooth caps the interval;
                   you cannot force it lower from user space) -- expect the
                   master's `drops` to be huge, because it offers ~80k vals/s
                   and the laptop can only drain a fraction. The RECEIVED
                   kbit/s below is the laptop ceiling; that's the number you want.

    pip install bleak
    python firmware/ble-rate/rate_receiver.py
"""
import asyncio
import time

from bleak import BleakClient, BleakScanner

NAME = "cclosed-blerate"
CHR = "12345678-1234-5678-1234-56789abcdef1"

st = {
    "win_bytes": 0,
    "win_pkts": 0,
    "tot_pkts": 0,
    "drops": 0,
    "last": None,   # last 16-bit counter value seen
}


def on_notify(_, data: bytearray):
    # payload = N consecutive little-endian uint16 counter values
    for i in range(0, len(data) - 1, 2):
        v = data[i] | (data[i + 1] << 8)
        if st["last"] is not None:
            gap = (v - st["last"] - 1) & 0xFFFF        # 16-bit wrap-safe
            if gap != 0 and gap < 0x8000:
                st["drops"] += gap
        st["last"] = v
    st["win_bytes"] += len(data)
    st["win_pkts"] += 1
    st["tot_pkts"] += 1


async def reporter():
    last_t = time.monotonic()
    while True:
        await asyncio.sleep(1.0)
        now = time.monotonic()
        dt = now - last_t                              # real elapsed, not assumed 1.0
        last_t = now

        b, p = st["win_bytes"], st["win_pkts"]
        st["win_bytes"] = 0
        st["win_pkts"] = 0

        kbps = (b * 8 / 1000.0) / dt
        pps = p / dt
        print(f"[rate] {kbps:8.1f} kbit/s   {pps:7.1f} pkts/s   "
              f"drops {st['drops']:>10}   total {st['tot_pkts']}")


async def main():
    print(f"scanning for '{NAME}'...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=30)
    if dev is None:
        print("device not found - is the ble-rate master advertising?")
        return
    async with BleakClient(dev) as client:
        print(f"connected to {dev.address} - subscribing, measuring below")
        await client.start_notify(CHR, on_notify)
        await reporter()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\nstopped. total packets {st['tot_pkts']}, total drops {st['drops']}")
