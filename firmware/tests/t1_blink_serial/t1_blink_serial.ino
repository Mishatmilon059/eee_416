// Bring-up 1: is the board alive and is serial working?
// Expect: "tick N" once a second at 115200 baud, and the onboard LED blinking.
// If you see garbage, the baud rate is wrong. If you see nothing, the board
// selection or the USB cable is wrong (many USB cables are charge-only).
#define LED_PIN 2   // onboard LED on most ESP32 devkits

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("\n=== t1: blink + serial ===");
  Serial.printf("chip: %s  cores: %d  flash: %u MB\n",
                ESP.getChipModel(), ESP.getChipCores(),
                ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("free heap: %u bytes\n", ESP.getFreeHeap());
  Serial.println("PASS if you can read this line.");
}

void loop() {
  static uint32_t n = 0;
  digitalWrite(LED_PIN, n % 2);
  Serial.printf("tick %lu\n", (unsigned long)n++);
  delay(1000);
}
