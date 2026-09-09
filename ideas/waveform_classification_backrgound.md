# Waveform Classification — Background

> Research context for the sine/square/triangle classifier rehearsal
> (`classification.py`) and the deferred on-chip spike-classification thesis
> goal. Compiled 2026-08-17 via a multi-source research pass (deep-research
> workflow + a targeted faculty-search agent), claims adversarially verified
> against primary sources.

## 1. The field: two camps, one real tension

General time-series / raw-waveform classification with ML splits into two
approaches that have been competing since ~2019:

- **End-to-end deep learning on raw signal** — CNNs (ResNet, and especially
  **InceptionTime**, a cascaded-Inception 1D-CNN) that learn features
  directly from raw time series, no hand engineering. The pitch: eliminate
  manual feature design entirely — the network learns whatever
  discriminative structure exists in the raw window.
- **Fast kernel/feature-transform methods** — **ROCKET** (10,000 random 1D
  convolutional kernels → 20,000 summary features, max value + proportion-of-
  positive-values per kernel → linear classifier) and its much faster
  reformulation **MiniRocket** (up to 75× faster, essentially the same
  accuracy). Not hand-engineered in the classical sense (kernels are random,
  not designed) but not end-to-end learned either — a genuine third category
  between raw deep learning and classic feature engineering.

**The honest empirical finding:** an independent benchmark ("Bake off redux,"
Middlehurst et al.) found the leading deep model (InceptionTime) merely
*competitive with*, not superior to, ROCKET/HIVE-COTE on the standard
UCR/UEA benchmark archives — partly because those archives are too small
(median ~217 training examples per dataset) for deep learning's usual
data-hungry advantage to show up. A comprehensive 2023/2024 survey (Foumani
et al., arXiv:2302.02515 / ACM Computing Surveys) maps the taxonomy: MLPs,
CNNs, RNNs, GNNs, attention/transformer models, self-supervised learning,
and augmentation/transfer learning.

**Transformers for time series get more skepticism than hype.** A
widely-cited paper (Zeng, Chen, Zhang, Xu, AAAI 2023, arXiv:2205.13504)
showed a trivial one-layer linear model (DLinear) beats contemporary
Transformer forecasters on most long-horizon benchmarks — a caution against
reaching for attention-heavy architectures by default.

**On embedded/MCU deployment** (directly relevant to the eventual nRF54
target): one paper found 1D-CNNs match or beat LSTMs on microcontroller-class
hardware — comparable or higher accuracy (~95% vs ~89%) while using ~35%
less RAM and ~25% less flash. This is a concrete data point for how to shrink
whatever architecture wins on the laptop before porting it.

## 2. The raw-vs-engineered-features debate, applied to this project

The literature validates the plan already in motion for `classification.py`:
train on the **raw time-domain window** (Option A), not hand-picked
scalar features like crest factor (Option B). That's where the field's
energy and best results concentrate, and it's the version that actually
rehearses what a real spike classifier will have to do — learn shape from
raw samples, including tolerating unknown phase.

If a simple raw-window classifier (e.g. logistic regression) underperforms,
the well-precedented next step **before** reaching for a bigger neural net is
a **ROCKET-style random-kernel transform** — cheap, robust, and a legitimate
middle ground supported by strong primary-source results, not a hand-wavy
guess.

## 3. What actually counts as "a feature" here

The methods above differ not just in *architecture* but in **where the
boundary between "feature" and "model" sits** — this is a sliding scale, not
a binary:

| | What counts as "the feature"? | Who decided it? |
|---|---|---|
| **Hand-engineered** (e.g. crest factor = peak ÷ RMS) | One computed summary number, from a formula chosen using domain knowledge of what differs between shapes | A human |
| **ROCKET / MiniRocket** | Two numbers *per random kernel* — max response and % of the window where it fired — from thousands of random small pattern-detectors | Nobody picks the patterns (random); the *aggregation rule* (max, %-positive) is fixed by the method [^rocket] |
| **Raw window, end-to-end** (our plan for `classification.py`) | Literally the raw amplitude value at every sample point in the window (e.g. 80–120 numbers), z-scored | Nobody — the classifier decides what to do with them during training |

For the raw-window approach specifically, there is **no separate feature-
extraction step at all** — the thing fed to the model *is* the signal, and
"eliminating manual feature engineering" is exactly the framing the survey
literature uses for this end-to-end approach [^eliminate1] [^eliminate2].

**What a raw-window classifier plausibly keys on, mechanistically:** a
logistic regression over raw samples learns one weight per sample position —
it discovers *which* sample points, and combinations of them, separate the
classes, purely from labeled data. A small 1D-CNN is more structured: each
convolutional filter has a small receptive field (a handful of adjacent
samples) and slides across the window, and filters of this kind are known to
learn **discriminative local subsequence patterns — functionally similar to
"shapelets"** in the time-series literature, though a caveat is worth
stating precisely: one study found that *unregularized* CNN filters often
learn patterns that don't correspond to any real, human-recognizable piece
of an actual input series, even when they're discriminative [^shapelet].
That's a **softer claim than "filters become edge detectors,"** which is
well-supported for *image* CNNs [^zeiler] but which I could not find a
verified time-series-specific source for — flagging that so the analogy
doesn't get overstated.

[^rocket]: Dempster, Petitjean, Webb, "ROCKET: Exceptionally fast and accurate time series classification using random convolutional kernels," arXiv:1910.13051. Verified quotes: "For 10,000 kernels (the default), Rocket produces 20,000 features" and each kernel contributes "the maximum value... [and] the proportion of positive values."
[^eliminate1]: Foumani, Miller, Tan, Webb, Forestier, Salehi, "Deep Learning for Time Series Classification and Extrinsic Regression: A Current Survey," arXiv:2302.02515 / ACM Computing Surveys 56(9). Verified quote: "Deep learning can autonomously learn informative features from raw data, eliminating the need for manual feature engineering."
[^eliminate2]: Ismail Fawaz, Forestier, Weber, Idoumghar, Muller, "Deep learning for time series classification: a review," Data Mining and Knowledge Discovery 33 (2019), arXiv:1809.04356.
[^shapelet]: Wang, Yan, Oates, "Learning Interpretable Shapelets for Time Series Classification through Adversarial Regularization," arXiv:1906.00917. Finding: standard (unregularized) 1D-CNN filters do learn discriminative local sliding-window patterns functionally like shapelets, but these are "often different from actual pieces of a real series" without added regularization — i.e. they act as local pattern-matchers, not necessarily human-recognizable shapes.
[^zeiler]: Zeiler & Fergus, "Visualizing and Understanding Convolutional Networks," ECCV 2014, arXiv:1311.2901. Verified quote (image-domain CNNs, not time series): "Layer 2 responds to corners and other edge/color conjunctions," with deeper layers showing "compositionality, increasing invariance and class discrimination as we ascend the layers." Note: this paper grounds the *image*-CNN edge-detector intuition only — I could not verify an equivalent filter-level claim specifically for 1D time-series CNNs; see [^shapelet] for the closest, softer, time-series-specific finding.

## 4. Key methods, concretely

| Method | What it does | Result |
|---|---|---|
| **InceptionTime** | Cascaded-Inception 1D-CNN, end-to-end on raw signal | Accuracy on par with HIVE-COTE, ~100× faster to train |
| **ROCKET** | 10,000 random conv kernels → 20,000 features → linear classifier | Competitive with (statistically indistinguishable from) HIVE-COTE, TS-CHIEF, InceptionTime |
| **MiniRocket** | Near-deterministic reformulation of ROCKET | Up to 75× faster than ROCKET, same accuracy |
| **1D-CNN on MCU** | Same CNN family, sized down | ~95% acc vs ~89% for LSTM, using less RAM/flash — the embedded-deployment analogue |

## 5. Caveats on this research pass

- **Time-sensitivity:** the empirical leaderboard (ROCKET vs. InceptionTime
  vs. newer transformer variants) moves fast. The comparisons above are
  accurate as of their cited 2019–2024 papers; treat exact rankings as
  historically situated, not "current SOTA."
- **Source concentration:** most claims trace back to a small cluster of
  related papers (Foumani et al. survey, Fawaz et al. 2019 review, the
  Dempster/Schmidt/Webb ROCKET/MiniRocket papers) — strong within-paper
  verification, less independent triangulation across unrelated groups.
- **Not covered in depth:** pure transformer architectures for time series
  (PatchTST, TimesNet) beyond the taxonomy level, self-supervised
  pretraining, and MCU-specific quantization/latency benchmarks sized for
  a window as short as this project's — these are open threads if this
  ever needs a deeper second pass.

## 6. Harvard / MIT faculty — general time-series ML (not neuro/spike-sorting-specific)

Screened explicitly to exclude people whose center of gravity is
neuroscience, spike sorting, or clinical applications — that's a deliberate
exclusion, not an oversight, since the question was about the general ML
subfield.

1. **Devavrat Shah** — MIT EECS (Andrew & Erna Viterbi Professor), directs the
   MIT Statistics and Data Science Center; LIDS/IDSS. Matrix-estimation /
   nearest-neighbor theory for general time-series prediction (e.g. "Time
   Series Analysis via Matrix Estimation," tspDB). Strongest, most direct
   match. — https://devavrat.mit.edu/
2. **Munther A. Dahleh** — MIT EECS (William A. Coolidge Professor), founding
   director of MIT IDSS; LIDS. Learning linear/nonlinear dynamical systems
   and mixtures of dynamical systems from trajectory data — methodologically
   close to learning structure from raw signal windows. —
   https://dahleh.lids.mit.edu/
3. **Yoon Kim** — MIT EECS/CSAIL, MIT-IBM Watson AI Lab. General
   sequence-model architectures (state-space models, efficient/linear
   attention) — domain-general methods, mostly demonstrated on text so a
   moderate match on "waveform" specifically, strong on "sequence models." —
   https://www.eecs.mit.edu/people/yoon-kim/
4. **Pavlos Protopapas** — Harvard IACS, Scientific Program Director /
   Lecturer (note: not tenure-track professor rank). Deep learning for
   time-series classification directly (astronomical time series, GAN-based
   time-series augmentation), non-neuro. Teaches Harvard's CS109 — the most
   realistically approachable option for an undergraduate. —
   https://iacs.seas.harvard.edu/people/pavlos-protopapas

**Considered and excluded** (verified real but off-target for this specific
ask): Sasha Rakhlin (MIT, theory of online/sequential prediction — abstract,
not waveform methods); David Alvarez-Melis (Harvard SEAS — optimal
transport/data-centric ML, not time series); Sham Kakade (Harvard — current
focus is LLM/foundation-model theory); Kalyan Veeramachaneni (MIT LIDS —
excellent time-series-anomaly-detection work, but Principal Research
Scientist, not faculty); Demba Ba, Cengiz Pehlevan, Finale Doshi-Velez
(Harvard SEAS/Kempner — real time-series people, but center of gravity is
neuro/spike-sorting/clinical, the exact thing this search was scoped to
exclude).

**Bottom line:** MIT has 2–3 clean matches (Shah, Dahleh, Kim); Harvard's
best fit is IACS's Protopapas, with the title caveat. No Harvard
tenure-track professor was found whose primary research centers on general
time-series/waveform ML rather than neuroscience or a clinical application —
worth a second pass into Harvard Applied Math or Statistics specifically if
this becomes a priority.
