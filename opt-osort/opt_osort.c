/*
 * opt-OSort profiler  (Wu et al. 2023, J. Neural Eng. 20 066015)
 *
 * The real-time, unsupervised spike sorter — the artifact we care about, written
 * in C because that's what eventually runs on the nRF54. It reads a snippet stream
 * from snippets.bin (produced by prep.py) exactly as the MCU would read detected
 * spikes off the SPI bus, sorts them into a FIXED set of cluster slots using the
 * correlation-coefficient (CC) criterion, and is instrumented to count the float
 * ops and memory it uses — so we can map cost onto the MCU's cycle/RAM budget.
 *
 * We count only float ops (mul/add/sqrt/div); integer/compare ops are negligible
 * and cheap on the M33, so they're deliberately ignored (noted in the README).
 *
 *   make && ./opt_osort snippets.bin
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

/* --- opt-OSort parameters (Wu 2023, Table 1) --- */
#define CNUMBER  4       /* fixed cluster slots (4-6 per single channel) */
#define RHO_THR  0.70f   /* CC threshold to join a cluster (paper: 0.6-0.8) */
#define NLOOP1   200     /* loop-check 1 cadence (reject tiny outlier clusters) */
#define GSIZE1   4
#define NLOOP2   1000    /* loop-check 2 cadence (drop drifted/stopped clusters) */
#define GSIZE2   50

/* --- MCU cost model (nRF54 Cortex-M33 + single-precision FPU) --- */
#define CLOCK_HZ   128000000.0
#define CYC_MULADD 1      /* VMUL / VADD ~1 cycle */
#define CYC_SQRTDIV 14    /* VSQRT / VDIV ~14 cycles */

static int K;             /* snippet length (from file header) */

/* float-op counters */
static uint64_t n_mul, n_add, n_sqrt, n_div;

typedef struct {
	float *center;    /* running-mean waveform */
	float *cc;        /* centered center (center - mean), cached for CC */
	float cc_norm;    /* ||cc||, cached */
	int   size;
	int   active;
} Cluster;

static Cluster clus[CNUMBER];

/* Centre a waveform (subtract mean) and return its norm; counts its float ops. */
static float centre(const float *w, float *out)
{
	float mean = 0.0f;
	for (int i = 0; i < K; i++) { mean += w[i]; }
	mean /= K;
	n_add += K; n_div += 1;

	float ss = 0.0f;
	for (int i = 0; i < K; i++) { out[i] = w[i] - mean; ss += out[i] * out[i]; }
	n_add += 2 * K; n_mul += K;               /* K subs + K sq-adds + K sq-muls */

	n_sqrt += 1;
	return sqrtf(ss);
}

/* Pearson CC between an already-centred spike and cluster c. */
static float cc_to(const float *cc_spike, float norm_spike, const Cluster *c)
{
	float dot = 0.0f;
	for (int i = 0; i < K; i++) { dot += cc_spike[i] * c->cc[i]; }
	n_mul += K; n_add += K;

	n_mul += 1; n_div += 1;
	return dot / (norm_spike * c->cc_norm);
}

/* Recompute a cluster's cached centred form + norm after its center changes. */
static void recache(Cluster *c) { c->cc_norm = centre(c->center, c->cc); }

int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: %s snippets.bin [rho_thr]\n", argv[0]); return 1; }
	float rho_thr = (argc > 2) ? atof(argv[2]) : RHO_THR;
	FILE *f = fopen(argv[1], "rb");
	if (!f) { perror("open"); return 1; }
	printf("rho_thr = %.2f\n", rho_thr);

	int32_t n; int32_t k;
	if (fread(&n, 4, 1, f) != 1 || fread(&k, 4, 1, f) != 1) { fprintf(stderr, "bad header\n"); return 1; }
	K = k;
	printf("stream: %d spikes x %d samples\n", n, K);

	for (int c = 0; c < CNUMBER; c++) {
		clus[c].center = calloc(K, sizeof(float));
		clus[c].cc = calloc(K, sizeof(float));
		clus[c].active = 0; clus[c].size = 0;
	}

	float *spike = malloc(K * sizeof(float));
	float *cc_spike = malloc(K * sizeof(float));
	FILE *lab = fopen("labels.txt", "w");   /* per-spike cluster id, for phase-2 accuracy */

	int discarded = 0;

	for (int s = 0; s < n; s++) {
		if (fread(spike, sizeof(float), K, f) != (size_t)K) break;

		float norm = centre(spike, cc_spike);

		/* 1. best-matching active cluster by CC */
		int best = -1; float bestcc = -2.0f;
		for (int c = 0; c < CNUMBER; c++) {
			if (!clus[c].active) { continue; }
			float v = cc_to(cc_spike, norm, &clus[c]);
			if (v > bestcc) { bestcc = v; best = c; }
		}

		if (best >= 0 && bestcc > rho_thr) {
			/* 2a. assign: running-mean update of the center */
			Cluster *c = &clus[best];
			int N = c->size;
			for (int i = 0; i < K; i++) { c->center[i] = (N * c->center[i] + spike[i]) / (N + 1); }
			n_mul += K; n_add += K; n_div += K;
			c->size = N + 1;
			recache(c);
			fprintf(lab, "%d\n", best);
		} else {
			/* 2b. create a new cluster in an empty slot, else discard */
			int slot = -1;
			for (int c = 0; c < CNUMBER; c++) { if (!clus[c].active) { slot = c; break; } }
			if (slot >= 0) {
				memcpy(clus[slot].center, spike, K * sizeof(float));
				clus[slot].size = 1; clus[slot].active = 1;
				recache(&clus[slot]);
				fprintf(lab, "%d\n", slot);
			} else {
				discarded++;
				fprintf(lab, "-1\n");
			}
		}

		/* 3. loop-checks: retire outlier / drifted clusters so slots free up */
		if ((s + 1) % NLOOP1 == 0)
			for (int c = 0; c < CNUMBER; c++)
				if (clus[c].active && clus[c].size < GSIZE1) { clus[c].active = 0; clus[c].size = 0; }
		if ((s + 1) % NLOOP2 == 0)
			for (int c = 0; c < CNUMBER; c++)
				if (clus[c].active && clus[c].size < GSIZE2) { clus[c].active = 0; clus[c].size = 0; }
	}
	fclose(f); fclose(lab);

	/* ---- report ---- */
	uint64_t ops = n_mul + n_add + n_sqrt + n_div;
	double cyc = (double)(n_mul + n_add) * CYC_MULADD + (double)(n_sqrt + n_div) * CYC_SQRTDIV;
	double cyc_spike = cyc / n;
	double us_spike = cyc_spike / CLOCK_HZ * 1e6;

	printf("\n--- per spike (single channel) ---\n");
	printf("float ops/spike : %.0f  (mul %.0f  add %.0f  sqrt %.0f  div %.0f)\n",
	       (double)ops / n, (double)n_mul / n, (double)n_add / n,
	       (double)n_sqrt / n, (double)n_div / n);
	printf("est. MCU cycles : %.0f  ->  %.2f us/spike @ %.0f MHz\n",
	       cyc_spike, us_spike, CLOCK_HZ / 1e6);

	printf("\n--- memory (fixed, per channel) ---\n");
	size_t mem = CNUMBER * (2 * K * sizeof(float) + sizeof(Cluster));
	printf("cluster state   : %zu bytes/ch  ->  %zu KB for 64 ch\n", mem, mem * 64 / 1024);

	printf("\n--- system feasibility (extrapolated) ---\n");
	printf("discarded spikes: %d / %d\n", discarded, n);
	for (int i = 0; i < 3; i++) {
		int rate[] = {1000, 3000, 6000};       /* aggregate spikes/s across 64 ch */
		double load = us_spike * rate[i] / 1e6 * 100.0;
		printf("  at %5d spikes/s aggregate : %.2f%% CPU\n", rate[i], load);
	}
	return 0;
}
