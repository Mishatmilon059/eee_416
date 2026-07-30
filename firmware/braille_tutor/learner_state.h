// Per-character learner history on the ESP32, persisted to the microSD card.
//
// This mirrors LearnerState in web/storage.js field for field. Any change
// there must land here, or the features logged on hardware stop being
// comparable to the ones the model was trained on.
#ifndef LEARNER_STATE_H
#define LEARNER_STATE_H

#include <Arduino.h>
#include <SD.h>

#include "braille_map.h"
#include "rule_engine.h"

#define STATE_FILE "/state.bin"
#define STATE_MAGIC 0x42524C31u   // "BRL1"

typedef struct {
  uint16_t seen;
  uint16_t correct;
  uint16_t mistakes;
  uint16_t streak;
  uint16_t wrong_streak;
  float    mastery;
  int64_t  last_practice_s;   // wall-clock seconds; -1 = never practiced
  uint8_t  last_confidence;
} CharState;

typedef struct {
  uint32_t  magic;
  uint16_t  session_number;
  uint8_t   difficulty;
  uint8_t   spec_version;
  int64_t   last_shutdown_s;
  CharState chars[BRAILLE_LETTER_COUNT];
} LearnerBlob;

static LearnerBlob g_state;

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------
// millis() restarts at 0 on every power-up, so it cannot measure the gap
// between one day's session and the next. feature 10
// (time_since_last_practice) depends on exactly that gap.
//
// With USE_RTC 1 and a DS3231 wired up, now_seconds() returns true wall-clock
// time and the feature is correct.
//
// With USE_RTC 0 the board cannot know how long it was off. Rather than
// silently logging a wrong number, it advances a persisted epoch by a declared
// assumption on each boot and stamps every affected row so the data stays
// auditable: rows carry rtc_present=0 and you can exclude or discount them.
// Do not quietly treat those rows as if the gap were measured.

#define ASSUMED_OFF_GAP_S 86400   // declared assumption when no RTC is present

static int64_t g_epoch_base_s = 0;
static bool    g_rtc_present  = false;

static inline int64_t now_seconds() {
  return g_epoch_base_s + (int64_t)(millis() / 1000UL);
}

static void clock_begin() {
#if USE_RTC
  // Wire up a DS3231 and set g_epoch_base_s from it, then g_rtc_present = true.
  // Left explicit rather than guessed at: pick your RTC library and fill this in.
  g_rtc_present = false;
#else
  g_rtc_present = false;
#endif
  if (!g_rtc_present) {
    g_epoch_base_s = g_state.last_shutdown_s > 0
                       ? g_state.last_shutdown_s + ASSUMED_OFF_GAP_S
                       : 0;
  }
}

// ---------------------------------------------------------------------------

static void state_reset() {
  memset(&g_state, 0, sizeof(g_state));
  g_state.magic = STATE_MAGIC;
  g_state.session_number = 0;
  g_state.difficulty = 1;
  g_state.spec_version = SPEC_VERSION;
  g_state.last_shutdown_s = 0;
  for (int i = 0; i < BRAILLE_LETTER_COUNT; i++) {
    g_state.chars[i].mastery = MASTERY_INITIAL;
    g_state.chars[i].last_practice_s = -1;
    g_state.chars[i].last_confidence = 1;  // HESITANT
  }
}

static bool state_load() {
  File f = SD.open(STATE_FILE, FILE_READ);
  if (!f) return false;
  if (f.size() != sizeof(LearnerBlob)) { f.close(); return false; }
  LearnerBlob tmp;
  f.read((uint8_t *)&tmp, sizeof(tmp));
  f.close();
  if (tmp.magic != STATE_MAGIC) return false;
  if (tmp.spec_version != SPEC_VERSION) {
    // A spec change alters what the labels mean. Carrying old history forward
    // would mix two different definitions in one dataset.
    Serial.printf("state.bin is spec v%u, firmware is v%u -- discarding history\n",
                  tmp.spec_version, (unsigned)SPEC_VERSION);
    return false;
  }
  g_state = tmp;
  return true;
}

static bool state_save() {
  g_state.last_shutdown_s = now_seconds();
  SD.remove(STATE_FILE);
  File f = SD.open(STATE_FILE, FILE_WRITE);
  if (!f) return false;
  size_t n = f.write((const uint8_t *)&g_state, sizeof(g_state));
  f.close();
  return n == sizeof(g_state);
}

static inline CharState *char_state(uint8_t id) { return &g_state.chars[id]; }

static inline float char_accuracy(uint8_t id) {
  CharState *c = char_state(id);
  return c->seen == 0 ? 0.0f : (float)c->correct / (float)c->seen;
}

// Seconds since this character was last practiced. A never-practiced character
// returns the clamp maximum, matching timeSinceLastPractice() in
// web/storage.js -- reporting 0 there would read as "just practiced" to the
// rule engine, which is the opposite of the truth.
static inline double time_since_last_practice(uint8_t id) {
  CharState *c = char_state(id);
  if (c->last_practice_s < 0) return FEATURE_MAX[9];
  double d = (double)(now_seconds() - c->last_practice_s);
  return d < 0 ? 0.0 : d;
}

// Apply a scored attempt. Call order matters: read the pre-attempt features
// BEFORE this, then read current_streak/wrong_streak after. See the spec's
// _feature_timing_contract.
static void apply_outcome(uint8_t id, bool correct, uint8_t confidence) {
  CharState *c = char_state(id);
  c->seen++;
  if (correct) {
    c->correct++;
    c->streak++;
    c->wrong_streak = 0;
  } else {
    c->mistakes++;
    c->wrong_streak++;
    c->streak = 0;
  }
  double m = update_mastery(c->mastery, correct ? 1 : 0);
  c->mastery = (float)(m < 0.0 ? 0.0 : (m > 1.0 ? 1.0 : m));
  c->last_practice_s = now_seconds();
  c->last_confidence = confidence;
}

#endif  // LEARNER_STATE_H
