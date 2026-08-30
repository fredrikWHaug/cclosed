#include <stdint.h>
#include <zephyr/drivers/spi.h>

const struct device *device;
const struct spi_config *config;

uint16_t acquire() {
    
}

uint16_t intan_transceive_word(uint16_t cmd) {
    const struct spi_buf_set *tx_bufs;
    const struct spi_buf_set *rx_bufs;

    uint16_t result = spi_transceive(device, config, tx_bufs, rx_bufs);

    uint16_t word = rx_bufs[0];

    return word;
}

int main() {
    return 0;
}