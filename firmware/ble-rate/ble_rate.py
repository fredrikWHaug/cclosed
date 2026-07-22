"""
BLE data-rate test - HOST side.

Subscribes to the 'cclosed-blerate' peripheral (the MCU/master) and measures how
fast data makes it through the real chain slave -> SPI -> master -> BLE -> host:
  - throughput in kbit/s and packets/s
  - dropped packets: the first 4 bytes of each notification are the SLAVE's
    incrementing counter, so any gap means data was lost somewhere in the chain.

    pip install bleak
    python firmware/ble-rate/ble_rate.py
"""
import asyncio
import struct
import time
from bleak import BleakScanner, BleakClient

NAME = "cclosed-blerate"
CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
DURATION = 15.0        # seconds to measure


async def main():
    print(f"scanning for '{NAME}' ...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=20.0)
    if dev is None:
        print("not found - is the board advertising?")
        return

    st = {"pkts": 0, "bytes": 0, "drops": 0, "prev": None, "t0": None}

    def on_data(_char, data: bytearray):
        seq = struct.unpack_from("<I", data)[0]
        if st["prev"] is not None:
            gap = (seq - st["prev"] - 1) & 0xFFFFFFFF   # wrap-safe
            if 0 < gap < 0x80000000:                    # forward gap = dropped
                st["drops"] += gap
        st["prev"] = seq
        st["pkts"] += 1
        st["bytes"] += len(data)
        if st["t0"] is None:
            st["t0"] = time.perf_counter()

    async with BleakClient(dev) as client:
        print("connected - subscribing\n")
        await client.start_notify(CHAR_UUID, on_data)
        last, last_bytes = time.perf_counter(), 0
        end = last + DURATION
        while time.perf_counter() < end:
            await asyncio.sleep(1.0)
            now = time.perf_counter()
            kbps = (st["bytes"] - last_bytes) * 8 / 1000.0 / (now - last)
            print(f"  {kbps:8.1f} kbit/s   {st['pkts']:>9} pkts   drops {st['drops']}")
            last, last_bytes = now, st["bytes"]
        await client.stop_notify(CHAR_UUID)

    if st["t0"] and st["pkts"] > 1:
        span = time.perf_counter() - st["t0"]
        avg = st["bytes"] * 8 / 1000.0 / span
        print(f"\naverage: {avg:.1f} kbit/s over {span:.1f}s")
        print(f"packets: {st['pkts']}   bytes: {st['bytes']}   dropped: {st['drops']}")


if __name__ == "__main__":
    asyncio.run(main())
