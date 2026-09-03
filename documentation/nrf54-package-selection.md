# nRF54LM20B package selection for the custom PCB

Quick reference on which nRF54LM20B package to order for the custom headstage PCB
(the final-prototype board that carries the Intan + nRF54). Written because the
CSP98 figure came up and is worth pinning down properly.

## First, a clarification

The **CSP98** figure mentioned earlier was **not** a recommendation of what to order —
it was a *cross-check*: the nRF54LM20 **DK** (the dev kit we prototype firmware on)
happens to carry the SoC in the CSP98 package. That's a fact about the dev board, not
a decision about our PCB. For the **custom PCB**, the package choice is genuinely open,
and it's a real trade-off worth making deliberately.

## The three options (verified from Nordic's product page)

| Package | Dimensions | Balls/pins | Pitch | GPIO | Assembly |
|---|---|---|---|---|---|
| **QFN52** | 6.0 × 6.0 mm | 52 pins | 0.4 mm | 32 | **Leaded — hand-solderable / reworkable** |
| **CSP61** | 3.02 × 2.43 mm | 61 balls | 0.325 mm | 40 | fine-pitch BGA-class (reflow, hard to rework) |
| **CSP98** | 3.67 × 3.85 mm | 98 balls | 0.35 mm | 66 | fine-pitch BGA-class (reflow, hard to rework) |

## The trade-off that actually matters here

It is **size vs. assembly risk**, and assembly risk is not abstract for this project —
you have already fought one 104-ball BGA (the Intan) through a reflow bring-up saga.
Adding a **second** fine-pitch BGA-class part (CSP61 or CSP98) doubles that class of
risk on the same board: BGA fan-out routing, reflow, and near-impossible hand-rework.

- **QFN52** — leaded, 0.4 mm pitch, hand-solderable and reworkable. Biggest footprint,
  fewest GPIO (32), but by far the **most robust to assemble** for a first board.
- **CSP61 / CSP98** — much smaller (the headstage win), but each is a fine-pitch part
  that must be reflowed and effectively cannot be reworked if a joint is bad.

**Does QFN52's 32 GPIO suffice?** For a minimal headstage the pin budget is small:
SPI to the Intan (SCLK/MOSI/MISO/CS ≈ 4–5), a few control/status lines, SWD (dedicated
pads, not GPIO), and the crystal (dedicated XTAL pins, not GPIO). BLE needs no GPIO —
the radio is integrated. So 32 GPIO is comfortably enough for the acquisition-focused
design. GPIO count is therefore **not** the deciding constraint; assembly risk is.

## Recommendation (fast AND robust — the two-step package strategy)

The lowest-total-risk path is the common one for exactly this situation:

1. **First bring-up board: QFN52.** Leaded and reworkable, so if something is wrong you
   can fix it by hand instead of scrapping a reflowed BGA. Prove the design works.
2. **Size-optimized revision: migrate to CSP61** (or CSP98 if you need the GPIO/size)
   once the schematic and firmware are validated on the forgiving package.

This matches the "fast *and* robust" priority: you don't gamble the first board's
bring-up on a second fine-pitch BGA, and you don't lock in a hard-to-assemble part
before the design is proven.

**For the proposal specifically:** stating **CSP61** as the *target* for the small
headstage is defensible (it's the size-forward choice with adequate GPIO), but it is
worth writing that the *first prototype* may be built on QFN52 for assembly robustness,
with migration to CSP61 once proven. That reads as sound engineering judgment rather
than an unexamined package pick.

## Source

- Nordic nRF54LM20B product page (package dimensions, ball/pin counts, pitch, GPIO),
  verified 2026-08. Core specs also confirmed: 128 MHz Cortex-M33, 512 KB RAM, 2 MB flash.
