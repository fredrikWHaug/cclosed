/*
 * Theo -- streaming proof of concept
 *
 * Sample Intan ch0 at exactly 30 kS/s and stream every sample to the laptop
 * over BLE. Bench check: a 1 kHz sine at in0 should show ~30 points/period
 * in stream_plot.py.
 *
 * SPI is the bench-validated SPIM00 path (21.33 MHz, hardware CSN, RXDELAY 5
 * -- see ratetest_main.c.keep and ideas/SPI_bringup_plan.md for the story).
 * Intan register init and the BLE plumbing are lifted from the proven
 * legacy classification-pilot. Sampling is paced by absolute GRTC deadlines
 * (k_timer ticks are too coarse for 33.3 us).
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>
#include <nrfx_spim.h>
#include <hal/nrf_gpio.h>

#define RATE_HZ      20000u  /* safe margin under the ~26-28k S/s BLE ceiling macOS grants (15 ms conn interval) */
#define PKT_SAMPLES  120                       /* 2 + 240 B = 242 <= 244 ATT */
#define RING_SAMPLES 8192

#define PIN_SCK   NRF_GPIO_PIN_MAP(2, 1)       /* SPIM00 dedicated pads */
#define PIN_MOSI  NRF_GPIO_PIN_MAP(2, 2)
#define PIN_MISO  NRF_GPIO_PIN_MAP(2, 4)
#define PIN_CSN   NRF_GPIO_PIN_MAP(2, 5)

#define CONVERT(ch)  ((uint16_t)(((ch) & 0x3F) << 8))
#define READ(r)      ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define WRITE(r, d)  ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CALIBRATE    ((uint16_t)0x5500)

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM00);
static uint8_t tx_buf[2], rx_buf[2];

static uint16_t xfer(uint16_t cmd)
{
	tx_buf[0] = (uint8_t)(cmd >> 8);
	tx_buf[1] = (uint8_t)cmd;
	nrfx_spim_xfer_desc_t x = NRFX_SPIM_XFER_TRX(tx_buf, 2, rx_buf, 2);
	nrfx_spim_xfer(&spim, &x, 0);
	return (uint16_t)((rx_buf[0] << 8) | rx_buf[1]);
}

/* Register init from the legacy pilot: 10 Hz - 10 kHz band, all amps on. */
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

/* ---- BLE (UUIDs shared with the legacy receiver scripts) ---- */
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
		/* Default connection interval is far too slow to drain 250
		 * pkts/s (30 kS/s / 120 samples). Ask for the fastest legal
		 * interval; whether the central honors it is another matter
		 * (see the printed connection-parameter log line). */
		static const struct bt_le_conn_param fast_params =
			BT_LE_CONN_PARAM_INIT(6, 12, 0, 400); /* 7.5-15 ms */
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
	/* interval is in 1.25 ms units. At 120 samples/pkt, 30 kS/s needs a
	 * packet every 4 ms -> interval must be well under ~3.2 units (4 ms)
	 * to have room for one notification per connection event. */
	printk("conn interval now %u.%02u ms (need <~4 ms for 30 kS/s)\n",
	       (interval * 125u) / 100u, (interval * 125u) % 100u);
}
BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
	.le_param_updated = param_updated,
};

/* ---- 30 kS/s sampler: absolute deadlines on the system cycle counter ---- */
static uint16_t ring[RING_SAMPLES];
static volatile uint32_t w_idx, r_idx, ring_drops;

static void sampler_thread(void *a, void *b, void *c)
{
	while (1) {
		while (!notify_enabled) {
			k_msleep(10);
		}
		xfer(CONVERT(0)); xfer(CONVERT(0));   /* prime the 2-deep pipeline */
		w_idx = r_idx = ring_drops = 0;

		uint32_t start = k_cycle_get_32();
		uint64_t n = 0;

		while (notify_enabled) {
			uint32_t target = start + (uint32_t)((++n *
				(uint64_t)CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC) / RATE_HZ);
			while ((int32_t)(k_cycle_get_32() - target) < 0) {
				k_yield();
			}
			uint16_t s = xfer(CONVERT(0));
			uint32_t nw = (w_idx + 1) % RING_SAMPLES;
			if (nw != r_idx) {
				ring[w_idx] = s;
				w_idx = nw;
			} else {
				ring_drops++;
			}
		}
	}
}
K_THREAD_DEFINE(sampler_id, 2048, sampler_thread, NULL, NULL, NULL,
		K_PRIO_PREEMPT(0), 0, 0);

int main(void)
{
	nrfx_spim_config_t cfg =
		NRFX_SPIM_DEFAULT_CONFIG(PIN_SCK, PIN_MOSI, PIN_MISO, PIN_CSN);
	cfg.frequency   = 21333333u;              /* 128 MHz / 6 */
	cfg.mode        = NRF_SPIM_MODE_0;
	cfg.bit_order   = NRF_SPIM_BIT_ORDER_MSB_FIRST;
	cfg.use_hw_ss   = true;
	cfg.ss_duration = 20;                     /* CSN high >= 156 ns */
	cfg.rx_delay    = 5;                      /* the bench-found sampling fix */

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
		printk("subscribed - streaming ch0 at %u S/s\n", RATE_HZ);
		seq = 0;

		while (notify_enabled) {
			uint32_t avail = (w_idx + RING_SAMPLES - r_idx) % RING_SAMPLES;
			if (avail < PKT_SAMPLES) {
				k_yield();
				continue;
			}
			pkt[0] = (uint8_t)seq;
			pkt[1] = (uint8_t)(seq >> 8);
			for (int i = 0; i < PKT_SAMPLES; i++) {
				uint16_t s = ring[r_idx];
				r_idx = (r_idx + 1) % RING_SAMPLES;
				pkt[2 + 2 * i]     = (uint8_t)s;
				pkt[2 + 2 * i + 1] = (uint8_t)(s >> 8);
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

			if ((seq % 250) == 0 && ring_drops) {
				printk("ring drops: %u\n", ring_drops);
			}
		}
		printk("unsubscribed\n");
	}
	return 0;
}
