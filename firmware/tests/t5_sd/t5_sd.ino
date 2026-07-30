// Bring-up 5: microSD logging.
//
// Expect: card info, then a row appended to /t5_test.csv each loop, then the
// file read back so you can see it actually persisted.
//
// Wiring (VSPI): CLK->18  MISO->19  MOSI->23  CS->5
// Most microSD breakout modules are 3.3V logic. Check yours before feeding it
// 5V -- an over-volted module usually mounts once and then corrupts the card.
#include <SD.h>
#include <SPI.h>
#define PIN_SD_CLK 18
#define PIN_SD_MISO 19
#define PIN_SD_MOSI 23
#define PIN_SD_CS 5
#define TEST_FILE "/t5_test.csv"

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== t5: microSD ===");
  SPI.begin(PIN_SD_CLK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  if (!SD.begin(PIN_SD_CS)) {
    Serial.println("FAIL: SD.begin() failed. Check CS pin, wiring, FAT32 format.");
    while (true) delay(1000);
  }
  Serial.printf("card type %d, size %llu MB\n",
                SD.cardType(), SD.cardSize() / (1024ULL * 1024ULL));
  if (!SD.exists(TEST_FILE)) {
    File f = SD.open(TEST_FILE, FILE_WRITE);
    if (f) { f.println("millis,counter,heap"); f.close(); }
  }
}

void loop() {
  static uint32_t n = 0;
  File f = SD.open(TEST_FILE, FILE_APPEND);
  if (!f) { Serial.println("FAIL: append failed"); delay(2000); return; }
  f.printf("%lu,%lu,%u\n", (unsigned long)millis(), (unsigned long)n++, ESP.getFreeHeap());
  f.close();   // close every row: a power cut then costs one row, not the file

  f = SD.open(TEST_FILE, FILE_READ);
  Serial.printf("--- %s is now %u bytes ---\n", TEST_FILE, (unsigned)f.size());
  while (f.available()) Serial.write(f.read());
  f.close();
  Serial.println("PASS if the row count grows every 3 s and survives a reset.\n");
  delay(3000);
}
