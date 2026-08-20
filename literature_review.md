# Literature Review — On-Device Real-Time Spike Sorting / Classification for Wireless Neural Implants

> **Scope.** Prior art for the target combination: **on-device, real-time, single-unit spike
> sorting OR per-spike classification** (resolving individual neurons — *beyond* threshold
> crossings) running **on the implant/headstage itself**, in a **wireless / freely-moving
> rodent**. "Any on-device hardware counts as competing" (ASIC, FPGA, neuromorphic, or
> commercial SoC/MCU) — this is the strict, honest prior-art bar.

> **How this was produced (epistemic status — read this).** This review is the output of an
> automated deep-research pass (fan-out web search → fetch of primary sources → 3-vote
> adversarial verification, needing 2/3 to kill a claim), then written up. **17 primary sources
> were fetched; 25 falsifiable claims were verified; 25/25 confirmed, 0 refuted**, all but one
> by unanimous 3-0 vote (the lone 2-1 is flagged below). The per-paper summaries come from
> source-extraction agents that fetched the actual papers, cross-checked. **This is a reading
> *guide*, not a substitute for reading the primaries** — verify exact numbers and the
> fabricated-vs-layout distinction yourself before anything load-bearing goes in the thesis.
> Produced 2026-08 (dates in-repo are simulated; treat "recent" as of mid-2026).

---

## 1. Headline finding

**No published system demonstrates the full target combination.** Genuine on-device real-time
single-unit sorting, a wireless untethered link, and a freely-moving rodent have each been
achieved *separately* — but **never together**, and **never on a commercial BLE SoC**. The
wireless-freely-moving-rodent systems sort **offline** after transmission; the genuine
on-device sorters are custom ASICs/FPGAs run on benchtop/pre-recorded/ex-vivo data. The only
cited commercial-BLE probe is **threshold-only** (Yoon 2022). [Synthesis across all verified
findings; sources per row below.]

A recurring, verified pattern: **titles/abstracts systematically overstate.** Several papers
advertising "on-device spike sorting" resolve, on inspection, to offline or two-phase
architectures.

---

## 2. Ranked reading list (importance × robustness)

Ranked for *your* thesis: how much you need to read it, weighted by how robust its
engineering/experimentation actually is. **"Built?"** = fabricated **and** measured silicon /
deployed hardware (most robust) vs. layout/synthesis-only (design work, not proven hardware).

| # | Paper | Venue | Built? | What runs on-device (real-time) | Why read it |
|---|-------|-------|--------|--------------------------------|-------------|
| 1 | **Shaeri & Sodagar 2020**, "A framework for on-implant spike sorting based on salient feature selection" | **Nature Communications** (highest impact) | **Layout only** — 512-ch 130 nm ASIC *laid out*, not fabricated/measured; validated on pre-recorded macaque V1 | Only **window-discrimination classification** (comparators); the clustering/feature-selection runs **offline on an external module** | Highest-impact near-neighbor; reviewers *will* cite it. Must position against — and note it is **not measured silicon**. |
| 2 | **Akhoundi et al. 2025**, 1024-ch online spatial spike-sorting chip (SOM) | **ISSCC 2025 §15.2 / IEEE JSSC** | **Yes — fabricated 40 nm, measured** | **Full pipeline on-chip incl. on-chip training**: detection + spatial features + self-organizing-map clustering, 76 µW total (74 nW/ch), ≤50 µs cluster latency | The strongest existence proof that *autonomous* single-unit sorting fits an ultra-low-power budget. The moving frontier. |
| 3 | **Luan et al. 2018**, "Compact standalone platform for neural recording with real-time spike sorting and data logging" | **J. Neural Eng.** | **Yes — FPGA+MCU+Intan AFE, deployed in vivo 24 h** | Real-time **template-matching** per-spike classification, untethered in a **freely-moving rhesus monkey** | Closest to a *real deployed* untethered on-device classifier. Its two-phase design (offline clustering → on-device matching) is essentially a primitive of your plan. |
| 4 | **Karkare et al. 2013**, "A 75-µW 16-channel neural spike-sorting processor with unsupervised clustering" | **IEEE JSSC** (top circuits venue) | **Yes — fabricated 65 nm, measured** | On-chip **unsupervised clustering**, 75 µW @ 0.27 V, 240× data reduction | The foundational low-power on-chip sorter; your power-budget anchor. |
| 5 | **Hao et al. 2021**, "A 10.8-µW neural signal recorder and processor with unsupervised analog classifier for spike sorting" | **IEEE TBioCAS** | **Yes — fabricated 180 nm SOI, measured** | Clockless/ADC-less **analog K-means** classifier, 10.8 µW total | Lowest-power point; shows the analog end of the design space. |
| 6 | **2018 hippocampal-prosthesis chip** (Osort), on-implant spike sorter | **J. Neurosci. Methods** | **Yes — fabricated 40 nm, measured** | Detection + **Osort unsupervised clustering** + Bayes template matching, 19 µW/ch, handles overlapping spikes | Genuine full on-chip sort; closest by *brain region* (hippocampus). |
| 7 | **Zhang et al. 2023** & **Zhu/Shin/Shoaran 2021** (surveys) | J. Neural Eng. / IEEE TBioCAS | n/a (reviews) | — | Landscape maps; use for coverage, not as evidence of any single demonstration. |

**If you read only three:** #1 (impact + must-cite), #2 (strongest real hardware), #3 (closest
real deployment).

---

## 3. Robustness tiers — "did they actually do the engineering?"

This is the cut you asked for. Same papers, sorted by *what was actually built and measured*.

### Tier A — Fabricated **and** measured (trust as real engineering)
- **Akhoundi 2025 (1024-ch SOM)** — fabricated 40 nm, measured; on-chip training; 80.8–99.2% accuracy on synthetic (MEArec) + **ex-vivo macaque retina** + Neuropixels; >80% Kilosort agreement. [[ResearchGate 389645842](https://www.researchgate.net/publication/389645842); [PMC12680097](https://pmc.ncbi.nlm.nih.gov/articles/PMC12680097/)]
- **Karkare 2013** — fabricated 65 nm, measured; 2.45 mm², ~75% accuracy. [[IEEE 6532404](https://ieeexplore.ieee.org/document/6532404/)]
- **Hao 2021** — fabricated 180 nm SOI SoC, measured; 93.2% on synthetic data. [[IEEE 9417633](https://ieeexplore.ieee.org/document/9417633/)]
- **2018 Osort hippocampal chip** — fabricated 40 nm, measured; 0.0175 mm²/ch. [[ScienceDirect S0165027018303273](https://www.sciencedirect.com/science/article/abs/pii/S0165027018303273)]
- **Luan 2018** — fabricated FPGA+MCU+Intan **system**, deployed 24 h untethered **in a freely-moving primate** (real system-integration robustness, not just a chip). [[bioRxiv 186627v2](https://www.biorxiv.org/content/10.1101/186627v2.full)]
- *(Possible Tier A, verify):* **96-ch Neural Spike Processor**, 180 nm ASIC — detection + sorting (constrained-Bayesian decision tree, ≤4 clusters/ch) + partial intention decoding on-chip; stated as fabricated. [[arXiv 2009.05210](https://arxiv.org/pdf/2009.05210)]

### Tier B — Layout / synthesis only (real design, **not** proven silicon — do not cite as "built")
- **Shaeri & Sodagar 2020 (Nature Comms)** — 512-ch ASIC **layout**, validated on pre-recorded data; ~88% accuracy, 905.9 µW. High impact ≠ measured hardware. [[Nature](https://www.nature.com/articles/s41467-020-17031-9); [PMC7327047](https://pmc.ncbi.nlm.nih.gov/articles/PMC7327047/)]
- **Strydis et al. 2024** (Purkinje spike-type classifier) — **synthesized** 45 nm (VHDL/Cadence/Vivado), **never fabricated**, never in an animal; stores output to on-board STT-RAM for **offline** retrieval; ternary spike-*type* (simple/complex/false-positive), *not* single-unit identity. [[arXiv 2311.04808](https://arxiv.org/pdf/2311.04808)]

### Tier C — Real wireless / freely-moving in vivo, but sorting is **offline** (not on-device)
- **Tasneem et al. 2023**, duty-cycled wireless optogenetic headstage — wireless, validated in freely-moving rats (VTA); but "**offline spike detection and sorting in LabVIEW**" after transmission. The headstage only amplifies (45.7 dB) + digitizes + transmits. [[NSF PAR 10488877](https://par.nsf.gov/biblio/10488877-multichannel-electrophysiological-recording-spike-detection-sorting-duty-cycled-wireless-optogenetic-headstage)]
- **Yoon et al. 2022**, 16-ch BLE wireless probe — real in-vivo wireless, but **threshold-crossing only**, no single-unit sorting. [Nat. Commun. 2022, doi:10.1038/s41467-022-33296-8]
- *(Watch — closest on the wireless+freely-moving axis, verify):* a **2026 bioRxiv** bidirectional neuromorphic wireless headstage (32-ch, closed-loop optogenetics) — but appears to do neuromorphic *decoding*, not single-unit sorting; **preprint**. [[bioRxiv 714179](https://www.biorxiv.org/content/10.64898/2026.03.25.714179v1.full)]

---

## 4. Novelty verdict for the planned thesis

Target: on-device real-time single-unit **classification** on a **commercial BLE SoC** (Nordic
nRF54LM20B + Axon NPU), mouse headstage (~10 ms, ~30 mW), applied to classifying single-unit
**spike content within sharp-wave ripples** to distinguish healthy vs. Alzheimer's-corrupted
ripples.

**Already done by others (de-risked, not novel):**
- On-device real-time single-unit sorting *in silicon* is well-established. [Tier A above]
- The **power budget is generous** — genuine sorters run at **75–76 µW, ~400× under 30 mW**.
  [Karkare 75 µW [[6532404](https://ieeexplore.ieee.org/document/6532404/)]; SOM 76 µW [[PMC12680097](https://pmc.ncbi.nlm.nih.gov/articles/PMC12680097/)]] — **but see caveat #1.**
- Untethered on-device template-matching classification exists (Luan — primate + SD-card). [[186627v2](https://www.biorxiv.org/content/10.1101/186627v2.full)]

**Close / partially shown:**
- Real-time per-spike classification against templates (Luan two-phase; Nature Comms comparator
  window-discrimination). [[186627v2](https://www.biorxiv.org/content/10.1101/186627v2.full); [Nature](https://www.nature.com/articles/s41467-020-17031-9)]

**Genuinely open (your novelty):**
1. **On a commercial BLE SoC/NPU** rather than a custom ASIC/FPGA — *no such demonstration
   found*; commercial-BLE prior art is threshold-only (Yoon 2022).
2. **The full triad** — on-device real-time single-unit + wireless + freely-moving rodent —
   *never jointly achieved*. [Synthesis]
3. **The application** — classifying single-unit spike *content within SWRs* to discriminate
   healthy vs. AD-corrupted ripples — *unaddressed by any verified prior system* (all target
   generic sorting or spike-type, none disease-state ripple discrimination). [Synthesis]

**Strategic read:** the novelty is *not* the hardware feat (on-chip sorting done; low power
done). It concentrates in the **commercial-SoC accessibility angle**, the **full
wireless/freely-moving integration**, and — strongest and most scientific — the **SWR-in-AD
application**. Lean there.

---

## 5. Caveats (honest limits of this review)

1. **Biggest technical risk — the power budget may be optimistic.** The 75 µW-class figures are
   **DSP-core only**. Karkare's 75 µW **excludes the AFE, ADC, and radio**
   [[6532404](https://ieeexplore.ieee.org/document/6532404/)]. Your ~30 mW must cover
   **amplifier + ADC + BLE radio + classifier** — a full-headstage accounting is a different,
   un-computed number. **This is the likeliest thing to bite; do a full power budget.**
2. **Prior-art only.** This sweep did **not** verify the nRF54LM20B / Axon NPU specs, the
   10 ms / 30 mW realism, or the SWR-healthy-vs-AD neuroscience. Those need separate checks.
3. **Accuracy numbers (88%, 93.2%, ~75%) are on synthetic/benchmark data**, not freely-moving
   in-vivo — they overstate expected real-world single-unit performance. [Synthesis]
4. **Layout/synthesis ≠ silicon.** Nature Comms 512-ch and Strydis are *not* taped-out. Don't
   cite them as proven hardware. [[Nature](https://www.nature.com/articles/s41467-020-17031-9); [arXiv 2311.04808](https://arxiv.org/pdf/2311.04808)]
5. **Fast-moving frontier.** The strongest sorter (1024-ch SOM) is a **2025** result; expect the
   on-device-sorting frontier to advance during the thesis. Monitor ISSCC / JSSC / TBioCAS.
6. **One 2-1 verification split:** whether Nature Comms 2020 counts as "on-device unsupervised
   sorting." Resolved here as a **hybrid** (on-device = comparator window-discrimination;
   sorting intelligence = offline external module).

## 6. Reference corrections (fix before citing)

- The two starting references "Nature Comms 2020" and "the 512-channel ~88% online sorter" are
  **the same paper** (Shaeri & Sodagar).
- **"Valencia & Alimohammad 2021 (binarized NN spike sorting)"** did **not** survive verification
  as attributed — re-check before relying on it. [Candidate source: [Valencia PDF](https://amir.sdsu.edu/Valencia20Neural.pdf)]

## 7. Full source list (verified primaries)

- Shaeri & Sodagar 2020, *Nat. Commun.* — [nature.com/articles/s41467-020-17031-9](https://www.nature.com/articles/s41467-020-17031-9) · [PMC7327047](https://pmc.ncbi.nlm.nih.gov/articles/PMC7327047/)
- Akhoundi et al. 2025, 1024-ch SOM chip, *ISSCC/JSSC* — [ResearchGate 389645842](https://www.researchgate.net/publication/389645842) · [PMC12680097](https://pmc.ncbi.nlm.nih.gov/articles/PMC12680097/)
- Luan et al. 2018, *J. Neural Eng.* — [bioRxiv 186627v2](https://www.biorxiv.org/content/10.1101/186627v2.full) (PMID 29623905)
- Karkare et al. 2013, *IEEE JSSC* 48(9):2230-2238 — [IEEE 6532404](https://ieeexplore.ieee.org/document/6532404/)
- Hao et al. 2021, *IEEE TBioCAS* 15(2):351-364 — [IEEE 9417633](https://ieeexplore.ieee.org/document/9417633/)
- 2018 hippocampal-prosthesis Osort chip, *J. Neurosci. Methods* — [ScienceDirect S0165027018303273](https://www.sciencedirect.com/science/article/abs/pii/S0165027018303273) (PMID 30339881)
- Strydis et al. 2024, *ACM Computing Frontiers* — [arXiv 2311.04808](https://arxiv.org/pdf/2311.04808)
- Tasneem et al. 2023, duty-cycled wireless optogenetic headstage, *IEEE Sensors J.* — [NSF PAR 10488877](https://par.nsf.gov/biblio/10488877-multichannel-electrophysiological-recording-spike-detection-sorting-duty-cycled-wireless-optogenetic-headstage)
- 96-ch Neural Spike Processor ASIC — [arXiv 2009.05210](https://arxiv.org/pdf/2009.05210)
- 2026 bidirectional neuromorphic wireless headstage (preprint) — [bioRxiv 714179](https://www.biorxiv.org/content/10.64898/2026.03.25.714179v1.full)
- Fully-wireless 6-ch recorder + stim (no on-device sorting; context) — [IEEE 10978891](https://ieeexplore.ieee.org/document/10978891/)
- On-implant sorting survey (context) — [Springer s42234-025-00177-6](https://link.springer.com/article/10.1186/s42234-025-00177-6)
- Spike-sorting SoC survey (context) — [arXiv 2405.10780](https://arxiv.org/pdf/2405.10780)
- Valencia & Alimohammad (FPGA/BNN; attribution unverified) — [Valencia PDF](https://amir.sdsu.edu/Valencia20Neural.pdf)
- From the thesis proposal (not re-fetched here): Yoon et al. 2022, *Nat. Commun.* doi:10.1038/s41467-022-33296-8; Zhang et al. 2023, *J. Neural Eng.* doi:10.1088/1741-2552/acc7cc; Zhu/Shin/Shoaran 2021, *IEEE TBioCAS* doi:10.1109/TBCAS.2021.3112756
