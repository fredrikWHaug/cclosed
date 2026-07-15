/*
 * ResNet spike classifier — runs a trained Small ResNet on a hardcoded snippet.
 *
 * Architecture (weights baked in from PyTorch with BatchNorm folded into the
 * preceding conv; see model/export_resnet_to_c.py). A ResBlock is:
 *     out = relu(conv1(x));  out = conv2(out);  out = relu(out + x)
 *
 *   stem   Conv(8->64,  k3) +ReLU                          : (8,40)   -> (64,40)
 *   res1   ResBlock(64)                    then MaxPool(2) : (64,40)  -> (64,20)
 *   expand Conv(64->128, k3) +ReLU                         : (64,20)  -> (128,20)
 *   res2   ResBlock(128)                   then MaxPool(2) : (128,20) -> (128,10)
 *   res3   ResBlock(128)                   then MaxPool(2) : (128,10) -> (128,5)
 *   fc1    Linear(640->128) +ReLU
 *   fc2    Linear(128->N_CLASSES)
 *   Argmax -> predicted unit
 *
 * Inference math lives in the shared ../nn.h.
 *
 * Three ping-pong buffers (main / tmp / res) are enough: inside a ResBlock the
 * block input stays put in one buffer as the "residual" while the two convs run
 * through the other two, then the add folds it back in.
 */

#include <zephyr/kernel.h>

#include "nn.h"
#include "../model_weights.h"
#include "../test_data.h"

/* Largest intermediate tensor is 64*40 = 128*20 = 2560 floats. */
#define BUF_FLOATS (128 * 40)
static float main_buf[BUF_FLOATS];
static float tmp_buf[BUF_FLOATS];
static float res_buf[BUF_FLOATS];

int main(void)
{
    printk("=== ResNet Spike Classifier on nRF54LM20B ===\n");
    printk("Running inference on hardcoded test snippet...\n");
    printk("True class: %d (unit %d)\n\n", TEST_TRUE_CLASS, TEST_TRUE_UNIT);

    uint32_t t_start = k_uptime_get_32();

    /* stem: Conv(8->64) + ReLU  ->  main = (64, 40) */
    nn_conv1d(test_snippet, main_buf, stem_w, stem_b, 8, 64, 40, 1);

    /* res1: residual is the stem output (stays in main_buf) */
    nn_conv1d(main_buf, tmp_buf, r1c1_w, r1c1_b, 64, 64, 40, 1); /* relu */
    nn_conv1d(tmp_buf, res_buf, r1c2_w, r1c2_b, 64, 64, 40, 0);  /* no relu */
    nn_residual_add_relu(res_buf, main_buf, 64 * 40);            /* res = relu(res + stem) */
    nn_maxpool1d(res_buf, main_buf, 64, 40);                     /* main = (64, 20) */

    /* expand: Conv(64->128) + ReLU  ->  res = (128, 20) */
    nn_conv1d(main_buf, res_buf, expand_w, expand_b, 64, 128, 20, 1);

    /* res2: residual is the expand output (stays in res_buf) */
    nn_conv1d(res_buf, tmp_buf, r2c1_w, r2c1_b, 128, 128, 20, 1);
    nn_conv1d(tmp_buf, main_buf, r2c2_w, r2c2_b, 128, 128, 20, 0);
    nn_residual_add_relu(main_buf, res_buf, 128 * 20);           /* main = relu(main + expand) */
    nn_maxpool1d(main_buf, res_buf, 128, 20);                    /* res = (128, 10) */

    /* res3: residual is the pool2 output (stays in res_buf) */
    nn_conv1d(res_buf, tmp_buf, r3c1_w, r3c1_b, 128, 128, 10, 1);
    nn_conv1d(tmp_buf, main_buf, r3c2_w, r3c2_b, 128, 128, 10, 0);
    nn_residual_add_relu(main_buf, res_buf, 128 * 10);           /* main = relu(main + pool2) */
    nn_maxpool1d(main_buf, res_buf, 128, 10);                    /* res = (128, 5) = 640 */

    /* classifier */
    nn_linear(res_buf, main_buf, fc1_w, fc1_b, 640, 128, 1);     /* 640 -> 128, ReLU */
    nn_linear(main_buf, res_buf, fc2_w, fc2_b, 128, N_CLASSES, 0); /* 128 -> N_CLASSES */

    uint32_t t_end = k_uptime_get_32();

    int predicted = nn_argmax(res_buf, N_CLASSES);

    printk("Output logits: ");
    for (int i = 0; i < N_CLASSES; i++) {
        printk("%d:%d  ", i, (int)(res_buf[i] * 100));
    }
    printk("\n");

    printk("Predicted class: %d\n", predicted);
    printk("Correct: %s\n", predicted == TEST_TRUE_CLASS ? "YES" : "NO");
    printk("Inference time: %u ms\n", t_end - t_start);

    return 0;
}
