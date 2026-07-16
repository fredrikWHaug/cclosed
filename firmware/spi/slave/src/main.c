/*
 * SPI Slave — emulates an Intan RHD2132 streaming REAL spike data.
 *
 * Stands in for a real Intan chip so the master firmware is exercised against
 * the actual protocol:
 *   - receives a 16-bit CONVERT(C) command (2 bytes, MSB first, mode 0)
 *   - returns the next sample of a recorded spike trace as a 16-bit ADC value,
 *     with Intan's real 2-command pipeline delay (reply to cmd i goes out at i+2)
 *
 * The trace (spike_data.h) is a real single-channel recording built from
 * dataset.npz: baseline with several genuine spikes, pre-converted to 16-bit
 * offset-binary. Swap this DK for a real RHD2132/2164 and the master is
 * unchanged. (Single channel for now; the CONVERT channel is decoded but the
 * stream is 1-D — multi-channel playback is a later step.)
 *
 * Note: SPIS spi_transceive returns rx_amount (>0) on success, <0 on error.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#include "spike_data.h"

#define SPI_NODE DT_NODELABEL(spi21)

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE, /* mode 0 */
	.slave = 0,
};

/* Walk the recorded trace one sample per call, looping at the end. */
static uint16_t next_spike_sample(void)
{
	static uint32_t t;
	uint16_t val = spike_stream[t];

	if (++t >= SPIKE_LEN) {
		t = 0;
	}
	return val;
}

int main(void)
{
	printk("=== SPI Slave (Intan emulator, streaming real spikes) ===\n");

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}
	printk("SPI ready. Streaming %d-sample spike trace. Waiting for master...\n",
	       SPIKE_LEN);

	/* Two-deep pipeline: reply to command i is transmitted at transaction i+2. */
	uint16_t resp_next = 0;
	uint16_t resp_after = 0;

	while (1) {
		uint8_t tx[2] = { resp_next >> 8, resp_next & 0xFF };   /* preloaded reply */
		uint8_t rx[2] = { 0, 0 };

		struct spi_buf tx_buf = { .buf = tx, .len = 2 };
		struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };
		struct spi_buf rx_buf = { .buf = rx, .len = 2 };
		struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

		int ret = spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
		if (ret < 0) {
			printk("SPI error: %d\n", ret);
			continue;
		}

		/* (channel is in rx[] bits [13:8]; unused while the stream is 1-D) */

		/* Advance the pipeline: this command's result becomes due in 2 frames. */
		resp_next = resp_after;
		resp_after = next_spike_sample();
	}

	return 0;
}
