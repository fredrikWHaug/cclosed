#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>

#define WORD_PERIOD_US 1000         
#define N_SLOTS 8         
#define CH_REAL 0
#define HALF 60                        
#define PAYLOAD (4 + HALF * 2)

#define CMD_CONVERT(c) ((uint16_t)(((c) & 0x3F) << 8))
#define CMD_READ(r)    ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define CMD_WRITE(r,d) ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CMD_CALIBRATE  ((uint16_t)0x5500)
#define CMD_DUMMY      CMD_READ(63)

#define CS_PIN 2

static const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi22));
static const struct device *gpio3 = DEVICE_DT_GET(DT_NODELABEL(gpio3));
static struct spi_config spi_cfg = {
	.frequency = 1000000,
	.operation = SPI_WORD_SET(8) | SPI_TRANSFER_MSB | SPI_OP_MODE_MASTER,
	.slave = 0,
};

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

static uint16_t xfer(uint16_t cmd)
{
	uint8_t tx[2] = { (uint8_t)(cmd >> 8), (uint8_t)cmd };
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
	k_usleep(WORD_PERIOD_US);
	return (uint16_t)((rx[0] << 8) | rx[1]);
}

static bool intan_init(void)
{
	static const uint16_t seq[] = {
		CMD_READ(63), CMD_READ(63),
		CMD_WRITE(0, 0xDE),          
		CMD_WRITE(1, 32),              
		CMD_WRITE(2, 40),            
		CMD_WRITE(3, 0x00),         
		CMD_WRITE(4, 0x80),  
		CMD_READ(40), CMD_READ(41), CMD_READ(42), CMD_READ(43), CMD_READ(44),
		CMD_READ(63), CMD_READ(63),    
		CMD_CALIBRATE,
		CMD_DUMMY, CMD_DUMMY, CMD_DUMMY, CMD_DUMMY, CMD_DUMMY,
		CMD_DUMMY, CMD_DUMMY, CMD_DUMMY, CMD_DUMMY,
	};
	uint16_t resp[ARRAY_SIZE(seq)];

	for (int i = 0; i < ARRAY_SIZE(seq); i++) {
		resp[i] = xfer(seq[i]);
	}

	char id[6] = {0};
	for (int i = 0; i < 5; i++) {
		id[i] = (char)(resp[9 + i] & 0xFF);
	}
	printk("ROM 40-44 = '%s' (%s)\n", id,
	       (id[0]=='I' && id[1]=='N' && id[2]=='T' && id[3]=='A' && id[4]=='N')
	       ? "INTAN check OK" : "MISMATCH");
	return id[0] == 'I';
}

int main(void)
{
	printk("=== master-intan: RHD-style controller -> BLE ===\n");
	if (!device_is_ready(spi_dev) || !device_is_ready(gpio3)) {
		printk("not ready\n");
		return 0;
	}
	gpio_pin_configure(gpio3, CS_PIN, GPIO_OUTPUT_HIGH);

	if (bt_enable(NULL) != 0 ||
	    bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
					    BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			    ad, ARRAY_SIZE(ad), NULL, 0) != 0) {
		printk("BLE init failed\n");
		return 0;
	}

	k_msleep(100);                     
	intan_init();
	printk("advertising as '%s' - connect and subscribe\n", CONFIG_BT_DEVICE_NAME);

	uint8_t hist[2] = { 0xFF, 0xFF };
	uint16_t ch0[HALF];
	int nch0 = 0;
	uint16_t seq16 = 0;
	uint8_t half = 0;
	uint32_t converts = 0;
	uint8_t slot = 0;

	while (1) {
		if (!notify_enabled) {
			k_msleep(50);
			continue;
		}

		uint16_t r = xfer(CMD_CONVERT(slot));

		uint8_t src = hist[0];           
		hist[0] = hist[1];
		hist[1] = slot;
		slot = (uint8_t)((slot + 1) % N_SLOTS);
		converts++;

		if (src != CH_REAL) {
			continue;
		}

		ch0[nch0++] = r;
		if (nch0 < HALF) {
			continue;
		}
		nch0 = 0;

		uint8_t pay[PAYLOAD];
		pay[0] = (uint8_t)seq16;
		pay[1] = (uint8_t)(seq16 >> 8);
		pay[2] = half;
		pay[3] = HALF;
		for (int i = 0; i < HALF; i++) {
			pay[4 + 2 * i] = (uint8_t)ch0[i];
			pay[5 + 2 * i] = (uint8_t)(ch0[i] >> 8);
		}
		while (bt_gatt_notify(NULL, &sig_svc.attrs[1], pay, PAYLOAD) != 0) {
			k_msleep(1);
		}
		if (half == 1) {
			seq16++;
			if ((seq16 % 10) == 0) {
				printk("converts %u  ch0 pkts seq %u\n", converts, seq16);
			}
		}
		half ^= 1;
	}
	return 0;
}
