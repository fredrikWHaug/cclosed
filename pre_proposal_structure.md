# ES100 Proposal — structure, rubric, and how our requirements map onto it

Reference for writing the ES100 project proposal (15% of thesis grade). Distilled from the three course documents: the Proposal Template, the Proposal Rubric, and the full Project Rubric. Keep this as the source of truth for *what the proposal must contain* and *how our requirements work maps onto the graded structure*.

---

## 1. What the proposal must contain (rubric-authoritative)

The proposal is graded on **Table 1 (all required)** + **exactly one item from Table 2**.

**Table 1 — required:**
- **F1 — Identify a Problem.** Background, purpose, motivation: why is this a problem, how big, who/what does it affect, who are the stakeholders (stakeholder map if feasible). Identify where the project sits in a larger system (diagram allowed). Include a clear **Problem Statement (Needs Statement)**: the specific unmet need + the requirements of a model solution; must NOT suggest a solution design.
- **F2 — Research previous and existing solutions.** What has already been designed and what are its shortcomings. **≥3 journal/technical papers** as references. Full numeric citations. Describe existing components that may be reused/modified. Delineate this ES100 capstone from any prior work of yours.
- **F3 — Tech Spec: Quantitative Value & Justification.** Multiple technical specifications aligned with problem/approach/client = the **critical metrics of success**, based on engineering standards or literature. For each: **(a) Quantitative Value** (numerical values, tolerances), **(b) Justification** (linked to a specific project goal, backed by literature citations / engineering standards / experimentation / calculations). **Summary table of design-INDEPENDENT (solution-agnostic) technical specifications.**

**Table 2 — pick exactly ONE:**
- **F4 — Tech Spec: Measurement.** Initial measurement plan for each spec: quantities, methods, software/tools, how often, sampling rates. Adds the **Measurement Method** column to the F3 table.  ← **OUR PICK (recommended)**: lowest friction, integrates directly into the F3 table we're already building.
- **D2 — Consideration of multiple design approaches.** ≥2 feasible approaches addressing the critical specs; technically sound + challenging; build/test feasibility; subsystem interactions.
- **L1 — Preliminary Timeline & Budget.** High-level plan in ≤2-week increments with specific milestones; stages for design/build/measure/analyze; preliminary budget (Active Learning Labs cap: **$500/year**, excl. faculty-lab funds).
- **F5 — Environmental, Societal, Global & Economic Impact.** Broader ethical/societal context: (i) public health/safety/welfare, (ii) global, (iii) cultural, (iv) social, (v) environmental, (vi) economic factors.

**Also required regardless:**
- **Project Executive Summary** — ≤150 words, written last, stands alone like an abstract. Must state the specific **design-engineering problem** and **critical project goals + constraints**. (Draft already written elsewhere.)
- **Signature pages** — student + advisor (+ thesis reader if advisor isn't SEAS ladder faculty). No proposal accepted without signatures; an email screenshot of approval is acceptable.

---

## 2. Template section order (black = required; blue = optional)

```
0. PROJECT EXECUTIVE SUMMARY            (write last; ≤150 words; standalone)
[DEFINE]
1. Background and Motivation
   i.   Background and motivation
   ii.  Stakeholders, Client, and End User of the Solution
   iii. Science, Technology & Society considerations (STS)   [optional]
2. Existing solutions and previous work
3. Problem Statement
4. Design Requirements / Technical Specifications
   a. Description
      i.   Values
      ii.  Justification
      iii. Measurement Method   [optional → becomes required if F4 is the Table 2 pick]
   b. Summary Table
[DESIGN]
5. Consideration of multiple design approaches
[REFERENCES & APPENDICES]
6. References
7. Appendices
   i. Preliminary Project Milestones and Budget   [optional]
```

**Summary-table columns (Section 4b — the graded artifact):**
`Alphanumeric Label | Requirement | Specification | Quantitative value | Measurement Method`

---

## 3. How OUR three-tier framework maps onto the template

Our framework (defined and locked earlier):
- **Functional requirements:** what the system does, distilled as behaviors.
- **Technical requirements:** the qualities the behaviors must satisfy.
- **Technical specifications:** quantitative and measurable form of the technical requirement.

Mapping to the template's summary-table columns:

| Template column | = our layer |
|---|---|
| **Requirement** | our **technical requirement** (the quality) |
| **Specification** | the specific measurable **parameter** |
| **Quantitative value** | our **technical specification** (number + tolerance) |
| **Measurement Method** | how we verify it (the **F4** pick) |

- Our **functional requirements** get no column — they become the *derivation narrative* in Section 4a Description and feed the systems-context part of F1.
- **Rubric subtlety that rewards our discipline:** F3 wants *design-**independent** (solution-agnostic)* specs. So the table stays solution-agnostic ("per-channel sample rate ≥ X"); the *specific design choices* (Intan, nRF54, SPI at ~20 MHz) go in **Section 5 (design approaches)**, NOT the requirements table. The rubric explicitly wants that separation.

---

## 4. The restructured Section 4 (requirements reorganized into three groups)

Two insights from earlier work became structural: (1) the **cross-cutting "no-loss/keep-up" requirement** that refused to sit under any single functional requirement, and (2) the **offline model** being a separate phase feeding the online pipeline. Both are now their own groups.

**4a. Description** — narrative establishing three groups:
> The system decomposes into five functional behaviors forming the **online (deployment) pipeline** (FR1–FR5), a set of **system-level qualities** spanning the whole pipeline, and an **offline (preparation) phase** producing the classifier the online system consumes.

**Group A — Per-behavior technical requirements** (each traced to a functional requirement):

| Label | Requirement (quality) | Traces to |
|---|---|---|
| A1 | ≥3 channels amplified and digitized | FR1 |
| A2 | Per-channel sample rate ≥ Nyquist for the spike band | FR1 |
| A3 | Aggregate digitization throughput ≥ (channels × per-channel rate) | FR1 |
| A4 | Amplitude resolution sufficient to resolve spikes above the noise floor | FR1 |
| A5 | ADC→MCU link throughput ≥ aggregate data rate | FR1 |
| A6 | Spikes separated from LFP (band-limiting) | FR2 |
| A7 | Detection sensitivity/specificity sufficient vs. ground truth | FR2 |
| A8 | Each spike classified to a unit ID from the pre-built library | FR4 |
| A9 | Classification accuracy above chance vs. Kilosort 4.0 | FR4 |
| A10 | Transmitted packet contains unit ID + timestamp | FR5 |

**Group B — System-level (cross-cutting) technical requirements** (lifted out; span the pipeline):

| Label | Requirement (quality) | Spans |
|---|---|---|
| B1 | No detected spike (or its source sample) dropped under sustained load | FR1–FR5 |
| B2 | Timestamp stamped at detection, on a stable clock, at sufficient resolution | FR3, FR5 |
| B3 | System keeps up in real time (throughput-bounded; latency bounded but non-closed-loop) | FR2–FR5 |

**Group C — Offline preparation preconditions** (NOT online requirements; exempt from online power/latency/bandwidth constraints):

| Label | Precondition | Feeds |
|---|---|---|
| C1 | A labeled unit library + trained classifier, produced offline from a reference recording via spike sorting | A8, A9 |

**4b. Summary Table** (acquisition fully worked as the example; `[TBD]` = value genuinely pending pilot measurement — the rubric permits proposal-stage specs to be refined later):

| Label | Requirement | Specification | Quantitative value | Measurement Method |
|---|---|---|---|---|
| A1 | ≥3 channels digitized | channel count | ≥ 3 (min); 32 (target) | count channels in acquired stream |
| A2 | Sample fast enough for spike band | per-channel sample rate | ≥ ~12.5 kS/s (Nyquist, 6 kHz); design point 25 kS/s | FFT of a known replayed test signal; verify sampling-timer period |
| A3 | Digitization keeps up across channels | aggregate conversion rate | ≥ channels × per-channel rate (≥ 75 kS/s at 3×25 k) | measure sustained conversion rate; count missed conversions |
| A4 | Resolve spikes above noise | ADC resolution / SNR | 16-bit; noise floor ≤ [TBD µV], spike SNR ≥ [TBD] | measure input-referred noise + SNR on a known-amplitude input |
| A5 | Link carries the stream | ADC→MCU link throughput | ≥ channels × rate × bits (≥ 1.2 Mbps at 3×25 k×16) | sustained SPI throughput; dropped-sample count |
| A7 | Detect reliably | detection TPR / FPR vs Kilosort | TPR ≥ [TBD]% at FPR ≤ [TBD]%, ±1 ms match window | compare detected events to Kilosort 4.0 labels |
| A9 | Classify better than chance | classification accuracy | > chance (=100%/K); target ≥ [TBD]% | confusion matrix vs Kilosort on held-out data |
| B1 | No loss under load | dropped events/samples | 0 drops up to sustained [TBD] spikes/s | stress test at rising event rate; count drops |
| B2 | Faithful timestamps | timestamp resolution; clock drift | ≤ 1 sample period (~40 µs); drift < [TBD] over session | align to reference recording; measure jitter/drift |

---

## 5. Solid vs. still-to-nail (the remaining risk)

- **Solid now (real numbers writable):** channel count, sample-rate floor (from spike-band biophysics), aggregate/link throughput *relationships*, resolution (16-bit), packet size (5 bytes/event = 1-byte unit ID + 4-byte timestamp).
- **`[TBD]` — need value + justification before submission:** detection TPR/FPR target, classification-accuracy target, sustained-event-rate for the no-loss test, noise-floor/SNR, clock-drift bound. Rubric wants each backed by *literature citations / engineering standards / experimentation / calculations* — several are backable by calculation (throughput, Nyquist) or by citing the benchmark papers (accuracy vs. what Chen/Jiang/Lukito report).

---

## 6. Technical-writing rules (graded, penalized if violated)

- Numeric citation style (IEEE-like). **NOT** author-date. No "Ibid".
- Limited first-person; not a personal narrative.
- Tables/figures: clear, correct labels/units/legends, captions that stand alone.
- No spelling/grammar/punctuation errors.
- Code goes in an appendix, used sparingly, only if necessary.
- Concise, logically organized, discrete sections, logical flow.

---

## 7. Deadlines / logistics (as of Tue this week)

- Draft to course-staff member: **tomorrow (Wed) night**.
- Meeting to discuss questions: **Friday**.
- Final deadline: **Monday PM**.
- Advisor situation: postdoc advisor status uncertain; **Prof. Gage Hills = SEAS thesis reader** (signed on). Signature page needs his signature on the *full* proposal (not the pre-proposal). No-animal-testing constraint from Dr. Moyer stands — proposal must not require animal testing; freely-moving-mouse deployment is framed as motivation/future work only, validation on replayed/synthetic data.
