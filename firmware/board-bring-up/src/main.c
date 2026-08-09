#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi22));
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));
#define CS_PIN 2

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
};

#define CMD_READ(r) ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))

static uint8_t xfer(uint16_t cmd)
{
	uint8_t tx[2] = { cmd >> 8, cmd };
	uint8_t rx[2];
	struct spi_buf tb = { .buf = tx, .len = 2 };
	struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
	struct spi_buf rb = { .buf = rx, .len = 2 };
	struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

	gpio_pin_set(gpio3, CS_PIN, 0);
	k_busy_wait(2);
	spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
	k_busy_wait(2);
	gpio_pin_set(gpio3, CS_PIN, 1);
	return rx[1];
}

int main(void)
{
	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);

	while (1) {
		xfer(CMD_READ(40));               
		xfer(CMD_READ(41));              
		uint8_t c0 = xfer(CMD_READ(42));  
		uint8_t c1 = xfer(CMD_READ(43)); 
		uint8_t c2 = xfer(CMD_READ(44));  
		uint8_t c3 = xfer(CMD_READ(63));  
		uint8_t c4 = xfer(CMD_READ(63));

		printk("ROM 40-44 = '%c%c%c%c%c'\n", c0, c1, c2, c3, c4);
		k_msleep(2000);
	}
}
