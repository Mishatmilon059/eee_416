// Pin map and electrical notes for the ESP32-WROOM-32 build.
//
// 18 pins on a chip with ~25 usable, so it fits, but the assignment is not
// arbitrary -- read the notes before moving anything.
#ifndef PINS_H
#define PINS_H

// --- buttons ---------------------------------------------------------------
// All six have usable internal pull-ups. Deliberately NOT on 34/35/36/39:
// those are input-only AND have no internal pull-up, so they would need six
// external resistors for no benefit.
static const int PIN_BUTTON[6] = { 32, 33, 25, 26, 27, 14 };
#define BUTTON_ACTIVE_LOW 1
#define BUTTON_DEBOUNCE_MS 20

// --- vibration motors, through a ULN2803A ----------------------------------
// Use the ULN2803A, not six discrete transistors. Coin motors are inductive;
// the ULN2803A has flyback diodes built in (tie its COM pin to +5V). Driving
// an inductive motor off a bare GPIO, or off a transistor with no flyback
// path, is the single most common way this build destroys a pin.
//
// GPIO 2 and 15 are strapping pins. They are usable as outputs but are sampled
// at boot, so add 10k pulldowns on both. GPIO 12 is deliberately unused: it
// must be LOW at boot or the chip picks the wrong flash voltage.
static const int PIN_MOTOR[6] = { 13, 4, 21, 22, 2, 15 };
#define MOTOR_ACTIVE_HIGH 1

// --- DFPlayer Mini, UART2 --------------------------------------------------
// Put a 1k resistor in series with the DFPlayer's RX line: it is a 3.3V-logic
// part fed from 5V and the resistor limits current into its input protection.
#define PIN_DF_RX 16   // ESP32 receives  <- DFPlayer TX
#define PIN_DF_TX 17   // ESP32 transmits -> DFPlayer RX
#define DF_VOLUME 22   // 0..30

// --- microSD, VSPI ---------------------------------------------------------
#define PIN_SD_CLK  18
#define PIN_SD_MISO 19
#define PIN_SD_MOSI 23
#define PIN_SD_CS    5

// --- optional DS3231 RTC, I2C ----------------------------------------------
// Strongly recommended. Without a real-time clock the board cannot know how
// much time passed while it was powered off, so feature 10
// (time_since_last_practice) -- one of the 14 the model consumes -- degrades
// to a guess across sessions. See the note in learner_state.h.
#define PIN_RTC_SDA
#define PIN_RTC_SCL
#define USE_RTC 0     // set to 1 after wiring a DS3231

// --- power -----------------------------------------------------------------
// 6 motors ~480 mA peak + ESP32 ~80 mA (WiFi off) + DFPlayer/speaker ~200 mA
// => ~800 mA peak. Use a 5V 2A supply, not a laptop USB port. Put a 1000 uF
// bulk capacitor across the motor rail: without it, the motor inrush browns
// out the 3V3 regulator and the ESP32 reboots mid-session, which looks like a
// firmware crash and is not one.
//
// Never drive the motors from the ESP32's 3V3 pin. Common ground everywhere.

#endif  // PINS_H
