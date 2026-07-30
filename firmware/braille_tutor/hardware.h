// Buttons, vibration motors, audio, and SD logging.
#ifndef HARDWARE_H
#define HARDWARE_H

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>

#include "pins.h"

// ---------------------------------------------------------------------------
// Buttons: 6 GPIO with debounce and per-dot press/release timing.
// Timing feeds response_time and press_duration, which the model consumes, so
// it is measured from the DEBOUNCED edge -- the raw edge bounces for several
// milliseconds and would add noise the web app does not have.
// ---------------------------------------------------------------------------

typedef struct {
  bool     stable[6];
  bool     raw[6];
  uint32_t last_change_ms[6];
  uint32_t press_ms[6];       // when this dot went down, 0 if never
  uint32_t release_ms[6];
  uint8_t  mask;              // dots pressed this attempt
  uint8_t  press_order[6];
  uint8_t  press_count;
  uint32_t first_press_ms;    // 0 until the first debounced press
  uint32_t total_hold_ms;
  uint8_t  hold_samples;
} ButtonState;

static ButtonState g_btn;

static void buttons_begin() {
  for (int i = 0; i < 6; i++) pinMode(PIN_BUTTON[i], INPUT_PULLUP);
  memset(&g_btn, 0, sizeof(g_btn));
  for (int i = 0; i < 6; i++) g_btn.stable[i] = g_btn.raw[i] = false;
}

static void buttons_reset_attempt() {
  g_btn.mask = 0;
  g_btn.press_count = 0;
  g_btn.first_press_ms = 0;
  g_btn.total_hold_ms = 0;
  g_btn.hold_samples = 0;
  for (int i = 0; i < 6; i++) {
    g_btn.press_ms[i] = 0;
    g_btn.release_ms[i] = 0;
  }
}

static inline bool button_raw(int i) {
#if BUTTON_ACTIVE_LOW
  return digitalRead(PIN_BUTTON[i]) == LOW;
#else
  return digitalRead(PIN_BUTTON[i]) == HIGH;
#endif
}

// Call often. Returns true if any dot changed state this call.
static bool buttons_poll() {
  bool changed = false;
  uint32_t now = millis();
  for (int i = 0; i < 6; i++) {
    bool r = button_raw(i);
    if (r != g_btn.raw[i]) {
      g_btn.raw[i] = r;
      g_btn.last_change_ms[i] = now;
    }
    if (r != g_btn.stable[i] && (now - g_btn.last_change_ms[i]) >= BUTTON_DEBOUNCE_MS) {
      g_btn.stable[i] = r;
      changed = true;
      if (r) {
        if (g_btn.first_press_ms == 0) g_btn.first_press_ms = now;
        g_btn.press_ms[i] = now;
        if (!(g_btn.mask & (1 << i))) {
          g_btn.mask |= (1 << i);
          if (g_btn.press_count < 6) g_btn.press_order[g_btn.press_count++] = i + 1;
        }
      } else {
        g_btn.release_ms[i] = now;
        if (g_btn.press_ms[i]) {
          g_btn.total_hold_ms += (now - g_btn.press_ms[i]);
          g_btn.hold_samples++;
        }
      }
    }
  }
  return changed;
}

// Mean press->release duration, ms. Dots still held are closed out at `now`,
// matching meanPressDuration() in web/braille_cell.js.
static double buttons_mean_press_duration() {
  uint32_t total = g_btn.total_hold_ms;
  uint8_t n = g_btn.hold_samples;
  uint32_t now = millis();
  for (int i = 0; i < 6; i++) {
    if (g_btn.stable[i] && g_btn.press_ms[i]) {
      total += (now - g_btn.press_ms[i]);
      n++;
    }
  }
  return n == 0 ? 0.0 : (double)total / (double)n;
}

static inline bool buttons_any_held() {
  for (int i = 0; i < 6; i++) if (g_btn.stable[i]) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Vibration motors (through the ULN2803A)
// ---------------------------------------------------------------------------

static void motors_begin() {
  for (int i = 0; i < 6; i++) {
    pinMode(PIN_MOTOR[i], OUTPUT);
    digitalWrite(PIN_MOTOR[i], MOTOR_ACTIVE_HIGH ? LOW : HIGH);
  }
}

static inline void motor_set(int i, bool on) {
  digitalWrite(PIN_MOTOR[i], (MOTOR_ACTIVE_HIGH ? on : !on) ? HIGH : LOW);
}

static void motors_all_off() {
  for (int i = 0; i < 6; i++) motor_set(i, false);
}

// Buzz the raised dots of a pattern simultaneously.
static void motors_show_pattern(uint8_t mask, uint16_t ms) {
  for (int i = 0; i < 6; i++) motor_set(i, mask & (1 << i));
  delay(ms);
  motors_all_off();
}

// Buzz the raised dots one at a time, in dot order. Easier to distinguish by
// touch than all-at-once when the learner is still building the mental map.
static void motors_show_sequential(uint8_t mask, uint16_t on_ms, uint16_t gap_ms) {
  for (int i = 0; i < 6; i++) {
    if (!(mask & (1 << i))) continue;
    motor_set(i, true);
    delay(on_ms);
    motor_set(i, false);
    delay(gap_ms);
  }
}

static void motors_buzz_all(uint16_t ms) {
  for (int i = 0; i < 6; i++) motor_set(i, true);
  delay(ms);
  motors_all_off();
}

// ---------------------------------------------------------------------------
// Audio (DFPlayer Mini on UART2)
// ---------------------------------------------------------------------------
// Requires the DFRobotDFPlayerMini library. Guarded so the sketch still builds
// and the model still runs without it, for bring-up on a bare board.

#if __has_include(<DFRobotDFPlayerMini.h>)
#include <DFRobotDFPlayerMini.h>
#define HAVE_DFPLAYER 1
static DFRobotDFPlayerMini g_df;
static bool g_df_ok = false;

static bool audio_begin() {
  Serial2.begin(9600, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  delay(400);
  g_df_ok = g_df.begin(Serial2, /*isACK=*/true, /*doReset=*/true);
  if (g_df_ok) g_df.volume(DF_VOLUME);
  return g_df_ok;
}

// Plays a track and BLOCKS until it finishes, so the response-time clock can
// start when the prompt ends. Starting it when playback begins would fold the
// clip length into response_time and break comparability with the web app,
// where the clock starts on the audio 'ended' event.
static void audio_play_blocking(uint16_t track, uint32_t timeout_ms = 4000) {
  if (!g_df_ok) { delay(250); return; }
  g_df.play(track);
  uint32_t t0 = millis();
  delay(120);
  while (millis() - t0 < timeout_ms) {
    if (g_df.available()) {
      uint8_t type = g_df.readType();
      if (type == DFPlayerPlayFinished) return;
    }
    delay(15);
  }
}
#else
#define HAVE_DFPLAYER 0
static bool g_df_ok = false;
static bool audio_begin() { return false; }
static void audio_play_blocking(uint16_t track, uint32_t timeout_ms = 4000) {
  (void)track; (void)timeout_ms; delay(300);
}
#endif

// ---------------------------------------------------------------------------
// microSD
// ---------------------------------------------------------------------------

#define LOG_FILE "/attempts.csv"

// Must match CSV_COLUMNS in web/storage.js and tools/export_dataset.py, so a
// card pulled from the device merges into the same dataset with no reshaping.
static const char *LOG_HEADER =
  "created_at,user_id,session_id,device_id,attempt_index,"
  "char_id,response_time,press_duration,retry_count,prev_accuracy,prev_mastery,"
  "hint_count,session_number,difficulty_level,time_since_last_practice,"
  "prev_confidence,current_streak,wrong_streak,prev_mistakes,"
  "teaching_action,confidence_state,expected_pattern,entered_pattern,is_correct,"
  "press_order,source,is_synthetic,spec_version,braille_map_verified,rtc_present";

static bool g_sd_ok = false;

static bool sd_begin() {
  SPI.begin(PIN_SD_CLK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  g_sd_ok = SD.begin(PIN_SD_CS);
  if (!g_sd_ok) return false;
  if (!SD.exists(LOG_FILE)) {
    File f = SD.open(LOG_FILE, FILE_WRITE);
    if (f) { f.println(LOG_HEADER); f.close(); }
  }
  return true;
}

static bool sd_append(const char *line) {
  if (!g_sd_ok) return false;
  File f = SD.open(LOG_FILE, FILE_APPEND);
  if (!f) return false;
  f.println(line);
  f.close();          // closed every row: a mid-session power loss then costs
  return true;        // at most the current row, not the whole session
}

#endif  // HARDWARE_H
