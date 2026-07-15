/*
 * SPI Master — Intan RHD2000-style link, with live DATA-RATE plot.
 *
 * Mimics how the nRF54 will talk to a real RHD2164/RHD2132 so that swapping
 * the slave DK for an actual Intan chip is close to plug-and-play:
 *
 *   - 16-bit transfers, MSB first, SPI mode 0 (CPOL=0, CPHA=0)
 *   - one CS pulse per 16-bit word (CS high between every transfer)
 *   - CONVERT(C) command format from the RHD2000 datasheet
 *
 * A "16-bit word" on Intan is just 16 SCLK cycles inside one CS-low window.
 * The nRF SPI driver only does 8-bit words, so we send a 2-byte buffer per
 * manual-CS frame — that IS a 16-bit Intan transfer.
 *
 * VISUALIZATION: this build measures the actual SPI throughput. It runs
 * transfers flat-out (no artificial delay) and redraws a single live gauge
 * IN PLACE (~10 Hz, via carriage-return) showing the measured rate as a bar
 * scaled against the clock-limited ceiling — so the bar shows bus UTILIZATION.
 * The display rate (10 Hz) is deliberately decoupled from the transfer rate
 * (thousands/sec): printing every transfer would throttle the SPI to UART
 * speed and measure the printer, not the bus. Inbound ADC = 2 bytes/transfer.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE   DT_NODELABEL(spi22)
#define CS_PIN     2          /* P3.02, driven manually */
#define SAMPLE_CH  0          /* single channel for now; round-robin is a later step */
#define PLOT_WIDTH 50         /* columns in the throughput bar */
#define GAUGE_MS   100        /* redraw the gauge every 100 ms (~10 Hz) */

#define SCLK_HZ       1000000
#define BITS_PER_XFER 16
/* Clock-limited ceiling: back-to-back 16-bit words at SCLK, zero framing overhead. */
#define MAX_XFER_PER_SEC  (SCLK_HZ / BITS_PER_XFER)   /* 62500 */
#define MAX_BYTES_PER_SEC (MAX_XFER_PER_SEC * 2)      /* inbound ADC bytes */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = SCLK_HZ,     /* well under Intan's 24 MHz max */
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

/* Redraw the live gauge in place (leading '\r', no newline). Fixed width, so
 * a shorter value never leaves stale characters behind. */
static void draw_gauge(uint32_t xfers_per_s, uint32_t bytes_per_s)
{
	char bar[PLOT_WIDTH + 1];
	uint32_t pct = (bytes_per_s * 100U) / MAX_BYTES_PER_SEC;
	int fill = (int)((uint64_t)bytes_per_s * PLOT_WIDTH / MAX_BYTES_PER_SEC);

	if (fill > PLOT_WIDTH) {
		fill = PLOT_WIDTH;
	}
	for (int i = 0; i < PLOT_WIDTH; i++) {
		bar[i] = (i < fill) ? '#' : ' ';
	}
	bar[PLOT_WIDTH] = '\0';

	printk("\rSPI %6u xfer/s  %6u B/s  [%s] %2u%%",
	       xfers_per_s, bytes_per_s, bar, pct);
}

int main(void)
{
	printk("=== SPI Master (Intan-style) - live data-rate plot ===\n");
	printk("bar = bus utilization vs %u B/s clock ceiling (1 MHz, 16-bit words)\n",
	       MAX_BYTES_PER_SEC);

	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}

	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);   /* CS idle high */

	uint32_t count = 0;
	int64_t window_start = k_uptime_get();

	while (1) {
		intan_xfer(convert_cmd(SAMPLE_CH));   /* run flat-out; no artificial delay */
		count++;

		int64_t now = k_uptime_get();
		int64_t elapsed = now - window_start;

		if (elapsed >= GAUGE_MS) {
			uint32_t xfers_per_s = (uint32_t)((int64_t)count * 1000 / elapsed);
			uint32_t bytes_per_s = xfers_per_s * 2;   /* 2 inbound ADC bytes / xfer */

			draw_gauge(xfers_per_s, bytes_per_s);

			count = 0;
			window_start = now;
		}
	}

	return 0;
}
