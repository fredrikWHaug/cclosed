/*
 * ndspi MASTER — clocks in one full frame and verifies the neural snippet.
 *
 * One transaction per frame: assert CS, clock all 322 words (644 bytes) in a
 * single spi_transceive, deassert. Because the slave preloaded the whole frame,
 * word 0 is exactly the SYNC marker — no per-word re-arm race, no duplication.
 *
 * Then: check word0 == SYNC, sum the 320 data words, compare to the checksum
 * word, and draw the peak channel so you SEE the reconstructed spike.
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

#define SPI_NODE   DT_NODELABEL(spi22)
#define CS_PIN     2          /* P3.02, driven manually */

/* Must mirror slave/src/nd_data.h (snippet is always 40x8). */
#define ND_LEN     40
#define ND_CH      8
#define ND_PEAK    3
#define SYNC_WORD  0x7FFFu
#define N_WORDS    (1 + ND_LEN * ND_CH + 1)   /* 322 */
#define PLOT_WIDTH 60

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER, /* mode 0 */
	.slave = 0,
};

static uint8_t tx[N_WORDS * 2];   /* all zeros — we only clock to read */
static uint8_t rx[N_WORDS * 2];

static uint16_t get_word(int word_idx)
{
	return (uint16_t)((rx[word_idx * 2] << 8) | rx[word_idx * 2 + 1]);
}

/* Draw one Q8-microvolt sample; centre column marks the 0 baseline. */
static void plot(int idx, int16_t q8)
{
	char line[PLOT_WIDTH + 1];
	int mid = PLOT_WIDTH / 2;
	int col = mid + ((int)q8 * (PLOT_WIDTH / 2)) / 9000;

	if (col < 0) {
		col = 0;
	}
	if (col >= PLOT_WIDTH) {
		col = PLOT_WIDTH - 1;
	}
	for (int i = 0; i < PLOT_WIDTH; i++) {
		line[i] = (i == col) ? '*' : (i == mid ? '.' : ' ');
	}
	line[PLOT_WIDTH] = '\0';
	printk("  s%02d %6d |%s|\n", idx, q8, line);
}

int main(void)
{
	printk("=== ndspi MASTER (whole-frame transfer) ===\n");

	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);   /* CS idle high */
	k_msleep(200);   /* let the slave arm its first frame before we clock */

	while (1) {
		struct spi_buf tx_buf = { .buf = tx, .len = sizeof(tx) };
		struct spi_buf_set tx_set = { .buffers = &tx_buf, .count = 1 };
		struct spi_buf rx_buf = { .buf = rx, .len = sizeof(rx) };
		struct spi_buf_set rx_set = { .buffers = &rx_buf, .count = 1 };

		/* One CS assertion for the entire frame. */
		gpio_pin_set(gpio3, CS_PIN, 0);
		k_busy_wait(50);
		spi_transceive(spi_dev, &spi_cfg, &tx_set, &rx_set);
		k_busy_wait(50);
		gpio_pin_set(gpio3, CS_PIN, 1);

		/* Alignment check: preloaded frame => word 0 is SYNC. */
		if (get_word(0) != SYNC_WORD) {
			printk("resync (word0=0x%04X, expected 0x%04X)\n",
			       get_word(0), SYNC_WORD);
			k_msleep(50);
			continue;
		}

		uint16_t sum = 0;
		static int16_t buf[ND_LEN][ND_CH];
		for (int k = 0; k < ND_LEN * ND_CH; k++) {
			uint16_t w = get_word(1 + k);
			buf[k / ND_CH][k % ND_CH] = (int16_t)w;
			sum = (uint16_t)(sum + w);
		}
		uint16_t chk = get_word(N_WORDS - 1);
		bool ok = (sum == chk);

		printk("\n--- snippet received ---  checksum got 0x%04X sum 0x%04X  [%s]\n",
		       chk, sum, ok ? "OK" : "MISMATCH");
		printk("peak channel (ch%d), Q8 microvolts:\n", ND_PEAK);
		for (int s = 0; s < ND_LEN; s++) {
			plot(s, buf[s][ND_PEAK]);
		}

		k_msleep(1000);
	}

	return 0;
}
