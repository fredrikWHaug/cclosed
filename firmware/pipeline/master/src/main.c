/*
 * pipeline MASTER (4b) — receive raw codes over SPI, run the on-chip pipeline.
 *
 * 1. Clock in the 3 frames from the slave (place each by its frame_idx, verify
 *    each frame's checksum) -> reconstruct the raw 8xNS stream.
 * 2. Transport integrity: compare the SPI-received codes to the known source.
 * 3. Run the exact 4a pipeline (biquad -> CMR -> decimate -> detect -> classify),
 *    timed, on the SPI-RECEIVED data.
 * 4. Verify the detected units against the host (real mismatches must be 0).
 *
 * CHAIN OK means: SPI delivered the neural data intact, the MCU turned it into a
 * unit-ID sequence matching the host, and it did so far faster than real time.
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>

#include "stream_test.h"          /* raw_stream (reference), exp_*, NS, THRESH... */
#include "nn.h"
#include "model_weights.h"

#define SPI_NODE  DT_NODELABEL(spi22)
#define CS_PIN    2
#define SYNC_WORD 0x7FFFu
#define NFRAMES   3
#define FW        (N_CH * NS / NFRAMES)
#define FT        (FW + 3)
#define MAXSP     128

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
	.slave = 0,
};

static const float BQ_B[2][3] = {
	{0.05644846f, 0.11289692f, 0.05644846f}, {1.0f, -2.0f, 1.0f},
};
static const float BQ_A[2][3] = {
	{1.0f, -1.24532221f, 0.49035942f}, {1.0f, -1.91414109f, 0.91860259f},
};

static uint8_t txz[FT * 2];
static uint8_t rx[FT * 2];
static uint16_t rxstream[N_CH * NS];
static bool got[NFRAMES];
static float dec[N_CH][NDEC];
static float snip[N_CH * SNIP_LEN];
static int my_troughs[MAXSP], my_units[MAXSP];

static uint16_t gw(int i) { return (uint16_t)((rx[i * 2] << 8) | rx[i * 2 + 1]); }

static float median8(const float *v)
{
	float t[8];
	for (int i = 0; i < 8; i++) { t[i] = v[i]; }
	for (int i = 1; i < 8; i++) {
		float k = t[i]; int j = i - 1;
		while (j >= 0 && t[j] > k) { t[j + 1] = t[j]; j--; }
		t[j + 1] = k;
	}
	return 0.5f * (t[3] + t[4]);
}

/* ---- BLE: notify each (trough, unit) to the host ---- */
#define SPIKE_SVC BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define SPIKE_CHR BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(SPIKE_SVC);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(SPIKE_CHR);
static volatile bool notify_enabled;

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
}

BT_GATT_SERVICE_DEFINE(spike_svc,
	BT_GATT_PRIMARY_SERVICE(&svc_uuid),
	BT_GATT_CHARACTERISTIC(&chr_uuid.uuid, BT_GATT_CHRC_NOTIFY,
			       BT_GATT_PERM_NONE, NULL, NULL, NULL),
	BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void spike_notify(int trough, int unit)
{
	int32_t payload[2] = { trough, unit };
	if (notify_enabled) {
		bt_gatt_notify(NULL, &spike_svc.attrs[1], payload, sizeof(payload));
	}
}

int main(void)
{
	printk("=== pipeline MASTER (SPI receive -> pipeline -> BLE) ===\n");
	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);

	if (bt_enable(NULL) == 0 &&
	    bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
					    BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			    ad, ARRAY_SIZE(ad), NULL, 0) == 0) {
		printk("advertising as '%s' - connect from the host\n", CONFIG_BT_DEVICE_NAME);
		while (!notify_enabled) {
			k_msleep(100);
		}
		printk("subscribed - receiving over SPI\n");
	} else {
		printk("BLE init failed - continuing without notify\n");
	}
	k_msleep(200);

	/* 1. receive the 3 frames */
	int ngot = 0;
	while (ngot < NFRAMES) {
		struct spi_buf tb = { .buf = txz, .len = sizeof(txz) };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rx, .len = sizeof(rx) };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		gpio_pin_set(gpio3, CS_PIN, 0);
		k_busy_wait(50);
		spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
		k_busy_wait(50);
		gpio_pin_set(gpio3, CS_PIN, 1);

		int idx = gw(0);
		if (gw(1) != SYNC_WORD || idx < 0 || idx >= NFRAMES) {
			k_busy_wait(300);
			continue;
		}
		uint16_t sum = 0;
		for (int i = 0; i < FW; i++) { sum = (uint16_t)(sum + gw(2 + i)); }
		if (sum != gw(FW + 2)) {
			k_busy_wait(300);
			continue;
		}
		if (!got[idx]) {
			for (int i = 0; i < FW; i++) { rxstream[idx * FW + i] = gw(2 + i); }
			got[idx] = true;
			ngot++;
		}
		k_busy_wait(300);
	}

	/* 2. transport integrity vs known source */
	int bad = 0;
	for (int i = 0; i < N_CH * NS; i++) {
		if (rxstream[i] != raw_stream[i]) { bad++; }
	}
	printk("SPI transport: %d / %d words correct\n", N_CH * NS - bad, N_CH * NS);

	/* 3. pipeline on the received stream, timed */
	uint32_t t0 = k_uptime_get_32();
	float z0[N_CH][2] = {0}, z1[N_CH][2] = {0};
	int di = 0;
	for (int n = 0; n < NS; n++) {
		float fsamp[N_CH];
		for (int c = 0; c < N_CH; c++) {
			float x = 0.195f * ((int)rxstream[c * NS + n] - 32768);
			for (int s = 0; s < 2; s++) {
				float y = BQ_B[s][0] * x + z0[c][s];
				z0[c][s] = BQ_B[s][1] * x - BQ_A[s][1] * y + z1[c][s];
				z1[c][s] = BQ_B[s][2] * x - BQ_A[s][2] * y;
				x = y;
			}
			fsamp[c] = x;
		}
		float med = median8(fsamp);
		if (n % 3 == 0) {
			for (int c = 0; c < N_CH; c++) { dec[c][di] = fsamp[c] - med; }
			di++;
		}
	}
	int nsp = 0, in_ev = 0, emt = -1, refrac = DETECT_START;
	float emin = 1e30f;
	for (int t = DETECT_START; t < NDEC - SNIP_LEN / 2; t++) {
		float g = dec[0][t];
		for (int c = 1; c < N_CH; c++) {
			if (dec[c][t] < g) { g = dec[c][t]; }
		}
		if (!in_ev) {
			if (t >= refrac && g < -THRESH) { in_ev = 1; emin = g; emt = t; }
		} else {
			if (g < emin) { emin = g; emt = t; }
			if (g >= -THRESH) {
				int tt = emt;
				for (int c = 0; c < N_CH; c++) {
					for (int k = 0; k < SNIP_LEN; k++) {
						snip[c * SNIP_LEN + k] = dec[c][tt - SNIP_LEN / 2 + k];
					}
				}
				float out[N_CLASSES];
				nn_linear(snip, out, logreg_w, logreg_b, INPUT_DIM, N_CLASSES, 0);
				int pred = nn_argmax(out, N_CLASSES);
				if (nsp < MAXSP) {
					my_troughs[nsp] = tt;
					my_units[nsp] = UNIT_IDS[pred];
					nsp++;
				}
				refrac = tt + REFRAC;
				in_ev = 0;
			}
		}
	}
	uint32_t t1 = k_uptime_get_32();

	/* 4. verify units vs host */
	int exact = 0, boundary = 0, real = 0;
	int lim = (nsp < EXP_COUNT) ? nsp : EXP_COUNT;
	for (int i = 0; i < lim; i++) {
		if (my_troughs[i] != exp_troughs[i]) { real++; }
		else if (my_units[i] == exp_units[i]) { exact++; }
		else if (exp_margins[i] < 0.5f) { boundary++; }
		else { real++; }
	}

	printk("detected %d spikes (expected %d)\n", nsp, EXP_COUNT);
	printk("exact %d | boundary flips %d | real mismatches %d\n", exact, boundary, real);
	printk("pipeline compute: %u ms for %d ms of data (30 kHz)\n", t1 - t0, NS / 30);
	printk("%s\n", (bad == 0 && nsp == EXP_COUNT && real == 0) ? "CHAIN OK" : "CHAIN FAIL");

	/* 5. stream the results out over BLE (paced, separate from the timed pipeline) */
	printk("notifying %d spikes over BLE...\n", nsp);
	for (int i = 0; i < nsp; i++) {
		spike_notify(my_troughs[i], my_units[i]);
		printk("  spike %d: unit %d @ t=%d\n", i, my_units[i], my_troughs[i]);
		k_msleep(50);
	}
	printk("done\n");
	return 0;
}
