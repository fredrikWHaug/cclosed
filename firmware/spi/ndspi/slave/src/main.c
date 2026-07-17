/*
 * ndspi SLAVE — sends one REAL 8-channel spike snippet as a single frame.
 *
 * Why one big transaction instead of word-by-word:
 *   The per-word version re-armed the SPIS between every 16-bit word. The
 *   nRF SPIS preloads its TX one transaction ahead, and that re-arm raced the
 *   master's clock — each preloaded word got sampled across TWO master
 *   transactions, so every sample came out DUPLICATED and the frame de-aligned.
 *
 *   Fix: preload the ENTIRE frame once and let the master clock all of it under
 *   a single CS assertion. One arm per frame, no per-word race, exact alignment.
 *
 * Frame (big-endian 16-bit words): [ SYNC=0x7FFF ][ 320 data ][ checksum ].
 *   data     = nd_snippet[sample][channel], Q8 fixed-point microvolts.
 *   checksum = 16-bit sum of the data words; the master re-sums to verify.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#include "nd_data.h"

#define SPI_NODE   DT_NODELABEL(spi21)
#define SYNC_WORD  0x7FFFu
#define N_WORDS    (1 + ND_LEN * ND_CH + 1)   /* sync + data + checksum = 322 */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE, /* mode 0 */
	.slave = 0,
};

static uint8_t frame[N_WORDS * 2];   /* the whole frame, MSB-first bytes */

static void put_word(int word_idx, uint16_t w)
{
	frame[word_idx * 2]     = w >> 8;
	frame[word_idx * 2 + 1] = w & 0xFF;
}

static void build_frame(void)
{
	uint16_t checksum = 0;

	put_word(0, SYNC_WORD);
	for (int k = 0; k < ND_LEN * ND_CH; k++) {
		uint16_t w = (uint16_t)nd_snippet[k / ND_CH][k % ND_CH];
		put_word(1 + k, w);
		checksum = (uint16_t)(checksum + w);
	}
	put_word(N_WORDS - 1, checksum);
}

int main(void)
{
	printk("=== ndspi SLAVE (whole-frame transfer, %d words) ===\n", N_WORDS);

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}
	build_frame();

	uint8_t rx[N_WORDS * 2];   /* master sends dummy zeros; we ignore them */

	while (1) {
		struct spi_buf tx_buf = { .buf = frame, .len = sizeof(frame) };
		struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };
		struct spi_buf rx_buf = { .buf = rx, .len = sizeof(rx) };
		struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

		/* Arm the whole frame and block until the master clocks it out. */
		int ret = spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
		if (ret < 0) {
			printk("SPI error: %d\n", ret);
		}
	}

	return 0;
}
