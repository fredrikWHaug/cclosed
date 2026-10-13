
const uint8_t SPIKE[] = {
  10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9, 9, 7, 6,
  4, 2, 0, 0, 1, 3, 5, 8, 10, 12, 13, 14, 14, 15, 15, 15,
  15, 15, 15, 14, 14, 13, 13, 13, 12, 12, 11, 11, 11, 11,
  10, 10, 10,10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
  10, 10, 10, 10, 10
};

const int N_SPIKE = sizeof(SPIKE);
const uint16_t SAMPLE_US = 100;   
const uint8_t  BASELINE = 10;    
const uint16_t GAP_MIN_MS = 20;    
const uint16_t GAP_MAX_MS = 80;

void setup() {
  pinMode(0, OUTPUT);
  pinMode(1, OUTPUT);
  pinMode(2, OUTPUT);
  pinMode(3, OUTPUT);
  pinMode(13, OUTPUT);             
  write_dac(BASELINE);
  randomSeed(analogRead(A0));
}

void write_dac(int val) {
  digitalWrite(0, 1 - ((val >> 0) & 0x1));
  digitalWrite(1, 1 - ((val >> 1) & 0x1));
  digitalWrite(2, 1 - ((val >> 2) & 0x1));
  digitalWrite(3, 1 - ((val >> 3) & 0x1));
}

void loop() {
  digitalWrite(13, HIGH);

  for (int i = 0; i < N_SPIKE; i++) {
    write_dac(SPIKE[i]);
    delayMicroseconds(SAMPLE_US);
  }

  digitalWrite(13, LOW);
  write_dac(BASELINE);
  delay(random(GAP_MIN_MS, GAP_MAX_MS));
}
