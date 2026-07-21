/*
 * pipeline SLAVE (4b) — Intan emulator streaming the raw 8-channel ADC codes.
 *
 * The raw stream (stream_test.h, 8 x NS uint16, channel-major) is too big for one
 * SPI transfer, so it goes out in 3 frames. Each frame is preloaded whole and
 * clocked under a single CS (the proven ndspi pattern — no per-word re-arm race):
 *
 *     [ frame_idx ][ SYNC=0x7FFF ][ FW data words ][ checksum ]
 *
 * The frame_idx lets the master place each frame correctly even if it starts
 * reading mid-cycle. The slave just free-runs 0,1,2,0,1,2,...
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>

#include "stream_test.h"          /* raw_stream[N_CH*NS], NS, N_CH */

#define SPI_NODE  DT_NODELABEL(spi21)
#define SYNC_WORD 0x7FFFu
#define NFRAMES   3
#define FW        (N_CH * NS / NFRAMES)     /* words per frame */
#define FT        (FW + 3)                  /* idx + sync + data + checksum */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE,
	.slave = 0,
};

static uint8_t frame[FT * 2];

static void put_word(int i, uint16_t w)
{
	frame[i * 2] = w >> 8;
	frame[i * 2 + 1] = w & 0xFF;
}

static void build(int f)
{
	uint16_t ck = 0;
	put_word(0, (uint16_t)f);
	put_word(1, SYNC_WORD);
	for (int i = 0; i < FW; i++) {
		uint16_t w = raw_stream[f * FW + i];
		put_word(2 + i, w);
		ck = (uint16_t)(ck + w);
	}
	put_word(FW + 2, ck);
}

int main(void)
{
	printk("=== pipeline SLAVE (Intan emulator: %d frames x %d words) ===\n", NFRAMES, FW);
	if (!device_is_ready(spi_dev)) {
		printk("SPI not ready\n");
		return 0;
	}

	static uint8_t rx[FT * 2];
	int f = 0;
	while (1) {
		build(f);
		struct spi_buf tb = { .buf = frame, .len = sizeof(frame) };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rx, .len = sizeof(rx) };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		int ret = spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
		if (ret < 0) {
			printk("SPI error: %d\n", ret);
		}
		f = (f + 1) % NFRAMES;
	}
	return 0;
}
