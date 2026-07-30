# AI-Assisted Bangla Braille Tutor — End-to-End Project Report

**Repository:** `Mishatmilon059/eee_416`
**Branch:** `claude/esp32-offline-ml-plan-uqbjnd`
**Report date:** 30 July 2026
**Status:** software complete and tested · data collection not started · hardware not built

---

## 1. What this project is

A system that teaches Bangla Braille, records how learners perform, trains a
small neural network on those recordings, and runs that network **entirely
offline on an ESP32 microcontroller** driving six vibration motors, six push
buttons, and spoken audio.

It has three parts:

| Part | Purpose | Status |
|---|---|---|
| **Web MVP** | Data-collection instrument. Teaches, and records every attempt. | ✅ Built and tested |
| **Training pipeline** | CSV → multi-task network → 8-bit model → C header | ✅ Built and tested |
| **ESP32 firmware** | Runs the model on hardware, no internet | ✅ Written, ⚠ not run on real hardware |

---

## 2. Honest summary — read this first

Three statements that must appear in any write-up of this project:

**2.1 The model imitates a rule engine; it does not discover teaching policy.**
The training labels are produced by a hand-written rule engine. A network
trained on them learns to reproduce that rule engine — measured at 96.7%
agreement. This is a legitimate TinyML result (train → quantize → deploy →
real-time offline inference in 5,928 bytes), but describing it as autonomous
adaptive learning would be false. One question — *"where did the labels come
from?"* — exposes the difference.

**2.2 No real learner data exists yet.** Every accuracy figure in this report
comes from a synthetic-data pipeline test. Those numbers are circular: the rows
were simulated and labelled by the same rule engine the network is asked to
reproduce. They prove the *pipeline* works. They say nothing about real people.

**2.3 39 of 50 Braille characters are unverified.** The 11 vowels were read
from supplied reference images. The 39 consonants still carry placeholder
patterns derived from the Bharati Braille standard. Evidence they are not
reliable: of 11 vowel guesses, **1 was wrong**. At that rate roughly 3–4
consonants are also wrong, and there is no way to tell which without images.

---

## 3. Architecture

```
                        ┌──────────────────────────┐
                        │  spec/engine_spec.json   │  ← source of truth
                        │  data/braille_map.json   │
                        └────────────┬─────────────┘
                                     │  code generators
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
      web/rule_engine.js    tools/rule_engine_gen.py   firmware/rule_engine.h
              │                      │                      │
              ▼                      ▼                      ▼
      ┌───────────────┐      ┌──────────────┐      ┌────────────────┐
      │  Web MVP      │      │  Synthetic   │      │  ESP32         │
      │  (browser)    │      │  generator   │      │  firmware      │
      └───────┬───────┘      └──────┬───────┘      └────────┬───────┘
              │ real rows           │ synthetic rows        │
              └──────────┬──────────┘                       │
                         ▼                                  │
                  ┌─────────────┐                           │
                  │  Supabase   │                           │
                  │  attempts   │                           │
                  └──────┬──────┘                           │
                         ▼                                  │
                  ┌─────────────┐                           │
                  │  train.py   │  1,161 params             │
                  └──────┬──────┘                           │
                         ▼                                  │
                  model.tflite (5,928 B int8) ──────────────┘
```

### 3.1 The central design decision

Everything downstream is **generated from two data files**. This exists to
eliminate one specific failure: the browser and the ESP32 computing features or
rules slightly differently, so a model trained on browser data misbehaves on
hardware. That class of bug is invisible until integration and expensive to
find then.

The rule engine is written **once** in `spec/engine_spec.json` and generated
into JavaScript, C, and Python. `tools/test_parity.py` pushes **3,000 feature
vectors** — including values sitting exactly on every decision threshold —
through all three and asserts identical output for the teaching action, the
confidence state, and all 14 normalized values. It passes.

Feature normalization uses **fixed ranges from the spec, not statistics derived
from the dataset**. A dataset-derived scale would shift every time the model is
retrained, silently desynchronising the ESP32 from the model it is running.

---

## 4. The learning model

### 4.1 Features (14)

Sampled at three distinct moments. Web and firmware must sample identically or
the model misbehaves on hardware.

| # | Feature | Unit | Sampled |
|---|---|---|---|
| 1 | `char_id` | 0–49 | before attempt |
| 2 | `response_time` | ms | during attempt |
| 3 | `press_duration` | ms | during attempt |
| 4 | `retry_count` | count | during attempt |
| 5 | `prev_accuracy` | 0–1 | before attempt |
| 6 | `prev_mastery` | 0–1 | before attempt |
| 7 | `hint_count` | count | during attempt |
| 8 | `session_number` | count | before attempt |
| 9 | `difficulty_level` | 1–5 | before attempt |
| 10 | `time_since_last_practice` | s | before attempt |
| 11 | `prev_confidence` | 0–2 | before attempt |
| 12 | `current_streak` | count | **after attempt** |
| 13 | `wrong_streak` | count | **after attempt** |
| 14 | `prev_mistakes` | count | before attempt |

**There is deliberately no `is_correct` feature.** Because the two streaks are
sampled *after* scoring, correctness is derivable: `current_streak > 0` means
the attempt was correct, `wrong_streak > 0` means it was wrong, and exactly one
is non-zero. This matters — the rule engine branches on `wrong_streak`. Had the
streaks been sampled before scoring, the engine would be branching on
information absent from the model's input, and accuracy would cap out for
reasons that look like a training bug but are not.

### 4.2 Outputs

- **Teaching action (6):** Repeat · Hint · Normal Practice · Increase Difficulty · Review Previous · Word Practice
- **Confidence state (3):** Confident · Hesitant · Guessing

### 4.3 Network

```
Input(14) → Dense(32, ReLU) → Dense(16, ReLU) → ┬→ Dense(3, softmax)  confidence
                                                 └→ Dense(6, softmax)  teaching
```

**1,161 trainable parameters.** Trains in seconds on a laptop CPU; no GPU.

Class balancing is folded into the loss function because Keras 3 rejects both
`class_weight` and `sample_weight` on multi-output models. Without it the rare
teaching actions are ignored in favour of the majority class, which reads as
good accuracy and is useless.

---

## 5. Results (pipeline validation only — no real data)

From `models/metrics.json`, trained on 600 synthetic rows:

| Metric | Value | Interpretation |
|---|---|---|
| Trainable parameters | 1,161 | |
| Teaching action accuracy | 96.7% | vs 37.4% majority baseline |
| Confidence state accuracy | 87.9% | vs 52.7% majority baseline |
| Rule-engine agreement | 96.7% | expected — the labels *are* the rule engine |
| TFLite vs Keras agreement | **100%** | 8-bit quantization changed nothing |
| Quantized model size | **5,928 bytes** | |
| Real-data accuracy | **N/A** | no real rows collected |

The majority baseline is reported beside every accuracy because "96.7%
accurate" is unreadable without it — a model barely above baseline has learned
almost nothing.

### 5.1 Memory footprint on ESP32

| Item | Size |
|---|---|
| Model | 5,928 B |
| Tensor arena | 8 KB |
| **Total** | **13.8 KB of 520 KB SRAM (2.7%)** |

**Model size was never a risk on this project.** The constraints are recruiting
participants and building hardware.

---

## 6. Data strategy: 40% real / 60% synthetic

### 6.1 Order is load-bearing

Collect real data **first**, fit distributions to it, *then* generate synthetic
data. Reversed, the synthetic rows are sampled from guessed ranges that
resemble nothing, and the model learns a distribution that does not exist.

### 6.2 Simulation, not sampling

`tools/gen_synthetic.py` **simulates virtual learners** through the same state
machine the web app uses, rather than sampling the 14 features independently.
Independent sampling produces impossible combinations — `current_streak = 7`
beside `prev_mastery = 0.02` — that cannot occur in reality and waste model
capacity on a region that will never be seen.

### 6.3 Rare classes

Some teaching actions occur rarely in natural use. The generator tops these up
with scenarios **capable of producing them**: `INCREASE_DIFFICULTY` and
`WORD_PRACTICE` require high mastery and long streaks, so simulating more
struggling learners can never yield them however long it runs. Those classes
draw a strong learner drilling a small character pool instead.

Every synthetic row carries `is_synthetic = true`. `train.py` always reports
real-only metrics separately.

---

## 7. Braille data verification

### 7.1 Current state

| Category | Verified | Source |
|---|---|---|
| Vowels | **11 / 11** | supplied reference images |
| Consonants | **0 / 39** | Bharati placeholder guesses |
| **Total** | **11 / 50** | |

### 7.2 What the images proved

Of 11 vowel patterns, 10 confirmed the placeholder and **1 was corrected**:

| Letter | Placeholder | Actual |
|---|---|---|
| ঋ (ri) | `[2,3,5]` | **`[1,2,3,5]`** |

`[1,2,3,5]` is `⠗` — the cell for *r* — which is the Bharati convention for
vocalic *r*. The placeholder was a guess at an unused pattern and was wrong.

### 7.3 Extraction method

`tools/braille_image_reader.py` finds the three row bands and two column bands
by projection profile, then samples a small disc at each of the six
intersections. A raised dot is a solid disc (dark centre); an unraised dot is a
hollow ring (light centre), so centre sampling distinguishes them where
measuring ink coverage would not.

**A bug worth recording:** the first implementation split the ink bounding box
into uniform sixths. It produced correct answers on all 11 images — but with a
confidence margin of **7 grey levels** instead of 127, because the circles do
not sit at exact sixths and the sample points landed half-on the disc. Correct
by luck. Band detection restored the full margin. This mattered little for 11
images and would have mattered a great deal for 39 more.

### 7.4 Known unresolved conflict

Corrected ঋ = `[1,2,3,5]` collides with the **unverified placeholder** for
র (ra). Two letters cannot share a pattern. Since র's value is itself a guess,
this likely resolves when its image is supplied. The tooling warns on
verified-vs-placeholder and hard-fails on verified-vs-verified — a real
conflict blocks the import, an expected one does not.

### 7.5 Per-letter provenance

Verification is tracked **per letter**, not with one global flag, because
images arrive in batches. Every logged row records whether *that row's
character* was verified — so the 11 vowels' rows are usable at training time
while the consonants remain unconfirmed, instead of whole sessions being
discarded.

---

## 8. Hardware design (not yet built)

### 8.1 Bill of materials

ESP32-WROOM-32 · DFPlayer Mini + 3 W speaker · **ULN2803A** · 6 coin vibration
motors · 6 tactile buttons · microSD module · 5 V 2 A supply · 1000 µF
capacitor · 6 × 1 kΩ · 2 × 10 kΩ · *(recommended)* DS3231 RTC

### 8.2 Pin allocation — 18 of ~25 usable

| Function | GPIO | Note |
|---|---|---|
| Buttons 1–6 | 32, 33, 25, 26, 27, 14 | all have usable internal pull-ups |
| Motors 1–6 → ULN2803A | 13, 4, 21, 22, 2, 15 | GPIO 2 and 15 need 10 kΩ pulldowns |
| DFPlayer (UART2) | 16 RX, 17 TX | 1 kΩ series resistor on DFPlayer RX |
| microSD (VSPI) | 18 CLK, 19 MISO, 23 MOSI, 5 CS | |

GPIO 12 is deliberately unused — it must be LOW at boot or the chip selects the
wrong flash voltage.

### 8.3 The three failure modes most likely to kill this build

1. **No flyback protection.** Coin motors are inductive. Driving them from a
   bare GPIO, or a transistor without a flyback path, destroys pins. The
   ULN2803A has flyback diodes built in — tie its COM pin to +5 V.
2. **Under-powered supply.** Six motors ≈ 480 mA, plus ESP32 ≈ 80 mA and
   DFPlayer ≈ 200 mA → **~800 mA peak**. Motor inrush on a weak supply browns
   out the regulator and reboots the board mid-session, which looks exactly like
   a firmware crash and is not one. Use 5 V 2 A and a 1000 µF bulk capacitor.
3. **Wiring everything at once.** `firmware/tests/` contains six staged
   bring-up sketches, one peripheral each, with expected output and the usual
   failure cause for each. Skipping them means one symptom and eighteen
   possible causes.

### 8.4 The clock problem, stated honestly

`millis()` resets on every power-up, so **without a real-time clock the board
cannot know how long it was switched off** — and `time_since_last_practice` is
one of the 14 features the model consumes.

Rather than log a silently wrong number, the firmware advances a persisted epoch
by a **declared assumption** and stamps every affected row `rtc_present = 0`, so
those rows remain auditable and can be excluded or discounted. A DS3231 costs
about $2 and removes the problem entirely.

### 8.5 On-device verification

`train.py` exports golden vectors — feature vectors with their expected
predictions — into `model_data.h`. The firmware replays them at boot. If any
mismatch, the ESP32 is not computing what the desktop computed, and everything
logged afterwards is measuring an unknown function. On failure the firmware
falls back to the rule engine rather than producing garbage.

---

## 9. Testing

| Suite | Checks | Status |
|---|---|---|
| `validate_braille_map.py` | 50 letters, no duplicate patterns, per-letter verification | ✅ |
| `test_parity.py` | 3,000 vectors × 16 fields, JS = C = Python | ✅ |
| `test_web_e2e.mjs` | 28 checks in a real browser session | ✅ |
| `test_firmware_headers.py` | 21 checks — headers compile, agree with source data | ✅ |
| `test_supabase.py` | backend reachable, table, RLS, dedupe | ⚠ see §10 |

Run everything: `python3 tools/run_all_tests.py`

### 9.1 The test that earns its keep

`test_web_e2e.mjs` drives a real browser through a real session and asserts the
resulting rows are **usable**: all 14 features finite, streak exclusivity holds,
correctness derivable, timings plausible, provenance correct per character. It
catches a session that looks fine but logs NaN features — a failure otherwise
discovered weeks later with the data already collected and the volunteers gone.

### 9.2 Offline resilience, measured

The storage layer promises that collection never stops because the backend is
down. This is now measured, not asserted: during a test run with the backend
unreachable, **12 of 12 rows were preserved and queued across 24 network
failures**, and the session ran to completion.

---

## 10. Known limitations and open items

| # | Item | Severity | Resolution |
|---|---|---|---|
| 1 | 39 consonants unverified; ~3–4 likely wrong | **High** | Supply reference images, re-run importer |
| 2 | Zero real learner data | **High** | Begin collection; needs calendar weeks, not hours |
| 3 | ঋ / র pattern collision | Medium | Supply `ra.webp` |
| 4 | Publishable-key insert path untested | Medium | Run one browser session, confirm rows arrive |
| 5 | Hardware never assembled | Medium | Work through `firmware/tests/` t1–t6 |
| 6 | No RTC → `time_since_last_practice` assumed across power cycles | Medium | Add DS3231, set `USE_RTC 1` |
| 7 | Audio is synthetic (espeak-ng), robotic | Low | Re-record; drop-in replacement by track number |
| 8 | Word Practice class has no word content | Low | Cut to a 5-class head if time is short |

### 10.1 Testing limitation affecting this report

The environment this project was built in blocks `supabase.co` and
`wikipedia.org` by egress policy. Consequently **no Supabase call was ever
executed during development**. `tools/test_supabase.py` exists specifically to
be run on an unrestricted machine and verifies the table, the RLS insert path,
and the deduplication index. A run using the *secret* key confirmed the schema
and dedupe index but **cannot** validate the publishable key the browser uses,
because the secret key bypasses row-level security.

---

## 11. Project statistics

| Area | Files | Lines |
|---|---|---|
| Web MVP | 8 | 1,633 |
| Tools (generators, dataset, training, tests) | 19 | 3,859 |
| ESP32 firmware | 7 | 1,753 |
| Bring-up sketches | 6 | 337 |
| Schema + spec + data | 3 | 1,045 |
| **Total** | **43** | **8,627** |

Generated assets: 50 SVG + 50 PNG Braille cells, 60 audio clips (letters +
system prompts), duplicated to `sd_card/mp3/` for the DFPlayer.

---

## 12. Remaining work, in dependency order

| # | Task | Blocks | Effort |
|---|---|---|---|
| 1 | Confirm browser can write to Supabase | data collection | 5 min |
| 2 | Begin vowel-only data collection | everything downstream | **weeks of calendar time** |
| 3 | Supply 39 consonant images | full-alphabet teaching | hours |
| 4 | Order and assemble hardware | firmware validation | 1–2 weeks |
| 5 | Work through bring-up sketches t1–t6 | main firmware | days |
| 6 | Retrain on real data, redeploy | final result | 1 day |

**Task 2 is the critical path.** Sessions must be spread across several days per
participant, or `session_number` and `time_since_last_practice` carry no signal
and two of the fourteen features are dead. This is calendar time that cannot be
compressed by working harder. Everything else can proceed in parallel.

---

## 13. What can honestly be claimed today

**Demonstrated:**
- A complete software pipeline from interaction logging to a deployable 8-bit model
- A 1,161-parameter multi-task network reproducing an adaptive teaching rule engine at 96.7%
- Quantization to 5,928 bytes with **zero** change in predictions
- 2.7% SRAM footprint, leaving ample headroom on ESP32
- A generator-based architecture that makes browser/firmware divergence structurally impossible, verified across 3,000 vectors
- Braille pattern extraction from reference images, which corrected a real error

**Not demonstrated:**
- Any behaviour with real learners
- Any execution on physical hardware
- That the model generalises beyond the rule engine it was trained to imitate
- That 39 of the 50 character mappings are correct

The gap between these two lists is data collection and hardware assembly — not
further software work.
