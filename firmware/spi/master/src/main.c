/*
 * SPI Master — with MANUAL chip-select control.
 *
 * The Zephyr driver was not toggling our cs-gpios pin (verified: CS stayed
 * high the whole time while SCK pulsed). So we drive CS ourselves as a plain
 * GPIO on P3.02:
 *   - idle high (inactive)
 *   - pull low, wait (setup), clock the byte, wait (hold), release high
 *
 * The setup delay after CS-low also gives the slave's SPIS time to be armed.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE DT_NODELABEL(spi22)
#define CS_PIN 2  /* P3.02 */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3 = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = 250000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
	.slave = 0,
	/* no .cs — we frame the transaction manually below */
};

int main(void)
{
	printk("=== SPI Master (manual CS on P3.02) ===\n");

	if (!device_is_ready(spi_dev)) {
		printk("SPI device not ready\n");
		return 0;
	}
	if (!device_is_ready(gpio3)) {
		printk("gpio3 not ready\n");
		return 0;
	}

	/* CS idle high (deasserted) */
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);

	uint8_t tx_byte = 0;

	while (1) {
		uint8_t rx_byte = 0xFF;

		struct spi_buf tx_buf = { .buf = &tx_byte, .len = 1 };
		struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };

		struct spi_buf rx_buf = { .buf = &rx_byte, .len = 1 };
		struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

		gpio_pin_set(gpio3, CS_PIN, 0);   /* assert CS low */
		k_busy_wait(50);                  /* 50us setup — let the slave arm */

		int ret = spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);

		k_busy_wait(50);                  /* 50us hold */
		gpio_pin_set(gpio3, CS_PIN, 1);   /* deassert CS high */

		if (ret) {
			printk("SPI error: %d\n", ret);
		} else {
			printk("Sent: 0x%02X  Received: 0x%02X\n", tx_byte, rx_byte);
		}

		tx_byte++;
		k_msleep(1000);
	}

	return 0;
}
