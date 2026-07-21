"""
Export the on-chip logreg for ONE shank to C headers for firmware/classifiers/logreg.

Trains exactly like train_onchip.py (on-chip dataset, TIME split) for the chosen
shank, then FOLDS the StandardScaler into the linear layer so the firmware runs a
raw dot product with no on-chip normalization:

    logit = W * ((x - mean)/std) + b  =  (W/std) * x + (b - sum(W*mean/std))
    => W' = W/std ,  b' = b - sum(W * mean/std)

Emits the same header format the existing firmware expects (N_CLASSES, INPUT_DIM,
logreg_w, logreg_b, test_snippet) plus UNIT_IDS (class index -> sorter unit id).
Verifies the folded weights reproduce sklearn's predictions bit-for-bit before writing.

Usage:  python model/export_onchip_logreg.py
"""
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
SHANK = 2
OUT = ROOT / "firmware" / "classifiers" / "logreg"


def export_array(f, name, arr):
    flat = arr.flatten()
    f.write(f"// shape: {list(arr.shape)}\n")
    f.write(f"static const float {name}[{len(flat)}] = {{\n")
    for i in range(0, len(flat), 8):
        f.write("    " + ", ".join(f"{v:.6f}f" for v in flat[i:i+8]) + ",\n")
    f.write("};\n\n")


def main():
    d = np.load(ROOT / "dataset" / "onchip_260413.npz")
    X, y, sh, t = d["snippets"], d["labels"], d["shanks"], d["times"]
    m = sh == SHANK
    Xs = X[m].reshape(m.sum(), -1).astype(np.float64)
    ys, ts = y[m], t[m]
    order = np.argsort(ts)
    cut = int(0.8 * len(order))
    tr, te = order[:cut], order[cut:]

    sc = StandardScaler().fit(Xs[tr])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    clf.fit(sc.transform(Xs[tr]), ys[tr])
    classes = clf.classes_                       # sorted sorter unit ids
    W, b = clf.coef_, clf.intercept_             # (C,320), (C,)

    # fold the scaler into the linear layer
    Wp = W / sc.scale_
    bp = b - (W * (sc.mean_ / sc.scale_)).sum(1)

    # verify: folded raw dot product == sklearn on the held-out test set
    logits = Xs[te] @ Wp.T + bp
    pred_folded = classes[logits.argmax(1)]
    pred_sklearn = clf.predict(sc.transform(Xs[te]))
    assert (pred_folded == pred_sklearn).all(), "scaler folding mismatch!"
    acc = (pred_folded == ys[te]).mean()
    print(f"shank {SHANK}: {len(classes)} units {classes.tolist()}")
    print(f"folded weights reproduce sklearn on all {len(te)} test snippets; "
          f"overall test acc {acc:.3f}")

    # a held-out test snippet the firmware will classify
    i0 = te[0]
    snip = Xs[i0].astype(np.float32)
    true_unit = int(ys[i0])
    true_class = int(np.where(classes == true_unit)[0][0])
    pred_class = int(logits[0].argmax())
    print(f"test snippet: true unit {true_unit} (class {true_class}), "
          f"folded prediction class {pred_class} -> unit {int(classes[pred_class])}")

    with open(OUT / "model_weights.h", "w") as f:
        f.write("#ifndef MODEL_WEIGHTS_H\n#define MODEL_WEIGHTS_H\n\n")
        f.write(f"#define N_CLASSES {len(classes)}\n#define INPUT_DIM 320\n\n")
        f.write("// class index -> offline sorter unit id\n")
        f.write(f"static const int UNIT_IDS[N_CLASSES] = {{ {', '.join(map(str, classes.tolist()))} }};\n\n")
        f.write("// scaler folded in: logits = logreg_w . x + logreg_b on the RAW snippet\n")
        export_array(f, "logreg_w", Wp.astype(np.float32))
        export_array(f, "logreg_b", bp.astype(np.float32))
        f.write("#endif\n")

    with open(OUT / "test_data.h", "w") as f:
        f.write("#ifndef TEST_DATA_H\n#define TEST_DATA_H\n\n")
        f.write(f"#define TEST_TRUE_CLASS {true_class}\n#define TEST_TRUE_UNIT {true_unit}\n\n")
        export_array(f, "test_snippet", snip)
        f.write("#endif\n")
    print(f"wrote {OUT/'model_weights.h'} and {OUT/'test_data.h'}")


if __name__ == "__main__":
    main()
