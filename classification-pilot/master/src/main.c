#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>
#include <math.h>
#include "templates.h"

/* ---- classification pilot ---------------------------------------------------
 * Same real signal path as signal-path-intan (FG -> Intan -> SPI -> nRF), but
 * instead of streaming raw samples the nRF classifies each window on-chip by
 * template matching (normalized cross-correlation vs. the templates in
 * templates.h) and sends the class id + timestamp + the window over BLE.
 * Time-domain shape only: no frequency / harmonic content is used, so this
 * rehearses the same method that works on real action-potential waveforms.
 * -------------------------------------------------------------------------- */

#define CH              0
#define SAMPLE_RATE_HZ  10000
#define WIN_LEN         100          /* samples per classification window       */
#define RING_SAMPLES    8192
#define SCORE_MIN       0.5f         /* best Pearson r below this -> "uncertain" */
#define CLASS_NONE      255

/* BLE packet (little-endian):
 *   [0..1]  seq        u16
 *   [2]     class_id   u8   (0..N_CLASSES-1, or 255 = uncertain)
 *   [3]     flags      u8   (reserved, 0)
 *   [4..7]  ts_ms      u32  (k_uptime_get_32 at window capture)
 *   [8..9]  score_q15  i16  (best Pearson r * 32767)
 *   [10..]  window     u16 * WIN_LEN (raw Intan codes, for the laptop plot)   */
#define HDR_LEN   10
#define PKT_LEN   (HDR_LEN + 2 * WIN_LEN)
BUILD_ASSERT(PKT_LEN <= 244, "packet exceeds ATT payload");
BUILD_ASSERT(WIN_LEN >= TEMPLATE_LEN, "window shorter than template");

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi22));
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));
#define CS_PIN 2

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
};

#define CMD_READ(r)    ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define CMD_WRITE(r,d) ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CMD_CONVERT(c) ((uint16_t)(((c) & 0x3F) << 8))
#define CMD_CALIBRATE  ((uint16_t)0x5500)

static uint16_t xfer(uint16_t cmd)
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
	return (uint16_t)((rx[0] << 8) | rx[1]);
}

static const uint16_t init_seq[] = {
	CMD_WRITE(0, 0xDE), CMD_WRITE(1, 32), CMD_WRITE(2, 40), CMD_WRITE(3, 0x00),
	CMD_WRITE(4, 0x00),
	CMD_WRITE(5, 0x00), CMD_WRITE(6, 0x00), CMD_WRITE(7, 0x00),
	CMD_WRITE(8, 17), CMD_WRITE(9, 0), CMD_WRITE(10, 16), CMD_WRITE(11, 0),
	CMD_WRITE(12, 5), CMD_WRITE(13, 1),
	CMD_WRITE(14, 0xFF), CMD_WRITE(15, 0xFF), CMD_WRITE(16, 0xFF), CMD_WRITE(17, 0xFF),
};

static void intan_init(void)
{
	xfer(CMD_READ(40));
	xfer(CMD_READ(41));
	char id[6] = {0};
	id[0] = xfer(CMD_READ(42)) & 0xFF;
	id[1] = xfer(CMD_READ(43)) & 0xFF;
	id[2] = xfer(CMD_READ(44)) & 0xFF;
	id[3] = xfer(CMD_READ(63)) & 0xFF;
	id[4] = xfer(CMD_READ(63)) & 0xFF;
	printk("ROM 40-44 = '%s'\n", id);

	for (int i = 0; i < ARRAY_SIZE(init_seq); i++) {
		xfer(init_seq[i]);
	}
	xfer(CMD_CALIBRATE);
	for (int i = 0; i < 9; i++) {
		xfer(CMD_READ(63));
	}
	printk("Intan configured (f 10 Hz - 10 kHz, amps on, ADC calibrated)\n");
}

/* ---- classifier: normalized cross-correlation (template matching) ---------- */

/* Slide each z-scored template across the window; at each lag compute the
 * Pearson correlation r between the window segment and the template, keep the
 * best lag; the class with the highest best-r wins. Sliding over all lags is
 * what makes this phase-invariant (the window need not start at a fixed point
 * in the cycle). Templates in templates.h are pre-normalized to mean 0 and
 * unit variance, so r = sum((seg-mean)*templ) / (M * std(seg)). */
static void classify(const float *win, uint8_t *cls, float *score)
{
	float best_r = -2.0f;
	uint8_t best_c = CLASS_NONE;

	for (int c = 0; c < N_CLASSES; c++) {
		for (int lag = 0; lag <= WIN_LEN - TEMPLATE_LEN; lag++) {
			const float *seg = &win[lag];

			float mean = 0.0f;
			for (int i = 0; i < TEMPLATE_LEN; i++) {
				mean += seg[i];
			}
			mean /= TEMPLATE_LEN;

			float var = 0.0f;
			for (int i = 0; i < TEMPLATE_LEN; i++) {
				float d = seg[i] - mean;
				var += d * d;
			}
			var /= TEMPLATE_LEN;
			float sd = sqrtf(var);
			if (sd < 1e-6f) {
				continue;          /* flat segment, no shape to match */
			}

			float dot = 0.0f;
			for (int i = 0; i < TEMPLATE_LEN; i++) {
				dot += (seg[i] - mean) * TEMPLATES[c][i];
			}
			float r = dot / ((float)TEMPLATE_LEN * sd);

			if (r > best_r) {
				best_r = r;
				best_c = c;
			}
		}
	}

	*score = best_r;
	*cls   = (best_r >= SCORE_MIN) ? best_c : CLASS_NONE;
}

/* ---- BLE ------------------------------------------------------------------- */

#define SVC_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define CHR_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(SVC_UUID);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(CHR_UUID);
static volatile bool notify_enabled;

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
}

BT_GATT_SERVICE_DEFINE(clf_svc,
	BT_GATT_PRIMARY_SERVICE(&svc_uuid),
	BT_GATT_CHARACTERISTIC(&chr_uuid.uuid, BT_GATT_CHRC_NOTIFY,
			       BT_GATT_PERM_NONE, NULL, NULL, NULL),
	BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (!err) {
		bt_conn_le_phy_update(conn, BT_CONN_LE_PHY_PARAM_2M);
	}
}
static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	notify_enabled = false;
}
BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
};

/* ---- acquisition (timer-paced sampler + ring buffer, as in signal-path) ---- */

static uint16_t ring[RING_SAMPLES];
static volatile uint32_t w_idx, r_idx;
static volatile uint32_t ring_drops;

K_SEM_DEFINE(tick_sem, 0, 1);
static void on_tick(struct k_timer *t) { k_sem_give(&tick_sem); }
K_TIMER_DEFINE(samp_timer, on_tick, NULL);

static void sampler_thread(void *a, void *b, void *c)
{
	while (1) {
		while (!notify_enabled) {
			k_msleep(10);
		}
		xfer(CMD_CONVERT(CH));
		xfer(CMD_CONVERT(CH));
		w_idx = r_idx = 0;
		ring_drops = 0;
		k_timer_start(&samp_timer, K_USEC(1000000 / SAMPLE_RATE_HZ),
				          K_USEC(1000000 / SAMPLE_RATE_HZ));

		while (notify_enabled) {
			k_sem_take(&tick_sem, K_FOREVER);
			uint16_t s = xfer(CMD_CONVERT(CH));
			uint32_t nw = (w_idx + 1) % RING_SAMPLES;
			if (nw != r_idx) {
				ring[w_idx] = s;
				w_idx = nw;
			} else {
				ring_drops++;
			}
		}
		k_timer_stop(&samp_timer);
	}
}
K_THREAD_DEFINE(sampler_id, 1536, sampler_thread, NULL, NULL, NULL,
		K_PRIO_COOP(7), 0, 0);

int main(void)
{
	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);
	intan_init();

	if (bt_enable(NULL) != 0 ||
	    bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
					    BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			    ad, ARRAY_SIZE(ad), NULL, 0) != 0) {
		printk("BLE init failed\n");
		return 0;
	}
	printk("advertising as '%s' - connect and subscribe\n", CONFIG_BT_DEVICE_NAME);

	uint8_t pkt[PKT_LEN];
	uint16_t seq = 0;
	static float    win[WIN_LEN];
	static uint16_t raw[WIN_LEN];

	while (1) {
		while (!notify_enabled) {
			k_msleep(20);
		}
		printk("subscribed - classifying ch%d, %d-sample windows at %d S/s\n",
		       CH, WIN_LEN, SAMPLE_RATE_HZ);
		seq = 0;

		while (notify_enabled) {
			uint32_t avail = (w_idx + RING_SAMPLES - r_idx) % RING_SAMPLES;
			if (avail < WIN_LEN) {
				k_msleep(1);
				continue;
			}

			for (int i = 0; i < WIN_LEN; i++) {
				uint16_t s = ring[r_idx];
				r_idx = (r_idx + 1) % RING_SAMPLES;
				raw[i] = s;
				win[i] = (float)s;   /* z-score in classify() removes offset/scale */
			}
			uint32_t ts = k_uptime_get_32();

			uint8_t cls;
			float score;
			classify(win, &cls, &score);
			int16_t sq = (int16_t)(score * 32767.0f);

			pkt[0] = seq;
			pkt[1] = seq >> 8;
			pkt[2] = cls;
			pkt[3] = 0;
			pkt[4] = ts;
			pkt[5] = ts >> 8;
			pkt[6] = ts >> 16;
			pkt[7] = ts >> 24;
			pkt[8] = sq;
			pkt[9] = sq >> 8;
			for (int i = 0; i < WIN_LEN; i++) {
				pkt[HDR_LEN + 2 * i]     = raw[i];
				pkt[HDR_LEN + 2 * i + 1] = raw[i] >> 8;
			}

			int err;
			do {
				err = bt_gatt_notify(NULL, &clf_svc.attrs[1], pkt, PKT_LEN);
				if (err) {
					k_yield();
				}
			} while (err && notify_enabled);
			seq++;

			if ((seq % 100) == 0 && ring_drops) {
				printk("ring drops %u (lower SAMPLE_RATE_HZ or WIN_LEN)\n", ring_drops);
			}
		}
		printk("unsubscribed\n");
	}
	return 0;
}
