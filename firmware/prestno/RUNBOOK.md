# Runbook, Experiment 1: sample rate, one channel

Hand off the FB128, SYNC mode, nothing else touched. Each block is one build: set the two knobs in `src/main.c`,
build, flash the headstage, reset the central, wait for `subscribed`, then run the lines. For `RAW_STREAM 0`
blocks also copy three `[prestno]` status lines. Tick each capture when `log.py` reports it written.

## Pass 1, runs a and b, rates going down

### build 1: `CH_RATE_HZ 30000u`, `RAW_STREAM 1`

- [x] `python log.py data/raw_1ch_30000_a.bin 60`
- [x] `python log.py data/raw_1ch_30000_b.bin 60`  (first attempt was empty, link was down; redone)

### build 2: `CH_RATE_HZ 30000u`, `RAW_STREAM 0`

- [x] `python log.py data/ev_1ch_30000_a.bin 60`
- [x] `python log.py data/ev_1ch_30000_b.bin 60`

### build 3: `CH_RATE_HZ 20000u`, `RAW_STREAM 1`

- [x] `python log.py data/raw_1ch_20000_a.bin 60`
- [x] `python log.py data/raw_1ch_20000_b.bin 60`

### build 4: `CH_RATE_HZ 20000u`, `RAW_STREAM 0`

- [x] `python log.py data/ev_1ch_20000_a.bin 60`
- [x] `python log.py data/ev_1ch_20000_b.bin 60`  (recorded on a second pass)

### build 5: `CH_RATE_HZ 15000u`, `RAW_STREAM 1`

- [x] `python log.py data/raw_1ch_15000_a.bin 60`
- [x] `python log.py data/raw_1ch_15000_b.bin 60`

### build 6: `CH_RATE_HZ 15000u`, `RAW_STREAM 0`

- [x] `python log.py data/ev_1ch_15000_a.bin 60`
- [x] `python log.py data/ev_1ch_15000_b.bin 60`

### build 7: `CH_RATE_HZ 10000u`, `RAW_STREAM 1`

- [x] `python log.py data/raw_1ch_10000_a.bin 60`
- [x] `python log.py data/raw_1ch_10000_b.bin 60`

### build 8: `CH_RATE_HZ 10000u`, `RAW_STREAM 0`

- [x] `python log.py data/ev_1ch_10000_a.bin 60`
- [x] `python log.py data/ev_1ch_10000_b.bin 60`

### build 9: `CH_RATE_HZ 6000u`, `RAW_STREAM 1`

- [x] `python log.py data/raw_1ch_6000_a.bin 60`
- [x] `python log.py data/raw_1ch_6000_b.bin 60`

### build 10: `CH_RATE_HZ 6000u`, `RAW_STREAM 0`

- [x] `python log.py data/ev_1ch_6000_a.bin 60`
- [x] `python log.py data/ev_1ch_6000_b.bin 60`

## Pass 2, runs c and d, rates going back up

### build 11: `CH_RATE_HZ 6000u`, `RAW_STREAM 1`

- [ ] `python log.py data/raw_1ch_6000_c.bin 60`
- [ ] `python log.py data/raw_1ch_6000_d.bin 60`

### build 12: `CH_RATE_HZ 6000u`, `RAW_STREAM 0`

- [ ] `python log.py data/ev_1ch_6000_c.bin 60`
- [ ] `python log.py data/ev_1ch_6000_d.bin 60`

### build 13: `CH_RATE_HZ 10000u`, `RAW_STREAM 1`

- [ ] `python log.py data/raw_1ch_10000_c.bin 60`
- [ ] `python log.py data/raw_1ch_10000_d.bin 60`

### build 14: `CH_RATE_HZ 10000u`, `RAW_STREAM 0`

- [ ] `python log.py data/ev_1ch_10000_c.bin 60`
- [ ] `python log.py data/ev_1ch_10000_d.bin 60`

### build 15: `CH_RATE_HZ 15000u`, `RAW_STREAM 1`

- [ ] `python log.py data/raw_1ch_15000_c.bin 60`
- [ ] `python log.py data/raw_1ch_15000_d.bin 60`

### build 16: `CH_RATE_HZ 15000u`, `RAW_STREAM 0`

- [ ] `python log.py data/ev_1ch_15000_c.bin 60`
- [ ] `python log.py data/ev_1ch_15000_d.bin 60`

### build 17: `CH_RATE_HZ 20000u`, `RAW_STREAM 1`

- [ ] `python log.py data/raw_1ch_20000_c.bin 60`
- [ ] `python log.py data/raw_1ch_20000_d.bin 60`

### build 18: `CH_RATE_HZ 20000u`, `RAW_STREAM 0`

- [ ] `python log.py data/ev_1ch_20000_c.bin 60`
- [ ] `python log.py data/ev_1ch_20000_d.bin 60`

### build 19: `CH_RATE_HZ 30000u`, `RAW_STREAM 1`

- [ ] `python log.py data/raw_1ch_30000_c.bin 60`
- [ ] `python log.py data/raw_1ch_30000_d.bin 60`

### build 20: `CH_RATE_HZ 30000u`, `RAW_STREAM 0`

- [ ] `python log.py data/ev_1ch_30000_c.bin 60`
- [ ] `python log.py data/ev_1ch_30000_d.bin 60`

## Then

- [ ] `python sweep.py`
