// Bring-up 2: all six buttons, with debounce and press timing.
//
// Expect: pressing dot N prints "dot N DOWN" then "dot N UP after XXX ms".
// Every button must respond, and a single press must produce exactly one
// DOWN/UP pair. Repeated pairs from one press mean the debounce window is too
// short for your switches -- raise DEBOUNCE_MS.
//
// Wire each button between its GPIO and GND. No external resistors: these six
// pins all have usable internal pull-ups.
static const int PIN_BUTTON[6] = { 32, 33, 25, 26, 27, 14 };
#define DEBOUNCE_MS 20

bool stable[6] = {false}, raw[6] = {false};
uint32_t lastChange[6] = {0}, pressedAt[6] = {0};

void setup() {
  Serial.begin(115200);
  delay(500);
  for (int i = 0; i < 6; i++) pinMode(PIN_BUTTON[i], INPUT_PULLUP);
  Serial.println("\n=== t2: buttons ===");
  Serial.println("Press each of the 6 buttons. All six must report.");
  Serial.println("Layout: dot1 dot2 dot3 = left column, dot4 dot5 dot6 = right.");
}

void loop() {
  static uint8_t seen = 0;
  uint32_t now = millis();
  for (int i = 0; i < 6; i++) {
    bool r = (digitalRead(PIN_BUTTON[i]) == LOW);
    if (r != raw[i]) { raw[i] = r; lastChange[i] = now; }
    if (r != stable[i] && (now - lastChange[i]) >= DEBOUNCE_MS) {
      stable[i] = r;
      if (r) {
        pressedAt[i] = now;
        Serial.printf("dot %d DOWN  (GPIO %d)\n", i + 1, PIN_BUTTON[i]);
        if (!(seen & (1 << i))) {
          seen |= (1 << i);
          if (seen == 0x3F) Serial.println(">>> PASS: all 6 buttons responded");
        }
      } else {
        Serial.printf("dot %d UP    after %lu ms\n", i + 1,
                      (unsigned long)(now - pressedAt[i]));
      }
    }
  }
  delay(2);
}
