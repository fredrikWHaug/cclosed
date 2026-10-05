/*
 * ap_dac.ino — play an action-potential-shaped waveform on the 4-bit R-2R DAC.
 *
 * Hardware: unchanged from the es152 lab setup. Pins 0..3 drive the ladder's
 * FET switches (bit0 = LSB on pin 0 ... bit3 = MSB on pin 3), inverted gates.
 * Probe vout_dac (output of U2) on the scope.
 *
 * Pin 13 fires a 3.3 V sync pulse at the onset of every spike — clip the
 * scope's CH2 (or EXT trigger) to it and trigger on its rising edge for a
 * rock-solid stationary display regardless of noise on the analog output.
 *
 * Scope settings: trigger CH2 rising edge (or CH4 falling edge on the analog
 * trough), ~1 ms/div, ~500 mV/div on the DAC output.
 */

/* Extracellular AP template: sharp negative trough, slower positive
 * overshoot (difference of Gaussians), quantized to the full 0..15 range.
 * Baseline = 10. 64 samples; at SAMPLE_US = 100 the spike spans ~6.4 ms —
 * slower than a real AP, deliberately: each step dwarfs digitalWrite skew
 * and timing jitter, so the shape is robust. Shrink SAMPLE_US to speed up. */
const uint8_t SPIKE[] = {
  10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,  9,  9,  7,  6,  4,
   2,  0,  0,  1,  3,  5,  8, 10, 12, 13, 14, 14, 15, 15, 15, 15,
  15, 15, 14, 14, 13, 13, 13, 12, 12, 11, 11, 11, 11, 10, 10, 10,
  10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
};
const int      N_SPIKE     = sizeof(SPIKE);
const uint16_t SAMPLE_US   = 100;   /* per-sample dwell: 10 kS/s playback   */
const uint8_t  BASELINE    = 10;    /* resting code between spikes          */
const uint16_t GAP_MIN_MS  = 20;    /* irregular inter-spike interval,      */
const uint16_t GAP_MAX_MS  = 80;    /* like a real neuron                   */

/* Unchanged from the lab code: write one 4-bit code to the ladder.
 * Gates are inverted because a LOW gate passes the high rail. */
void write_dac(int val) {
  digitalWrite(0, 1 - ((val >> 0) & 0x1));
  digitalWrite(1, 1 - ((val >> 1) & 0x1));
  digitalWrite(2, 1 - ((val >> 2) & 0x1));
  digitalWrite(3, 1 - ((val >> 3) & 0x1));
}

void setup() {
  pinMode(0, OUTPUT);
  pinMode(1, OUTPUT);
  pinMode(2, OUTPUT);
  pinMode(3, OUTPUT);
  pinMode(13, OUTPUT);              /* scope sync pulse */

  write_dac(BASELINE);
  randomSeed(analogRead(A0));       /* noise-seeded spike timing */
}

void loop() {
  digitalWrite(13, HIGH);           /* sync: spike starts now */

  for (int i = 0; i < N_SPIKE; i++) {
    write_dac(SPIKE[i]);
    delayMicroseconds(SAMPLE_US);
  }

  digitalWrite(13, LOW);
  write_dac(BASELINE);
  delay(random(GAP_MIN_MS, GAP_MAX_MS));
}
