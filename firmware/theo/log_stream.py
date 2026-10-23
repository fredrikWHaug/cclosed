"""Log the Theo stream to a .bin file.

    python log_stream.py out.bin 60                           # straight from the headstage over BLE
    python log_stream.py out.bin 60 --serial /dev/tty.usbmodemXXXX   # via the theo-central relay DK
"""
import asyncio, struct, sys, time
from bleak import BleakClient, BleakScanner

NAME = "cclosed-theo"
CHR = "12345678-1234-5678-1234-56789abcdef1"

path, seconds = sys.argv[1], float(sys.argv[2])
fh = open(path, "wb")
n = [0]

def record(data):
    fh.write(struct.pack("<dH", time.time(), len(data)) + bytes(data))
    n[0] += 1

if "--serial" in sys.argv:
    from serial_source import frames, list_ports
    args = sys.argv[sys.argv.index("--serial") + 1:]
    if not args:
        raise SystemExit("give the relay DK's VCOM1 port, one of: " + ", ".join(list_ports()))
    print(f"logging to {path} for {seconds:.0f} s from {args[0]}")
    stop = time.time() + seconds
    for payload in frames(args[0]):
        record(payload)
        if time.time() > stop:
            break
else:
    async def main():
        dev = await BleakScanner.find_device_by_name(NAME, timeout=15)
        if dev is None:
            raise SystemExit(f"'{NAME}' not found - is the DK advertising?")
        async with BleakClient(dev) as client:
            await client.start_notify(CHR, lambda _, data: record(data))
            print(f"logging to {path} for {seconds:.0f} s over BLE")
            await asyncio.sleep(seconds)
    asyncio.run(main())

fh.close()
print(f"done: {n[0]} packets")
