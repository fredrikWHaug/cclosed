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
	return (uint16_t)raw << 2;
}

static uint16_t exec(uint16_t cmd)
{
	uint8_t op = cmd >> 14;
	uint8_t addr = (cmd >> 8) & 0x3F;

	switch (op) {
	case 0:                                
		if (addr == 0) {
			return adc_sample16();
		}
		return 32768;                   
	case 2:                                 
		regs[addr] = (uint8_t)cmd;
		return 0xFF00 | (uint8_t)cmd;  
	case 3:                                
		return regs[addr];
	default:                              
		return 0;
	}
}

int main(void)
{
	regs[40] = 'I'; regs[41] = 'N'; regs[42] = 'T'; regs[43] = 'A'; regs[44] = 'N';
	regs[60] = 1;                        
	regs[61] = 1;                         
	regs[62] = 32;                       
	regs[63] = 1;                

	if (!device_is_ready(spi_dev)) {
		printk("SPI not ready\n");
		return 0;
	}
	adc_channel_setup_dt(&adc_chan);
	printk("slave-intan: RHD2132 emulator, ch0 = SAADC on P1.03, one word per CS\n");

	uint16_t pipe0 = 0, pipe1 = 0;    
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
