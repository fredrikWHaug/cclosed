/*
 * SPI Slave — receives the master's SEQUENCE NUMBERS and streams them out as
 * RAW BINARY over the console UART: 2 bytes, little-endian, per received word.
 *
 * Binary instead of ASCII printk("%u\n") removes the per-word formatting cost
 * that capped the old monitor at ~2 kHz. The slave now keeps up with the
 * master's full SPI rate (~8 kHz, set by the master's per-word CS timing), so
 * the counter test runs at the real link speed. monitor.py locks onto the
 * 2-byte stream and detects drops from sequence gaps.
 *
 * Note: SPIS spi_transceive returns rx_amount (>0) on success, <0 on error.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/drivers/uart.h>

#define SPI_NODE DT_NODELABEL(spi21)

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *con = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE, /* mode 0 */
	.slave = 0,
};

int main(void)
{
	/* Plain-text banner at boot; everything after is raw binary. monitor.py
	 * locks onto the counter ramp and ignores this header automatically. */
	printk("=== SPI Slave - streaming raw 16-bit counter (binary) ===\n");
	printk("console current-speed = %d baud\n",
	       DT_PROP(DT_CHOSEN(zephyr_console), current_speed));

	if (!device_is_ready(spi_dev) || !device_is_ready(con)) {
		printk("device not ready!\n");
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
			continue;   /* drop the errored word (no ASCII - would desync stream) */
		}

		uint16_t seq = (uint16_t)((rx[0] << 8) | rx[1]);   /* master sends MSB first */
		uart_poll_out(con, (uint8_t)(seq & 0xFF));         /* out as little-endian */
		uart_poll_out(con, (uint8_t)(seq >> 8));
	}

	return 0;
}
