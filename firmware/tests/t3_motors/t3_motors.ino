// Bring-up 3: the six vibration motors, through a ULN2803A.
//
// Expect: each motor buzzes alone for 400 ms in order 1..6, then all six
// together, then repeat.
//
// Wiring: ESP32 GPIO -> ULN2803A input (pins 1-6)
//         ULN2803A output (pins 18-13) -> motor negative
//         motor positive -> +5V
//         ULN2803A COM (pin 10) -> +5V     <-- flyback diodes, do not skip
//         ULN2803A GND (pin 9)  -> GND
//
// If a motor is weak or the ESP32 resets when several fire: your supply cannot
// hold 800 mA, or the 1000 uF bulk capacitor is missing.
// If nothing buzzes at all: COM is not tied to +5V, or you wired the motors to
// the ULN2803A inputs instead of its outputs.
static const int PIN_MOTOR[6] = { 13, 4, 21, 22, 2, 15 };

void setup() {
  Serial.begin(115200);
  delay(500);
  for (int i = 0; i < 6; i++) { pinMode(PIN_MOTOR[i], OUTPUT); digitalWrite(PIN_MOTOR[i], LOW); }
  Serial.println("\n=== t3: motors ===");
  Serial.println("Each motor buzzes alone, then all six together.");
  Serial.println("GPIO 2 and 15 are strapping pins -- they need 10k pulldowns.");
}

void loop() {
  for (int i = 0; i < 6; i++) {
    Serial.printf("motor %d (GPIO %d)\n", i + 1, PIN_MOTOR[i]);
    digitalWrite(PIN_MOTOR[i], HIGH);
    delay(400);
    digitalWrite(PIN_MOTOR[i], LOW);
    delay(250);
  }
  Serial.println("all six together -- watch for a brownout reset here");
  for (int i = 0; i < 6; i++) digitalWrite(PIN_MOTOR[i], HIGH);
  delay(600);
  for (int i = 0; i < 6; i++) digitalWrite(PIN_MOTOR[i], LOW);
  Serial.println("PASS if all six buzzed and the board did not reset.\n");
  delay(1500);
}
