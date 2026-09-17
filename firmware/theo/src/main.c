#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <nrfx_spim.h>
#include <hal/nrf_spim.h>
#include <hal/nrf_timer.h>
#include <hal/nrf_dppi.h>
#include <hal/nrf_gpio.h>

#define SCLK_HZ      21333333u  
                                 
#define CSNDUR_TICKS 20u        
#define MEASURE_SEC  2u         
#define DPPI_CH      0u

#define PIN_SCK   NRF_GPIO_PIN_MAP(2, 1)
#define PIN_MOSI  NRF_GPIO_PIN_MAP(2, 2)
#define PIN_MISO  NRF_GPIO_PIN_MAP(2, 4)
#define PIN_CSN   NRF_GPIO_PIN_MAP(2, 5)

/* Intan command words (16-bit, MSB first) */
#define CONVERT(ch) ((uint16_t)(((ch) & 0x3F) << 8))
#define READ(reg)   ((uint16_t)(0xC000 | (((reg) & 0x3F) << 8)))

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM00);

/* Static = in RAM = reachable by EasyDMA. */
static uint8_t tx_buf[2];
static uint8_t rx_buf[2];

/* One blocking 16-bit word via the driver. Hardware CSN pulses around it. */
static uint16_t intan_transceive_word(uint16_t cmd)
{
	tx_buf[0] = (uint8_t)(cmd >> 8);
	tx_buf[1] = (uint8_t)cmd;
	nrfx_spim_xfer_desc_t x = NRFX_SPIM_XFER_TRX(tx_buf, 2, rx_buf, 2);
	nrfx_spim_xfer(&spim, &x, 0);
	return (uint16_t)((rx_buf[0] << 8) | rx_buf[1]);
}

/* Soft-CS variant: drive CSN as a plain GPIO around the word, like the
 * known-good P3 bring-up did (Intan requires CS to pulse high per word). */
static uint16_t intan_transceive_word_softcs(uint16_t cmd)
{
	nrf_gpio_pin_clear(PIN_CSN);
	k_busy_wait(1);
	uint16_t r = intan_transceive_word(cmd);
	k_busy_wait(1);
	nrf_gpio_pin_set(PIN_CSN);
	return r;
}

/* Keep the nrfx driver's hands off SPIM+0xC80 so each pass controls it. */
static void errata_flag_off(void)
{
#if NRF_ERRATA_STATIC_CHECK(54L, 55) || NRF_ERRATA_STATIC_CHECK(54L, 69)
	spim.cb.apply_nrf54l_errata_55_69 = 0;
#endif
}

/* One ROM read pass (regs 40-44, two-word pipeline lag), raw + ascii. */
static void rom_pass(const char *label, bool softcs)
{
	uint16_t (*xfer)(uint16_t) = softcs ? intan_transceive_word_softcs
					    : intan_transceive_word;
	xfer(READ(40));
	xfer(READ(41));
	uint16_t raw[5];
	char id[6] = { 0 };
	raw[0] = xfer(READ(42));
	raw[1] = xfer(READ(43));
	raw[2] = xfer(READ(44));
	raw[3] = xfer(READ(63));
	raw[4] = xfer(READ(63));
	for (int i = 0; i < 5; i++) {
		id[i] = (char)raw[i];
	}
	printk("%s: %04x %04x %04x %04x %04x  \"%s\"%s\n",
	       label, raw[0], raw[1], raw[2], raw[3], raw[4], id,
	       (raw[0] == 0x49 && raw[1] == 0x4e && raw[2] == 0x54) ? "  <<<< MATCH" : "");
}

int main(void)
{
	/* --- bring SPIM00 up: pins, 21.33 MHz, mode 0, hardware CSN --- */
	nrfx_spim_config_t cfg =
		NRFX_SPIM_DEFAULT_CONFIG(PIN_SCK, PIN_MOSI, PIN_MISO, PIN_CSN);
	cfg.frequency   = SCLK_HZ;
	cfg.mode        = NRF_SPIM_MODE_0;             
	cfg.bit_order   = NRF_SPIM_BIT_ORDER_MSB_FIRST;
	cfg.use_hw_ss   = true;                     
	cfg.ss_duration = CSNDUR_TICKS;

	int err = nrfx_spim_init(&spim, &cfg, NULL, NULL);
	if (err != 0) {
		printk("spim init failed: %d (-EINVAL would mean bad SCLK_HZ)\n", err);
		return 0;
	}

	errata_flag_off();

	/* P2 is the extra-high-drive port; stiffen the outputs for 21 MHz edges. */
#if defined(GPIO_PIN_CNF_DRIVE0_E0) || defined(GPIO_PIN_CNF_DRIVE_E0E1)
	nrf_gpio_cfg(PIN_SCK,  NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
		     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_E0E1, NRF_GPIO_PIN_NOSENSE);
	nrf_gpio_cfg(PIN_MOSI, NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
		     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_E0E1, NRF_GPIO_PIN_NOSENSE);
	nrf_gpio_cfg(PIN_CSN,  NRF_GPIO_PIN_DIR_OUTPUT, NRF_GPIO_PIN_INPUT_DISCONNECT,
		     NRF_GPIO_PIN_NOPULL, NRF_GPIO_PIN_E0E1, NRF_GPIO_PIN_NOSENSE);
#endif

	/* Margin map at full speed: which RXDELAY values read clean at 21.33 MHz. */
	for (uint32_t d = 0; d <= 7; d++) {
		*(volatile uint32_t *)((uintptr_t)NRF_SPIM00 + 0x5AC) = d;
		char lbl[24];
		snprintk(lbl, sizeof(lbl), "21MHz RXDELAY=%u   ", (unsigned)d);
		rom_pass(lbl, false);
	}

	/* Chosen operating point: RXDELAY 5 (39 ns after the sampling edge,
	 * centered in the measured-valid window; chip+switch round trip is
	 * ~25-30 ns, next bit arrives ~77 ns after the edge at 21.33 MHz). */
	*(volatile uint32_t *)((uintptr_t)NRF_SPIM00 + 0x5AC) = 5;
	rom_pass("run RXDELAY=5     ", false);

	/* --- TIMER00 as a pure hardware event counter --- */
	nrf_timer_mode_set(NRF_TIMER00, NRF_TIMER_MODE_COUNTER);
	nrf_timer_bit_width_set(NRF_TIMER00, NRF_TIMER_BIT_WIDTH_32);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_CLEAR);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_START);
	nrf_spim_publish_set(NRF_SPIM00, NRF_SPIM_EVENT_END, DPPI_CH);
	nrf_timer_subscribe_set(NRF_TIMER00, NRF_TIMER_TASK_COUNT, DPPI_CH);
	nrf_dppi_channels_enable(NRF_DPPIC00, BIT(DPPI_CH));

	/* --- free-run: one CONVERT(0) per transaction --- */
	tx_buf[0] = (uint8_t)(CONVERT(0) >> 8);
	tx_buf[1] = (uint8_t)CONVERT(0);
	nrf_spim_tx_buffer_set(NRF_SPIM00, tx_buf, 2);
	nrf_spim_rx_buffer_set(NRF_SPIM00, rx_buf, 2);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);
	nrf_spim_shorts_enable(NRF_SPIM00, NRF_SPIM_SHORT_END_START_MASK);
	nrf_spim_task_trigger(NRF_SPIM00, NRF_SPIM_TASK_START);

	k_busy_wait(100000);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_CAPTURE0);
	uint32_t c0 = nrf_timer_cc_get(NRF_TIMER00, NRF_TIMER_CC_CHANNEL0);
	k_busy_wait(MEASURE_SEC * 1000000u);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_CAPTURE1);
	uint32_t c1 = nrf_timer_cc_get(NRF_TIMER00, NRF_TIMER_CC_CHANNEL1);
	nrf_spim_shorts_disable(NRF_SPIM00, NRF_SPIM_SHORT_END_START_MASK);
	k_busy_wait(100);
	nrf_spim_task_trigger(NRF_SPIM00, NRF_SPIM_TASK_STOP);

	uint32_t wps = (c1 - c0) / MEASURE_SEC;
	printk("max sampling rate (SCLK %u Hz): %u S/s\n", SCLK_HZ, wps);
	printk("per-channel at 32 ch: %u S/s\n", wps / 32u);
	return 0;
}
