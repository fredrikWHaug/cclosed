#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/conn.h>

#define CH              0
#define SAMPLE_RATE_HZ  6000             
#define PAYLOAD         244
#define SAMPLES_PER_PKT ((PAYLOAD - 2) / 2)   
#define RING_SAMPLES    8192

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

	uint8_t pkt[PAYLOAD];
	uint16_t seq = 0;

	while (1) {
		while (!notify_enabled) {
			k_msleep(20);
		}
		printk("subscribed - streaming ch%d at %d S/s\n", CH, SAMPLE_RATE_HZ);
		seq = 0;

		while (notify_enabled) {
			uint32_t avail = (w_idx + RING_SAMPLES - r_idx) % RING_SAMPLES;
			if (avail < SAMPLES_PER_PKT) {
				k_msleep(1);
				continue;
			}
			pkt[0] = seq;
			pkt[1] = seq >> 8;
			for (int i = 0; i < SAMPLES_PER_PKT; i++) {
				uint16_t s = ring[r_idx];
				r_idx = (r_idx + 1) % RING_SAMPLES;
				pkt[2 + 2 * i] = s;
				pkt[3 + 2 * i] = s >> 8;
			}
			int err;
			do {
				err = bt_gatt_notify(NULL, &sig_svc.attrs[1], pkt, PAYLOAD);
				if (err) {
					k_yield();
				}
			} while (err && notify_enabled);
			seq++;
			if ((seq % 50) == 0 && ring_drops) {
				printk("ring drops %u (lower SAMPLE_RATE_HZ)\n", ring_drops);
			}
		}
		printk("unsubscribed\n");
	}
	return 0;
}
