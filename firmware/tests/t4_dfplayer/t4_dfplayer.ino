// Bring-up 4: DFPlayer Mini audio.
//
// Expect: tracks 1, 2, 3 (Bangla letters) then 51 ("সঠিক") play in turn.
//
// SD card layout the DFPlayer requires -- it plays by NUMBER, not filename:
//     /mp3/0001.mp3 ... /mp3/0050.mp3   letters
//     /mp3/0051.mp3 ... /mp3/0060.mp3   system prompts
// Copy the generated sd_card/mp3/ folder to the card root.
//
// Wiring: ESP32 GPIO17 -> 1k resistor -> DFPlayer RX
//         ESP32 GPIO16 <-              DFPlayer TX
//         DFPlayer VCC -> 5V, GND -> GND, SPK_1/SPK_2 -> speaker
//
// "begin() failed" almost always means the card is not FAT32, the mp3 folder
// is missing, or RX/TX are swapped.
#include <DFRobotDFPlayerMini.h>
#define PIN_DF_RX 16
#define PIN_DF_TX 17

DFRobotDFPlayerMini df;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== t4: DFPlayer ===");
  Serial2.begin(9600, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  delay(400);
  if (!df.begin(Serial2, true, true)) {
    Serial.println("FAIL: DFPlayer begin() failed.");
    Serial.println("  - card FAT32 formatted?");
    Serial.println("  - files in /mp3 named 0001.mp3 ... ?");
    Serial.println("  - RX/TX swapped?");
    while (true) delay(1000);
  }
  df.volume(22);
  Serial.printf("ok. files on card: %d (expect 60)\n", df.readFileCounts());
}

void loop() {
  const uint16_t tracks[] = { 1, 2, 3, 51 };
  for (uint16_t t : tracks) {
    Serial.printf("play track %u\n", t);
    df.play(t);
    delay(2000);
  }
  Serial.println("PASS if you heard four clips.\n");
  delay(1500);
}
