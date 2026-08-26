# Literature Review — On-Device Real-Time Spike Sorting / Classification for Wireless Neural Implants

> **Scope.** Prior art for the target combination: **on-device, real-time, single-unit spike
> sorting OR per-spike classification** (resolving individual neurons — *beyond* threshold
> crossings) running **on the implant/headstage itself**, in a **wireless / freely-moving
> rodent**. "Any on-device hardware counts as competing" (ASIC, FPGA, neuromorphic, or
> commercial SoC/MCU) — this is the strict, honest prior-art bar.

> **How this was produced (epistemic status — read this).** Two automated deep-research passes
> (fan-out web search → fetch primaries → 3-vote adversarial verification, 2/3 to kill a claim),
> **plus four 2026 primary papers read in full from PDF** this round.
> - **Pass 1 (2026-08-20):** 17 sources, 25 claims, 25/25 confirmed.
> - **Pass 2 (2026-08-26):** 17 sources, 25 claims, **23 confirmed / 2 refuted**; targeted at
>   verifying the four PDFs' context and enriching the prior-art table. It produced a **material
>   correction** (Akhoundi is **40 nm**, not 22 nm; validated on **ex-vivo macaque retina**, not
>   rodent) and a **reclassification** of the closest wireless/freely-moving headstage (see §3).
> **This is a reading *guide*, not a substitute for reading the primaries** — verify exact numbers
> and the fabricated-vs-layout distinction before anything load-bearing goes in the thesis.
> Dates in-repo are simulated; treat "recent" as of mid-2026.

---

## 1. Headline finding

**No published system demonstrates the full target combination**, and Pass 2 *strengthens* this
against a much stronger prior-art set. On-device real-time single-unit sorting in silicon is now
firmly solved — **fabricated and measured up to 1024 channels** (Akhoundi 2025; Jiang 2026), with
multiple 2026 SoCs — but:

- **None is wireless.** Every fabricated full-pipeline sorter (Chen 2026, Jiang 2026, Lukito 2026,
  Akhoundi 2025, Do 2019, Chen 2023) is a benchtop/replayed-data chip with **no radio**.
- **None is validated in a freely-moving animal.** Validation is synthetic (MEArec/Quiroga),
  ex-vivo (macaque retina), or **replayed** pre-recorded in-vivo data — never a behaving rodent.
- **None runs on a commercial BLE SoC.** All are custom ASICs. The one genuinely
  wireless + freely-moving + on-device-sorting system (Gagnon-Turcotte 2023) runs on a **COTS
  FPGA + MicroBlaze softcore with a custom UWB radio** — not a BLE SoC, not an ASIC.

So the three axes — on-device single-unit sorting, untethered wireless, freely-moving rodent —
have each been achieved, and pairs of them co-exist, but **the full triad has never been jointly
demonstrated, and never on a commodity BLE SoC.** [Synthesis across both passes; per-row sources below.]

A recurring, verified pattern: **titles/abstracts systematically overstate.** Several papers
advertising "on-implant spike sorting" resolve, on inspection, to **layout-only** designs
(Shaeri & Sodagar 2020), **simulation-only** ASICs (L-Sort), or **two-phase** architectures whose
"intelligence" runs offline.

---

## 2. Ranked reading list (importance × robustness)

Ranked for *your* thesis: how much you need to read it × how robust the engineering actually is.
**"Built?"** = fabricated **and** measured silicon / deployed hardware (most robust) vs.
layout/synthesis/simulation-only (design work, not proven hardware). **★ = read in full this round.**

| # | Paper | Venue | Built? | What runs on-device | Why read it |
|---|-------|-------|--------|--------------------|-------------|
| 1 | **★ Chen et al. 2026** — 128-ch level-crossing digitization + spike-sorting SoC | **IEEE TBCAS 2026** (imec/KU Leuven) | **Yes — 22 nm FDSOI, measured** | Full pipeline: LC-ADC → LC detection → spatial realignment → 8-feature STFE → **Geo-Osort online unsupervised clustering**. LNA off-chip. 1.09 µW/ch digital +1.2 µW/ch ADC; 142.6 µs latency. Datasets only. | The current strongest fabricated *event-driven* full sorter. Direct must-position-against; Gielen/Mora Lopez group (imec — the Neuralink-adjacent world). |
| 2 | **★ Jiang et al. 2026** — 1024-ch 583 nW/ch spike-sorting SoC, 16K templates | **IEEE TCAS-I 2026** (Fudan) | **Yes — 28 nm, measured** | NEO detection + FSDE features + **firing-rate-Osort**, 16K templates via hybrid on-chip SRAM + off-chip FeRAM; 11.7 µs latency. Validated on datasets **and replayed in-vivo mouse** vs Kilosort (93.7%/85.1%). | Highest channel count with in-vivo-*data* validation. The scaling frontier; shows the memory-hierarchy problem you'd inherit at high channel counts. |
| 3 | **★ Lukito et al. 2026** — Δ-detection + analog-CIM autoencoder spike-sorting SoC | **IEEE JSSC 2026** (KAIST/NYU-AD/Kyung Hee) | **Yes — 65 nm, measured** | **Includes on-chip LNA/AFE** → Δ-detection → **analog compute-in-memory binary autoencoder** feature extraction → L1 K-means. 32-ch (multi-chip); 94.54% Quiroga; 5.11 µs; 3.11 µW/ch + 5.12 µW/ch AFE. Datasets only. | The only one with the **analog front end on-chip** — most relevant to the analog-ASIC angle. Lead author is a **BioE bachelor**; co-author a BioE PhD — a direct precedent for your path. |
| 4 | **Akhoundi et al. 2025** — 1024-ch online spatial spike-sorting chip (SOM) | **ISSCC 2025 §15.2 / IEEE JSSC** | **Yes — 40 nm, measured** | Detection + spatial features + **self-organizing-map clustering** on-chip, on-chip training; 74 nW/ch, ≤50 µs latency, >1000× compression. No LNA (consumes wired-OR of a separate recording IC). Synthetic + **ex-vivo macaque retina**. | The ultra-low-power existence proof. Note: **40 nm** (earlier draft said 22 nm — corrected) and **retina, not rodent**. |
| 5 | **Do/Zeinolabedin/Kim 2019** — 128-ch area-efficient spike-sorting processor | **IEEE TVLSI 2019** | **Yes — 65 nm, measured** | Full on-chip: detection + features + **improved K-means** (not Osort/template-matching). 0.175 µW/ch, 333 ch/mm². LNA off-chip; no radio; no in-vivo. | The efficiency anchor; a clean fabricated full-pipeline reference and a K-means data point for your Tier-1 classifier. |
| 6 | **Chen et al. 2023** — 384-ch online-spike-sorting IC (Geo-Osort) | **IEEE JSSC 2023** | **Yes — 22 nm, measured** | NEO detection + spatial features + **geometry-aware Osort**; 1.78 µW/ch, 0.0013 mm²/ch. | The direct predecessor of #1 (same lineage); shows the Geo-Osort idea one generation earlier. |
| 7 | **Karkare et al. 2013** — 75 µW 16-ch neural spike-sorting processor | **IEEE JSSC** | **Yes — 65 nm, measured** | On-chip **unsupervised clustering**; 75 µW @ 0.27 V, 240× reduction. | The foundational low-power on-chip sorter; historical power anchor. |
| 8 | **Hao et al. 2021** — 10.8 µW recorder + analog classifier | **IEEE TBioCAS** | **Yes — 180 nm SOI, measured** | Clockless/ADC-less **analog K-means**; 10.8 µW total. | Lowest-power point; the analog end of the design space (compare to Lukito's analog CIM). |
| 9 | **Russo et al. 2026** — event-based SerDes telemetry network | **Neuromorph. Comput. Eng. 2026** (imec) | **Yes — 65 nm serializer, measured (deserializer on FPGA)** | **Compression/telemetry, NOT sorting**: send-on-delta + ternary-packet AER + Manchester coding; >7–12× compression, RMSE <6 µVrms. Replayed in-vivo rodent data. | Read for the **"getting rid of sampled data" + wireless-link** angle, not classification. The imec NCT-chip family. |
| 10 | **Shaeri & Sodagar 2020** — on-implant spike-sorting framework | **Nature Communications** | **Layout only** — 512-ch 130 nm, *not* fabricated | Only comparator **window-discrimination** on-implant; feature/window computation runs **offline on an external module**. Pre-recorded macaque V1. | Highest-impact near-neighbor; reviewers will cite it. Position against — and note it is **not measured silicon**, now surrounded by real fabricated sorters. |
| 11 | Surveys (Zhang 2023; Zhu/Shin/Shoaran 2021) | J. Neural Eng. / TBioCAS | n/a | — | Landscape maps; coverage, not evidence of any one demonstration. |

**If you read only three for the meeting/thesis positioning:** #1 (Chen 2026 — strongest event-driven
sorter), #3 (Lukito 2026 — analog front end on-chip, your path), #2 (Jiang 2026 — scaling + in-vivo data).

---

## 3. Robustness tiers — "did they actually do the engineering?"

Same papers, sorted by *what was actually built and measured*.

### Tier A — Fabricated **and** measured (trust as real engineering)
- **★ Chen 2026 (128-ch, imec)** — 22 nm FDSOI, measured; full event-driven pipeline + Geo-Osort; LNA off-chip; datasets. *[read in full]*
- **★ Jiang 2026 (1024-ch, Fudan)** — 28 nm, measured; NEO + FSDE + firing-rate-Osort, 16K templates; **replayed in-vivo mouse** vs Kilosort. *[read in full]*
- **★ Lukito 2026 (32-ch, KAIST)** — 65 nm, measured; **on-chip LNA** + Δ-detection + analog-CIM autoencoder + L1 K-means; datasets. *[read in full]*
- **Akhoundi 2025 (1024-ch SOM)** — 40 nm, measured; on-chip training; synthetic + **ex-vivo macaque retina** + Neuropixels. No LNA; not wireless. [[PMC12680097](https://pmc.ncbi.nlm.nih.gov/articles/PMC12680097/); [Stanford PDF](https://med.stanford.edu/content/dam/sm/artificial-retina/documents/Akhoundi2025.pdf)]
- **Do 2019 (128-ch)** — 65 nm, measured; detection + features + improved K-means; 0.175 µW/ch. [[IEEE 8519756](https://ieeexplore.ieee.org/document/8519756)]
- **Chen 2023 (384-ch Geo-Osort)** — 22 nm, measured; 1.78 µW/ch. [[ResearchGate 373473812](https://www.researchgate.net/publication/373473812)]
- **Karkare 2013** — 65 nm, measured; ~75% accuracy. [[IEEE 6532404](https://ieeexplore.ieee.org/document/6532404/)]
- **Hao 2021** — 180 nm SOI, measured; 93.2% synthetic. [[IEEE 9417633](https://ieeexplore.ieee.org/document/9417633/)]
- **2018 Osort hippocampal chip** — 40 nm, measured; 0.0175 mm²/ch; closest by *brain region* (hippocampus). [[ScienceDirect S0165027018303273](https://www.sciencedirect.com/science/article/abs/pii/S0165027018303273)]
- **Zeinolabedin 2024 (68-ch)** — 22 nm GF FDSOI, measured; recording/processing front-end, in-vitro (cell culture + replayed spikes). Primarily AFE, not a full freely-moving sorter. [[Frontiers 2024](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2024.1432750/full)]
- *(Possible Tier A, verify):* **96-ch Neural Spike Processor**, 180 nm — detection + constrained-Bayesian sorting + partial decoding; stated fabricated. [[arXiv 2009.05210](https://arxiv.org/pdf/2009.05210)]

### Tier B — Wireless + freely-moving + on-device sorting, but **COTS FPGA (not ASIC, not BLE)**
- **Gagnon-Turcotte / Gosselin 2023** — duty-cycled wireless optogenetic headstage; **on-device** detection + wavelet compression + sorting on a **low-power FPGA + MicroBlaze softcore, all COTS**; custom **UWB** link (>7.5 m); **32 rec + 32 opto ch, in freely-moving transgenic rodents**. **Satisfies (a) on-device sorting, (b) wireless, (c) freely-moving rodent — misses only (d) commercial BLE SoC / ASIC.** The single closest system to the target. [[NSF PAR 10488877](https://par.nsf.gov/biblio/10488877-multichannel-electrophysiological-recording-spike-detection-sorting-duty-cycled-wireless-optogenetic-headstage); [IEEE 10251115](https://ieeexplore.ieee.org/document/10251115)]
  - ⚠️ **Citation must be reconciled before use.** In Pass 1 the *same* NSF PAR record was read as **Tasneem et al., *IEEE Sensors J.* 2023**, with sorting done **offline in LabVIEW** — the opposite of on-device. Pass 2's abstract quote clearly describes on-device FPGA/MicroBlaze DSP (Gagnon-Turcotte-style). **Open the actual PDF and confirm both the author/venue and whether sorting is on-device before citing.** A refuted sub-claim (a specific in-vivo VTA/rat recording) means: cite the freely-moving capability generically, not that experiment.

### Tier C — Layout / synthesis / simulation only (real design, **not** proven silicon)
- **Shaeri & Sodagar 2020 (Nature Comms)** — 512-ch 130 nm **layout**, pre-recorded data; ~88%. High impact ≠ measured hardware; feature/window intelligence is **offline external**. [[Nature](https://www.nature.com/articles/s41467-020-17031-9); [PMC7327047](https://pmc.ncbi.nlm.nih.gov/articles/PMC7327047/)]
- **L-Sort 2025** — FPGA-prototyped (ZCU104) + 180 nm ASIC via **post-place-&-route simulation only (no tape-out)**; all 3 stages on-device (median-of-median detection + geometric features + O-Sort); Neuropixels-only. [[arXiv 2501.17885](https://arxiv.org/html/2501.17885)]
- **Strydis et al. 2024** (Purkinje spike-*type* classifier) — **synthesized** 45 nm, never fabricated, offline retrieval from STT-RAM; ternary spike-type, not single-unit identity. [[arXiv 2311.04808](https://arxiv.org/pdf/2311.04808)]

### Tier D — Real wireless in vivo, but **no single-unit sorting on-device**
- **Yoon et al. 2022**, 16-ch BLE wireless probe — real in-vivo wireless, but **threshold-crossing only**. The only *commercial-BLE* prior art, and it does not sort. [Nat. Commun. 2022, doi:10.1038/s41467-022-33296-8]
- *(Watch, preprint):* 2026 bioRxiv bidirectional neuromorphic wireless headstage (32-ch, closed-loop) — appears to *decode*, not single-unit sort. [[bioRxiv 714179](https://www.biorxiv.org/content/10.64898/2026.03.25.714179v1.full)]

---

## 4. Novelty verdict for the planned thesis

Target: on-device real-time single-unit **classification** on a **commercial BLE SoC** (Nordic
nRF54LM20B + Axon NPU), mouse headstage (~10 ms, ~30 mW), applied to classifying single-unit
**spike content within sharp-wave ripples** to distinguish healthy vs. Alzheimer's-corrupted ripples.

**Already done by others (de-risked, not novel):**
- On-device real-time single-unit sorting *in custom silicon* — **thoroughly solved**, up to
  1024 ch, multiple 2026 SoCs. [Tier A]
- **Power budget is generous** — genuine sorters run at **74 nW–1.2 µW/ch** — but these are
  **DSP/ADC figures excluding the radio and (usually) the LNA**. See caveat #1.
- On-device sorting + wireless + freely-moving *together on COTS FPGA* — Gagnon-Turcotte 2023
  (pending citation reconciliation). [Tier B]

**Genuinely open (your novelty), in order of strength:**
1. **The SWR-in-AD application** — classifying single-unit spike *content within sharp-wave
   ripples* to discriminate healthy vs. AD-corrupted ripples. **Unaddressed by any verified
   system** (all target generic sorting or spike-type). Strongest, most scientific, and the one
   least likely to be scooped by a circuits group.
2. **On a commercial BLE SoC/NPU** rather than a custom ASIC or COTS-FPGA — **no such
   demonstration found**; commercial-BLE prior art is threshold-only (Yoon 2022). This is the
   accessibility/reproducibility angle.
3. **The full triad on that platform** — on-device single-unit + wireless + freely-moving rodent,
   *jointly*, on a commodity SoC — never done. Gagnon-Turcotte is closest but is bespoke FPGA+UWB.

**Strategic read:** the novelty is **not** the hardware feat (on-chip sorting and low power are
done, and now clearly so). It concentrates in the **application (SWR-in-AD)**, the
**commercial-SoC accessibility angle**, and the **full wireless/freely-moving integration on that
platform**. Lead with the application.

---

## 5. Caveats (honest limits of this review)

1. **Biggest technical risk — the power budget is optimistic as usually quoted.** The nW–µW/ch
   figures are **DSP-core (± ADC) only**; most **exclude the LNA and the radio** (Akhoundi
   consumes a separate recording IC; Chen/Jiang/Do have off-chip LNAs). Your ~30 mW headstage must
   cover **amplifier + ADC + BLE radio + classifier**. Lukito 2026 is the useful exception — it
   reports **AFE (5.12 µW/ch) separately from the classifier (3.11 µW/ch)**, so use it to anchor a
   real full-front-end number. **Do a full-headstage power budget; this is the likeliest thing to bite.**
2. **The novelty conclusion is a negative existence claim** — only as strong as survey coverage
   (Pass 2 confidence: *medium* on the gap specifically). Broad but not exhaustive of all
   wireless-headstage / commercial-MCU literature. Frame as "none found in a rigorous but bounded
   search," not "none exists."
3. **Validation realism.** Accuracy figures (88–99%) are on synthetic/benchmark or **replayed**
   data, or **ex-vivo macaque retina** (Akhoundi) — **not** freely-moving rodent in-vivo. They
   overstate expected real-world single-unit performance.
4. **Prior-art only.** This sweep did **not** verify nRF54LM20B / Axon NPU specs, the 10 ms/30 mW
   realism, or the SWR-healthy-vs-AD neuroscience. Separate checks needed.
5. **Layout/sim ≠ silicon.** Shaeri & Sodagar (layout), L-Sort (sim), Strydis (synthesis) are
   *not* taped-out. Don't cite as proven hardware.
6. **Refuted sub-claims (Pass 2) — do not cite:** (a) Akhoundi "5-feature" extraction (feature
   count unconfirmed); (b) Gagnon-Turcotte specific in-vivo VTA/rat recording.
7. **Fast-moving frontier.** Three of the strongest sorters are **2026** results. Monitor
   ISSCC/JSSC/TBCAS/TCAS-I through the thesis.

## 6. Reference corrections (fix before citing)

- **Akhoundi 2025 is 40 nm** (earlier draft: 22 nm) and validated on **ex-vivo macaque retina +
  synthetic**, not rodent.
- **NSF PAR 10488877** has been read two ways: **Gagnon-Turcotte/Gosselin, TBioCAS, on-device
  FPGA sorting** (Pass 2) vs **Tasneem et al., IEEE Sensors J., offline LabVIEW sorting** (Pass 1).
  These are mutually exclusive — **resolve from the PDF before citing** (title "duty-cycled wireless
  optogenetic headstage" strongly matches the Gagnon-Turcotte/Laval lineage).
- Shaeri & Sodagar 2020 and "the 512-ch ~88% online sorter" are **the same paper**.
- **"Valencia & Alimohammad 2021 (binarized-NN sorting)"** did not survive Pass 1 as attributed;
  the fabricated Valencia & Alimohammad 2019 parallel-Osort system is the real item — re-check.

## 7. Full source list

**Read in full from PDF this round (primaries):**
- Chen, Xing, Yang, Jung, Tacca, Verhelst, Gielen, Mora Lopez 2026, "A 128-Channel Level-Crossing-Based Neural Digitization and Spike Sorting SoC…," *IEEE TBCAS* (DOI 10.1109/TBCAS.2026.3714087).
- Jiang, Chen, Lu, He, Yang, Chen, Liu, Chen, Liu, Liu 2026, "A 1024-Ch 583-nW/Ch Spike-Sorting SoC…," *IEEE TCAS-I* 73(8):5556–5568.
- Lukito, Choi, Chang, Ha, Je 2026, "A Spike Sorting SoC With Δ-Based Spike Detection and End-to-End Autoencoder Feature Extraction Using Analog CIM," *IEEE JSSC* 61(4):1710–1721. [[IEEE 11096105](https://ieeexplore.ieee.org/document/11096105)]
- Russo, He, Romme, Traferro, van Schaik, Liaw, Ren, Gao, Dolmans, Liu 2026, "Event-based SerDes telemetry network for distributed BCIs," *Neuromorph. Comput. Eng.* 6:014001.

**Verified secondaries / prior art:**
- Akhoundi et al. 2025, 1024-ch SOM chip, *ISSCC/JSSC* — [PMC12680097](https://pmc.ncbi.nlm.nih.gov/articles/PMC12680097/) · [Stanford PDF](https://med.stanford.edu/content/dam/sm/artificial-retina/documents/Akhoundi2025.pdf)
- Do/Zeinolabedin/Kim 2019, *IEEE TVLSI* 27(1):126–137 — [IEEE 8519756](https://ieeexplore.ieee.org/document/8519756)
- Chen et al. 2023, 384-ch Geo-Osort IC, *IEEE JSSC* — [ResearchGate 373473812](https://www.researchgate.net/publication/373473812)
- Zeinolabedin et al. 2024, 68-ch 22 nm FDSOI SoC, *Front. Neurosci.* — [Frontiers](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2024.1432750/full)
- Karkare et al. 2013, *IEEE JSSC* 48(9):2230–2238 — [IEEE 6532404](https://ieeexplore.ieee.org/document/6532404/)
- Hao et al. 2021, *IEEE TBioCAS* 15(2):351–364 — [IEEE 9417633](https://ieeexplore.ieee.org/document/9417633/)
- 2018 hippocampal Osort chip, *J. Neurosci. Methods* — [ScienceDirect S0165027018303273](https://www.sciencedirect.com/science/article/abs/pii/S0165027018303273)
- Gagnon-Turcotte / (or Tasneem) 2023, duty-cycled wireless optogenetic headstage — [NSF PAR 10488877](https://par.nsf.gov/biblio/10488877-multichannel-electrophysiological-recording-spike-detection-sorting-duty-cycled-wireless-optogenetic-headstage) · [IEEE 10251115](https://ieeexplore.ieee.org/document/10251115) *(reconcile attribution)*
- Shaeri & Sodagar 2020, *Nat. Commun.* — [Nature](https://www.nature.com/articles/s41467-020-17031-9) · [PMC7327047](https://pmc.ncbi.nlm.nih.gov/articles/PMC7327047/)
- L-Sort 2025 — [arXiv 2501.17885](https://arxiv.org/html/2501.17885)
- Strydis et al. 2024 — [arXiv 2311.04808](https://arxiv.org/pdf/2311.04808)
- 96-ch Neural Spike Processor ASIC — [arXiv 2009.05210](https://arxiv.org/pdf/2009.05210)
- 2026 bidirectional neuromorphic wireless headstage (preprint) — [bioRxiv 714179](https://www.biorxiv.org/content/10.64898/2026.03.25.714179v1.full)
- Surveys — [Springer s42234-025-00177-6](https://link.springer.com/article/10.1186/s42234-025-00177-6) · [arXiv 2405.10780](https://arxiv.org/pdf/2405.10780)
- From the thesis proposal (not re-fetched): Yoon et al. 2022, *Nat. Commun.* doi:10.1038/s41467-022-33296-8; Zhang et al. 2023, *J. Neural Eng.* doi:10.1088/1741-2552/acc7cc; Zhu/Shin/Shoaran 2021, *IEEE TBioCAS* doi:10.1109/TBCAS.2021.3112756
