/*
 * SPI Master — Intan RHD2000-style link, plotting a streamed spike trace.
 *
 * Mimics how the nRF54 will talk to a real RHD2164/RHD2132:
 *   - 16-bit transfers, MSB first, SPI mode 0 (CPOL=0, CPHA=0)
 *   - one CS pulse per 16-bit word (CS high between every transfer)
 *   - CONVERT(C) command format from the RHD2000 datasheet
 *
 * The slave streams a REAL recorded spike trace (16-bit offset-binary ADC
 * codes). This build reconstructs it as a live scrolling waveform in the
 * serial terminal — so you watch actual spike data cross the SPI link.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE   DT_NODELABEL(spi22)
#define CS_PIN     2          /* P3.02, driven manually */
#define SAMPLE_CH  3          /* channel the trace was recorded on */
#define PLOT_WIDTH 60         /* columns in the terminal waveform */
#define SAMPLE_MS  25         /* ~40 samples/sec — slow enough to see spikes scroll */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = 1000000,     /* well under Intan's 24 MHz max */
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER, /* mode 0 */
	.slave = 0,
	/* no .cs — we frame the transaction manually below */
};

/* Build a 16-bit CONVERT(C) command: bits [13:8]=channel, bit0=H (0 here). */
static uint16_t convert_cmd(uint8_t channel)
{
	return (uint16_t)((channel & 0x3F) << 8);
}

/* One Intan-style 16-bit transaction inside a single manual-CS frame. */
static uint16_t intan_xfer(uint16_t cmd)
{
	uint8_t tx[2] = { cmd >> 8, cmd & 0xFF };   /* MSB first */
	uint8_t rx[2] = { 0, 0 };

	struct spi_buf tx_buf = { .buf = tx, .len = 2 };
	struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };
	struct spi_buf rx_buf = { .buf = rx, .len = 2 };
	struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

	gpio_pin_set(gpio3, CS_PIN, 0);   /* assert CS low */
	k_busy_wait(50);                  /* 50us setup — let the slave's SPIS arm (proven value) */
	spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
	k_busy_wait(50);                  /* 50us hold */
	gpio_pin_set(gpio3, CS_PIN, 1);   /* deassert CS high (>154 ns between words) */

	return (uint16_t)((rx[0] << 8) | rx[1]);
}

/* Draw one 16-bit sample as a '*' positioned by amplitude (centre = baseline). */
static void plot(uint16_t val)
{
	char line[PLOT_WIDTH + 1];
	int col = ((int)val * PLOT_WIDTH) / 65536;   /* 0..65535 -> 0..PLOT_WIDTH-1 */
	int mid = PLOT_WIDTH / 2;

	if (col < 0) {
		col = 0;
	}
	if (col >= PLOT_WIDTH) {
		col = PLOT_WIDTH - 1;
	}

	for (int i = 0; i < PLOT_WIDTH; i++) {
		line[i] = (i == col) ? '*' : (i == mid ? '.' : ' ');   /* '.' marks baseline */
	}
	line[PLOT_WIDTH] = '\0';

	printk("%5u |%s|\n", val, line);
}

int main(void)
{
	printk("=== SPI Master - streaming real spike data ===\n");

	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}

	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);   /* CS idle high */

	while (1) {
		uint16_t sample = intan_xfer(convert_cmd(SAMPLE_CH));

		plot(sample);
		k_msleep(SAMPLE_MS);
	}

	return 0;
}
