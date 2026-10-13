#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <nrfx_spim.h>
#include <hal/nrf_gpio.h>

#define PIN_SCK NRF_GPIO_PIN_MAP(2, 1)
#define PIN_MOSI NRF_GPIO_PIN_MAP(2, 2)
#define PIN_MISO NRF_GPIO_PIN_MAP(2, 4)
#define PIN_CSN NRF_GPIO_PIN_MAP(2, 5)

#define CONVERT(ch) ((uint16_t)(((ch) & 0x3F) << 8))
#define READ(r) ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define WRITE(r, d) ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CALIBRATE ((uint16_t)0x5500)

#define SAMPLE_US 33           
#define WINDOW 30000        

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM00);
static uint8_t tx[2], rx[2];

static uint16_t xfer(uint16_t cmd)
{
	tx[0] = (uint8_t)(cmd >> 8);
	tx[1] = (uint8_t)cmd;
	nrfx_spim_xfer_desc_t x = NRFX_SPIM_XFER_TRX(tx, 2, rx, 2);
	nrfx_spim_xfer(&spim, &x, 0);
	return (uint16_t)((rx[0] << 8) | rx[1]);
}

static const uint16_t init_seq[] = {
	WRITE(0, 0xDE), WRITE(1, 32), WRITE(2, 40), WRITE(3, 0x00), WRITE(4, 0x00),
	WRITE(5, 0x00), WRITE(6, 0x00), WRITE(7, 0x00),
	WRITE(8, 22), WRITE(9, 0), WRITE(10, 23), WRITE(11, 0),
	WRITE(12, 5), WRITE(13, 1),
	WRITE(14, 0xFF), WRITE(15, 0xFF), WRITE(16, 0xFF), WRITE(17, 0xFF),
};

static void intan_init(void)
{
	xfer(READ(40)); xfer(READ(41));
	char id[6] = { 0 };
	id[0] = (char)xfer(READ(42));
	id[1] = (char)xfer(READ(43));
	id[2] = (char)xfer(READ(44));
	id[3] = (char)xfer(READ(63));
	id[4] = (char)xfer(READ(63));
	printk("ROM 40-44 = \"%s\"  (expect INTAN)\n", id);

	for (int i = 0; i < ARRAY_SIZE(init_seq); i++) {
		xfer(init_seq[i]);
	}
	xfer(CALIBRATE);
	for (int i = 0; i < 9; i++) {
		xfer(READ(63));
	}
	printk("Intan configured (10 Hz - 7.5 kHz, amps on, calibrated)\n");
}

static inline int32_t code_to_uv(uint16_t code)
{
	return ((int32_t)code - 32768) * 195 / 1000;
}

int main(void)
{
	nrfx_spim_config_t cfg = NRFX_SPIM_DEFAULT_CONFIG(PIN_SCK, PIN_MOSI, PIN_MISO, PIN_CSN);
	cfg.frequency = 21333333u;
	cfg.mode = NRF_SPIM_MODE_0;
	cfg.bit_order = NRF_SPIM_BIT_ORDER_MSB_FIRST;
	cfg.use_hw_ss = true;
	cfg.ss_duration = 20;
	cfg.rx_delay = 5;

	if (nrfx_spim_init(&spim, &cfg, NULL, NULL) != 0) {
		printk("spim init failed\n");
		return 0;
	}
	intan_init();

	xfer(CONVERT(0));
	xfer(CONVERT(0));
	printk("min max mean [uV]\n");

	while (1) {
		int32_t mn = INT32_MAX, mx = INT32_MIN, sum = 0;
		uint16_t last = 0;
		for (int i = 0; i < WINDOW; i++) {
			last = xfer(CONVERT(0));
			k_busy_wait(SAMPLE_US);
			int32_t uv = code_to_uv(last);
			if (uv < mn) mn = uv;
			if (uv > mx) mx = uv;
			sum += uv;
		}
		(void)last;
		printk("%d %d %d\n", mn, mx, sum / WINDOW);
	}
	return 0;
}
