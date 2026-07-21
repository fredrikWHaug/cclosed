"""
Step-4a verification vector: a ~0.3 s raw stream (several shank-2 spikes) plus the
reference output of the STREAMING pipeline, so the firmware's streaming detector
can be checked against the host spike-for-spike.

Streaming detection (the exact causal state machine host and firmware both run):
  g[t] = min over channels of the decimated CMR signal.
  - not in an event: if t past refractory and g[t] < -THRESH -> start event.
  - in an event: track the minimum (the trough); when g[t] rises back above
    -THRESH, finalize: extract the 8x40 snippet at the trough, classify (folded
    logreg), and start a refractory window.

THRESH is a robust 5*MAD estimate from this stream; host and firmware use the same
value. Emits firmware/classifiers/onchip/stream_test.h.
"""
import sys
import numpy as np
from pathlib import Path
from scipy import signal
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))
from stream_rhd import parse_header

SOS = signal.butter(2, [300, 3000], "bandpass", fs=30000, output="sos").astype(np.float32)
CHN2 = [57, 56, 39, 38, 36, 37, 58, 59]
SB = SA = 20
NS = 9000            # raw samples (~0.3 s @ 30 kHz)
START = 5000
DETECT_START = 60    # decimated samples to skip (cold-start filter transient)
REFRAC = 15          # decimated-sample refractory
OUT = ROOT / "firmware" / "classifiers" / "onchip"


def pipeline(codes):
    uv = (0.195 * (codes.astype(np.float32) - 32768)).astype(np.float32)
    f = signal.sosfilt(SOS, uv, axis=1).astype(np.float32)
    f = f - np.median(f, axis=0, keepdims=True)
    return f[:, ::3].astype(np.float32)


def folded_model():
    d = np.load(ROOT / "dataset" / "onchip_260413.npz")
    X, y, shk, ti = d["snippets"], d["labels"], d["shanks"], d["times"]
    m = shk == 2
    Xs = X[m].reshape(m.sum(), -1); ys = y[m]
    order = np.argsort(ti[m]); cut = int(0.8 * len(order))
    sc = StandardScaler().fit(Xs[order[:cut]])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(sc.transform(Xs[order[:cut]]), ys[order[:cut]])
    Wp = clf.coef_ / sc.scale_
    bp = clf.intercept_ - (clf.coef_ * (sc.mean_ / sc.scale_)).sum(1)
    return Wp.astype(np.float32), bp.astype(np.float32), clf.classes_


def detect(dec, THRESH, Wp, bp, classes):
    g = dec.min(axis=0)
    ndec = dec.shape[1]
    troughs, units, margins = [], [], []
    in_ev, emin, emt, refrac = False, 1e30, -1, DETECT_START
    for t in range(DETECT_START, ndec - SA):
        if not in_ev:
            if t >= refrac and g[t] < -THRESH:
                in_ev, emin, emt = True, g[t], t
        else:
            if g[t] < emin:
                emin, emt = g[t], t
            if g[t] >= -THRESH:
                tt = emt
                snip = dec[:, tt - SB:tt + SA].reshape(-1)
                logits = Wp @ snip + bp
                o = np.argsort(logits)[::-1]
                troughs.append(tt); units.append(int(classes[o[0]]))
                margins.append(float(logits[o[0]] - logits[o[1]]))  # top-2 gap
                refrac, in_ev = tt + REFRAC, False
    return troughs, units, margins


def main():
    fp = sorted((ROOT / "raw-data" / "MA1_260413_131912").glob("*.rhd"))[0]
    f = open(fp, "rb"); h = parse_header(f)
    N, NAMP, bpb, he = h["block"], h["n_amp"], h["bpb"], h["header_end"]
    f.seek(he); raw = f.read(); nb = len(raw) // bpb
    codes = np.empty((8, nb * N), np.uint16)
    for b in range(nb):
        amp = np.frombuffer(raw, '<u2', count=NAMP * N, offset=b * bpb + N * 4).reshape(NAMP, N)
        codes[:, b * N:(b + 1) * N] = amp[CHN2]
    stream = codes[:, START:START + NS].copy()

    dec = pipeline(stream)
    ndec = dec.shape[1]
    THRESH = float(5 * np.median(np.abs(dec)) / 0.6745)
    Wp, bp, classes = folded_model()
    troughs, units, margins = detect(dec, THRESH, Wp, bp, classes)
    nb = sum(mg < 0.5 for mg in margins)
    print(f"host detected {len(troughs)} spikes, THRESH={THRESH:.1f} uV, {nb} near-ties (margin<0.5)")
    print("units:", units)

    def arr(name, a, ctype, fmt):
        flat = a.flatten()
        s = f"static const {ctype} {name}[{max(flat.size,1)}] = {{\n"
        for i in range(0, flat.size, 12):
            s += "    " + ", ".join(fmt(v) for v in flat[i:i+12]) + ",\n"
        return s + "};\n\n"

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "stream_test.h", "w") as fo:
        fo.write("#ifndef STREAM_TEST_H\n#define STREAM_TEST_H\n#include <stdint.h>\n\n")
        fo.write(f"#define N_CH 8\n#define NS {NS}\n#define NDEC {ndec}\n#define SNIP_LEN 40\n")
        fo.write(f"#define DETECT_START {DETECT_START}\n#define REFRAC {REFRAC}\n")
        fo.write(f"#define THRESH {THRESH:.6f}f\n#define EXP_COUNT {len(troughs)}\n\n")
        fo.write(arr("exp_troughs", np.array(troughs, np.int32), "int32_t", lambda v: f"{int(v)}"))
        fo.write(arr("exp_units", np.array(units, np.int32), "int32_t", lambda v: f"{int(v)}"))
        fo.write(arr("exp_margins", np.array(margins, np.float32), "float", lambda v: f"{v:.4f}f"))
        fo.write(arr("raw_stream", stream, "uint16_t", lambda v: f"{int(v)}"))
        fo.write("#endif\n")
    print(f"wrote {OUT/'stream_test.h'}")


if __name__ == "__main__":
    main()
