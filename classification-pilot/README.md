# classification-pilot

On-chip waveform classification over the real signal path. The nRF54 samples
ch0 of the real Intan, classifies each window **on-chip** by template matching
(normalized cross-correlation), and sends the **class id + timestamp + window**
over BLE. The laptop just plots the window under its live label.

This is a deliberate rehearsal of real action-potential classification: it uses
**time-domain waveform shape only** (no frequency/harmonic content), because
that is what transfers to spikes. See `../waveform_classification_backrgound.md`
for the method background.

## Signal path

```
function generator      Intan RHD2164       nRF54LM20B                     laptop
(sine/square/triangle,  amplify + digitize  SPI master: sample ch0,        classify_plot.py
 ~1 mV, fixed freq) ──► ch0; SPI slave  ──► window, cross-correlate    ──► plot window +
                                            vs. templates, pick best         label + timestamp
                                            │  BLE notify:
                                            │  [seq][class][ts_ms][score][window]
```

## How classification works

Each 100-sample window is compared against one z-scored **template** per class.
Every template is slid across the window (all lags); at each lag we compute the
Pearson correlation *r* between the window segment and the template. The best
lag's *r* is that class's score; the highest-scoring class wins. Sliding over
all lags is what makes it **phase-invariant** (the window needn't start at a
fixed point in the cycle); z-scoring makes it **amplitude/offset-invariant**.
Best *r* below `SCORE_MIN` (0.5) → reported as **uncertain**.

Config lives at the top of `master/src/main.c` (`WIN_LEN`, `SCORE_MIN`,
`SAMPLE_RATE_HZ`) and `record_templates.py` (`F0`, `TEMPLATE_LEN`).

## Workflow

Firmware is built/flashed by Fredrik via the VS Code Nordic extension. Python
runs from the repo venv (`./venv/bin/python`).

1. **Record templates** (needs the raw-stream firmware first):
   - Flash `firmware/signal-path-intan/master` (advertises `cclosed-sigpath`).
   - `./venv/bin/python classification-pilot/record_templates.py`
     — for each class it prompts you to set the FG, captures ~3 s, averages
     many aligned cycles into a clean template, and writes
     `master/src/templates.h`.
   - No hardware handy? `record_templates.py --analytic` writes ideal
     mathematical templates so the firmware still builds and runs (a committed
     analytic placeholder already ships in `templates.h`).
2. **Flash the classifier**: `classification-pilot/master`
   (advertises `cclosed-classify`).
3. **Watch it classify**: `./venv/bin/python classification-pilot/classify_plot.py`
   — live plot of the incoming window, its label (colored), the match score *r*,
   and the on-chip timestamp.

## Fixed frequency

Templates are fixed-length, so they only match their own period: keep the
function generator at the same fundamental (`F0`, default 500 Hz) for recording
and classifying. At 10 kHz sampling that is 20 samples/cycle — enough to
resolve sine vs. triangle vs. square shape. Changing `F0` means re-recording
templates.

## Verified

The exact on-chip `classify()` formula was simulated in Python against noisy,
random-phase, random-amplitude synthetic waves: 97–100% correct, mean best-*r*
≈ 0.98, only occasional sine↔triangle confusion (the two closest shapes).
