/*
 * signal-path SLAVE-INTAN — emulates the RHD2132's SPI mechanics faithfully.
 *
 * Mechanics replicated from the RHD2000 datasheet (see
 * documentation/intan-rhd-reference.md):
 *   - 16-bit words MSB-first, SPI mode 0, chip is always the slave
 *   - CS pulses high between EVERY word; each word is its own transaction
 *   - No internal clock: one CONVERT command = exactly one ADC conversion,
 *     entirely master-paced. No free-running, no batching, no frames.
 *   - Pipelined: the result of command N is transmitted in word N+2
 *   - Command set: CONVERT / READ / WRITE / CALIBRATE (encodings DS p16-18)
 *   - ROM registers 40-44 spell "INTAN"; 60-63 = die rev/unipolar/#amps/chip ID
 *   - Amplifier results in 16-bit offset-binary (Reg 4 default 0x80)
 *
 * Channel 0 is REAL: each CONVERT(0) triggers a one-shot SAADC conversion of
 * P1.03 (the function generator), scaled 14-bit -> 16-bit offset-binary-ish
 * (code << 2). All other channels return midscale 32768 ("no electrode").
 *
 * Emulation limits: the ADC conversion happens ~us after the command word
 * completes (real chip samples on the CS falling edge itself), and the master
 * must pace words slowly enough for the per-word SPIS re-arm (~100 us).
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/spi.h>

static const struct adc_dt_spec adc_chan =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 0);

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi21));
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_SLAVE,
	.slave = 0,
};

static uint8_t regs[64];

static uint16_t adc_sample16(void)
{
	int16_t raw = 0;
	struct adc_sequence one = {
		.buffer = &raw,
		.buffer_size = sizeof(raw),
	};

	adc_sequence_init_dt(&adc_chan, &one);
	adc_read_dt(&adc_chan, &one);
	if (raw < 0) {
		raw = 0;
	}
	return (uint16_t)raw << 2;   /* 14-bit code -> 16-bit range */
}

/* Execute one 16-bit command word, return its result (sent 2 words later). */
static uint16_t exec(uint16_t cmd)
{
	uint8_t op = cmd >> 14;
	uint8_t addr = (cmd >> 8) & 0x3F;

	switch (op) {
	case 0:                                 /* CONVERT(C) */
		if (addr == 0) {
			return adc_sample16();
		}
		return 32768;                   /* unconnected channel: midscale */
	case 2:                                 /* WRITE(R,D) */
		regs[addr] = (uint8_t)cmd;
		return 0xFF00 | (uint8_t)cmd;   /* upper byte all 1s, echo D */
	case 3:                                 /* READ(R) */
		return regs[addr];
	default:                                /* CALIBRATE / CLEAR / dummies */
		return 0;
	}
}

int main(void)
{
	regs[40] = 'I'; regs[41] = 'N'; regs[42] = 'T'; regs[43] = 'A'; regs[44] = 'N';
	regs[60] = 1;                           /* die revision */
	regs[61] = 1;                           /* unipolar amps */
	regs[62] = 32;                          /* number of amplifiers */
	regs[63] = 1;                           /* chip ID: RHD2132 */

	if (!device_is_ready(spi_dev)) {
		printk("SPI not ready\n");
		return 0;
	}
	adc_channel_setup_dt(&adc_chan);
	printk("slave-intan: RHD2132 emulator, ch0 = SAADC on P1.03, one word per CS\n");

	uint16_t pipe0 = 0, pipe1 = 0;          /* 2-deep result pipeline */
	uint8_t tx[2], rx[2];
	uint32_t words = 0;

	while (1) {
		tx[0] = pipe0 >> 8;
		tx[1] = (uint8_t)pipe0;

		struct spi_buf tb = { .buf = tx, .len = 2 };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rx, .len = 2 };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		if (spi_transceive(spi_dev, &spi_cfg, &ts, &rs) < 0) {
			continue;
		}

		uint16_t cmd = (uint16_t)((rx[0] << 8) | rx[1]);
		pipe0 = pipe1;
		pipe1 = exec(cmd);

		if ((++words % 10000) == 0) {
			printk("words %u  last cmd 0x%04x\n", words, cmd);
		}
	}
	return 0;
}
