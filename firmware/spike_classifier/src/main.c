/*
 * Spike Classifier — runs a trained 1D CNN on a hardcoded test snippet.
 *
 * Architecture (all weights baked in from PyTorch with BatchNorm folded):
 *   Conv1d(8->32, k=3, pad=1) + ReLU + MaxPool(2)   : (8,40) -> (32,20)
 *   Conv1d(32->64, k=3, pad=1) + ReLU + MaxPool(2)   : (32,20) -> (64,10)
 *   Conv1d(64->64, k=3, pad=1) + ReLU + MaxPool(2)   : (64,10) -> (64,5)
 *   Linear(320->64) + ReLU
 *   Linear(64->N_CLASSES)
 *   Argmax -> predicted unit
 */

#include <zephyr/kernel.h>
#include <string.h>

#include "../model_weights.h"
#include "../test_data.h"

/* ---- helpers ---- */

static inline float relu(float x) { return x > 0.0f ? x : 0.0f; }

/*
 * conv1d with kernel_size=3, padding=1, stride=1.
 * in:  (c_in, len_in)
 * out: (c_out, len_in)   (same length due to padding=1)
 * w:   (c_out, c_in, 3)
 * b:   (c_out,)
 */
static void conv1d_relu(const float *in, float *out,
                        const float *w, const float *b,
                        int c_in, int c_out, int len)
{
    for (int co = 0; co < c_out; co++) {
        for (int t = 0; t < len; t++) {
            float sum = b[co];
            for (int ci = 0; ci < c_in; ci++) {
                for (int k = 0; k < 3; k++) {
                    int tt = t + k - 1; /* padding=1 */
                    if (tt >= 0 && tt < len) {
                        sum += w[(co * c_in + ci) * 3 + k]
                             * in[ci * len + tt];
                    }
                }
            }
            out[co * len + t] = relu(sum);
        }
    }
}

/*
 * max_pool1d with kernel_size=2, stride=2.
 * in:  (channels, len_in)
 * out: (channels, len_in / 2)
 */
static void maxpool1d(const float *in, float *out, int channels, int len_in)
{
    int len_out = len_in / 2;
    for (int c = 0; c < channels; c++) {
        for (int t = 0; t < len_out; t++) {
            float a = in[c * len_in + 2 * t];
            float b = in[c * len_in + 2 * t + 1];
            out[c * len_out + t] = a > b ? a : b;
        }
    }
}

/*
 * linear layer: out = W * in + b, optionally with ReLU.
 * W: (out_dim, in_dim), in: (in_dim,), out: (out_dim,)
 */
static void linear(const float *in, float *out,
                   const float *w, const float *b,
                   int in_dim, int out_dim, int apply_relu)
{
    for (int o = 0; o < out_dim; o++) {
        float sum = b[o];
        for (int i = 0; i < in_dim; i++) {
            sum += w[o * in_dim + i] * in[i];
        }
        out[o] = apply_relu ? relu(sum) : sum;
    }
}

static int argmax(const float *arr, int len)
{
    int best = 0;
    for (int i = 1; i < len; i++) {
        if (arr[i] > arr[best]) {
            best = i;
        }
    }
    return best;
}

/* ---- buffers ---- */

/* Largest intermediate: 64 * 20 = 1280 floats */
static float buf_a[64 * 40];
static float buf_b[64 * 40];

int main(void)
{
    printk("=== Spike Classifier on nRF54LM20B ===\n");
    printk("Running inference on hardcoded test snippet...\n");
    printk("True class: %d (unit %d)\n\n", TEST_TRUE_CLASS, TEST_TRUE_UNIT);

    uint32_t t_start = k_uptime_get_32();

    /* Input: test_snippet is (8, 40) */

    /* Block 1: Conv(8->32, k3) + ReLU + MaxPool -> (32, 20) */
    conv1d_relu(test_snippet, buf_a, conv1_w, conv1_b, 8, 32, 40);
    maxpool1d(buf_a, buf_b, 32, 40);

    /* Block 2: Conv(32->64, k3) + ReLU + MaxPool -> (64, 10) */
    conv1d_relu(buf_b, buf_a, conv2_w, conv2_b, 32, 64, 20);
    maxpool1d(buf_a, buf_b, 64, 20);

    /* Block 3: Conv(64->64, k3) + ReLU + MaxPool -> (64, 5) */
    conv1d_relu(buf_b, buf_a, conv3_w, conv3_b, 64, 64, 10);
    maxpool1d(buf_a, buf_b, 64, 10);

    /* buf_b is now (64, 5) = 320 floats, already flattened in memory */

    /* FC1: 320 -> 64, ReLU */
    linear(buf_b, buf_a, fc1_w, fc1_b, 320, 64, 1);

    /* FC2: 64 -> N_CLASSES */
    linear(buf_a, buf_b, fc2_w, fc2_b, 64, N_CLASSES, 0);

    uint32_t t_end = k_uptime_get_32();

    /* Result */
    int predicted = argmax(buf_b, N_CLASSES);

    printk("Output logits: ");
    for (int i = 0; i < N_CLASSES; i++) {
        printk("%d:%d  ", i, (int)(buf_b[i] * 100));
    }
    printk("\n");

    printk("Predicted class: %d\n", predicted);
    printk("Correct: %s\n", predicted == TEST_TRUE_CLASS ? "YES" : "NO");
    printk("Inference time: %u ms\n", t_end - t_start);

    return 0;
}
