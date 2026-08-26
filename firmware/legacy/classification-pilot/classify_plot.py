
import asyncio
import re
import threading
from pathlib import Path

import numpy as np
from bleak import BleakClient, BleakScanner
import matplotlib.pyplot as plt
import matplotlib.animation as animation

NAME = "cclosed-classify"
CHR = "12345678-1234-5678-1234-56789abcdef1"
UV_PER_CODE = 0.195
LABELS = ["sine", "square", "triangle"]               # class_id -> name; 255 = uncertain
COLORS = {"sine": "tab:blue", "square": "tab:red",
          "triangle": "tab:green", "uncertain": "0.5"}

# Load the same templates the firmware uses so we can independently recompute
# ALL per-class scores here (the packet only carries the winning class + score).
# This exposes the runner-up margin -- the key diagnostic for sine/triangle --
# and confirms the on-chip decision matches a laptop recompute of the formula.
def load_templates():
    try:
        h = (Path(__file__).parent / "master" / "src" / "templates.h").read_text()
    except FileNotFoundError:
        return {}
    rows = re.findall(r"\{([^{}]*)\},\s*/\*\s*(\w+)", h)
    return {name: np.array([float(x.replace("f", "")) for x in body.split(",")], float)
            for body, name in rows}


TEMPLATES = load_templates()
TEMPLATE_LEN = len(next(iter(TEMPLATES.values()))) if TEMPLATES else 0


def best_r_all(win):
    """Per-class best-lag Pearson r, same formula as the firmware's classify()
    (templates are zero-mean unit-variance)."""
    if TEMPLATE_LEN == 0 or len(win) < TEMPLATE_LEN:
        return {}
    segs = np.lib.stride_tricks.sliding_window_view(win, TEMPLATE_LEN)   # (L, M)
    d = segs - segs.mean(axis=1, keepdims=True)
    sd = np.sqrt((d ** 2).mean(axis=1))                                  # (L,)
    return {c: float(np.max((d * t).mean(axis=1) / (sd + 1e-12)))
            for c, t in TEMPLATES.items()}


latest = {"uv": np.zeros(1), "label": "uncertain", "r": 0.0, "ts": 0, "seq": 0, "pkts": 0}

# per-second diagnostic accumulators (printed once a second, then reset)
acc = {"pkts": 0, "drops": 0, "last_seq": None,
       "counts": {}, "r_sum": {}, "margin_sum": 0.0, "agree": 0}


def reset_acc():
    acc.update(pkts=0, drops=0, counts={}, r_sum={}, margin_sum=0.0, agree=0)


print(f"templates: {list(TEMPLATES) or 'NONE (run record_templates.py first)'}  len={TEMPLATE_LEN}")


def on_notify(_, data: bytearray):
    cls = data[2]
    ts = int.from_bytes(data[4:8], "little")
    r = int.from_bytes(data[8:10], "little", signed=True) / 32767.0
    seq = data[0] | (data[1] << 8)
    n = (len(data) - 10) // 2
    codes = np.frombuffer(data, dtype="<u2", count=n, offset=10).astype(float)
    fw_label = LABELS[cls] if cls < len(LABELS) else "uncertain"

    latest["uv"] = (codes - 32768.0) * UV_PER_CODE
    latest["label"] = fw_label
    latest["r"] = r
    latest["ts"] = ts
    latest["seq"] = seq
    latest["pkts"] += 1

    # diagnostics: recompute every class score on the laptop from the same window
    if acc["last_seq"] is not None:
        gap = (seq - acc["last_seq"] - 1) & 0xFFFF
        if 0 < gap < 0x8000:
            acc["drops"] += gap
    acc["last_seq"] = seq

    scores = best_r_all(codes)
    acc["pkts"] += 1
    acc["counts"][fw_label] = acc["counts"].get(fw_label, 0) + 1
    for c, v in scores.items():
        acc["r_sum"][c] = acc["r_sum"].get(c, 0.0) + v
    if len(scores) >= 2:
        top2 = sorted(scores.values(), reverse=True)[:2]
        acc["margin_sum"] += top2[0] - top2[1]
        if max(scores, key=scores.get) == fw_label:
            acc["agree"] += 1


async def ble_task():
    print(f"scanning for '{NAME}'...")
    dev = await BleakScanner.find_device_by_name(NAME, timeout=30)
    if dev is None:
        print("not found - is the classifier firmware flashed and advertising?")
        return
    async with BleakClient(dev) as client:
        print(f"connected to {dev.address} - subscribing")
        await client.start_notify(CHR, on_notify)
        print("  time     pkts drops | predicted-label counts | laptop mean r/class | margin | fw==laptop")
        while True:
            await asyncio.sleep(1.0)
            if acc["pkts"] == 0:
                continue
            dist = "  ".join(f"{k} {v}" for k, v in sorted(acc["counts"].items()))
            rmean = {c: acc["r_sum"].get(c, 0.0) / acc["pkts"] for c in TEMPLATES}
            rstr = "  ".join(f"{c[:3]}={rmean[c]:.2f}"
                             for c in ["sine", "square", "triangle"] if c in rmean)
            margin = acc["margin_sum"] / acc["pkts"]
            print(f"[{latest['ts'] / 1000:7.1f}s] {acc['pkts']:4d} {acc['drops']:5d} | "
                  f"{dist:26s} | {rstr} | {margin:.3f} | {acc['agree']}/{acc['pkts']}")
            reset_acc()


threading.Thread(target=lambda: asyncio.run(ble_task()), daemon=True).start()

fig, ax = plt.subplots(figsize=(11, 4))
(line,) = ax.plot([], [], lw=1.5)
label_text = ax.text(0.5, 0.92, "", transform=ax.transAxes, ha="center",
                     fontsize=22, fontweight="bold")
ax.set_ylim(-3000, 5000)
ax.set_xlabel("sample index")
ax.set_ylabel("uV (electrode-referred)")
ax.grid(True, alpha=0.3)


def update(_):
    uv = latest["uv"]
    label = latest["label"]
    color = COLORS.get(label, "0.5")
    line.set_data(np.arange(len(uv)), uv)
    line.set_color(color)
    ax.set_xlim(0, max(1, len(uv)))
    label_text.set_text(f"{label.upper()}   r={latest['r']:.2f}")
    label_text.set_color(color)
    ax.set_title(f"t = {latest['ts'] / 1000.0:.2f} s   |   pkt {latest['seq']}   "
                 f"|   {latest['pkts']} classified")
    return (line, label_text)


anim = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.show()
