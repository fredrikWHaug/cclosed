/*
 * signal-path MASTER — fetch SAADC frames from the slave over SPI, stream the
 * samples to the host over BLE.
 *
 * Polls the slave (manual CS, whole frame under one CS), validates SYNC +
 * checksum, dedupes on the frame seq (the slave re-serves the same frame until
 * a new buffer completes), then forwards each new frame as two 244-byte
 * notifications:
 *
 *     [ seq lo ][ seq hi ][ half 0|1 ][ n=120 ][ 120 x int16 LE samples ]
 */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>

#define NS_F 240
#define SYNC_WORD 0x7FFFu
#define FT (NS_F + 3)
#define CS_PIN 2
#define HALF (NS_F / 2)
#define PAYLOAD (4 + HALF * 2)

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi22));
static const struct device *gpio3 = DEVICE_DT_GET(DT_NODELABEL(gpio3));
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
	.slave = 0,
};

static uint8_t txz[FT * 2];
static uint8_t rx[FT * 2];

static uint16_t gw(int i)
{
	return (uint16_t)((rx[i * 2] << 8) | rx[i * 2 + 1]);
}

#define SVC_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define CHR_UUID BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(SVC_UUID);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(CHR_UUID);
static volatile bool notify_enabled;

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
}

BT_GATT_SERVICE_DEFINE(sig_svc,
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

int main(void)
{
	printk("=== signal-path MASTER: SPI fetch -> BLE stream ===\n");
	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);

	if (bt_enable(NULL) != 0) {
		printk("BLE init failed\n");
		return 0;
	}
	if (bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
					    BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			    ad, ARRAY_SIZE(ad), NULL, 0) != 0) {
		printk("advertising failed\n");
		return 0;
	}
	printk("advertising as '%s' - connect and subscribe\n", CONFIG_BT_DEVICE_NAME);

	uint16_t last_seq = 0;
	bool have_seq = false;
	uint32_t frames = 0, skipped = 0;

	while (1) {
		if (!notify_enabled) {
			k_msleep(50);
			have_seq = false;
			continue;
		}

		struct spi_buf tb = { .buf = txz, .len = sizeof(txz) };
		struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
		struct spi_buf rb = { .buf = rx, .len = sizeof(rx) };
		struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

		gpio_pin_set(gpio3, CS_PIN, 0);
		k_busy_wait(50);
		spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
		k_busy_wait(50);
		gpio_pin_set(gpio3, CS_PIN, 1);

		if (gw(1) != SYNC_WORD) {
			k_msleep(1);
			continue;
		}
		uint16_t sum = 0;
		for (int i = 0; i < NS_F; i++) {
			sum = (uint16_t)(sum + gw(2 + i));
		}
		if (sum != gw(NS_F + 2)) {
			k_msleep(1);
			continue;
		}

		uint16_t s = gw(0);
		if (have_seq && s == last_seq) {
			k_msleep(1);
			continue;
		}
		if (have_seq) {
			skipped += (uint16_t)(s - last_seq) - 1;
		}
		last_seq = s;
		have_seq = true;

		for (int half = 0; half < 2; half++) {
			uint8_t pay[PAYLOAD];

			pay[0] = (uint8_t)s;
			pay[1] = (uint8_t)(s >> 8);
			pay[2] = (uint8_t)half;
			pay[3] = HALF;
			for (int i = 0; i < HALF; i++) {
				uint16_t w = gw(2 + half * HALF + i);
				pay[4 + 2 * i] = (uint8_t)w;
				pay[5 + 2 * i] = (uint8_t)(w >> 8);
			}
			while (bt_gatt_notify(NULL, &sig_svc.attrs[1], pay, PAYLOAD) != 0) {
				k_msleep(1);
			}
		}

		if (++frames % 500 == 0) {
			printk("frames %u  skipped %u\n", frames, skipped);
		}
	}
	return 0;
}
