#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>

#define SPI_NODE    DT_NODELABEL(spi22)
#define CS_PIN      2       /* P3.02, driven manually */
#define PAYLOAD_MAX 244     /* upper bound; actual send size = negotiated MTU - 3 */

static const struct device *spi_dev = DEVICE_DT_GET(SPI_NODE);
static const struct device *gpio3   = DEVICE_DT_GET(DT_NODELABEL(gpio3));

static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER, /* mode 0 */
	.slave = 0,
	/* CS framed manually below */
};

/* Same 128-bit UUIDs as the pipeline BLE service, so tooling stays familiar. */
#define RATE_SVC BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define RATE_CHR BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(RATE_SVC);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(RATE_CHR);
static volatile bool notify_enabled;
static struct bt_conn *cur_conn;

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
}

BT_GATT_SERVICE_DEFINE(rate_svc,
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
	if (err) {
		return;
	}
	cur_conn = conn;
	bt_conn_le_phy_update(conn, BT_CONN_LE_PHY_PARAM_2M);   /* ask for 2M PHY */
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	cur_conn = NULL;
	notify_enabled = false;
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
};


static void log_link(void)
{
	static uint16_t l_mtu, l_int = 0xFFFF;
	static uint8_t l_phy;
	struct bt_conn_info info;

	if (!cur_conn || bt_conn_get_info(cur_conn, &info) != 0) {
		return;
	}
	uint16_t mtu = bt_gatt_get_mtu(cur_conn);
	uint8_t phy = info.le.phy ? info.le.phy->tx_phy : 0;

	if (mtu == l_mtu && info.le.interval == l_int && phy == l_phy) {
		return;
	}
	l_mtu = mtu;
	l_int = info.le.interval;
	l_phy = phy;

	printk("[link] PHY=%sM  interval=%u.%02u ms  MTU=%u\n",
	       (phy == BT_GAP_LE_PHY_2M) ? "2" : "1",
	       (info.le.interval * 125) / 100, (info.le.interval * 125) % 100, mtu);
}

/* Clock one 4-byte counter word out of the slave, inside a manual-CS frame. */
static void spi_read_word(uint8_t out[4])
{
	uint8_t tx[4] = {0};   /* MOSI don't-care; we only read MISO */

	struct spi_buf tb = { .buf = tx, .len = 4 };
	struct spi_buf_set ts = { .buffers = &tb, .count = 1 };
	struct spi_buf rb = { .buf = out, .len = 4 };
	struct spi_buf_set rs = { .buffers = &rb, .count = 1 };

	gpio_pin_set(gpio3, CS_PIN, 0);   /* assert CS low */
	k_busy_wait(50);                  /* let the slave's SPIS arm its tx buffer */
	spi_transceive(spi_dev, &spi_cfg, &ts, &rs);
	k_busy_wait(50);
	gpio_pin_set(gpio3, CS_PIN, 1);   /* deassert CS high */
}

int main(void)
{
	printk("=== BLE data-rate MASTER (SPI read -> BLE) ===\n");

	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("SPI or GPIO not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);   /* CS idle high */

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

	while (!notify_enabled) {
		k_msleep(50);
	}
	printk("subscribed - streaming SPI counter over BLE at max rate\n");

	/* Lever #4: ask the central for a fast, fixed connection interval (15 ms).
	 * The Mac may clamp or ignore it - log_link() will show what it actually did. */
	if (cur_conn) {
		struct bt_le_conn_param *cp = BT_LE_CONN_PARAM(12, 12, 0, 400); /* 15 ms, 4 s sup. */
		bt_conn_le_param_update(cur_conn, cp);
	}

	uint8_t payload[PAYLOAD_MAX] = {0};

	while (notify_enabled) {
		spi_read_word(payload);   /* first 4 bytes = slave's counter (LE) */
		log_link();               /* prints only when PHY/interval/MTU changes */

		/* size this notification to the negotiated MTU (grows once the central
		 * finishes the MTU exchange shortly after connecting) */
		uint16_t len = cur_conn ? (bt_gatt_get_mtu(cur_conn) - 3) : 20;
		if (len > PAYLOAD_MAX) {
			len = PAYLOAD_MAX;
		}

		int err;
		do {
			err = bt_gatt_notify(NULL, &rate_svc.attrs[1], payload, len);
			if (err) {
				k_yield();   /* tx buffers full - drain, then retry same word */
			}
		} while (err && notify_enabled);
	}

	printk("host unsubscribed - stopping\n");
	return 0;
}
