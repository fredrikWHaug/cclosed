/*
 * SPI Slave — receives the master's SEQUENCE NUMBERS and prints them.
 *
 * Part of the data-integrity / latency test. The master streams 0,1,2,3,... as
 * 16-bit words; this slave receives each one and prints it (one integer per
 * line) over its serial port. A host-side Python script reads that stream and
 * graphs it — gaps in the sequence reveal dropped data, arrival timing reveals
 * streaming delay.
 *
 * Plain-number output (no banners between samples) keeps it trivial for Python
 * to parse: any line that isn't a bare integer is ignored on the host side.
 *
 * Note: SPIS spi_transceive returns rx_amount (>0) on success, <0 on error.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE DT_NODELABEL(spi21)

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE, /* mode 0 */
	.slave = 0,
};

int main(void)
{
	printk("=== SPI Slave - receiving sequence numbers ===\n");

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}

	while (1) {
		uint8_t tx[2] = { 0, 0 };            /* nothing to send back */
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

		uint16_t seq = (uint16_t)((rx[0] << 8) | rx[1]);
		printk("%u\n", seq);   /* one bare integer per received word */
	}

	return 0;
}
