#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>

#define TARGET_NAME "cclosed-blerate"

#define RATE_SVC BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define RATE_CHR BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)
static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(RATE_SVC);
static struct bt_uuid_128 chr_uuid = BT_UUID_INIT_128(RATE_CHR);

static struct bt_conn *cur_conn;
static struct bt_gatt_discover_params disc;
static struct bt_gatt_subscribe_params sub;
static struct bt_gatt_exchange_params mtu_params;

static volatile uint32_t win_bytes, win_pkts;
static volatile uint32_t tot_pkts, drops;
static uint32_t last_seq;
static bool have_last;

#define CONN_PARAM BT_LE_CONN_PARAM(6, 6, 0, 100)

static uint8_t on_notify(struct bt_conn *conn, struct bt_gatt_subscribe_params *params,
			 const void *data, uint16_t len)
{
	if (!data) {                 
		return BT_GATT_ITER_STOP;
	}
	uint32_t seq;
	memcpy(&seq, data, sizeof(seq));   

	if (have_last) {
		uint32_t gap = seq - last_seq - 1;      
		if (gap != 0 && gap < 0x80000000u) {
			drops += gap;
		}
	}
	last_seq = seq;
	have_last = true;

	tot_pkts++;
	win_pkts++;
	win_bytes += len;
	return BT_GATT_ITER_CONTINUE;
}

static uint8_t discover_func(struct bt_conn *conn, const struct bt_gatt_attr *attr,
			     struct bt_gatt_discover_params *params)
{
	if (!attr) {
		printk("discover complete without finding characteristic\n");
		return BT_GATT_ITER_STOP;
	}

	if (!bt_uuid_cmp(disc.uuid, &svc_uuid.uuid)) {
		disc.uuid = &chr_uuid.uuid;
		disc.start_handle = attr->handle + 1;
		disc.type = BT_GATT_DISCOVER_CHARACTERISTIC;
		bt_gatt_discover(conn, &disc);
	} else if (!bt_uuid_cmp(disc.uuid, &chr_uuid.uuid)) {
		sub.value_handle = bt_gatt_attr_value_handle(attr);
		disc.uuid = BT_UUID_GATT_CCC;
		disc.start_handle = attr->handle + 2;
		disc.type = BT_GATT_DISCOVER_DESCRIPTOR;
		bt_gatt_discover(conn, &disc);
	} else {
		sub.notify = on_notify;
		sub.value = BT_GATT_CCC_NOTIFY;
		sub.ccc_handle = attr->handle;
		if (bt_gatt_subscribe(conn, &sub) == 0) {
			printk("subscribed - measuring (read kbit/s below)\n");
		} else {
			printk("subscribe failed\n");
		}
		return BT_GATT_ITER_STOP;
	}
	return BT_GATT_ITER_STOP;
}

static void mtu_cb(struct bt_conn *conn, uint8_t err, struct bt_gatt_exchange_params *params)
{
	printk("MTU exchanged (%u) - discovering service\n", bt_gatt_get_mtu(conn));
	disc.uuid = &svc_uuid.uuid;
	disc.func = discover_func;
	disc.start_handle = 0x0001;
	disc.end_handle = 0xffff;
	disc.type = BT_GATT_DISCOVER_PRIMARY;
	bt_gatt_discover(conn, &disc);
}

static bool ad_has_name(struct bt_data *data, void *user_data)
{
	bool *found = user_data;

	if (data->type == BT_DATA_NAME_COMPLETE || data->type == BT_DATA_NAME_SHORTENED) {
		if (data->data_len == strlen(TARGET_NAME) &&
		    memcmp(data->data, TARGET_NAME, data->data_len) == 0) {
			*found = true;
			return false;   
		}
	}
	return true;
}

static void scan_cb(const bt_addr_le_t *addr, int8_t rssi, uint8_t type,
		    struct net_buf_simple *ad)
{
	if (cur_conn) {
		return;
	}
	bool found = false;
	bt_data_parse(ad, ad_has_name, &found);
	if (!found) {
		return;
	}
	bt_le_scan_stop();
	printk("found '%s' - connecting at 7.5 ms / 2M\n", TARGET_NAME);
	if (bt_conn_le_create(addr, BT_CONN_LE_CREATE_CONN, CONN_PARAM, &cur_conn) != 0) {
		printk("connect failed - rescanning\n");
		bt_le_scan_start(BT_LE_SCAN_ACTIVE, scan_cb);
	}
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		printk("connect err %u - rescanning\n", err);
		bt_conn_unref(cur_conn);
		cur_conn = NULL;
		bt_le_scan_start(BT_LE_SCAN_ACTIVE, scan_cb);
		return;
	}
	printk("connected - upgrading link\n");
	bt_conn_le_phy_update(conn, BT_CONN_LE_PHY_PARAM_2M);
	bt_conn_le_data_len_update(conn, BT_LE_DATA_LEN_PARAM_MAX);
	mtu_params.func = mtu_cb;
	bt_gatt_exchange_mtu(conn, &mtu_params);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	printk("disconnected (0x%02x) - rescanning\n", reason);
	bt_conn_unref(cur_conn);
	cur_conn = NULL;
	have_last = false;
	bt_le_scan_start(BT_LE_SCAN_ACTIVE, scan_cb);
}

static bool le_param_req(struct bt_conn *conn, struct bt_le_conn_param *param)
{
	return false;
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
	.le_param_req = le_param_req,
};

int main(void)
{
	if (bt_enable(NULL) != 0) {
		printk("BLE init failed\n");
		return 0;
	}
	if (bt_le_scan_start(BT_LE_SCAN_ACTIVE, scan_cb) != 0) {
		printk("scan start failed\n");
		return 0;
	}
	printk("scanning for '%s'...\n", TARGET_NAME);

	while (1) {
		k_msleep(1000);

		uint32_t b = win_bytes, p = win_pkts;
		win_bytes = 0;
		win_pkts = 0;
		if (!cur_conn || p == 0) {
			continue;
		}

		uint32_t kbps = (b * 8u) / 1000u;
		uint16_t iv = 0;
		struct bt_conn_info info;
		if (bt_conn_get_info(cur_conn, &info) == 0) {
			iv = info.le.interval;   
		}
		printk("[rate] %6u kbit/s   %5u pkts/s   interval %u.%02u ms   drops %u   total %u\n",
		       kbps, p, (iv * 125) / 100, (iv * 125) % 100, drops, tot_pkts);
	}
	return 0;
}
