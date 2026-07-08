/*
 * SPI Slave — receives a byte from master and responds.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE DT_NODELABEL(spi22)

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE,
	.slave = 0,
};

int main(void)
{
	printk("=== SPI Slave ===\n");

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}
	printk("SPI device ready, waiting for master...\n");

	uint8_t rx_byte = 0;
	uint8_t tx_byte = 0x55;

	while (1) {
		struct spi_buf tx_buf = { .buf = &tx_byte, .len = 1 };
		struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };

		struct spi_buf rx_buf = { .buf = &rx_byte, .len = 1 };
		struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

		int ret = spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
		if (ret) {
			printk("SPI error: %d\n", ret);
		} else {
			printk("Received: 0x%02X\n", rx_byte);
			tx_byte = rx_byte + 1;
		}
	}

	return 0;
}
