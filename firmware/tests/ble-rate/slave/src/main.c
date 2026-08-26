#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE DT_NODELABEL(spi21)

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE,
};

int main(void)
{
	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready!\n");
		return 0;
	}

	uint32_t counter = 0;

	while (1) {
		uint8_t tx[4] = {
			(uint8_t)(counter),        (uint8_t)(counter >> 8),
			(uint8_t)(counter >> 16),  (uint8_t)(counter >> 24),
		};
		uint8_t rx[4] = {0};

		struct spi_buf tb = { .buf = tx, .len = 4 };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rx, .len = 4 };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		int ret = spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
		if (ret < 0) {
			printk("SPI error: %d\n", ret);
			continue;
		}
		counter++;
	}

	return 0;
}
