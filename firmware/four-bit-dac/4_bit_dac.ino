
char dac_value_write = 0;

void setup() {
  pinMode(13, OUTPUT);

  pinMode(12, INPUT);

  pinMode(0,OUTPUT);
  pinMode(1,OUTPUT);
  pinMode(2,OUTPUT);
  pinMode(3,OUTPUT);

  Serial.begin(9600);
}

void write_dac(int val) {

  char dac_value_0 = (val & 0x1) >> 0; // get bit [0]
  char dac_value_1 = (val & 0x2) >> 1; // get bit [1]
  char dac_value_2 = (val & 0x4) >> 2; // get bit [2]
  char dac_value_3 = (val & 0x8) >> 3; // get bit [3]

  digitalWrite(0, 1-dac_value_0);
  digitalWrite(1, 1-dac_value_1);
  digitalWrite(2, 1-dac_value_2);
  digitalWrite(3, 1-dac_value_3);

}


int read_adc() {

  int dac_tmp;
  int val;
  int delay_ms = 1;

  dac_tmp = 0x0;

  dac_tmp = dac_tmp | 0x8;
  write_dac(dac_tmp);
  delay(delay_ms);
  val = digitalRead(12);
  if (val == 1) {
    dac_tmp = dac_tmp ^ 0x8;
  }

  dac_tmp = dac_tmp | 0x4;
  write_dac(dac_tmp);
  delay(delay_ms);
  val = digitalRead(12);
  if (val == 1) {
    dac_tmp = dac_tmp ^ 0x4;
  }

  dac_tmp = dac_tmp | 0x2;
  write_dac(dac_tmp);
  delay(delay_ms);
  val = digitalRead(12);
  if (val == 1) {
    dac_tmp = dac_tmp ^ 0x2;
  }

  dac_tmp = dac_tmp | 0x1;
  write_dac(dac_tmp);
  delay(delay_ms);
  val = digitalRead(12);
  if (val == 1) {
    dac_tmp = dac_tmp ^ 0x1;
  }

  return dac_tmp;

}

void loop_iteration_dac() {
  dac_value_write = dac_value_write + 1;
  dac_value_write = dac_value_write & 0xf;

  write_dac(dac_value_write);

  Serial.println("dac_value:\n");
  Serial.print((int)dac_value_write);
  Serial.println("\n");
}

void loop_iteration_adc() {
  int value_adc_read;

  value_adc_read = read_adc();

  Serial.println("value_adc_read:\n");
  Serial.print(value_adc_read);
  Serial.println("\n");
}

void loop() {
  int delay_ms = 1;
  digitalWrite(13, HIGH);
  delay(delay_ms);
  digitalWrite(13, LOW);
  delay(delay_ms);

  if (1) {
    loop_iteration_dac();
  } else {
    loop_iteration_adc();
  }

}