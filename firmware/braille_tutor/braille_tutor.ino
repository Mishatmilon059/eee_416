// Bangla Braille Tutor -- ESP32 firmware.
//
// Runs the trained model fully offline: no WiFi, no network, no cloud. The
// radio is explicitly turned off in setup().
//
// Board: ESP32-WROOM-32 (Arduino core 3.x)
// Libraries: DFRobotDFPlayerMini (optional at build time; the sketch runs
//            without it so you can bring the board up before the audio works)
//
// Before flashing, regenerate the headers so firmware matches the data:
//   python3 tools/gen_engine.py
//   python3 tools/gen_braille_header.py
//   python3 tools/train.py && python3 tools/tflite_to_header.py
//
// Bring-up order matters. Do not flash this sketch first -- work through
// firmware/tests/ one peripheral at a time. Wiring six motors, six buttons,
// a DFPlayer and an SD card all at once and then debugging the result is
// how a week disappears.

#include <Arduino.h>
#include <WiFi.h>
#include <esp_bt.h>

#include "pins.h"
#include "braille_map.h"
#include "rule_engine.h"
#include "hardware.h"
#include "learner_state.h"
#include "model_data.h"

// --- TFLite Micro ----------------------------------------------------------
#include <TensorFlowLite_ESP32.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {
const tflite::Model *g_model = nullptr;
tflite::MicroInterpreter *g_interpreter = nullptr;
TfLiteTensor *g_input = nullptr;
TfLiteTensor *g_out_conf = nullptr;    // 3 classes
TfLiteTensor *g_out_teach = nullptr;   // 6 classes
alignas(16) uint8_t g_arena[MODEL_ARENA_SIZE];
}  // namespace

// --- session ---------------------------------------------------------------
#define MAX_TRIES_PER_PROMPT 4     // must match web/app.js
#define ATTEMPTS_PER_SESSION SESSION_TARGET_ATTEMPTS
#define DEVICE_ID "esp32_01"
#define USER_ID   "HW01"

static char g_session_id[24];
static int  g_attempt_index = 0;
static bool g_model_ok = false;

// ===========================================================================
// model
// ===========================================================================

static bool model_begin() {
  g_model = tflite::GetModel(MODEL_DATA);
  if (g_model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.printf("model schema %lu != supported %d\n",
                  (unsigned long)g_model->version(), TFLITE_SCHEMA_VERSION);
    return false;
  }

  // MicroMutableOpResolver, not AllOpsResolver: this model needs four kernels
  // and linking all ~80 wastes a large amount of flash for nothing.
  static tflite::MicroMutableOpResolver<4> resolver;
  resolver.AddFullyConnected();
  resolver.AddSoftmax();
  resolver.AddQuantize();
  resolver.AddDequantize();

  static tflite::MicroInterpreter interpreter(g_model, resolver, g_arena, sizeof(g_arena));
  g_interpreter = &interpreter;
  if (g_interpreter->AllocateTensors() != kTfLiteOk) {
    Serial.println("AllocateTensors failed -- raise MODEL_ARENA_SIZE");
    return false;
  }

  g_input = g_interpreter->input(0);
  // Match outputs by class count rather than index: the converter does not
  // promise to preserve the order the Keras model declared them in.
  for (size_t i = 0; i < g_interpreter->outputs_size(); i++) {
    TfLiteTensor *t = g_interpreter->output(i);
    int n = t->dims->data[t->dims->size - 1];
    if (n == MODEL_CONF_CLASSES) g_out_conf = t;
    else if (n == MODEL_TEACH_CLASSES) g_out_teach = t;
  }
  if (!g_input || !g_out_conf || !g_out_teach) {
    Serial.println("could not match model outputs to heads");
    return false;
  }

  Serial.printf("model ok: %u bytes, arena used %u / %u\n",
                (unsigned)MODEL_DATA_LEN,
                (unsigned)g_interpreter->arena_used_bytes(),
                (unsigned)sizeof(g_arena));
  return true;
}

// Run inference on already-normalized features.
static void model_infer(const float *norm, uint8_t *teaching, uint8_t *confidence) {
  for (int i = 0; i < FEATURE_COUNT; i++) {
    int32_t q = (int32_t)lroundf(norm[i] / MODEL_INPUT_SCALE) + MODEL_INPUT_ZERO_POINT;
    if (q < -128) q = -128;
    if (q > 127) q = 127;
    g_input->data.int8[i] = (int8_t)q;
  }
  if (g_interpreter->Invoke() != kTfLiteOk) {
    Serial.println("Invoke failed");
    *teaching = TA_NORMAL_PRACTICE;
    *confidence = CS_HESITANT;
    return;
  }
  int best = 0;
  for (int i = 1; i < MODEL_TEACH_CLASSES; i++)
    if (g_out_teach->data.int8[i] > g_out_teach->data.int8[best]) best = i;
  *teaching = (uint8_t)best;

  best = 0;
  for (int i = 1; i < MODEL_CONF_CLASSES; i++)
    if (g_out_conf->data.int8[i] > g_out_conf->data.int8[best]) best = i;
  *confidence = (uint8_t)best;
}

// Replay the vectors train.py captured. If any mismatches, the board is not
// computing what the desktop computed and every number downstream is suspect.
static bool model_self_test() {
  if (GOLDEN_VECTOR_COUNT == 0) {
    Serial.println("no golden vectors compiled in -- skipping self-test");
    return true;
  }
  int fails = 0;
  for (int i = 0; i < GOLDEN_VECTOR_COUNT; i++) {
    uint8_t ta, cs;
    model_infer(GOLDEN_VECTORS[i].features_norm, &ta, &cs);
    if (ta != GOLDEN_VECTORS[i].expect_teaching ||
        cs != GOLDEN_VECTORS[i].expect_confidence) {
      fails++;
      Serial.printf("  golden[%d] MISMATCH: got ta=%u cs=%u, expected ta=%d cs=%d\n",
                    i, ta, cs, GOLDEN_VECTORS[i].expect_teaching,
                    GOLDEN_VECTORS[i].expect_confidence);
    }
  }
  Serial.printf("golden self-test: %d/%d passed\n",
                GOLDEN_VECTOR_COUNT - fails, GOLDEN_VECTOR_COUNT);
  return fails == 0;
}

// ===========================================================================
// session
// ===========================================================================

static uint8_t pick_letter(uint8_t prev_action, uint8_t prev_id, bool have_prev) {
  // Mirrors pickLetter() in web/app.js.
  if (have_prev && (prev_action == TA_REPEAT || prev_action == TA_HINT)) return prev_id;

  if (have_prev && prev_action == TA_REVIEW_PREVIOUS) {
    uint8_t weak[BRAILLE_LETTER_COUNT];
    int n = 0;
    for (int i = 0; i < BRAILLE_LETTER_COUNT; i++)
      if (g_state.chars[i].seen > 0 && g_state.chars[i].mastery < 0.6f) weak[n++] = i;
    if (n > 0) return weak[random(n)];
  }

  // weight inversely to mastery so weak characters recur more often
  float weights[BRAILLE_LETTER_COUNT], total = 0.0f;
  for (int i = 0; i < BRAILLE_LETTER_COUNT; i++) {
    weights[i] = 0.15f + (1.0f - g_state.chars[i].mastery);
    total += weights[i];
  }
  float r = (float)random(10000) / 10000.0f * total;
  for (int i = 0; i < BRAILLE_LETTER_COUNT; i++) {
    r -= weights[i];
    if (r <= 0) return i;
  }
  return BRAILLE_LETTER_COUNT - 1;
}

static void log_attempt(uint8_t id, const Features *f, uint8_t action, uint8_t confidence,
                        uint8_t expected, uint8_t entered, bool correct) {
  char order[24] = "[";
  for (int i = 0; i < g_btn.press_count; i++) {
    char tmp[6];
    snprintf(tmp, sizeof(tmp), "%s%u", i ? "," : "", g_btn.press_order[i]);
    strncat(order, tmp, sizeof(order) - strlen(order) - 2);
  }
  strncat(order, "]", sizeof(order) - strlen(order) - 1);

  char line[560];
  snprintf(line, sizeof(line),
    "%lld,%s,%s,%s,%d,"
    "%d,%.1f,%.1f,%d,%.4f,%.4f,"
    "%d,%d,%d,%.1f,"
    "%d,%d,%d,%d,"
    "%u,%u,%u,%u,%s,"
    "\"%s\",esp32,false,%d,%s,%d",
    (long long)now_seconds(), USER_ID, g_session_id, DEVICE_ID, g_attempt_index,
    (int)f->char_id, f->response_time, f->press_duration, (int)f->retry_count,
    f->prev_accuracy, f->prev_mastery,
    (int)f->hint_count, (int)f->session_number, (int)f->difficulty_level,
    f->time_since_last_practice,
    (int)f->prev_confidence, (int)f->current_streak, (int)f->wrong_streak,
    (int)f->prev_mistakes,
    action, confidence, expected, entered, correct ? "true" : "false",
    order, (int)SPEC_VERSION, BRAILLE_MAP_VERIFIED ? "true" : "false",
    g_rtc_present ? 1 : 0);

  if (!sd_append(line)) Serial.println("SD append failed");
  Serial.println(line);
}

// One prompt: play audio, collect the pattern, score, infer, give feedback.
// Returns the teaching action chosen.
static uint8_t run_attempt(uint8_t id, int tries, int hints) {
  CharState *c = char_state(id);
  uint8_t expected = BRAILLE_PATTERN[id];

  // --- prompt ---------------------------------------------------------
  buttons_reset_attempt();
  audio_play_blocking(braille_track(id));
  uint32_t prompt_end_ms = millis();   // clock starts when the prompt ENDS

  // --- collect the answer ---------------------------------------------
  // Submit = all six released after at least one press, or a 15 s timeout.
  uint32_t deadline = prompt_end_ms + 15000;
  bool saw_press = false;
  while (millis() < deadline) {
    buttons_poll();
    if (g_btn.mask) saw_press = true;
    if (saw_press && !buttons_any_held()) {
      delay(450);                       // settle window for multi-dot patterns
      buttons_poll();
      if (!buttons_any_held()) break;
    }
    delay(3);
  }

  uint8_t entered = g_btn.mask;
  bool correct = (entered == expected);

  // --- pre-attempt history (read BEFORE apply_outcome) ------------------
  double pre_accuracy = char_accuracy(id);
  double pre_mastery  = c->mastery;
  double pre_mistakes = c->mistakes;
  double pre_conf     = c->last_confidence;
  double gap_s        = time_since_last_practice(id);

  double response_time = g_btn.first_press_ms
                           ? (double)(g_btn.first_press_ms - prompt_end_ms)
                           : (double)(millis() - prompt_end_ms);
  if (response_time < 0) response_time = 0;

  // --- post-attempt state, then read the streaks -----------------------
  apply_outcome(id, correct, (uint8_t)pre_conf);

  Features f;
  f.char_id                  = (double)id;
  f.response_time            = response_time;
  f.press_duration           = buttons_mean_press_duration();
  f.retry_count              = (double)tries;
  f.prev_accuracy            = pre_accuracy;
  f.prev_mastery             = pre_mastery;
  f.hint_count               = (double)hints;
  f.session_number           = (double)g_state.session_number;
  f.difficulty_level         = (double)g_state.difficulty;
  f.time_since_last_practice = gap_s;
  f.prev_confidence          = pre_conf;
  f.current_streak           = (double)c->streak;
  f.wrong_streak             = (double)c->wrong_streak;
  f.prev_mistakes            = pre_mistakes;

  // --- decide -----------------------------------------------------------
  uint8_t action, confidence;
  if (g_model_ok) {
    float norm[FEATURE_COUNT];
    normalize_features(&f, norm);
    model_infer(norm, &action, &confidence);
  } else {
    // The rule engine is the fallback, and it is the same rules the model was
    // trained on, so behaviour degrades gracefully rather than stopping.
    action = (uint8_t)evaluate_teaching_action(&f);
    confidence = (uint8_t)evaluate_confidence(&f);
  }
  c->last_confidence = confidence;

  if (action == TA_INCREASE_DIFFICULTY && g_state.difficulty < 5) g_state.difficulty++;
  else if (action == TA_REVIEW_PREVIOUS && g_state.difficulty > 1) g_state.difficulty--;

  // --- feedback ---------------------------------------------------------
  if (correct) {
    audio_play_blocking(51);            // "সঠিক"
    motors_buzz_all(160);
  } else {
    audio_play_blocking(52);            // "ভুল"
    delay(120);
    motors_show_sequential(expected, 320, 180);   // feel the right answer
  }
  if (action == TA_HINT) {
    audio_play_blocking(54);
    motors_show_sequential(expected, 400, 220);
  }

  log_attempt(id, &f, action, confidence, expected, entered, correct);
  g_attempt_index++;
  return action;
}

// ===========================================================================

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println("\n=== Bangla Braille Tutor (ESP32) ===");

  // Offline by design. The radio is the largest power draw on this board and
  // nothing here needs it -- inference, audio, and logging are all local.
  WiFi.mode(WIFI_OFF);
  btStop();
  Serial.println("WiFi + BT off (offline inference)");

  buttons_begin();
  motors_begin();
  motors_all_off();

  if (!sd_begin()) Serial.println("SD init FAILED -- rows will not be logged");
  else             Serial.println("SD ok");

  state_reset();
  if (state_load()) Serial.println("learner history loaded from SD");
  else              Serial.println("no usable history -- starting fresh");
  clock_begin();

  if (!g_rtc_present) {
    Serial.println("!! No RTC. Time across power-offs is ASSUMED, not measured.");
    Serial.printf("!! Rows are stamped rtc_present=0; gap assumed %d s.\n",
                  ASSUMED_OFF_GAP_S);
  }
  if (!BRAILLE_MAP_VERIFIED) {
    Serial.println("!! Braille map is UNVERIFIED (placeholder patterns).");
  }

  if (!audio_begin()) Serial.println("DFPlayer not found -- running silent");
  else                Serial.println("DFPlayer ok");

  g_model_ok = model_begin();
  if (g_model_ok) {
    if (!model_self_test()) {
      Serial.println("!! golden self-test FAILED -- falling back to the rule engine");
      g_model_ok = false;
    }
  } else {
    Serial.println("!! model unavailable -- using the rule engine");
  }

  randomSeed(esp_random());
  g_state.session_number++;
  snprintf(g_session_id, sizeof(g_session_id), "esp_%u_%lu",
           g_state.session_number, (unsigned long)(now_seconds() & 0xFFFF));
  Serial.printf("\nsession %u starting (%d attempts)\n",
                g_state.session_number, ATTEMPTS_PER_SESSION);
  audio_play_blocking(59);
}

void loop() {
  static uint8_t prev_action = TA_NORMAL_PRACTICE;
  static uint8_t prev_id = 0;
  static bool have_prev = false;

  if (g_attempt_index >= ATTEMPTS_PER_SESSION) {
    audio_play_blocking(60);
    state_save();
    Serial.printf("\nsession complete: %d attempts logged to %s\n",
                  g_attempt_index, LOG_FILE);
    Serial.println("state saved. Power off, or reset for another session.");
    while (true) delay(1000);
  }

  uint8_t id = pick_letter(prev_action, prev_id, have_prev);
  int tries = 0, hints = 0;

  while (g_attempt_index < ATTEMPTS_PER_SESSION) {
    uint8_t action = run_attempt(id, tries, hints);
    tries++;
    if (action == TA_HINT) hints++;

    bool wrong = (g_btn.mask != BRAILLE_PATTERN[id]);
    bool retry_same = wrong && tries < MAX_TRIES_PER_PROMPT &&
                      (action == TA_REPEAT || action == TA_HINT);
    prev_action = action;
    prev_id = id;
    have_prev = true;
    if (!retry_same) break;
    delay(500);
  }

  state_save();      // persist after each prompt: a power cut costs one prompt
  delay(700);
}
