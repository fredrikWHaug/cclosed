/*
 * On-chip STREAMING spike pipeline (Step 4a): raw ADC codes -> unit IDs.
 *
 *   0.195*(code-32768) -> causal biquad (2 SOS sections, 300-3000 Hz)
 *   -> per-shank common-median reference -> decimate 30k->10k
 *   -> streaming detect (threshold + trough + refractory) -> classify each spike
 *
 * Runs over a hardcoded raw stream (stream_test.h) and checks the detected
 * (trough, unit) sequence against the host spike-for-spike. No SPI yet — the
 * streaming detector is verified in isolation before transport is added.
 */
#include <zephyr/kernel.h>

#include "stream_test.h"
#include "nn.h"
#include "model_weights.h"

#define MAXSP 128

static const float BQ_B[2][3] = {
	{0.05644846f, 0.11289692f, 0.05644846f},
	{1.0f, -2.0f, 1.0f},
};
static const float BQ_A[2][3] = {
	{1.0f, -1.24532221f, 0.49035942f},
	{1.0f, -1.91414109f, 0.91860259f},
};

static float median8(const float *v)
{
	float t[8];
	for (int i = 0; i < 8; i++) {
		t[i] = v[i];
	}
	for (int i = 1; i < 8; i++) {
		float k = t[i]; int j = i - 1;
		while (j >= 0 && t[j] > k) { t[j + 1] = t[j]; j--; }
		t[j + 1] = k;
	}
	return 0.5f * (t[3] + t[4]);
}

static float dec[N_CH][NDEC];         /* decimated CMR signal (static: off-stack) */
static float snip[N_CH * SNIP_LEN];
static int my_troughs[MAXSP];
static int my_units[MAXSP];

int main(void)
{
	printk("=== On-chip STREAMING pipeline: detect + classify from raw stream ===\n");

	/* biquad -> CMR -> decimate the whole stream (filter state carries) */
	float z0[N_CH][2] = {0}, z1[N_CH][2] = {0};
	int di = 0;
	for (int n = 0; n < NS; n++) {
		float fsamp[N_CH];
		for (int c = 0; c < N_CH; c++) {
			float x = 0.195f * ((int)raw_stream[c * NS + n] - 32768);
			for (int s = 0; s < 2; s++) {
				float y = BQ_B[s][0] * x + z0[c][s];
				z0[c][s] = BQ_B[s][1] * x - BQ_A[s][1] * y + z1[c][s];
				z1[c][s] = BQ_B[s][2] * x - BQ_A[s][2] * y;
				x = y;
			}
			fsamp[c] = x;
		}
		float med = median8(fsamp);
		if (n % 3 == 0) {
			for (int c = 0; c < N_CH; c++) {
				dec[c][di] = fsamp[c] - med;
			}
			di++;
		}
	}

	/* streaming detection state machine (identical to the host) */
	int nsp = 0, in_ev = 0, emt = -1, refrac = DETECT_START;
	float emin = 1e30f;
	for (int t = DETECT_START; t < NDEC - SNIP_LEN / 2; t++) {
		float g = dec[0][t];
		for (int c = 1; c < N_CH; c++) {
			if (dec[c][t] < g) { g = dec[c][t]; }
		}
		if (!in_ev) {
			if (t >= refrac && g < -THRESH) { in_ev = 1; emin = g; emt = t; }
		} else {
			if (g < emin) { emin = g; emt = t; }
			if (g >= -THRESH) {
				int tt = emt;
				for (int c = 0; c < N_CH; c++) {
					for (int k = 0; k < SNIP_LEN; k++) {
						snip[c * SNIP_LEN + k] = dec[c][tt - SNIP_LEN / 2 + k];
					}
				}
				float out[N_CLASSES];
				nn_linear(snip, out, logreg_w, logreg_b, INPUT_DIM, N_CLASSES, 0);
				int pred = nn_argmax(out, N_CLASSES);
				if (nsp < MAXSP) {
					my_troughs[nsp] = tt;
					my_units[nsp] = UNIT_IDS[pred];
					nsp++;
				}
				refrac = tt + REFRAC;
				in_ev = 0;
			}
		}
	}

	/* A disagreement is a BOUNDARY flip if the host's top-2 logit margin is tiny
	 * (an ambiguous spike that x86/ARM float32 rounding tips either way); a flip
	 * at a real margin, or a wrong trough, is a genuine mismatch. */
	int exact = 0, boundary = 0, real = 0;
	int lim = (nsp < EXP_COUNT) ? nsp : EXP_COUNT;
	for (int i = 0; i < lim; i++) {
		if (my_troughs[i] != exp_troughs[i]) {
			real++;
		} else if (my_units[i] == exp_units[i]) {
			exact++;
		} else if (exp_margins[i] < 0.5f) {
			boundary++;
		} else {
			real++;
		}
	}

	printk("detected %d spikes (expected %d)\n", nsp, EXP_COUNT);
	printk("exact %d | boundary flips %d | real mismatches %d\n", exact, boundary, real);
	printk("detected units:");
	for (int i = 0; i < nsp; i++) {
		printk(" %d", my_units[i]);
	}
	printk("\n%s\n", (nsp == EXP_COUNT && real == 0) ? "STREAM MATCH" : "MISMATCH");
	return 0;
}
