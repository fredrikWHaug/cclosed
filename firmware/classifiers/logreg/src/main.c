/*
 * Logistic Regression spike classifier.
 *
 * The entire model is one fully-connected layer:  logits = W * input + b,
 * then argmax. Input is the flattened (8,40)=320-sample snippet.
 *
 * Inference math lives in the shared ../nn.h.
 */

#include <zephyr/kernel.h>

#include "nn.h"
#include "../model_weights.h"
#include "../test_data.h"

int main(void)
{
	printk("=== Logistic Regression Spike Classifier ===\n");
	printk("Running inference on hardcoded test snippet...\n");
	printk("True class: %d (unit %d)\n\n", TEST_TRUE_CLASS, TEST_TRUE_UNIT);

	/* test_snippet is (8, 40) = 320 floats, already contiguous == flattened */
	float output[N_CLASSES];

	uint32_t t_start = k_uptime_get_32();

	/* Single linear layer, no ReLU: output = W * input + b */
	nn_linear(test_snippet, output, logreg_w, logreg_b, INPUT_DIM, N_CLASSES, 0);

	uint32_t t_end = k_uptime_get_32();

	int predicted = nn_argmax(output, N_CLASSES);

	printk("Output logits: ");
	for (int i = 0; i < N_CLASSES; i++) {
		printk("%d:%d  ", i, (int)(output[i] * 100));
	}
	printk("\n");

	printk("Predicted class: %d\n", predicted);
	printk("Correct: %s\n", predicted == TEST_TRUE_CLASS ? "YES" : "NO");
	printk("Inference time: %u ms\n", t_end - t_start);

	return 0;
}
