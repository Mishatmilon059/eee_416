#!/usr/bin/env python3
"""Compile-test the generated firmware headers on the host.

    python3 tools/test_firmware_headers.py

The full sketch needs the Arduino toolchain, but the three GENERATED headers
are plain C++ and can be checked here. This catches the failure where a
generator emits something that only breaks at flash time -- by which point you
are debugging on hardware, which is far slower than debugging here.

Checks: the headers compile together, the Braille table is complete with no
duplicate patterns, the model's feature count matches the spec, the golden
vectors are well formed, and the C dot masks agree with data/braille_map.json.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW = ROOT / "firmware" / "braille_tutor"

PROBE = r"""
#include <cstdio>
#include <cstdint>
#include <cmath>
#include "rule_engine.h"
#include "braille_map.h"
#include "model_data.h"

int main() {
  printf("FEATURE_COUNT %d\n", FEATURE_COUNT);
  printf("SPEC_VERSION %d\n", SPEC_VERSION);
  printf("LETTERS %d\n", BRAILLE_LETTER_COUNT);
  printf("VOWELS %d\n", BRAILLE_VOWEL_COUNT);
  printf("MAP_VERIFIED %d\n", BRAILLE_MAP_VERIFIED);
  printf("MODEL_BYTES %d\n", MODEL_DATA_LEN);
  printf("ARENA %d\n", (int)MODEL_ARENA_SIZE);
  printf("GOLDEN %d\n", GOLDEN_VECTOR_COUNT);
  printf("TEACH_CLASSES %d\n", MODEL_TEACH_CLASSES);
  printf("CONF_CLASSES %d\n", MODEL_CONF_CLASSES);
  printf("INPUT_SCALE %.10f\n", (double)MODEL_INPUT_SCALE);
  printf("INPUT_ZP %d\n", MODEL_INPUT_ZERO_POINT);

  for (int i = 0; i < BRAILLE_LETTER_COUNT; i++)
    printf("PATTERN %d %d %d\n", i, (int)BRAILLE_PATTERN[i], (int)BRAILLE_VERIFIED[i]);
  printf("VERIFIED_COUNT %d\n", BRAILLE_VERIFIED_COUNT);

  // the sketch indexes audio by this
  printf("TRACK_FIRST %d\n", (int)braille_track(0));
  printf("TRACK_LAST %d\n", (int)braille_track(BRAILLE_LETTER_COUNT - 1));

  // exercise the rule engine + normalizer exactly as the firmware does
  Features f{};
  f.char_id = 3; f.response_time = 1200; f.press_duration = 150;
  f.retry_count = 0; f.prev_accuracy = 0.9; f.prev_mastery = 0.9;
  f.hint_count = 0; f.session_number = 4; f.difficulty_level = 2;
  f.time_since_last_practice = 300; f.prev_confidence = 0;
  f.current_streak = 6; f.wrong_streak = 0; f.prev_mistakes = 1;
  printf("RULE_TA %d\n", (int)evaluate_teaching_action(&f));
  printf("RULE_CS %d\n", (int)evaluate_confidence(&f));
  float norm[FEATURE_COUNT];
  normalize_features(&f, norm);
  printf("NORM0 %.8f\n", norm[0]);
  printf("MASTERY_UP %.8f\n", update_mastery(0.5, 1));

  // golden vectors must be finite and in [0,1] -- they are already normalized
  int bad = 0;
  for (int i = 0; i < GOLDEN_VECTOR_COUNT; i++) {
    for (int j = 0; j < FEATURE_COUNT; j++) {
      float v = GOLDEN_VECTORS[i].features_norm[j];
      if (!(v >= 0.0f && v <= 1.0f) || !std::isfinite(v)) bad++;
    }
    if (GOLDEN_VECTORS[i].expect_teaching < 0 ||
        GOLDEN_VECTORS[i].expect_teaching >= MODEL_TEACH_CLASSES) bad++;
    if (GOLDEN_VECTORS[i].expect_confidence < 0 ||
        GOLDEN_VECTORS[i].expect_confidence >= MODEL_CONF_CLASSES) bad++;
  }
  printf("GOLDEN_BAD %d\n", bad);
  return 0;
}
"""

failures = 0


def check(name, cond, detail=""):
    global failures
    if cond:
        print(f"  PASS  {name}")
    else:
        failures += 1
        print(f"  FAIL  {name}" + (f"  -- {detail}" if detail else ""))


def main():
    cc = next((c for c in ("c++", "g++", "clang++") if shutil.which(c)), None)
    if not cc:
        sys.exit("no C++ compiler found (need c++, g++, or clang++)")

    missing = [h for h in ("rule_engine.h", "braille_map.h", "model_data.h")
               if not (FW / h).exists()]
    if missing:
        sys.exit(f"missing generated header(s): {', '.join(missing)}\n"
                 "run tools/gen_engine.py, tools/gen_braille_header.py, "
                 "tools/train.py && tools/tflite_to_header.py")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for h in ("rule_engine.h", "braille_map.h", "model_data.h"):
            shutil.copy(FW / h, td / h)
        (td / "probe.cpp").write_text(PROBE)
        r = subprocess.run(
            [cc, "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-parameter",
             "-I", str(td), str(td / "probe.cpp"), "-o", str(td / "probe")],
            capture_output=True, text=True)
        print("\n-- compile --")
        check("headers compile as C++17 with -Wall -Wextra", r.returncode == 0,
              r.stderr.strip()[:600])
        if r.returncode != 0:
            return 1
        if r.stderr.strip():
            print("  note: compiler warnings:\n" +
                  "\n".join("    " + l for l in r.stderr.strip().splitlines()[:10]))

        out = subprocess.run([str(td / "probe")], capture_output=True,
                             text=True, check=True).stdout

    vals, patterns, verified = {}, {}, {}
    for line in out.strip().splitlines():
        parts = line.split()
        if parts[0] == "PATTERN":
            patterns[int(parts[1])] = int(parts[2])
            verified[int(parts[1])] = bool(int(parts[3]))
        else:
            vals[parts[0]] = parts[1]

    spec = json.loads((ROOT / "spec" / "engine_spec.json").read_text(encoding="utf-8"))
    bmap = json.loads((ROOT / "data" / "braille_map.json").read_text(encoding="utf-8"))

    print("\n-- consistency with the source data --")
    check("FEATURE_COUNT matches the spec",
          int(vals["FEATURE_COUNT"]) == len(spec["features"]),
          f'header {vals["FEATURE_COUNT"]} vs spec {len(spec["features"])}')
    check("SPEC_VERSION matches the spec",
          int(vals["SPEC_VERSION"]) == spec["version"])
    check("letter count is 50", int(vals["LETTERS"]) == 50, vals["LETTERS"])
    check("vowel count is 11", int(vals["VOWELS"]) == 11, vals["VOWELS"])
    check("teaching head is 6 classes",
          int(vals["TEACH_CLASSES"]) == len(spec["outputs"]["teaching_action"]["classes"]))
    check("confidence head is 3 classes",
          int(vals["CONF_CLASSES"]) == len(spec["outputs"]["confidence_state"]["classes"]))

    # C masks must equal the JSON dot arrays
    mismatched = []
    for l in bmap["letters"]:
        want = 0
        for d in l["dots"]:
            want |= 1 << (d - 1)
        if patterns.get(l["id"]) != want:
            mismatched.append(f'{l["char"]}({l["name"]}) json={want:#04x} '
                              f'header={patterns.get(l["id"]):#04x}')
    check("every C dot mask matches data/braille_map.json",
          not mismatched, "; ".join(mismatched[:3]))

    # Two-tier, same rule as validate_braille_map.py. Two VERIFIED letters
    # sharing a pattern is a real defect -- a learner could not tell them apart
    # and neither could the model. A verified letter sharing with an unverified
    # PLACEHOLDER is expected while images arrive in batches, and blocking on it
    # would stall every build until all 50 images exist.
    groups = {}
    for lid, mask in patterns.items():
        groups.setdefault(mask, []).append(lid)
    hard, soft = [], []
    id_to_name = {l["id"]: f'{l["char"]}({l["name"]})' for l in bmap["letters"]}
    for mask, ids in sorted(groups.items()):
        if len(ids) < 2:
            continue
        v = [i for i in ids if verified[i]]
        if len(v) > 1:
            hard.append(f"{[id_to_name[i] for i in v]} share pattern {mask:#04x}")
        else:
            soft.append(f"{[id_to_name[i] for i in ids]} share {mask:#04x} "
                        "(one is an unverified placeholder)")
    check("no two VERIFIED letters share a dot pattern", not hard, "; ".join(hard))
    for s in soft:
        print(f"  note  {s}")

    check("BRAILLE_VERIFIED[] agrees with data/braille_map.json",
          all(verified[l["id"]] == bool(l.get("verified")) for l in bmap["letters"]))
    check("BRAILLE_VERIFIED_COUNT matches the array",
          int(vals["VERIFIED_COUNT"]) == sum(verified.values()),
          f'{vals["VERIFIED_COUNT"]} vs {sum(verified.values())}')

    print("\n-- audio track numbering --")
    check("track numbers are 1..50 (DFPlayer plays by number)",
          vals["TRACK_FIRST"] == "1" and vals["TRACK_LAST"] == "50",
          f'{vals["TRACK_FIRST"]}..{vals["TRACK_LAST"]}')

    print("\n-- model --")
    model_bytes = int(vals["MODEL_BYTES"])
    arena = int(vals["ARENA"])
    check("model is embedded and non-empty", model_bytes > 0, str(model_bytes))
    check("model + arena fit comfortably in ESP32 SRAM (520 KB)",
          model_bytes + arena < 200 * 1024,
          f"{(model_bytes + arena) / 1024:.1f} KB")
    check("input quantization scale is sane",
          0 < float(vals["INPUT_SCALE"]) < 1, vals["INPUT_SCALE"])
    check("golden vectors present", int(vals["GOLDEN"]) > 0, vals["GOLDEN"])
    check("all golden vectors well formed", int(vals["GOLDEN_BAD"]) == 0,
          f'{vals["GOLDEN_BAD"]} bad values')

    print("\n-- rule engine runs in C++ --")
    # high mastery + 6-streak + high accuracy => WORD_PRACTICE (index 5)
    check("rule engine returns WORD_PRACTICE for a mastered character",
          vals["RULE_TA"] == "5", f'got {vals["RULE_TA"]}')
    check("rule engine returns CONFIDENT for a fast clean answer",
          vals["RULE_CS"] == "0", f'got {vals["RULE_CS"]}')
    check("normalizer maps char_id 3 of 0..49 to 3/49",
          abs(float(vals["NORM0"]) - 3.0 / 49.0) < 1e-6, vals["NORM0"])
    check("mastery EMA matches the spec (0.5 correct -> 0.625)",
          abs(float(vals["MASTERY_UP"]) - 0.625) < 1e-9, vals["MASTERY_UP"])

    print(f"\nmodel {model_bytes} B + arena {arena // 1024} KB = "
          f"{(model_bytes + arena) / 1024:.1f} KB of 520 KB SRAM")

    if not int(vals["MAP_VERIFIED"]):
        print("\n  !! BRAILLE_MAP_VERIFIED is 0 -- placeholder patterns compiled in")

    print("\nOK - firmware headers consistent\n" if failures == 0
          else f"\n{failures} CHECK(S) FAILED\n")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
