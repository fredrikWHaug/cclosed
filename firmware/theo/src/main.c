#include <stdint.h>
#include <zephyr/drivers/spi.h>

uint16_t acquire() {
    
}

uint16_t intan_transceive_word(int cmd) {
    int word = spi_transceiver(dev, config, tx_bufs, rx_bufs);
    return word
}

int main() {
    return 0;
}