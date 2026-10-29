#include <math.h>
#include <string.h>
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

/* One channel at 30 kS/s until the windowed path is proven equal to the raw path. Every converted channel needs a wire. */
#define N_CH 1
#define CH_RATE_HZ 30000u
/* 1: send every sample (seq u16 | 120 x u16 codes) for the raw benchmark.  0: detect spikes and send only the windows. */
#define RAW_STREAM 1
#define RATE_HZ (N_CH * CH_RATE_HZ)

/* Intan analog low-pass (datasheet table "Setting Upper Bandwidth", registers 8-11): the highest standard cutoff at or
 * below 0.4 x the per-channel rate, at most 10 kHz, so nothing above half the sample rate folds back into the band.
 *   cutoff   10 kHz   7.5 kHz   5 kHz   3 kHz   2.5 kHz   2 kHz   1.5 kHz
 *   rate >=  25000    18750     12500   7500    6250      5000    (lower)  */
#define FH_SEL   (CH_RATE_HZ >= 25000u ? 0 : CH_RATE_HZ >= 18750u ? 1 : CH_RATE_HZ >= 12500u ? 2 : \
                  CH_RATE_HZ >= 7500u ? 3 : CH_RATE_HZ >= 6250u ? 4 : CH_RATE_HZ >= 5000u ? 5 : 6)
#define FH_HZ    (FH_SEL == 0 ? 10000 : FH_SEL == 1 ? 7500 : FH_SEL == 2 ? 5000 : FH_SEL == 3 ? 3000 : \
                  FH_SEL == 4 ? 2500 : FH_SEL == 5 ? 2000 : 1500)
#define RH1_DAC1 (FH_SEL == 0 ? 17 : FH_SEL == 1 ? 22 : FH_SEL == 2 ? 33 : FH_SEL == 3 ? 3 : FH_SEL == 4 ? 13 : FH_SEL == 5 ? 27 : 1)
#define RH1_DAC2 (FH_SEL <= 2 ? 0 : FH_SEL <= 5 ? 1 : 2)
#define RH2_DAC1 (FH_SEL == 0 ? 16 : FH_SEL == 1 ? 23 : FH_SEL == 2 ? 37 : FH_SEL == 3 ? 13 : FH_SEL == 4 ? 25 : FH_SEL == 5 ? 44 : 23)
#define RH2_DAC2 (FH_SEL <= 2 ? 0 : FH_SEL <= 5 ? 1 : 2)
#define DPPI_CH 7u

#define RX_TOTAL 40960u
#define RESTART_AT (RX_TOTAL - 4096u)
BUILD_ASSERT(RATE_HZ <= 1050000u, "RHD2164 ADC tops out at 1.05 MS/s total");

/* Intan regs 1-2 must follow the total ADC rate (datasheet, "Analog-to-Digital Converter" table) */
#define ADC_BUF_BIAS (RATE_HZ <= 120000u ? 32 : RATE_HZ <= 140000u ? 16 : RATE_HZ <= 280000u ? 8 : \
                      RATE_HZ <= 350000u ? 4 : RATE_HZ <= 525000u ? 3 : 2)
#define MUX_BIAS     (RATE_HZ <= 175000u ? 40 : RATE_HZ <= 220000u ? 32 : RATE_HZ <= 280000u ? 26 : \
                      RATE_HZ <= 350000u ? 18 : RATE_HZ <= 440000u ? 16 : RATE_HZ <= 525000u ? 7 : 4)

#define HP_HZ 300.0f
#define LP_HZ (CH_RATE_HZ >= 15000u ? 6000.0f : 0.4f * (float)CH_RATE_HZ)
#define THRESH_SIGMA 4.0f
#define SIGMA_PER_MEAN 1.3263f           /* sigma / mean|y| for Gaussian y clipped at 3x the estimate (1.2533 unclipped) */
#define SETTLE_MS 500u                   /* no detections while the noise estimate warms up */
#define RESTART_BLANK_MS 1u              /* no noise update for this long after a restart */
#define RESTART_HOLD (CH_RATE_HZ / 3000u)   /* no new detection for 0.33 ms after a restart; spikes in flight continue */
#define NOISE_ALPHA (1.0f / 8192.0f)     /* running mean of |filtered|, ~0.3 s at 30 kS/s */
#define RING 256

#define PRE  (CH_RATE_HZ * 2u / 3000u)          /* 0.67 ms before the trough */
#define POST (CH_RATE_HZ * 41u / 30000u)        /* 1.37 ms after it: 61 samples at 30k, Kilosort's default */
#define REFRACT (3u * CH_RATE_HZ / 1000u)       /* 3 ms dead time after a spike: the filter's dip after the rebound is not a new spike */
#define NOISE_BLANK (3u * CH_RATE_HZ / 1000u)   /* no noise update for 3 ms after a spike's trough: its tail is not noise */
#define WIN  (PRE + POST)
BUILD_ASSERT(WIN + CH_RATE_HZ / 1000 < RING, "ring must hold window + 1 ms lookahead");
BUILD_ASSERT(WIN >= 2 && WIN <= 255, "window must fit the n_samples byte");

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
	WRITE(0, 0xDE), WRITE(1, ADC_BUF_BIAS), WRITE(2, MUX_BIAS), WRITE(3, 0x00), WRITE(4, 0x00),
	WRITE(5, 0x00), WRITE(6, 0x00), WRITE(7, 0x00),
	WRITE(8, RH1_DAC1), WRITE(9, RH1_DAC2), WRITE(10, RH2_DAC1), WRITE(11, RH2_DAC2),
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
	printk("Intan configured (10 Hz - %u Hz analog band, amps on, calibrated)\n", FH_HZ);
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
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
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
static void param_updated(struct bt_conn *conn, uint16_t interval, uint16_t latency, uint16_t timeout)
{
	printk("conn interval now %u.%02u ms\n", (interval * 125u) / 100u, (interval * 125u) % 100u);
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
	xfer(CONVERT(1 % N_CH));

	static bool tx_filled;
	if (!tx_filled) {                /* same command list every start */
		for (uint32_t i = 0; i < RX_TOTAL; i++) {
			uint16_t cmd = CONVERT((i + 2u) % N_CH);
			tx_region[2 * i]     = (uint8_t)(cmd >> 8);
			tx_region[2 * i + 1] = (uint8_t)cmd;
		}
		tx_filled = true;
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

/* ---- per-channel detector ---- */
struct chan {
	int16_t ring[RING];
	uint32_t n;                      /* samples seen on this channel = timestamp */
	float hp_s[4], lp_s[4];          /* biquad states: x1 x2 y1 y2 */
	float noise;                     /* running mean of |filtered|, spikes excluded */
	uint32_t quiet_until;            /* no detection before this sample (settle, blanking, refractory) */
	uint32_t blank_until;            /* no noise update before this sample (after a spike or a restart) */
	uint8_t state;                   /* 0 idle, 1 searching trough, 2 waiting for POST */
	uint32_t t_trough, search_end;
	float v_trough;
};
static struct chan chans[N_CH];
struct biquad { float b0, b1, b2, a1, a2; };
static struct biquad hp, lp;

/* 2nd-order Butterworth section, bilinear transform */
static struct biquad butter2(float f_hz, bool highpass)
{
	float k = tanf(3.14159265f * f_hz / (float)CH_RATE_HZ);
	float norm = 1.0f / (1.0f + 1.41421356f * k + k * k);
	struct biquad q;
	q.b0 = highpass ? norm : k * k * norm;
	q.b1 = highpass ? -2.0f * q.b0 : 2.0f * q.b0;
	q.b2 = q.b0;
	q.a1 = 2.0f * (k * k - 1.0f) * norm;
	q.a2 = (1.0f - 1.41421356f * k + k * k) * norm;
	return q;
}

static inline float biquad_run(const struct biquad *q, float s[4], float x)
{
	float y = q->b0 * x + q->b1 * s[0] + q->b2 * s[1] - q->a1 * s[2] - q->a2 * s[3];
	s[1] = s[0]; s[0] = x; s[3] = s[2]; s[2] = y;
	return y;
}

static void detector_init(void)
{
	hp = butter2(HP_HZ, true);
	lp = butter2(LP_HZ, false);
	memset(chans, 0, sizeof(chans));
	for (int c = 0; c < N_CH; c++) {
		chans[c].quiet_until = SETTLE_MS * (CH_RATE_HZ / 1000u);
		chans[c].noise = 1000.0f;        /* start high; the clipped update only shrinks it toward the true floor */
	}
}

#define EV_HDR 9
#define EV_PACKED ((WIN * 3 + 1) / 2)
#define EV_BYTES (EV_HDR + EV_PACKED)
#define NOTIFY_MAX 244                   /* ATT payload at MTU 247 */
#define EV_PER_NOTIFY (NOTIFY_MAX / EV_BYTES)
BUILD_ASSERT(EV_PER_NOTIFY >= 1, "event must fit one notification");
#define EV_QUEUE 256                     /* power of two; ~0.3 s of SYNC at 8 channels */
BUILD_ASSERT((EV_QUEUE & (EV_QUEUE - 1)) == 0, "queue size must be a power of two");
static uint8_t evq[EV_QUEUE][EV_BYTES];
static uint32_t evq_w, evq_r;
static uint32_t evq_first_drained;    /* aggregate sample count when the oldest queued event was queued */
static uint32_t detected, sent, dropped, restarts, drained, lag;
#if RAW_STREAM
#define RAW_SAMPLES 120
static uint8_t raw_pkt[2 + 2 * RAW_SAMPLES];
static uint32_t raw_n;
static uint16_t raw_seq;

static void raw_push(uint16_t code)
{
	raw_pkt[2 + 2 * raw_n] = (uint8_t)code;
	raw_pkt[3 + 2 * raw_n] = (uint8_t)(code >> 8);
	if (++raw_n == RAW_SAMPLES) {
		raw_pkt[0] = (uint8_t)raw_seq; raw_pkt[1] = (uint8_t)(raw_seq >> 8); raw_seq++;
		if (bt_gatt_notify(NULL, &stream_svc.attrs[1], raw_pkt, sizeof(raw_pkt)) == 0) {
			sent++;
		} else {
			dropped++;
		}
		raw_n = 0;
	}
}
#endif
static uint16_t seq;

static void emit(uint8_t c, struct chan *ch)
{
	detected++;
	if (evq_w - evq_r >= EV_QUEUE) {
		dropped++;
		return;
	}
	if (evq_w == evq_r) {
		evq_first_drained = drained;
	}
	uint8_t *p = evq[evq_w % EV_QUEUE];
	p[0] = (uint8_t)seq; p[1] = (uint8_t)(seq >> 8); seq++;
	p[2] = c; p[3] = (uint8_t)WIN; p[4] = (uint8_t)PRE;
	memcpy(&p[5], &ch->t_trough, 4);
	uint32_t first = ch->t_trough - PRE;
	uint8_t *q = &p[EV_HDR];
	for (uint32_t k = 0; k < WIN; k += 2) {
		/* 12-bit two's complement: drop the 4 LSBs (3 uV), keep the full +-6.4 mV range */
		uint16_t a = (uint16_t)(ch->ring[(first + k) & (RING - 1)] >> 4) & 0xFFFu;
		uint16_t b = (k + 1 < WIN) ? (uint16_t)(ch->ring[(first + k + 1) & (RING - 1)] >> 4) & 0xFFFu : 0u;
		*q++ = (uint8_t)a;                          /* a[7:0]            */
		*q++ = (uint8_t)((a >> 8) | (b << 4));      /* b[3:0] a[11:8]    */
		if (k + 1 < WIN) {
			*q++ = (uint8_t)(b >> 4);               /* b[11:4]           */
		}
	}
	evq_w++;
}

static inline void process(uint8_t c, int16_t s)
{
	struct chan *ch = &chans[c];
	ch->ring[ch->n & (RING - 1)] = s;
	float y = biquad_run(&lp, ch->lp_s, biquad_run(&hp, ch->hp_s, (float)s));
	uint32_t n = ch->n++;
	if (ch->state == 0 && n >= ch->blank_until && fabsf(y) < 3.0f * ch->noise) {
		ch->noise += (fabsf(y) - ch->noise) * NOISE_ALPHA;
	}
	if (n < ch->quiet_until) {
		return;
	}
	switch (ch->state) {
	case 0:
		if (y < -THRESH_SIGMA * SIGMA_PER_MEAN * ch->noise) {
			ch->state = 1; ch->t_trough = n; ch->v_trough = y;
			ch->search_end = n + CH_RATE_HZ / 1000u;       /* 1 ms lookahead for the true trough */
		}
		break;
	case 1:
		if (y < ch->v_trough) { ch->v_trough = y; ch->t_trough = n; }
		if (n >= ch->search_end) { ch->state = 2; }
		break;
	case 2:
		if (n + 1 >= ch->t_trough + POST) {
			emit(c, ch);
			ch->state = 0;
			ch->quiet_until = ch->t_trough + REFRACT;
			ch->blank_until = ch->t_trough + NOISE_BLANK;
		}
		break;
	}
}

static void blank_after_restart(void)
{
	for (int c = 0; c < N_CH; c++) {
		chans[c].blank_until = chans[c].n + RESTART_BLANK_MS * (CH_RATE_HZ / 1000u);
		if (chans[c].state == 0) {
			chans[c].quiet_until = MAX(chans[c].quiet_until, chans[c].n + RESTART_HOLD);
		}
	}
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
	    bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN, BT_GAP_ADV_FAST_INT_MIN_2,
					    BT_GAP_ADV_FAST_INT_MAX_2, NULL), ad, ARRAY_SIZE(ad), NULL, 0) != 0) {
		printk("BLE init failed\n");
		return 0;
	}
	printk("advertising as '%s' - prestno spike detector, %u ch x %u S/s, window %u+%u samples\n",
	       CONFIG_BT_DEVICE_NAME, N_CH, CH_RATE_HZ, PRE, POST);
	printk("event %u B (%u samples x 12 bit), %u events per notification\n", EV_BYTES, WIN, EV_PER_NOTIFY);

	while (1) {
		while (!notify_enabled) {
			k_msleep(20);
		}
		printk("subscribed - detecting on %u channels at %u S/s each\n", N_CH, CH_RATE_HZ);
		detector_init();
		evq_w = evq_r = 0;
		seq = 0; detected = sent = dropped = restarts = drained = 0;
		uint32_t r_pos = 0;
		int64_t next_report = k_uptime_get() + 1000;
		uint32_t last_drained = 0, last_detected = 0, last_sent = 0, last_dropped = 0;
		acq_start();

		while (notify_enabled) {
			uint32_t w = acq_pos();
			bool wrap = w >= RESTART_AT;
			if (wrap) {
				acq_stop();              /* region nearly full: stop, drain the rest, start over */
			}
			bool busy = false;
			if (w > r_pos) {
				busy = true;
				if (w - r_pos > lag) {
					lag = w - r_pos;     /* samples the detector is behind the DMA */
				}
				drained += w - r_pos;
				for (; r_pos < w; r_pos++) {
					uint16_t raw = rx_region[r_pos];
					raw = (uint16_t)((raw >> 8) | (raw << 8));
#if RAW_STREAM
					raw_push(raw);
#else
					process(r_pos % N_CH, (int16_t)(raw - 32768));
#endif
				}
			}
			if (wrap) {
				r_pos = 0;
				restarts++;
				blank_after_restart();
				acq_start();
				continue;
			}
			uint32_t queued = evq_w - evq_r;
			if (queued >= EV_PER_NOTIFY || (queued && drained - evq_first_drained > RATE_HZ / 1000u)) {
				busy = true;                       /* send full notifications, or a partial one after 1 ms */
				uint32_t n = MIN(queued, (uint32_t)EV_PER_NOTIFY);
				n = MIN(n, EV_QUEUE - (evq_r % EV_QUEUE));          /* contiguous in the ring */
				if (bt_gatt_notify(NULL, &stream_svc.attrs[1], evq[evq_r % EV_QUEUE], n * EV_BYTES) == 0) {
					evq_r += n; sent += n;
				} else {
					k_yield();                 /* radio buffers full; let the stack drain */
				}
			}
			if (!busy) {
				k_yield();
			}
			if (k_uptime_get() >= next_report) {
				next_report += 1000;
#if RAW_STREAM
				printk("[prestno] %u S/s drained  lag %u  ch0 noise -  raw packets sent %u/s  dropped %u/s  restarts %u\n",
				       drained - last_drained, lag, sent - last_sent, dropped - last_dropped, restarts);
#else
				printk("[prestno] %u S/s drained  lag %u  ch0 noise %u uV  detected %u/s  sent %u/s  dropped %u/s  queued %u  restarts %u\n",
				       drained - last_drained, lag, (unsigned)(chans[0].noise * SIGMA_PER_MEAN * 0.195f),
				       detected - last_detected, sent - last_sent, dropped - last_dropped, evq_w - evq_r, restarts);
#endif
				last_drained = drained; last_detected = detected; last_sent = sent; last_dropped = dropped;
				lag = 0;
			}
		}
		acq_stop();
		printk("unsubscribed\n");
	}
	return 0;
}