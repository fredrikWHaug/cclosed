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

#define RATE_HZ 24000u                 
#define PKT_SAMPLES 120                 
#define DPPI_CH 7u                  

#define REWIND_AT 0xFFFFFFFFu
#define RX_TOTAL 40960u            

#define PIN_SCK NRF_GPIO_PIN_MAP(2, 1)
#define PIN_MOSI NRF_GPIO_PIN_MAP(2, 2)
#define PIN_MISO NRF_GPIO_PIN_MAP(2, 4)
#define PIN_CSN NRF_GPIO_PIN_MAP(2, 5)

#define CONVERT(ch) ((uint16_t)(((ch) & 0x3F) << 8))
#define READ(r) ((uint16_t)(0xC000 | (((r) & 0x3F) << 8)))
#define WRITE(r, d) ((uint16_t)(0x8000 | (((r) & 0x3F) << 8) | ((d) & 0xFF)))
#define CALIBRATE ((uint16_t)0x5500)

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM00);
static uint8_t drv_tx[2], drv_rx[2];            

static uint16_t rx_region[RX_TOTAL];             

static uint8_t tx_region[2 * RX_TOTAL];

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
	WRITE(18, 0xFF), WRITE(19, 0xFF), WRITE(20, 0xFF), WRITE(21, 0xFF),
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
	printk("ROM 40-44 = \"%s\" (expect INTAN)\n", id);

	for (int i = 0; i < ARRAY_SIZE(init_seq); i++) {
		xfer(init_seq[i]);
	}
	xfer(CALIBRATE);
	for (int i = 0; i < 9; i++) {
		xfer(READ(63));
	}
	printk("Intan configured (10 Hz - 10 kHz, amps on, calibrated)\n");
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

BT_GATT_SERVICE_DEFINE(stream_svc,
	BT_GATT_PRIMARY_SERVICE(&svc_uuid),
	BT_GATT_CHARACTERISTIC(&chr_uuid.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE, NULL, NULL, NULL),
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
		static const struct bt_le_conn_param fast_params = BT_LE_CONN_PARAM_INIT(6, 12, 0, 400);
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

static inline uint32_t acq_pos(void)
{
	return (NRF_SPIM00->DMA.RX.PTR - (uint32_t)rx_region) / 2u;
}

static void acq_start(void)
{
	xfer(READ(40)); xfer(READ(41));
	char rom[6] = { 0 };
	rom[0] = (char)xfer(READ(42));
	rom[1] = (char)xfer(READ(43));
	rom[2] = (char)xfer(READ(44));
	rom[3] = (char)xfer(READ(63));
	rom[4] = (char)xfer(READ(63));
	if (rom[0] != 'I' || rom[1] != 'N' || rom[2] != 'T') {
		printk("acq_start: ROM check FAILED (\"%s\")\n", rom);
	}

	xfer(CONVERT(0));
	xfer(CONVERT(1));

	for (uint32_t i = 0; i < RX_TOTAL; i++) {
		uint16_t cmd = CONVERT((i + 2u) & 3u);
		tx_region[2 * i]     = (uint8_t)(cmd >> 8);
		tx_region[2 * i + 1] = (uint8_t)cmd;
	}
	nrf_spim_tx_buffer_set(NRF_SPIM00, tx_region, 2);
	nrf_spim_rx_buffer_set(NRF_SPIM00, (uint8_t *)rx_region, 2);
	nrf_spim_tx_list_enable(NRF_SPIM00);
	nrf_spim_rx_list_enable(NRF_SPIM00);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);

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
	k_busy_wait(100);                       
	nrf_spim_disable(NRF_SPIM00);

	nrf_spim_tx_list_disable(NRF_SPIM00);
	nrf_spim_rx_list_disable(NRF_SPIM00);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);
}

static uint32_t rewinds;
static uint16_t carry[8192];             
static uint32_t carry_len, carry_idx;

static bool rewind_wait_end(void)
{
	uint32_t spins = 0;
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	while (!nrf_spim_event_check(NRF_SPIM00, NRF_SPIM_EVENT_END)) {
		if (++spins > 20000000u) {
			return false;         
		}
	}
	return true;
}

static bool acq_rewind(uint32_t from)
{
	if (!rewind_wait_end()) {
		return false;
	}
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_STOP);

	uint32_t tail_end = acq_pos();

	if (tail_end - from > 8192u) {
		return false;
	}

	carry_len = 0;
	carry_idx = 0;
	for (uint32_t i = from; i < tail_end; i++) {
		carry[carry_len++] = rx_region[i];
	}

	nrf_spim_disable(NRF_SPIM00);
	nrf_spim_tx_buffer_set(NRF_SPIM00, tx_region + 2 * (tail_end & 3u), 2);
	nrf_spim_rx_buffer_set(NRF_SPIM00, (uint8_t *)rx_region, 2);
	nrf_spim_tx_list_enable(NRF_SPIM00);
	nrf_spim_rx_list_enable(NRF_SPIM00);
	nrf_spim_event_clear(NRF_SPIM00, NRF_SPIM_EVENT_END);
	nrf_spim_enable(NRF_SPIM00);
	nrf_timer_task_trigger(NRF_TIMER00, NRF_TIMER_TASK_START);

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
	nrfx_spim_config_t cfg = NRFX_SPIM_DEFAULT_CONFIG(PIN_SCK, PIN_MOSI, PIN_MISO, PIN_CSN);
	cfg.frequency = 16000000u;           
	cfg.mode = NRF_SPIM_MODE_0;
	cfg.bit_order = NRF_SPIM_BIT_ORDER_MSB_FIRST;
	cfg.use_hw_ss = true;
	cfg.ss_duration = 20;                   
	cfg.rx_delay = 6;                    

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
		printk("subscribed - hw-timed streaming ch0-ch3 interleaved, %u S/s per channel\n", RATE_HZ / 4u);
		seq = 0;
		rewinds = 0;
		carry_len = carry_idx = 0;
		uint32_t r_pos = 0;
		acq_start();
		while (notify_enabled) {
			uint32_t w = acq_pos();
			if (w >= RX_TOTAL - 8u) {
				printk("region full - clean restart (expected every ~1.7 s in no-rewind mode)\n");
				acq_stop();
				r_pos = 0;
				carry_len = carry_idx = 0;
				acq_start();
				continue;
			}
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
				s = (uint16_t)((s >> 8) | (s << 8));
				pkt[2 + 2 * k]     = (uint8_t)s;
				pkt[2 + 2 * k + 1] = (uint8_t)(s >> 8);
			}
			if (carry_idx == carry_len) {
				carry_len = carry_idx = 0;
			}
			int err;
			do {
				err = bt_gatt_notify(NULL, &stream_svc.attrs[1], pkt, sizeof(pkt));
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
