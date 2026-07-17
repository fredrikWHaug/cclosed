/*
 * SPI Master — streams an incrementing SEQUENCE NUMBER over the Intan-style link.
 *
 * This is the data-integrity / latency test: the master sends 0,1,2,3,... as
 * 16-bit words. The slave prints each value it receives; a host-side Python
 * script graphs the sequence. Because the numbers should increase by exactly 1
 * each step, any gap = dropped data, and arrival timing = streaming delay.
 *
 * Same physical protocol as the real Intan link (16-bit words, MSB first,
 * mode 0, one CS pulse per word) — only the payload is a counter instead of a
 * CONVERT command, so this genuinely exercises the link we'll use.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE      DT_NODELABEL(spi22)
#define CS_PIN        2       /* P3.02, driven manually */
#define SEND_PERIOD_MS 5      /* ~200 Hz — slow enough the slave can print every value */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = 1000000,     /* well under Intan's 24 MHz max */
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER, /* mode 0 */
	.slave = 0,
	/* no .cs — we frame the transaction manually below */
};

/* Send one 16-bit word inside a single manual-CS frame (Intan-style). */
static void intan_send(uint16_t word)
{
	uint8_t tx[2] = { word >> 8, word & 0xFF };   /* MSB first */
	uint8_t rx[2] = { 0, 0 };

	struct spi_buf tx_buf = { .buf = tx, .len = 2 };
	struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };
	struct spi_buf rx_buf = { .buf = rx, .len = 2 };
	struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

	gpio_pin_set(gpio3, CS_PIN, 0);   /* assert CS low */
	k_busy_wait(50);                  /* 50us setup — let the slave's SPIS arm */
	spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
	k_busy_wait(50);                  /* 50us hold */
	gpio_pin_set(gpio3, CS_PIN, 1);   /* deassert CS high */
}

int main(void)
{
	printk("=== SPI Master - streaming sequence numbers ===\n");

	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}

	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);   /* CS idle high */

	uint16_t seq = 0;

	while (1) {
		intan_send(seq);   /* send the counter; wraps at 65536 */
		seq++;
		k_msleep(SEND_PERIOD_MS);
	}

	return 0;
}
