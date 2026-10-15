"""Log the Theo BLE stream to a .bin file: python log_stream.py out.bin 60"""
import asyncio, struct, sys, time
from bleak import BleakClient, BleakScanner

NAME = "cclosed-theo"
CHR = "12345678-1234-5678-1234-56789abcdef1"

path, seconds = sys.argv[1], float(sys.argv[2])
fh = open(path, "wb")
n = [0]

def on_notify(_, data: bytearray):
    fh.write(struct.pack("<dH", time.time(), len(data)) + bytes(data))
    n[0] += 1

async def main():
    dev = await BleakScanner.find_device_by_name(NAME, timeout=15)
    if dev is None:
        raise SystemExit(f"'{NAME}' not found - is the DK advertising?")
    async with BleakClient(dev) as client:
        await client.start_notify(CHR, on_notify)
        print(f"logging to {path} for {seconds:.0f} s")
        await asyncio.sleep(seconds)
    fh.close()
    print(f"done: {n[0]} packets")

asyncio.run(main())
