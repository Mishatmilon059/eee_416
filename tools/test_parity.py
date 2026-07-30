#!/usr/bin/env python3
"""Prove all THREE generated rule engines behave identically.

  web/rule_engine.js          labels rows during collection
  firmware/rule_engine.h      runs on the ESP32
  tools/rule_engine_gen.py    labels synthetic rows and evaluates the model

Pushes N feature vectors through all three and compares the teaching action,
the confidence state, and all 14 normalized values.

This failing means one of three things, all bad: a model trained on
web-collected data will misbehave on the ESP32, or 60% of the dataset carries
labels that disagree with the 40% collected from real users. It must stay
green. Run it after every tools/gen_engine.py.

    python3 tools/test_parity.py [N]

Needs: node, and a C compiler (cc/gcc/clang).
"""
import json
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "spec" / "engine_spec.json").read_text(encoding="utf-8"))
FEATURES = SPEC["features"]
TOL = 1e-6

C_HARNESS = r"""
#include <stdio.h>
#include "rule_engine.h"

int main(void) {
  double v[FEATURE_COUNT];
  while (1) {
    for (int i = 0; i < FEATURE_COUNT; i++) {
      if (scanf("%lf", &v[i]) != 1) return 0;
    }
    Features f;
    double *p = (double *)&f;
    for (int i = 0; i < FEATURE_COUNT; i++) p[i] = v[i];

    float norm[FEATURE_COUNT];
    normalize_features(&f, norm);
    printf("%d %d", (int)evaluate_teaching_action(&f), (int)evaluate_confidence(&f));
    for (int i = 0; i < FEATURE_COUNT; i++) printf(" %.9g", (double)norm[i]);
    printf("\n");
  }
}
"""

JS_HARNESS = """
import { readFileSync } from 'node:fs';
import {
  evaluateTeachingAction, evaluateConfidence, normalizeFeatures, FEATURE_RANGES,
} from '%s';

const names = FEATURE_RANGES.map((r) => r.name);
const lines = readFileSync(0, 'utf-8').trim().split('\\n');
const out = [];
for (const line of lines) {
  if (!line.trim()) continue;
  const nums = line.trim().split(/\\s+/).map(Number);
  const f = {};
  names.forEach((n, i) => { f[n] = nums[i]; });
  const norm = normalizeFeatures(f);
  const row = [evaluateTeachingAction(f), evaluateConfidence(f)];
  for (let i = 0; i < norm.length; i++) row.push(Number(norm[i]).toPrecision(9));
  out.push(row.join(' '));
}
process.stdout.write(out.join('\\n') + '\\n');
"""


def sample_vector(rng):
    """Mix of edge cases and random values -- thresholds are where drift hides."""
    row = []
    for f in FEATURES:
        lo, hi = float(f["min"]), float(f["max"])
        mode = rng.random()
        if mode < 0.25:
            # sit exactly on / adjacent to a threshold value
            cands = [lo, hi, 0.0, 1.0, 2.0, 3.0, 5.0, 0.5, 0.7, 0.85, 0.8,
                     2500.0, 6000.0, 400.0, 86400.0]
            v = rng.choice(cands)
        elif mode < 0.35:
            v = rng.uniform(lo - abs(lo) - 5, hi + abs(hi) + 5)  # out of range
        elif f["unit"] in ("count", "level", "id", "enum"):
            v = float(rng.randint(int(lo) - 1, int(hi) + 1))
        else:
            v = rng.uniform(lo, hi)
        row.append(v)
    return row


def find_cc():
    for c in ("cc", "gcc", "clang"):
        if shutil.which(c):
            return c
    return None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    rng = random.Random(20260730)

    cc = find_cc()
    if not cc:
        print("FAIL: no C compiler found (need cc, gcc, or clang)")
        return 1
    if not shutil.which("node"):
        print("FAIL: node not found")
        return 1

    rows = [sample_vector(rng) for _ in range(n)]
    # %r round-trips a double exactly, so both sides parse the same value
    stdin_txt = "\n".join(" ".join(repr(x) for x in r) for r in rows) + "\n"

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        shutil.copy(ROOT / "firmware" / "braille_tutor" / "rule_engine.h", td / "rule_engine.h")
        (td / "harness.c").write_text(C_HARNESS)
        r = subprocess.run([cc, "-O0", "-I", str(td), str(td / "harness.c"), "-o", str(td / "harness")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("FAIL: C harness did not compile\n" + r.stderr)
            return 1
        c_out = subprocess.run([str(td / "harness")], input=stdin_txt,
                               capture_output=True, text=True, check=True).stdout

        js_path = (ROOT / "web" / "rule_engine.js").resolve().as_uri()
        (td / "harness.mjs").write_text(JS_HARNESS % js_path)
        r = subprocess.run(["node", str(td / "harness.mjs")], input=stdin_txt,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("FAIL: JS harness errored\n" + r.stderr)
            return 1
        js_out = r.stdout

    # --- Python engine, in-process -----------------------------------------
    sys.path.insert(0, str(ROOT / "tools"))
    import rule_engine_gen as py_engine  # noqa: E402  (generated, must exist by now)

    py_lines = []
    for row in rows:
        f = {name: row[i] for i, name, _, _ in py_engine.FEATURE_RANGES}
        norm = py_engine.normalize_features(f)
        parts = [str(int(py_engine.evaluate_teaching_action(f))),
                 str(int(py_engine.evaluate_confidence(f)))]
        parts += [f"{v:.9g}" for v in norm]
        py_lines.append(" ".join(parts))

    c_lines = [l for l in c_out.strip().split("\n") if l]
    js_lines = [l for l in js_out.strip().split("\n") if l]
    if not (len(c_lines) == len(js_lines) == len(py_lines) == n):
        print(f"FAIL: row count mismatch C={len(c_lines)} JS={len(js_lines)} "
              f"PY={len(py_lines)} expected={n}")
        return 1

    ta_names = SPEC["outputs"]["teaching_action"]["classes"]
    cs_names = SPEC["outputs"]["confidence_state"]["classes"]
    mismatches = []
    ta_hist, cs_hist = {}, {}

    for i, (cl, jl, pl) in enumerate(zip(c_lines, js_lines, py_lines)):
        cf, jf, pf = cl.split(), jl.split(), pl.split()
        ta_hist[int(cf[0])] = ta_hist.get(int(cf[0]), 0) + 1
        cs_hist[int(cf[1])] = cs_hist.get(int(cf[1]), 0) + 1

        for other, label in ((jf, "JS"), (pf, "PY")):
            if cf[0] != other[0]:
                mismatches.append(f"row {i}: teaching_action C={ta_names[int(cf[0])]} "
                                  f"{label}={ta_names[int(other[0])]}  in={rows[i]}")
            if cf[1] != other[1]:
                mismatches.append(f"row {i}: confidence C={cs_names[int(cf[1])]} "
                                  f"{label}={cs_names[int(other[1])]}  in={rows[i]}")
        for k in range(len(FEATURES)):
            cv = float(cf[2 + k])
            for other, label in ((jf, "JS"), (pf, "PY")):
                ov = float(other[2 + k])
                if abs(cv - ov) > TOL:
                    mismatches.append(f"row {i}: norm[{FEATURES[k]['name']}] "
                                      f"C={cv!r} {label}={ov!r} delta={abs(cv - ov):.3g}")

    print(f"vectors compared : {n}")
    print(f"fields per vector: {2 + len(FEATURES)}")
    print("\nteaching action coverage:")
    for idx, name in enumerate(ta_names):
        print(f"  {name:<22} {ta_hist.get(idx, 0)}")
    print("confidence coverage:")
    for idx, name in enumerate(cs_names):
        print(f"  {name:<22} {cs_hist.get(idx, 0)}")

    uncovered = [n_ for i_, n_ in enumerate(ta_names) if ta_hist.get(i_, 0) == 0]
    uncovered += [n_ for i_, n_ in enumerate(cs_names) if cs_hist.get(i_, 0) == 0]
    if uncovered:
        print(f"\nWARN  rules never exercised: {', '.join(uncovered)}")

    if mismatches:
        print(f"\nFAIL  {len(mismatches)} mismatch(es):")
        for m in mismatches[:20]:
            print(f"  {m}")
        if len(mismatches) > 20:
            print(f"  ... {len(mismatches) - 20} more")
        return 1

    print("\nOK - JS, C and Python rule engines agree on every vector")
    return 0


if __name__ == "__main__":
    sys.exit(main())
