"""Analyze a stream_plot.py --log capture: achieved sampling rate over time.

usage: python analyze.py capture.bin [expected_rate]
Log format per packet: <double host_time> <u16 len> <len bytes payload>
Payload: u16 seq + N x u16 samples (little endian).
"""
import sys, struct
import numpy as np
import matplotlib.pyplot as plt

path = sys.argv[1]
expected = float(sys.argv[2]) if len(sys.argv) > 2 else 20000.0

times, seqs, nsamps = [], [], []
with open(path, "rb") as f:
    while True:
        hdr = f.read(10)
        if len(hdr) < 10:
            break
        t, ln = struct.unpack("<dH", hdr)
        payload = f.read(ln)
        if len(payload) < ln:
            break
        times.append(t)
        seqs.append(payload[0] | (payload[1] << 8))
        nsamps.append((ln - 2) // 2)

t = np.array(times); t -= t[0]
seqs = np.array(seqs); nsamps = np.array(nsamps)

# packet loss from 16-bit seq gaps
gaps = (np.diff(seqs) - 1) & 0xFFFF
gaps[gaps >= 0x8000] = 0
lost_pkts = int(gaps.sum())
lost_samples = lost_pkts * int(np.median(nsamps))

total = int(nsamps.sum())
dur = t[-1] - t[0]
fs_avg = total / dur

# rolling delivered rate, 1 s windows
edges = np.arange(0, dur, 1.0)
idx = np.searchsorted(t, edges)
per_sec = [nsamps[idx[i]:idx[i+1]].sum() for i in range(len(idx) - 1)]

print(f"packets {len(t)}   samples {total}   duration {dur:.1f} s")
print(f"lost packets {lost_pkts}  (= {lost_samples} samples)")
print(f"achieved rate {fs_avg:.1f} S/s   (expected {expected:.0f}, "
      f"error {100*(fs_avg-expected)/expected:+.3f}%)")

report = (f"stream capture report: {path}\n"
          f"packets            {len(t)}\n"
          f"samples            {total}\n"
          f"duration           {dur:.1f} s\n"
          f"lost packets       {lost_pkts} ({lost_samples} samples)\n"
          f"achieved rate      {fs_avg:.1f} S/s (host clock)\n"
          f"expected rate      {expected:.0f} S/s (device clock)\n"
          f"difference         {100*(fs_avg-expected)/expected:+.4f}% "
          f"({1e6*(fs_avg-expected)/expected:+.0f} ppm = host-vs-device crystal skew)\n"
          f"completeness       {100.0*total/(total+lost_samples):.4f}%\n")
base = path.rsplit(".", 1)[0]
open(base + "_report.txt", "w").write(report)
print("\nsaved " + base + "_report.txt")

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(edges[:-1], per_sec, ".-")
ax.axhline(expected, color="0.6", ls="--", label=f"expected {expected:.0f}")
ax.set_xlabel("time (s)"); ax.set_ylabel("delivered samples/s")
ax.set_title(f"achieved sampling rate: {fs_avg:.1f} S/s over {dur:.0f} s, "
             f"{lost_pkts} lost packets")
ax.legend(); plt.tight_layout()
fig.savefig(base + "_rate.png", dpi=150)
print("saved " + base + "_rate.png")
plt.show()
