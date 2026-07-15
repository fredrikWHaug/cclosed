# cclosed — wireless electrophysiology on the nRF54LM20B

Bachelor's-thesis work on running "useful" neural-data processing **on-chip**
for a wireless electrophysiology system: take raw extracellular voltage from a
mesh probe, classify spikes on the Nordic nRF54LM20B, and stream the result over
BLE instead of raw waveforms. Two workstreams live here — the **spike
classifiers** (train offline, deploy to the board) and the **SPI link** between
the nRF54 and the Intan acquisition chip.

## Layout

```
dataset/                 build the training set from sorted recordings
  build_dataset.py         firings.npz + filtered recording -> dataset.npz
                           (snippets: 8 channels x 40 samples @ 10 kHz)

model/                   train / compare / export the classifiers (PyTorch)
  train.py                 train the CNN, save checkpoints/shank0_best.pt
  compare_models.py        logreg vs CNN vs ResNet on one identical split
  time_split_test.py       chronological split -> overfitting check
  evaluate.py              per-unit evaluation
  export_to_c.py           CNN     -> firmware/classifiers/cnn/*.h
  export_logreg_to_c.py    logreg  -> firmware/classifiers/logreg/*.h
  export_resnet_to_c.py    ResNet  -> firmware/classifiers/resnet/*.h
  checkpoints/             trained weights (*.pt)

firmware/                Zephyr / nRF Connect SDK apps (board: nrf54lm20b/cpuapp)
  classifiers/
    nn.h                   shared bare-metal inference primitives (all models)
    cnn/                   1D CNN spike classifier   (deployed, 44 ms)
    logreg/                logistic-regression classifier
    resnet/                small ResNet classifier   (the heavy ceiling)
  spi/
    master/                SPI master (nRF-as-master; stand-in for the real link)
    slave/                 SPI slave  (stand-in for the Intan)

documentation/
  model-comparison.md      compression-vs-fidelity results across the 3 models
  lessons-learned.md       the two-board SPI debugging journey
```

Each firmware app is three files: `prj.conf` (features to compile in),
`boards/*.overlay` (pins/peripherals), and `src/main.c` (the program). Build
artifacts (`build/`), the virtualenv, and large data (`*.npz`) are gitignored.

## Quick start

```bash
python -m venv venv && source venv/bin/activate && pip install torch numpy
python model/compare_models.py                      # offline accuracy table

# build + flash a classifier (needs the nRF Connect SDK / west on PATH)
west build --build-dir firmware/classifiers/cnn/build --pristine \
    --board nrf54lm20dk/nrf54lm20b/cpuapp firmware/classifiers/cnn
# then flash and open serial @ 115200 8N1; reset to see the prediction + timing
```

## Status
- **Classifiers:** logreg / CNN / ResNet all train (~98%), export to C, and build
  for the board. CNN verified on-device (44 ms). See `documentation/model-comparison.md`.
- **SPI:** two-DK master↔slave link working and documented. See
  `documentation/lessons-learned.md`.
