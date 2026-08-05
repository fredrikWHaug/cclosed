#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/spi.h>

#define SAMPLE_INTERVAL_US 100
#define NS_F 240
#define SYNC_WORD 0x7FFFu
#define FT (NS_F + 3)      

static const struct adc_dt_spec adc_chan =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 0);

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi21));
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE,
	.slave = 0,
};

static int16_t bufs[2][NS_F];
static volatile int latest = -1;
static volatile uint16_t seq;

static uint8_t frame[FT * 2];
static uint8_t rxjunk[FT * 2];

static void put_word(int i, uint16_t w)
{
	frame[i * 2] = w >> 8;
	frame[i * 2 + 1] = w & 0xFF;
}

static void spi_serve(void *a, void *b, void *c)
{
	while (latest < 0) {
		k_msleep(1);
	}
	while (1) {
		uint16_t s = seq;
		const int16_t *src = bufs[latest];
		uint16_t ck = 0;

		put_word(0, s);
		put_word(1, SYNC_WORD);
		for (int i = 0; i < NS_F; i++) {
			uint16_t w = (uint16_t)src[i];
			put_word(2 + i, w);
			ck = (uint16_t)(ck + w);
		}
		put_word(NS_F + 2, ck);

		struct spi_buf tb = { .buf = frame, .len = sizeof(frame) };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rxjunk, .len = sizeof(rxjunk) };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
	}
}
K_THREAD_DEFINE(spi_tid, 2048, spi_serve, NULL, NULL, NULL, 5, 0, 0);

int main(void)
{
	struct adc_sequence_options opts = {
		.interval_us = SAMPLE_INTERVAL_US,
		.extra_samplings = NS_F - 1,
	};
	struct adc_sequence adcseq = {
		.options = &opts,
		.buffer_size = NS_F * sizeof(int16_t),
	};
	int pp = 0;

	if (!device_is_ready(spi_dev)) {
		printk("SPI not ready\n");
		return 0;
	}
	adc_channel_setup_dt(&adc_chan);
	printk("signal-path SLAVE: SAADC 10 kS/s on P1.03 -> SPIS %d-sample frames\n", NS_F);

	while (1) {
		adc_sequence_init_dt(&adc_chan, &adcseq);
		adcseq.buffer = bufs[pp];
		adc_read_dt(&adc_chan, &adcseq);
		latest = pp;
		seq++;
		if ((seq % 100) == 0) {
			static int64_t last_t;
			int64_t now = k_uptime_get();
			int16_t mn = bufs[pp][0], mx = bufs[pp][0];
			for (int i = 1; i < NS_F; i++) {
				if (bufs[pp][i] < mn) mn = bufs[pp][i];
				if (bufs[pp][i] > mx) mx = bufs[pp][i];
			}
			printk("seq %u  min %d  max %d  rate %d S/s\n", seq, mn, mx,
			       last_t ? (int)((100 * NS_F * 1000LL) / (now - last_t)) : 0);
			last_t = now;
		}
		pp ^= 1;
	}
	return 0;
}
