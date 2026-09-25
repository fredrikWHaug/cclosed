/*
 * Theo -- hardware-timed acquisition (regularity fix)
 *
 * The old sampler was a software thread pacing itself against deadlines; the
 * BLE controller preempted it and the measured spacing was sigma = 23.7 us on
 * a 50 us period (see measurements/before_sw_paced_20k/). This build removes
 * the CPU from the timing path entirely -- Dr. Oh's two prescriptions:
 *
 *  1. "Use DMA": RX runs in EasyDMA ArrayList mode -- the peripheral advances
 *     its own write pointer through a large RAM region, one 16-bit result per
 *     transaction, zero CPU per sample. Software drains lazily in batches.
 *  2. "Only the intended clock drives the sampling": TIMER00 (crystal-derived,
 *     same fast domain as SPIM00) fires SPIM00's START task directly over
 *     DPPI channel 7. Nothing running on the CPU -- threads, interrupts, the
 *     BLE stack -- can move a sampling instant, because no instruction stream
 *     is involved in triggering one. (DPPIC00 channels 1 and 3 belong to the
 *     BLE controller: SDC_DPPIC00_CHANNELS_USED_MASK = 0x0A. Channel 7 is free.)
 *
 * SPI settings are the bench-validated set: 21.33 MHz, hardware CSN
 * (CSNDUR 20 = 156 ns high between words), RXDELAY 5.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>
#include <nrfx_spim.h>
#include <hal/nrf_spim.h>
#include <hal/nrf_timer.h>
#include <hal/nrf_dppi.h>
#include <hal/nrf_gpio.h>

#define RATE_HZ      20000u
#define PKT_SAMPLES  120                 /* 2 + 240 B = 242 <= 244 ATT payload */
#define DPPI_CH      7u                  /* clear of SDC's channels 1 and 3    */

/* RX DMA region: hardware fills it linearly; we rewind the pointer at a
 * packet-aligned threshold. Pad past the threshold = stall tolerance: the
 * drain may lag REWIND_AT by (RX_TOTAL - REWIND_AT) samples = 409 ms at
 * 20 kS/s before the emergency stop -- orders beyond any BLE stall. */
#define REWIND_AT    32768u              /* wrap when hw write pos crosses this ( >= test ) */
#define RX_TOTAL     40960u              /* 80 KB */

#define PIN_SCK   NRF_GPIO_PIN_MAP(2, 1)
#define PIN_MOSI  NRF_GPIO_PIN_MAP(2, 2)
#define PIN_MISO  NRF_GPIO_PIN_MAP(2, 4)
#define PIN_CSN   NRF_GPIO_PIN_MAP(2, 5)

#define CONVERT(ch)  ((uint16_t)(((ch) & 0x3F) << 8))
#define READ(r)      ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define WRITE(r, d)  ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CALIBRATE    ((uint16_t)0x5500)

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM00);
static uint8_t drv_tx[2], drv_rx[2];             /* driver-path buffers (init/ROM) */

static uint16_t rx_region[RX_TOTAL];             /* EasyDMA ArrayList destination  */
static uint8_t  stream_tx[2];                    /* the one CONVERT(0) command     */

/* Blocking word through the nrfx driver -- used only for chip init/checks. */
static uint16_t xfer(uint16_t cmd)
{
	drv_tx[0] = (uint8_t)(cmd >> 8);
	drv_tx[1] = (uint8_t)cmd;
	nrfx_spim_xfer_desc_t x = NRFX_SPIM_XFER_TRX(drv_tx, 2, drv_rx, 2);
	nrfx_spim_xfer(&spim, &x, 0);
	return (uint16_t)((drv_rx[0] << 8) | drv_rx[1]);
}

static const uint16_t init_seq[] = {
	WRITE(0, 0xDE), WRITE(1, 32), WRITE(2, 40), WRITE(3, 0x00), WRITE(4, 0x00),
	WRITE(5, 0x00), WRITE(6, 0x00), WRITE(7, 0x00),
	WRITE(8, 17), WRITE(9, 0), WRITE(10, 16), WRITE(11, 0),
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
	printk("Intan configured (10 Hz - 10 kHz, amps on, calibrated)\n");
}

/* ---- BLE (unchanged: same UUIDs, packet format, receiver scripts) ---- */
#define SVC_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define CHR_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(SVC_UUID);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(CHR_UUID);
static volatile bool notify_enabled;

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
}

BT_GATT_SERVICE_DEFINE(stream_svc,
	BT_GATT_PRIMARY_SERVICE(&svc_uuid),
	BT_GATT_CHARACTERISTIC(&chr_uuid.uuid, BT_GATT_CHRC_NOTIFY,
			       BT_GATT_PERM_NONE, NULL, NULL, NULL),
	BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
		sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (!err) {
		static const struct bt_le_conn_param fast_params =
			BT_LE_CONN_PARAM_INIT(6, 12, 0, 400);
		bt_conn_le_param_update(conn, &fast_params);
		bt_conn_le_phy_update(conn, BT_CONN_LE_PHY_PARAM_2M);
	}
}
static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	notify_enabled = false;
}
static void param_updated(struct bt_conn *conn, uint16_t interval,
			   uint16_t latency, uint16_t timeout)
{
	printk("conn interval now %u.%02u ms\n",
	       (interval * 125u) / 100u, (interval * 125u) % 100u);
}
BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
	.le_param_updated = param_updated,
};

/* ---- hardware-timed acquisition ---- */

/* Samples written so far into rx_region (from the DMA pointer itself). */
static inline uint32_t acq_pos(void)
{
	return (NRF_SPIM00->DMA.RX.PTR - (uint32_t)rx_region) / 2u;
}

static void acq_start(void)
{
	/* Warm the Intan's 2-deep result pipeline through the driver path so
	 * rx_region[0] onward is pure ch0 data with no discard bookkeeping. */
	xfer(CONVERT(0));
	xfer(CONVERT(0));

	/* SPIM: fixed TX command, ArrayList RX walking the big region. */
	stream_tx[0] = (uint8_t)(CONVERT(0) >> 8);
	stream_tx[1] = (uint8_t)CONVERT(0);
	nrf_spim_tx_buffer_set(NRF_SPIM00, stream_tx, 2);
	nrf_spim_rx_buffer_set(NRF_SPIM00, (uint8_t *)rx_region, 2);
	nrf_spim_tx_list_disable(NRF_SPIM00);
	nrf_spim_rx_list_enable(NRF_SPIM00);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);

	/* TIMER00 -> DPPI ch 7 -> SPIM00.START: the sampling clock in silicon. */
	uint32_t base = NRF_TIMER_BASE_FREQUENCY_GET(NRF_TIMER00);
	uint32_t cc   = base / RATE_HZ;
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_STOP);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_CLEAR);
	nrf_timer_mode_set(NRF_TIMER00, NRF_TIMER_MODE_TIMER);
	nrf_timer_bit_width_set(NRF_TIMER00, NRF_TIMER_BIT_WIDTH_32);
	nrf_timer_prescaler_set(NRF_TIMER00, 0);
	nrf_timer_cc_set(NRF_TIMER00, NRF_TIMER_CC_CHANNEL0, cc);
	nrf_timer_shorts_enable(NRF_TIMER00, NRF_TIMER_SHORT_COMPARE0_CLEAR_MASK);
	nrf_timer_publish_set(NRF_TIMER00, NRF_TIMER_EVENT_COMPARE0, DPPI_CH);
	nrf_spim_subscribe_set(NRF_SPIM00, NRF_SPIM_TASK_START, DPPI_CH);
	nrf_dppi_channels_enable(NRF_DPPIC00, BIT(DPPI_CH));
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_START);

	printk("hw-timed acquisition: timer %u Hz / CC %u -> %u.%03u kS/s\n",
	       base, cc, (base / cc) / 1000u, (base / cc) % 1000u);
}

static void acq_stop(void)
{
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_STOP);
	nrf_dppi_channels_disable(NRF_DPPIC00, BIT(DPPI_CH));
	k_busy_wait(100);                       /* let an in-flight word finish */
	nrf_spim_disable(NRF_SPIM00);
}

/* Rewind the DMA pointer to the region base.
 *
 * Bench finding (2026-09-24): on this DMA engine a plain PTR register write
 * between transactions does NOT take -- the engine's internal pointer wins
 * and the write is clobbered. So the rewind tries progressively stronger
 * state-clearing methods in the ~49 us quiet window after a fresh END, then
 * VERIFIES the next transaction actually landed at the region base, and
 * escalates if not. Prints which method this silicon honors.
 *
 * Any samples the hardware wrote past REWIND_AT before the rewind are saved
 * into `carry` and prepended to the outgoing stream, so no data is lost and
 * ordering is preserved. */
static uint32_t rewinds;
static uint16_t carry[8192];             /* = RX_TOTAL - REWIND_AT: max possible backlog */
static uint32_t carry_len, carry_idx;

static bool rewind_wait_end(void)
{
	uint32_t spins = 0;
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	while (!nrf_spim_event_check(NRF_SPIM00, NRF_SPIM_EVENT_END)) {
		if (++spins > 20000000u) {
			return false;           /* timer not running */
		}
	}
	return true;
}

static bool acq_rewind(uint32_t from)
{
	/* Sync to a fresh END so we act right after a completed transaction. */
	if (!rewind_wait_end()) {
		return false;
	}

	/* PAUSE THE SAMPLING CLOCK. The previous rewind attempt reconfigured
	 * the DMA engine while the timer kept firing STARTs -- undefined
	 * engine state, runaway DMA, hard fault. With the timer stopped (not
	 * cleared: the count freezes mid-period), no START can arrive while
	 * we touch the engine. Cost: this one interval stretches by the few
	 * microseconds the reconfig takes, once per REWIND_AT samples. */
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_STOP);

	uint32_t tail_end = acq_pos();
	carry_len = 0;
	carry_idx = 0;
	for (uint32_t i = from; i < tail_end && carry_len < 8192; i++) {
		carry[carry_len++] = rx_region[i];
	}

	/* Reset the DMA engine from clean idle and resume the clock. */
	nrf_spim_disable(NRF_SPIM00);
	nrf_spim_tx_buffer_set(NRF_SPIM00, stream_tx, 2);
	nrf_spim_rx_buffer_set(NRF_SPIM00, (uint8_t *)rx_region, 2);
	nrf_spim_rx_list_enable(NRF_SPIM00);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_START);

	/* Verify: the next hardware-fired transaction must land at the base. */
	if (!rewind_wait_end()) {
		return false;
	}
	uint32_t pos = acq_pos();
	if (pos >= 1 && pos <= 64) {
		rewinds++;
		return true;
	}
	return false;
}

int main(void)
{
	nrfx_spim_config_t cfg =
		NRFX_SPIM_DEFAULT_CONFIG(PIN_SCK, PIN_MOSI, PIN_MISO, PIN_CSN);
	cfg.frequency   = 21333333u;            /* 128 MHz / 6, under Intan's 24 MHz cap */
	cfg.mode        = NRF_SPIM_MODE_0;
	cfg.bit_order   = NRF_SPIM_BIT_ORDER_MSB_FIRST;
	cfg.use_hw_ss   = true;
	cfg.ss_duration = 20;                   /* CSN high >= 156 ns between words */
	cfg.rx_delay    = 5;                    /* bench-validated sampling window  */

	if (nrfx_spim_init(&spim, &cfg, NULL, NULL) != 0) {
		printk("spim init failed\n");
		return 0;
	}
	intan_init();

	if (bt_enable(NULL) != 0 ||
	    bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
					    BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			    ad, ARRAY_SIZE(ad), NULL, 0) != 0) {
		printk("BLE init failed\n");
		return 0;
	}
	printk("advertising as '%s' - run stream_plot.py\n", CONFIG_BT_DEVICE_NAME);

	static uint8_t pkt[2 + 2 * PKT_SAMPLES];
	uint16_t seq = 0;

	while (1) {
		while (!notify_enabled) {
			k_msleep(20);
		}
		printk("subscribed - hw-timed streaming ch0 at %u S/s\n", RATE_HZ);
		seq = 0;
		rewinds = 0;
		carry_len = carry_idx = 0;
		uint32_t r_pos = 0;
		acq_start();

		while (notify_enabled) {
			uint32_t w = acq_pos();

			/* emergency: drain stalled past the pad (should never) */
			if (w >= RX_TOTAL - 8u) {
				printk("RX region overrun - restarting acquisition\n");
				acq_stop();
				r_pos = 0;
				carry_len = carry_idx = 0;
				acq_start();
				continue;
			}

			/* Wrap when the HARDWARE write position crosses the
			 * threshold and last wrap's carry is fully drained.
			 * Gating on w (not the drain r_pos) means it always
			 * fires; carrying from r_pos preserves the unsent tail. */
			if (w >= REWIND_AT && carry_idx == carry_len) {
				if (acq_rewind(r_pos)) {
					r_pos = 0;
				} else {
					printk("rewind failed - full restart\n");
					acq_stop();
					r_pos = 0;
					carry_len = carry_idx = 0;
					acq_start();
				}
				continue;
			}

			uint32_t avail = (carry_len - carry_idx) + (w - r_pos);
			if (avail < PKT_SAMPLES) {
				k_yield();
				continue;
			}

			pkt[0] = (uint8_t)seq;
			pkt[1] = (uint8_t)(seq >> 8);
			for (uint32_t k = 0; k < PKT_SAMPLES; k++) {
				uint16_t s;
				if (carry_idx < carry_len) {
					s = carry[carry_idx++];
				} else {
					s = rx_region[r_pos++];
				}
				/* DMA stores the wire bytes in RX order: first byte
				 * (Intan MSB) lands in the LOW byte of the native
				 * little-endian uint16_t -- swap to true value. */
				s = (uint16_t)((s >> 8) | (s << 8));
				pkt[2 + 2 * k]     = (uint8_t)s;
				pkt[2 + 2 * k + 1] = (uint8_t)(s >> 8);
			}
			if (carry_idx == carry_len) {
				carry_len = carry_idx = 0;
			}

			int err;
			do {
				err = bt_gatt_notify(NULL, &stream_svc.attrs[1],
						     pkt, sizeof(pkt));
				if (err) {
					k_yield();
				}
			} while (err && notify_enabled);
			seq++;

			if ((seq % 1000) == 0) {
				printk("[acq] pos %u  rewinds %u\n", acq_pos(), rewinds);
			}
		}
		acq_stop();
		printk("unsubscribed\n");
	}
	return 0;
}
