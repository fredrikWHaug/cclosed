"""
Receive on-chip spike classifications over BLE (Step 5a).

Scans for the 'cclosed-spikes' peripheral, subscribes to its notify
characteristic, and prints each spike the MCU classifies as
{ unit_id, timestamp } — the compressed output of the whole chain, arriving
wirelessly.

Setup:  pip install bleak
Run:    python sim/ble_receiver.py
"""
import asyncio
import struct
from collections import Counter
from bleak import BleakScanner, BleakClient

NAME = "cclosed-spikes"
CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"


async def main():
    print(f"scanning for '{NAME}' ...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=20.0)
    if dev is None:
        print("not found — is the board advertising?")
        return

    counts = Counter()
    n = 0

    def on_spike(_char, data: bytearray):
        nonlocal n
        trough, unit = struct.unpack("<ii", data)
        counts[unit] += 1
        n += 1
        print(f"  spike {n:3d}: unit {unit:3d}  @ t={trough}")

    async with BleakClient(dev) as client:
        print("connected — subscribing")
        await client.start_notify(CHAR_UUID, on_spike)
        await asyncio.sleep(12.0)          # let the stream play out
        await client.stop_notify(CHAR_UUID)

    print(f"\nreceived {n} spikes over BLE")
    for unit in sorted(counts):
        print(f"  unit {unit}: {counts[unit]}")


if __name__ == "__main__":
    asyncio.run(main())
