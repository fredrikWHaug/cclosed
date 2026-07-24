# BLE bitrate — push to plateau

**Goal:** maximize sustained BLE app throughput (master → laptop), **zero drops**,
until it demonstrably plateaus.

**Stop condition:** a lever yields **< ~5%** gain **AND** the master's printed link
params confirm we're at the floor (2M PHY active, connection event full, interval
at the central's minimum). At that point the number is the real ceiling.

**Rule:** one change per flash cycle, so every gain is attributable. Instrumentation
(the `[link]` print) is permanent from here and rides along in every build.

---

## Measurement protocol (identical every run)
1. Slave (board A) + master (board B) powered; SPI wired as usual.
2. **Pristine**-build the master after any change, flash board B. Slave unchanged.
3. Watch the master's serial for `[link] PHY=.. interval=.. MTU=..`.
4. Run `python ble_rate.py` (15 s).
5. Record avg kbit/s, packets/s, drops, and the `[link]` line in the results log.

---

## Baseline (done)
- MTU 247 (244 B/packet), 1M PHY (assumed — Lever 2 will confirm), default params.
- **~160 kbit/s avg, ~64–139 pkt/s, 0 drops.**
- Diagnosis: payload is maxed; the wall is now **packets per second**.
- To reach ~1.4 Mbps at 244 B/packet we need ~**700 pkt/s** — a ~5–10× packet-rate gain.

---

## Levers (in order of expected payoff)

| # | Lever | Knob | Expected | In our control? |
|---|-------|------|----------|-----------------|
| 1 | Fat notifications | ATT MTU 247 + DLE 251 | ~9× (done) | ✅ done |
| 2 | **2M PHY** | `bt_conn_le_phy_update()` + `CONFIG_BT_CTLR_PHY_2M` | ~2× | ✅ (Mac may refuse — print tells us) |
| 3 | **Pack the connection event** | more TX buffers + max event length: `CONFIG_BT_BUF_ACL_TX_COUNT`, `CONFIG_BT_L2CAP_TX_BUF_COUNT`, `CONFIG_BT_CONN_TX_MAX`, `CONFIG_BT_CTLR_SDC_MAX_CONN_EVENT_LEN_DEFAULT` | large if Mac allows long events | ✅ firmware; event length is negotiated |
| 4 | Shorter connection interval | `bt_conn_le_param_update()` (7.5–15 ms) | more events/s | ⚠️ Apple clamps |
| 5 | Change central | Android tablet or nRF-as-central | unlocks true FW ceiling | ✅ separates FW limit from macOS limit |

---

_Status: **~1.05 Mbps, 0 drops** via nRF-DK central (Lever 5) — 4.2× the macOS
ceiling. The laptop was the throttle, not the nRF54. Considered done; push to ~1.4
Mbps left as optional polish (SDK-specific RX-buffer / event-length tuning)._

## Results log

| cycle | change | PHY | interval | MTU | kbit/s | pkt/s | drops |
|-------|--------|-----|----------|-----|--------|-------|-------|
| 0 | baseline (MTU only) | 1M? | ? | 247 | 160 | ~90 | 0 |
| 1 | + 2M PHY | 2M ✅ | 30→50 ms | 247 | ~117 | ~60 | 0 |
| 2 | + TX buffers ×24 | 2M | 30→50 ms | 247 | ~83 | ~44 | 0 |
| 3 | + request 15 ms interval | 2M | 30→**15 ms** | 247 | **~234** | ~120 | 0 |
| 4 | **nRF DK as central** (Lever 5) | 2M | **7.50 ms** | 247 | **~1048** | ~537 | 0 |

**Cycle 4 — BREAKTHROUGH:** replaced the Mac with an nRF DK as central
(`firmware/ble-rate/central`). As central *we* set 7.5 ms + 2M and reject the
peripheral's param request. Result: **~1.05 Mbps, 0 drops** — **4.2× the macOS
ceiling**, proving the wall was the laptop, not the nRF54. Steady at ~4 packets
per connection event (537 pkt/s ÷ 133 events/s); 2M could in principle fit ~16,
so there may be headroom toward ~1.4 Mbps (likely gated by central RX buffering
/ event packing).

**Cycle 1 finding:** 2M accepted but throughput *fell* — Mac widened the interval to
50 ms and we were capped at **~3 packets/event** (= default TX buffer count of 3).
Bottleneck is packets-per-event, not PHY. → Lever 3.

**Cycle 2 finding:** more buffers did **not** help — our 24 buffers sit *full*; the
Mac drains only **~2 packets/connection event** and holds a 50 ms interval. The wall
is the **central (macOS)**, not our firmware. → Lever 4 (ask for a faster interval),
then if that's clamped, **Lever 5: controlled central** (2nd nRF DK as central — we
set the params ourselves and find the true radio ceiling).

**Cycle 3 finding:** the Mac **honored** the 15 ms interval request → **234 kbit/s**,
0 drops (best yet). But packets/event stayed at **~1.8** (120 pkt/s ÷ 66 events/s) —
the 3× gain was purely 3× more events. Both Mac-side knobs are now maxed: interval at
its floor, packets/event stuck at ~2.

---

## Where we landed

**Two ceilings, one conclusion — the receiver is the variable, not the nRF54.**

| Central | Best sustained | interval | pkts/event | drops |
|---------|----------------|----------|-----------|-------|
| macOS laptop | ~234–248 kbit/s | 15 ms (Apple floor) | ~2 | 0 |
| **nRF DK (ours)** | **~1.05 Mbps** | **7.5 ms** | ~4 | 0 |

- On **macOS**, firmware was never the limiter — our TX buffers sat full; the Mac
  accepts only ~2 packets/event at a 15 ms floor and we can't change that from the
  peripheral. ~234 kbit/s is *its* plateau.
- With an **nRF DK as central** (`firmware/ble-rate/central`), *we* set 7.5 ms +
  2M + reject the peripheral's param request → **~1.05 Mbps, 0 drops, 4.2×** the
  Mac. That is the real result: **the laptop was the throttle, not the chip.**
- Config that got us here: fat notifications (MTU 247 + DLE), 2M PHY, big TX
  buffers (master), and — decisively — a controlled central setting the params.

## Optional polish (not pursued)

Getting from ~1.05 → ~1.4 Mbps means lifting ~4 packets/event higher: more RX
buffering on the central and/or longer connection-event length. It's SDK-specific
(`CONFIG_BT_BUF_ACL_RX_COUNT` was rejected on NCS v3.3.1 — needs the correct
symbol) and low-yield for a characterization thesis, so we stopped at 1.05 Mbps.

The thesis takeaway: even ~1 Mbps sits far below raw broadband ephys (~10 Mbps /
32 ch), so on-chip reduction does the real work. This test pins the transmit
ceiling **and** shows the receiver is as much a design variable as the radio —
the eventual product wants a controlled dongle, not a laptop.

---

## Notes
- **DMA is not the limiter at these rates** (SPI reads ≈ 2% CPU). Revisit only as
  BLE nears ~1 Mbps *and* SPI carries real 64-ch data.
- **4 Mbps Nordic proprietary mode** exists but abandons BLE interop (needs a Nordic
  dongle as receiver — no phone/laptop). Out of scope unless we drop standard centrals.
- The thesis point: whatever this ceiling turns out to be, raw broadband ephys
  (~10 Mbps for 32 ch) sits far above it — so the gap is exactly what on-chip
  reduction has to absorb. This test pins the transmit ceiling.
