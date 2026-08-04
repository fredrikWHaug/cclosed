#include <zephyr/kernel.h>
#include <zephyr/drivers/adc.h>

static const struct adc_dt_spec adc_chan =
	ADC_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 0);

int main(void)
{
	int16_t raw;
	struct adc_sequence seq = {
		.buffer = &raw,
		.buffer_size = sizeof(raw),
	};

	adc_channel_setup_dt(&adc_chan);

	while (1) {
		adc_sequence_init_dt(&adc_chan, &seq);
		adc_read_dt(&adc_chan, &seq);
		int32_t mv = raw;
		adc_raw_to_millivolts_dt(&adc_chan, &mv);
		printk("raw %5d  =  %4d mV\n", raw, mv);
		k_sleep(K_MSEC(100));
	}
	return 0;
}