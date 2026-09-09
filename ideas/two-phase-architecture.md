# Two-phase system architecture

Authoritative description of the system's two-phase structure. Supersedes the
framing in `system-architecture.md` (which predates the offline/online split).
This is **design Approach A (offline-supervised)**; Approach B (online-unsupervised,
single-phase) is the alternative under consideration — see `classification_options.md`
and the proposal's Design section.

---

## Overview

The system runs in **two phases under different constraints**, and the online phase
does not exist without the offline phase.

```
   OFFLINE PHASE (workstation, once)                 ONLINE PHASE (nRF54 SoC, real time)
   ─────────────────────────────────                ────────────────────────────────────
   wired reference recording                         acquire → detect → (timestamp) →
        │                                                   classify → transmit
        ▼                                                        ▲
   spike sorting (unsupervised clustering)                       │  consumes
        │                                                        │
        ▼                                             ┌──────────┴───────────┐
   train + quantize classifier  ───────────────────► │ model + unit library │
        │                                             │   (the ARTIFACT)     │
        ▼                                             └──────────────────────┘
   model + unit library artifact
```

**The artifact is the interface between the two phases.** Offline produces it; online
consumes it at the classify step. Nothing else crosses the boundary.

---

## Offline phase (workstation, runs once, no device constraints)

- **Input:** a wired, tethered, high-fidelity reference recording.
- **Steps:**
  1. **Spike sorting** — unsupervised clustering (e.g. Kilosort / MountainSort) of the
     reference recording into labeled units. Produces `(waveform, unit_id)` training pairs.
  2. **Train** a supervised classifier on those pairs.
  3. **Quantize** the trained model for integer, on-device inference.
- **Output (artifact):** a **unit library + quantized classifier model**, flashed onto
  the device alongside the firmware (e.g. as `model.h`).
- **Constraints:** none of the device's. Runs on a workstation with the *full* data set
  available in advance. Not power-, latency-, memory-, or bandwidth-bound.

---

## Online phase (nRF54 SoC, real time, device-constrained)

Consumes the offline artifact and runs the real-time pipeline. Subject to the power,
latency (bounded, non-closed-loop), memory, and BLE-bandwidth constraints that motivate
the thesis.

**The five functional operations** (proposal-level view):
`acquire → detect → record time → classify → transmit`.

**The firmware decomposition** (implementation view) — five functions plus one shared
data structure. Four functions are invariant plumbing; `classify` is the swappable seam
(see `design_considerations.md` for the contracts and the swap discipline).

```
[SPI/Intan acquire] → [ring buffer] → [detect + align] → [classify] → [packetize + BLE]
       │                   │                │                 │              │
    invariant          invariant        invariant        SWAPPABLE       invariant
```

- `acquire_sample(ch)` — one Intan SPI conversion → one 16-bit sample. Built on
  `intan_transceive_word(cmd)` → Zephyr's `spi_transceive()`. Touches only SPI; knows
  nothing of the ring buffer.
- ring buffer — samples land here; snippets are cut from here. Exists so `extract` can
  reach *backward* in time to samples that arrived before a spike was confirmed.
- `detect(sample)` — returns true at the instant a spike is confirmed. **The timestamp is
  captured here, at detection**, and carried through to `emit` — so "record the time"
  (functional op 3) is folded into the detect→emit flow, not a separate stage.
- `extract_snippet(snippet)` — copies the peak-aligned window out of the ring (Contract A:
  `int16 snippet[N]` in).
- `classify(snippet)` — inference against the offline model → `unit_id` (Contract B out).
  The one file that changes between classifier designs.
- `emit_event(unit_id, timestamp)` — packetize + `bt_gatt_notify` over BLE.

**Contracts (frozen interfaces):**
- **Contract A** — `int16 snippet[N]` into `classify`.
- **Contract B** — `uint8 unit_id` (+ timestamp) out of `classify`.

**File structure (one firmware image):**
- `main.c` — the invariant plumbing (SPI, ring, detect, BLE).
- `classify.{c,h}` — the swappable classifier; `classify.h` is the contract.
- `model.h` — the offline artifact (generated, not hand-written).

---

## Cross-cutting properties (span the whole online pipeline, not one stage)

- **No-loss / keep-up** — no detected spike (or its source sample) dropped under sustained
  load. A drop anywhere in the chain compromises the result identically.
- **Timestamp fidelity** — stamped at detection, on a stable clock, at sufficient
  resolution; spans detect and transmit.

---

## Design-approach context

This two-phase structure **is a design decision**, not a requirement — it is the axis
along which the two candidate designs differ:

- **Approach A (this document):** offline-supervised, two-phase. Higher accuracy; requires
  offline calibration/training per subject.
- **Approach B:** online-unsupervised, single-phase (on-device Osort clustering). No offline
  phase, self-contained; expected lower sorted-unit stability/accuracy.

The functional and technical *requirements* are design-agnostic and satisfied by both; only
the realization differs.

---

## Related documents

- `design_considerations.md` — the plumbing/contracts and the swap discipline (dialogue + decisions).
- `classification_options.md` — the classifier tiers (what runs in the `classify` seam).
- `classification_benchmark.md` — how online output is validated against Kilosort ground truth.
- `SPI_bringup_plan.md` — scaling acquisition (the `acquire` throughput/LVDS work) to 32 channels.
