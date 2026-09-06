#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>
#include <string.h>

#define PAYLOAD_MAX  244
#define VALS_PER_PKT (PAYLOAD_MAX / 2)

#define PRODUCE_RATE_HZ 60000
#define PER_TICK        (PRODUCE_RATE_HZ / 1000)

#define RING_CAP 4096

static volatile uint32_t produced;
static uint32_t sent;                
static uint32_t lost;                

static void produce_tick(struct k_timer *t)
{
	produced += PER_TICK;
}
K_TIMER_DEFINE(prod_timer, produce_tick, NULL);

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

int main(void)
{
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
	printk("subscribed - producing %u vals/s, draining over BLE\n", PRODUCE_RATE_HZ);

	uint8_t payload[PAYLOAD_MAX];
	uint32_t pkts = 0;

	k_timer_start(&prod_timer, K_MSEC(1), K_MSEC(1));

	while (notify_enabled) {
		uint32_t p = produced;

		/* backlog overflowed: skip the oldest values, count them */
		if (p - sent > RING_CAP) {
			lost += (p - sent) - RING_CAP;
			sent = p - RING_CAP;
		}

		/* not enough values for a full packet yet */
		if (p - sent < VALS_PER_PKT) {
			k_msleep(1);
			continue;
		}

		for (uint32_t i = 0; i < VALS_PER_PKT; i++) {
			uint16_t v = (uint16_t)(sent + i);
			payload[2 * i]     = (uint8_t)v;
			payload[2 * i + 1] = (uint8_t)(v >> 8);
		}

		if (bt_gatt_notify(NULL, &rate_svc.attrs[1], payload, PAYLOAD_MAX) == 0) {
			sent += VALS_PER_PKT;
			if (++pkts % 537 == 0) {
				printk("[master] lost %u vals\n", lost);
			}
		} else {
			k_msleep(1);
		}
	}

	k_timer_stop(&prod_timer);
	printk("host unsubscribed - stopping\n");
	return 0;
}
