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

python3 tools/import_braille_images.py --write   # read braille_img/ into the map
python3 tools/verify_braille_images.py           # QA sheet -- then look at it

python3 tools/run_all_tests.py         # everything must be green
```

Run the app — **serve the repository root**, not `web/`, because the app reads
`data/braille_map.json`:

```bash
python3 -m http.server 8000
# open http://localhost:8000/web/
```

---

## Braille verification status — 11 of 50

Verification is tracked **per letter**, because reference images arrive in
batches. All 11 vowels were read from `braille_img/`; the 39 consonants still
carry Bharati **placeholder** patterns.

The 11 vowels confirmed 10 of my placeholder guesses and **corrected one**:
ঋ was `[2,3,5]`, actually `[1,2,3,5]` (`⠗`).

### Adding the remaining 39

Drop images into `braille_img/` — one Braille cell per image, any of
webp/png/jpg — add their filenames to `tools/braille_aliases.json`, then:

```bash
python3 tools/import_braille_images.py           # dry run: shows what would change
python3 tools/import_braille_images.py --write
python3 tools/verify_braille_images.py           # then LOOK at the sheet
python3 tools/gen_braille_header.py
python3 tools/gen_braille_images.py
```

The importer **refuses to guess** a filename it does not recognise. That is
deliberate: your `uu.webp` is উ, which this project calls `u`, while your
`uuuu.webp` is ঊ, which it calls `uu`. The literal string `uu` means different
letters in the two schemes, so any fallback name matching would put one
letter's pattern on another — producing a map that passes every structural
check while being wrong. The alias table is the only lookup path.

### What "verified" changes

- **Per-row provenance.** `braille_map_verified` records whether *that row's
  character* was verified, not whether the whole map was. Rows for the 11
  vowels are usable now; you can filter at training time instead of throwing
  away whole sessions.
- **The app** shows "verified for N of 50" and tags an individual prompt when
  that character is still a placeholder.
- **The firmware** exposes `BRAILLE_VERIFIED[id]` and stamps each SD row the
  same way.

### One known collision

Corrected ঋ = `[1,2,3,5]`, which equals the **unverified placeholder** for
র (ra). Two letters cannot share a pattern. Since র's value is itself a guess,
this most likely resolves when you supply `ra.webp`. The tooling reports it as
a warning rather than an error — a clash between two *verified* letters would
be a hard failure and blocks the import.

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

**Supabase is already wired up** (`web/config.js` holds the project URL and
publishable key). Two things left to do once:

```bash
# 1. paste supabase/schema.sql into the Supabase SQL editor and run it
# 2. prove it works -- this was NOT runnable where the project was built,
#    because supabase.co is blocked by egress policy there
cp .env.example .env
python3 tools/test_supabase.py --write
```

`test_supabase.py` checks the things that actually break collection: that the
table exists, that the publishable key can INSERT (a project can be reachable
and readable while still rejecting writes), and that the dedupe index turns a
replayed row into a no-op — which is what the offline queue depends on when a
laptop reconnects mid-session.

Without any of this the app still runs fully offline and exports CSV per device.

**Key hygiene:** the publishable key in `web/config.js` is meant to be public —
RLS decides what it can do. The **secret** key bypasses RLS entirely and belongs
only in `.env` (gitignored). If it is ever pasted into a chat, a screenshot, or
a commit, rotate it in Supabase → Settings → API Keys. Rotation is instant.

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
| `verify_braille_images.py` | Every stored pattern re-reads identically from its source image |

`test_web_e2e.mjs` is the one that earns its keep: it catches a session that
looks fine but logs null or NaN features — otherwise discovered weeks later
with the data already collected and the volunteers gone.

---

## Layout

```
spec/engine_spec.json        ⭐ 14 features, thresholds, normalization
data/braille_map.json        ⭐ 50 letters → dot patterns + per-letter verified
braille_img/                 your reference cell images (11 vowels so far)
tools/braille_aliases.json   filename → letter, the ONLY lookup path
assets/braille/              generated SVG + PNG + contact sheet
web/                         MVP app (rule_engine.js is GENERATED)
tools/                       generators, dataset, training, tests
firmware/braille_tutor/      main sketch (3 headers are GENERATED)
firmware/tests/              staged bring-up sketches t1..t6
supabase/schema.sql          attempts table + monitoring views
sd_card/mp3/                 audio, ready to copy to the card
```
