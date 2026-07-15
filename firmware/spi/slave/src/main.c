/*
 * SPI Slave — emulates an Intan RHD2132 (single-data-rate; DDR deferred).
 *
 * Stands in for a real Intan chip so the master firmware is exercised against
 * the actual protocol:
 *   - receives a 16-bit CONVERT(C) command (2 bytes, MSB first, mode 0)
 *   - decodes channel C from bits [13:8]
 *   - returns a 16-bit "ADC value" for that channel, with Intan's real
 *     2-command pipeline delay (the reply to command i goes out at i+2)
 *
 * The emulated ADC is a per-channel sine wave so the master can draw a live
 * waveform. Swap this DK for a real RHD2132/2164 and the master is unchanged.
 *
 * Note: SPIS spi_transceive returns rx_amount (>0) on success, <0 on error.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE DT_NODELABEL(spi21)
#define LUT_LEN  32

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE, /* mode 0 */
	.slave = 0,
};

/* One period of a sine, centred at 2048, amplitude ~1800 (fits a 12-bit range). */
static const uint16_t sine_lut[LUT_LEN] = {
	2048, 2399, 2737, 3048, 3321, 3545, 3711, 3813,
	3848, 3813, 3711, 3545, 3321, 3048, 2737, 2399,
	2048, 1697, 1359, 1048,  775,  551,  385,  283,
	 248,  283,  385,  551,  775, 1048, 1359, 1697,
};

/* Fake ADC: each channel walks its own phase so channels look different. */
static uint16_t adc_emulate(uint8_t channel)
{
	static uint16_t phase[64];
	uint16_t val = sine_lut[phase[channel] % LUT_LEN];

	phase[channel] += 1 + channel;   /* higher channels advance faster */
	return val;
}

int main(void)
{
	printk("=== SPI Slave (Intan RHD2132 emulator) ===\n");

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}
	printk("SPI ready, emulating Intan. Waiting for master...\n");

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

		uint16_t cmd = (uint16_t)((rx[0] << 8) | rx[1]);
		uint8_t channel = (cmd >> 8) & 0x3F;

		/* Advance the pipeline: this command's result becomes due in 2 frames. */
		resp_next = resp_after;
		resp_after = adc_emulate(channel);
	}

	return 0;
}
