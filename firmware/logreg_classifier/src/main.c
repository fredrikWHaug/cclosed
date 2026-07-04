/*
 * Logistic Regression Spike Classifier
 *
 * One matrix multiply: output = W * input + b, then argmax.
 * That's the entire model.
 */

#include <zephyr/kernel.h>

#include "../model_weights.h"
#include "../test_data.h"

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

int main(void)
{
	printk("=== Logistic Regression Spike Classifier ===\n");
	printk("Running inference on hardcoded test snippet...\n");
	printk("True class: %d (unit %d)\n\n", TEST_TRUE_CLASS, TEST_TRUE_UNIT);

	/* Flatten input: test_snippet is (8, 40) = 320 floats, already contiguous */
	const float *input = test_snippet;
	float output[N_CLASSES];

	uint32_t t_start = k_uptime_get_32();

	/* Single matrix multiply: output[c] = sum(W[c][i] * input[i]) + b[c] */
	for (int c = 0; c < N_CLASSES; c++) {
		float sum = logreg_b[c];
		for (int i = 0; i < INPUT_DIM; i++) {
			sum += logreg_w[c * INPUT_DIM + i] * input[i];
		}
		output[c] = sum;
	}

	uint32_t t_end = k_uptime_get_32();

	int predicted = argmax(output, N_CLASSES);

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
