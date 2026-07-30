# Bangla Braille Tutor — AI-assisted, offline on ESP32

Teaches Bangla Braille, logs learner interaction data, trains a small
multi-task model on that data, and runs it **fully offline** on an ESP32 with
push buttons, vibration motors, and audio.

Three pieces:

| Piece | What it is | Where |
|---|---|---|
| **MVP web app** | Data-collection instrument. Single page, no build step. | `web/` |
| **Training pipeline** | CSV → multi-task net → int8 TFLite → C header | `tools/` |
| **Firmware** | ESP32 sketch, no WiFi, inference on-device | `firmware/` |

---

## The one thing to understand before changing anything

Two data files are the source of truth. Almost everything else is **generated**:

```
spec/engine_spec.json  ──gen_engine.py──►  web/rule_engine.js
                                           firmware/braille_tutor/rule_engine.h
                                           tools/rule_engine_gen.py

data/braille_map.json  ──gen_braille_header.py──►  firmware/braille_tutor/braille_map.h
                       ──gen_braille_images.py──►  assets/braille/*.svg, *.png
                       ──gen_audio.py───────────►  web/audio/, sd_card/mp3/

models/model.tflite    ──tflite_to_header.py──►  firmware/braille_tutor/model_data.h
```

This exists to kill one bug class: the web app and the ESP32 computing features
or rules slightly differently, so a model trained on web-collected data
misbehaves on hardware. `tools/test_parity.py` proves all three rule engines
agree on every vector. **Never hand-edit a generated file.** Edit the spec,
regenerate, re-run parity.

---

## Quick start

```bash
pip install tensorflow numpy Pillow
sudo apt-get install -y espeak-ng ffmpeg

python3 tools/gen_engine.py            # 3 rule engines
python3 tools/gen_braille_header.py    # firmware dot table
python3 tools/gen_braille_images.py    # 50 SVG + 50 PNG + contact sheet
python3 tools/gen_audio.py             # 50 letters + 10 prompts

python3 tools/run_all_tests.py         # everything must be green
```

Run the app — **serve the repository root**, not `web/`, because the app reads
`data/braille_map.json`:

```bash
python3 -m http.server 8000
# open http://localhost:8000/web/
```

---

## ⚠ Before any real learner sees this

`data/braille_map.json` currently holds **Bharati Braille placeholder
patterns** and is marked `"verified": false`. Bangladesh Braille differs from
Indian Bharati Braille in places. The app shows a loud banner and every logged
row is stamped `braille_map_verified=false` while this is true.

To fix it — a one-file change, no code touched:

1. Replace the `dots` arrays in `data/braille_map.json` from a verified
   Bangladesh National Braille chart.
2. Set `"verified": true` and `"standard": "BANGLADESH_NATIONAL"`.
3. Re-run:
   ```bash
   python3 tools/validate_braille_map.py     # catches duplicate patterns
   python3 tools/gen_braille_header.py
   python3 tools/gen_braille_images.py
   ```
4. Print `assets/braille/_contact_sheet.png` and check all 50 against the chart.

Data collected before this is still *structurally* valid — the features and
timings are real — but the character↔pattern association is unverified, so
treat it as a pilot, not as final results.

---

## Workflow, in order

### 1. Collect real data — start this the day the app works

Calendar time is the constraint, not coding time. Sessions must be spread
across **several days per participant**, otherwise `session_number` and
`time_since_last_practice` have no variance and two of the 14 features are dead.

- Sighted volunteers doing eyes-closed recall produce realistic timing. You do
  not need visually-impaired participants at this stage.
- Target ~400 real attempts (the 40% share).
- Watch the **class balance** panel in the app while collecting. Any class stuck
  near zero is a problem you want to find on day 2, not at training time.
- Use **targeted** mode to make rare classes fire. It biases character
  selection toward genuinely stale and genuinely weak characters — it does not
  fabricate feature values.

Set up Supabase (optional but recommended for two people on two laptops):
run `supabase/schema.sql` in the SQL editor, then put the project URL and anon
key in `web/config.js`. Without it the app still works fully offline and
exports CSV per device.

### 2. Generate synthetic data — *after* step 1, not before

```bash
python3 tools/export_dataset.py --out dataset/real.csv
python3 tools/gen_synthetic.py --real dataset/real.csv --n 600
```

Order matters. `gen_synthetic.py` fits timing distributions to your real rows,
then simulates learners through the same state machine the web app uses. Run
before any real data exists and it falls back to priors — which are guesses,
and it says so loudly.

It simulates rather than sampling features independently, because independent
sampling produces impossible vectors (`current_streak=7` beside
`prev_mastery=0.02`) that waste model capacity on a region that cannot occur.

### 3. Train

```bash
python3 tools/train.py
python3 tools/tflite_to_header.py
```

Reports **real-only test accuracy separately** from combined, with a
majority-class baseline beside every number, and dumps held-out disagreements
to `models/disagreements.csv`.

### 4. Hardware

Work through `firmware/tests/` **in order** — one peripheral per sketch. Do not
flash the main sketch first. See `firmware/tests/README.md`.

```
sd_card/mp3/  →  copy to the microSD card root (DFPlayer needs a folder named "mp3")
```

---

## What this model actually is — read before writing it up

The labels come from the rule engine. A 1,161-parameter network trained on them
learns to **compress your if/else logic**, reaching ~96–97% agreement. It does
not discover teaching policy.

That is a legitimate TinyML result — train → quantize → deploy → real-time
offline inference at ~5.8 KB — and it should be written up that way. Describing
it as autonomous adaptive learning would be false, and any examiner who asks
"where did the labels come from?" will find that out in one question.

The genuinely interesting material is `models/disagreements.csv`: the held-out
**real** rows where the model departs from the rule engine. Read them.

---

## Hardware

ESP32-WROOM-32 · DFPlayer Mini + 3 W speaker · **ULN2803A** · 6 coin motors ·
6 tactile buttons · microSD module · 5 V 2 A supply · 1000 µF cap · 6× 1 kΩ ·
2× 10 kΩ · *(recommended)* DS3231 RTC

| Function | GPIO |
|---|---|
| Buttons 1–6 | 32, 33, 25, 26, 27, 14 |
| Motors 1–6 → ULN2803A | 13, 4, 21, 22, 2, 15 |
| DFPlayer (UART2) | 16 RX, 17 TX |
| microSD (VSPI) | 18 CLK, 19 MISO, 23 MOSI, 5 CS |

Three things that will bite you, in order of likelihood:

1. **Use the ULN2803A, not discrete transistors.** Coin motors are inductive;
   it has flyback diodes built in (tie COM to +5 V). Driving them off a bare
   GPIO destroys pins.
2. **5 V 2 A supply + 1000 µF across the motor rail.** Six motors pull ~480 mA;
   with the ESP32 and DFPlayer you are near 800 mA peak. Motor inrush on a weak
   supply browns out the regulator and reboots the board mid-session — which
   looks exactly like a firmware crash and is not one.
3. **GPIO 2 and 15 are strapping pins** — add 10 kΩ pulldowns. GPIO 12 is
   deliberately unused; it must be LOW at boot.

**Fit:** model 5,928 B + 8 KB arena ≈ **13.8 KB of 520 KB SRAM**. Size was never
the risk on this project.

### The RTC, and why it matters

`millis()` resets on every power-up, so without an RTC the board cannot know how
long it was switched off — and `time_since_last_practice` is one of the 14
features the model consumes. Firmware handles this honestly rather than silently:
without an RTC it advances a persisted epoch by a **declared assumption** and
stamps every row `rtc_present=0`, so those rows stay auditable. A DS3231 costs
about $2 and removes the problem. Set `USE_RTC 1` in `pins.h` after wiring it.

---

## Tests

```bash
python3 tools/run_all_tests.py
```

| Test | Proves |
|---|---|
| `validate_braille_map.py` | 50 letters, no duplicate dot patterns |
| `test_parity.py` | JS, C and Python rule engines agree on every vector |
| `test_web_e2e.mjs` | A real browser session logs usable rows |
| `test_firmware_headers.py` | Generated headers compile and agree with the source data |

`test_web_e2e.mjs` is the one that earns its keep: it catches a session that
looks fine but logs null or NaN features — otherwise discovered weeks later
with the data already collected and the volunteers gone.

---

## Layout

```
spec/engine_spec.json        ⭐ 14 features, thresholds, normalization
data/braille_map.json        ⭐ 50 letters → dot patterns
assets/braille/              generated SVG + PNG + contact sheet
web/                         MVP app (rule_engine.js is GENERATED)
tools/                       generators, dataset, training, tests
firmware/braille_tutor/      main sketch (3 headers are GENERATED)
firmware/tests/              staged bring-up sketches t1..t6
supabase/schema.sql          attempts table + monitoring views
sd_card/mp3/                 audio, ready to copy to the card
```
