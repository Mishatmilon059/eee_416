// Bring-up 6: TFLite Micro inference, verified against the desktop.
//
// Expect: "golden self-test: N/N passed" and a printed arena usage figure.
//
// This is the most important bring-up step and the easiest to skip. It replays
// the exact feature vectors train.py ran through the quantized model on the
// desktop and compares the predictions. If they match, the ESP32 is computing
// what you validated. If they do not, everything the device logs afterwards is
// measuring an unknown function, and no amount of session testing will reveal it.
//
// Copy the generated headers in first (from the repo root):
//   cp firmware/braille_tutor/{rule_engine.h,braille_map.h,model_data.h} \
//      firmware/tests/t6_model/

#include <Arduino.h>
#include <WiFi.h>

#include "rule_engine.h"
#include "braille_map.h"
#include "model_data.h"

#include <TensorFlowLite_ESP32.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {
const tflite::Model *model = nullptr;
tflite::MicroInterpreter *interpreter = nullptr;
TfLiteTensor *input = nullptr;
TfLiteTensor *out_conf = nullptr;
TfLiteTensor *out_teach = nullptr;
alignas(16) uint8_t arena[MODEL_ARENA_SIZE];
}  // namespace

static void infer(const float *norm, uint8_t *ta, uint8_t *cs) {
  for (int i = 0; i < FEATURE_COUNT; i++) {
    int32_t q = (int32_t)lroundf(norm[i] / MODEL_INPUT_SCALE) + MODEL_INPUT_ZERO_POINT;
    q = q < -128 ? -128 : (q > 127 ? 127 : q);
    input->data.int8[i] = (int8_t)q;
  }
  interpreter->Invoke();
  int b = 0;
  for (int i = 1; i < MODEL_TEACH_CLASSES; i++)
    if (out_teach->data.int8[i] > out_teach->data.int8[b]) b = i;
  *ta = b;
  b = 0;
  for (int i = 1; i < MODEL_CONF_CLASSES; i++)
    if (out_conf->data.int8[i] > out_conf->data.int8[b]) b = i;
  *cs = b;
}

void setup() {
  Serial.begin(115200);
  delay(600);
  WiFi.mode(WIFI_OFF);
  Serial.println("\n=== t6: TFLite Micro ===");
  Serial.printf("model %u bytes, free heap %u\n",
                (unsigned)MODEL_DATA_LEN, ESP.getFreeHeap());

  model = tflite::GetModel(MODEL_DATA);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.printf("FAIL: schema %lu != %d -- regenerate model_data.h\n",
                  (unsigned long)model->version(), TFLITE_SCHEMA_VERSION);
    while (true) delay(1000);
  }

  // Four kernels, not AllOpsResolver: linking ~80 unused kernels costs a large
  // amount of flash and buys nothing.
  static tflite::MicroMutableOpResolver<4> resolver;
  resolver.AddFullyConnected();
  resolver.AddSoftmax();
  resolver.AddQuantize();
  resolver.AddDequantize();

  static tflite::MicroInterpreter iface(model, resolver, arena, sizeof(arena));
  interpreter = &iface;
  if (interpreter->AllocateTensors() != kTfLiteOk) {
    Serial.println("FAIL: AllocateTensors -- raise MODEL_ARENA_SIZE in model_data.h");
    while (true) delay(1000);
  }

  input = interpreter->input(0);
  for (size_t i = 0; i < interpreter->outputs_size(); i++) {
    TfLiteTensor *t = interpreter->output(i);
    int n = t->dims->data[t->dims->size - 1];
    if (n == MODEL_CONF_CLASSES) out_conf = t;
    else if (n == MODEL_TEACH_CLASSES) out_teach = t;
  }
  if (!out_conf || !out_teach) {
    Serial.println("FAIL: could not match outputs to heads");
    while (true) delay(1000);
  }

  Serial.printf("arena used %u of %u bytes  <- you can shrink MODEL_ARENA_SIZE to this\n",
                (unsigned)interpreter->arena_used_bytes(), (unsigned)sizeof(arena));

  // --- the actual check ---------------------------------------------------
  int fails = 0;
  for (int i = 0; i < GOLDEN_VECTOR_COUNT; i++) {
    uint8_t ta, cs;
    infer(GOLDEN_VECTORS[i].features_norm, &ta, &cs);
    bool ok = (ta == GOLDEN_VECTORS[i].expect_teaching &&
               cs == GOLDEN_VECTORS[i].expect_confidence);
    if (!ok) fails++;
    Serial.printf("  golden[%2d] %s  ta=%u/%d  cs=%u/%d\n", i, ok ? "ok  " : "FAIL",
                  ta, GOLDEN_VECTORS[i].expect_teaching,
                  cs, GOLDEN_VECTORS[i].expect_confidence);
  }
  Serial.printf("\ngolden self-test: %d/%d passed\n",
                GOLDEN_VECTOR_COUNT - fails, GOLDEN_VECTOR_COUNT);
  if (fails) {
    Serial.println(">>> FAIL. The board is NOT computing what train.py computed.");
    Serial.println("    Usual cause: model_data.h is stale. Re-run");
    Serial.println("    tools/train.py then tools/tflite_to_header.py and re-copy.");
  } else {
    Serial.println(">>> PASS. Inference on-device matches the desktop.");
  }

  // timing -- this is what "real-time" means in practice
  uint8_t ta, cs;
  uint32_t t0 = micros();
  for (int i = 0; i < 100; i++) infer(GOLDEN_VECTORS[0].features_norm, &ta, &cs);
  uint32_t per = (micros() - t0) / 100;
  Serial.printf("\ninference: %lu us per call (%.1f per second)\n",
                (unsigned long)per, 1e6 / (float)per);
  Serial.printf("free heap after init: %u bytes\n", ESP.getFreeHeap());
}

void loop() { delay(5000); }
