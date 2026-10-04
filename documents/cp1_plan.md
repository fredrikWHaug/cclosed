# Checkpoint 1 plan — fwh_ES100_cp1.tex (v2, rubric-aligned)

Sources: `grading_template.csv` (Coughlin's sheet) + `ES100 Project Rubric.pdf`
(AY2025). v2 fixes from the second pass are marked ⚠.

## Item accounting (⚠ corrected from v1)

CP1 requires **6 items attempted**; missing any (including the +1 free choice)
is −1 each. The six:

1. **F4** Tech spec measurement — already SAT at proposal; **carries over**
   ("early attempt SAT items will carry over"). Zero new work.
2. **D1** Systems diagram
3. **D2** Consideration of multiple design approaches
4. **B1** Training list
5. **L1** Preliminary timeline and budget
6. **D3** Quantitative evaluation of ≥2 approaches — the chosen +1.
   ⚠ Strategic note: D3 is also a Design-Review item, so SAT now banks it
   for DR ("early attempt SAT carries over").

**Plus, on top of the six:** F1 retry (In Progress → SAT = +0.5; an UNSAT item
"must be retried at the next assignment"). Largely done in the feedback pass;
see F1 checklist below.

## F1 retry — rubric checklist (⚠ new; the rubric adds detail beyond Coughlin's comments)

- Rubric F1.1 asks "why is this a problem / how big / who is affected /
  stakeholders," and says "**if feasible, please include a stakeholder map**."
  Settled: deferred to the final figure-design step (last item in Order of
  work) — restore small if the figure allowance permits.
- Rubric F1.2: "identified where the project resides in an overall larger
  system." Add one explicit sentence in §1.1 (headstage within the
  probe → acquisition → analysis chain of a systems-neuroscience rig).
- Rubric F1.3: problem statement must "list the requirements of a model
  solution that addresses the shortfalls of existing solutions" while NOT
  suggesting a design. ⚠ Our rewritten statement states the dilemma but lists
  no solution requirements. Resolution that honors both the rubric and
  Coughlin's "zero solution hints": close §1.3 with one solution-neutral
  requirements sentence, e.g. "A solution must deliver the scientifically
  relevant content of many channels within the power and bandwidth budget of
  an untethered head-mounted device." (Capabilities, not mechanisms.)

## The new sections — rubric-driven content requirements

### D1 Systems diagram (figure; caption only costs text)
Full chain with every subsystem and sub-block: signal source/electrode →
Intan RHD2164 (amp, 300 Hz–6 kHz band, MUX, 16-bit ADC) → SPI link →
nRF54 (hardware-timed acquisition engine: TIMER→DPPI→SPIM→DMA; then detect →
extract → classify → packetize) → BLE radio → host (Kilosort ground truth,
analysis). ⚠ Rubric explicitly requires labeled **interfaces and pathway
types**: mark each arrow with medium + rate (analog µV diff pair; SPI @
21.33 MHz, 757 k words/s measured ceiling; BLE 2.4 GHz, 2 Mbps theoretical /
~1.05 Mbps measured nRF↔nRF; USB/serial at host).

### D2 Multiple design approaches (~1 pg text)
Two-plus feasible approaches per major component. ⚠ Rubric requires, per
approach: (a) **build & test feasibility** discussion, (b) **subsystem
interaction** description — not just a list of alternatives. Structure each
as: approach → how the subsystems would interact → build/test feasibility →
kept/rejected because X. Decisions to cover:
- Compute platform: commodity BLE SoC (nRF54) vs FPGA vs custom ASIC vs
  host-side sorting (rejected: defeats compression).
- Acquisition topology: single SPI bus vs dual front-end / dual bus
  (the pre-PCB decision the measured ceiling forces).
- Classifier: template matching vs feature + cluster vs small NN —
  feasibility = cycles/spike budget on the nRF54 at 32 ch.
- Delivery: direct BLE to laptop vs nRF relay (measured macOS ceiling).

### D3 Quantitative evaluation (~0.75 pg + small table)
Rubric: evaluations must apply **models** (analytical, computational,
statistical analysis of prior data). Three evaluations, all already in hand
or one evening of writing:
1. **Statistical, measured:** software-paced vs hardware-timed sampling —
   σ = 23.67 µs vs 0.38 µs, 100.0% vs 0.7% within ±10%, n ≈ 12.8 k scope
   intervals each (`firmware/theo/measurements/`). This is a completed
   quantitative evaluation of two design approaches by direct measurement.
2. **Analytical + measured:** single- vs dual-bus channel ceiling —
   words/s = f(SCLK, word time, CSN gap) with the measured 757,741 words/s
   anchor → 23.7 kS/s/ch × 32 single-bus vs 30 kS/s × 32 dual-bus.
3. ⚠ **Analytical model (new, strengthens D3):** link-budget model of raw
   vs spike-ID transmission: raw = ch × 30 kS/s × 16 bit vs
   spike-ID = ch × r_spike × 5 B. At 32 ch and 40 spikes/s/ch: 15.36 Mbps
   vs 51.2 kbps (≈ 300×), with the crossover firing rate where the scheme
   stops winning — the core design claim, quantified.

### B1 Training (~0.25 pg table)
⚠ Rubric requires completed-vs-pending **with dates**. Columns:
tool/skill | status | date (done or planned). Completed: Zephyr/nRF Connect
SDK + DPPI/DMA (Sep 2026), KiCad + BGA assembly (served the test PCB),
TBS2204B scope workflows (Sep–Oct 2026), Intan SPI protocol (Sep 2026),
Python analysis tooling. Pending with target dates: Kilosort 4 (install +
tutorial), power profiling (PPK2), multi-channel firmware patterns.

### L1 Timeline + budget (~0.75 pg, two tables)
⚠ Rubric: schedule in **two-week increments or less**, with milestones, and
broken into **design / build / measure / analyze / verify** stages. Build the
timeline table in 2-week rows from CP1 → Design Review → CP2 → final thesis.
Budget: spent (PCB fab + RHD2164, nRF54 DKs, Pi Zero + PCM5102 + microSD
≈ $35 ground-truth rig) and projected (battery, passives, possible 2nd fab).

## Page budget (⚠ v1 table summed to 10.5; fixed)

Constraints: **10 pages text incl. tables, excl. figures; ≤12 with figures;
refs excluded. Settled: title page and TOC do NOT count** — TOC stays.

| Section | Text pages |
|---|---|
| Exec summary (Fig 1 excluded from count) | 0.50 |
| 1 Problem identification (improved; + F1 checklist items) | 1.50 |
| 2 Existing solutions + previous work | 1.50 |
| 3 Requirements + specs + justifications (2 tables) | 2.75 |
| 4 Measurement plan (+ table), compressed | 1.00 |
| 5 Design approach: D1 caption + D2 | 1.00 |
| 6 D3 quantitative evaluation (+ small table) | 0.75 |
| 7 B1 training table | 0.25 |
| 8 L1 timeline + budget tables | 0.75 |
| Reserve | 1.00 |
| **Total** | **10.00** |

Figures outside the text count: Fig 1 (0.5) + systems diagram (0.75) +
(optional) small stakeholder map (0.4) ≈ 1.65 ≤ 2.0 allowance.

## Technical-writing rubric checks (⚠ new — graded with a −0.5 penalty risk)

- Numerical citations only (IEEE style; no author-date, no ibid) — current
  manual [n] scheme is compliant; keep numbering continuous after edits.
- Every figure/table: standalone descriptive caption, labeled axes/units.
- Limited first person ("to my knowledge" is fine; no narrative voice).
- No code in body text (appendix only, sparingly) — keep firmware details
  as prose + diagram, not listings.

## Out of scope for CP1 (deliberate)

- F5 (Env/Soc/Global/Econ + STS questions) — not among the six; a natural
  Design-Review add. Note Winner-1980 reading for when it comes due.
- D4 (Pugh-style chosen-approach justification per component), D5, B2+ —
  DR/CP2 items; D3's tables are written so D4 can cite them later.

## Order of work

1. Systems diagram (SVG → PNG) with labeled interfaces + rates.
2. §5 D2 prose (approach → interactions → feasibility → verdict).
3. §6 D3: two measured evaluations + link-budget model, one table.
4. §7 B1 and §8 L1 tables (dates; 2-week increments).
5. F1 checklist edits in §1 (larger-system sentence; requirements sentence
   in problem statement).
6. Compression pass to the table above; compile; page audit; proofread pass
   against the technical-writing rubric.
7. Final figure design: restore stakeholder map (small) if space permits
   (Fig 1 ≈ 0.5 + systems diagram ≈ 0.75 + map ≈ 0.4 ≈ 1.65 ≤ 2.0 allowance).
