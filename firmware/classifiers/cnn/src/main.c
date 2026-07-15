/*
 * CNN spike classifier — runs a trained 1D CNN on a hardcoded test snippet.
 *
 * Architecture (weights baked in from PyTorch with BatchNorm folded):
 *   Conv1d(8->32, k=3, pad=1) + ReLU + MaxPool(2)   : (8,40)  -> (32,20)
 *   Conv1d(32->64, k=3, pad=1) + ReLU + MaxPool(2)  : (32,20) -> (64,10)
 *   Conv1d(64->64, k=3, pad=1) + ReLU + MaxPool(2)  : (64,10) -> (64,5)
 *   Linear(320->64) + ReLU
 *   Linear(64->N_CLASSES)
 *   Argmax -> predicted unit
 *
 * Inference math lives in the shared ../nn.h.
 */

#include <zephyr/kernel.h>

#include "nn.h"
#include "../model_weights.h"
#include "../test_data.h"

/* Ping-pong buffers. Largest intermediate is 64 * 40 floats. */
static float buf_a[64 * 40];
static float buf_b[64 * 40];

int main(void)
{
    printk("=== CNN Spike Classifier on nRF54LM20B ===\n");
    printk("Running inference on hardcoded test snippet...\n");
    printk("True class: %d (unit %d)\n\n", TEST_TRUE_CLASS, TEST_TRUE_UNIT);

    uint32_t t_start = k_uptime_get_32();

    /* Input: test_snippet is (8, 40) */

    /* Block 1: Conv(8->32, k3) + ReLU + MaxPool -> (32, 20) */
    nn_conv1d(test_snippet, buf_a, conv1_w, conv1_b, 8, 32, 40, 1);
    nn_maxpool1d(buf_a, buf_b, 32, 40);

    /* Block 2: Conv(32->64, k3) + ReLU + MaxPool -> (64, 10) */
    nn_conv1d(buf_b, buf_a, conv2_w, conv2_b, 32, 64, 20, 1);
    nn_maxpool1d(buf_a, buf_b, 64, 20);

    /* Block 3: Conv(64->64, k3) + ReLU + MaxPool -> (64, 5) */
    nn_conv1d(buf_b, buf_a, conv3_w, conv3_b, 64, 64, 10, 1);
    nn_maxpool1d(buf_a, buf_b, 64, 10);

    /* buf_b is now (64, 5) = 320 floats, already flattened in memory */

    /* FC1: 320 -> 64, ReLU */
    nn_linear(buf_b, buf_a, fc1_w, fc1_b, 320, 64, 1);

    /* FC2: 64 -> N_CLASSES */
    nn_linear(buf_a, buf_b, fc2_w, fc2_b, 64, N_CLASSES, 0);

    uint32_t t_end = k_uptime_get_32();

    int predicted = nn_argmax(buf_b, N_CLASSES);

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
