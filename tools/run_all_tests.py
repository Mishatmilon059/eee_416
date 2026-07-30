#!/usr/bin/env python3
"""Run every check in the project.

    python3 tools/run_all_tests.py
    python3 tools/run_all_tests.py --skip-web    # no browser available

Regenerates all generated files first, so a stale generated file can never
make a broken spec look green.
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(title, cmd, cwd=ROOT, optional=False):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    dt = time.time() - t0
    tail = [l for l in r.stdout.strip().splitlines()
            if l.strip() and not l.startswith(("I0000", "W0000", "E0000", "WARNING"))]
    for line in tail[-14:]:
        print(line)
    if r.returncode != 0:
        print((r.stderr or "").strip()[-800:])
    status = "PASS" if r.returncode == 0 else ("SKIP" if optional else "FAIL")
    print(f"\n-> {status} ({dt:.1f}s)")
    return r.returncode == 0 or optional


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-web", action="store_true",
                    help="skip the browser end-to-end test")
    args = ap.parse_args()

    py = sys.executable
    results = {}

    # regenerate first -- a stale generated file would mask a broken spec
    print("regenerating all generated files ...")
    for script in ("gen_engine.py", "gen_braille_header.py"):
        r = subprocess.run([py, str(ROOT / "tools" / script)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL: {script}\n{r.stderr}")
            return 1
    print("  ok")

    results["braille map"] = run(
        "Braille map: 50 letters, no duplicate patterns",
        [py, str(ROOT / "tools" / "validate_braille_map.py")])

    results["rule engine parity"] = run(
        "Rule engine parity: JS == C == Python",
        [py, str(ROOT / "tools" / "test_parity.py"), "3000"])

    if (ROOT / "firmware" / "braille_tutor" / "model_data.h").exists():
        results["firmware headers"] = run(
            "Firmware headers: compile + agree with source data",
            [py, str(ROOT / "tools" / "test_firmware_headers.py")])
    else:
        print("\nskipping firmware headers: model_data.h not built yet "
              "(run tools/train.py then tools/tflite_to_header.py)")

    if not args.skip_web:
        if shutil.which("node") and (ROOT / "node_modules" / "playwright").exists():
            results["web e2e"] = run(
                "Web app end-to-end: a real browser session logs usable rows",
                ["node", str(ROOT / "tools" / "test_web_e2e.mjs")])
        else:
            print("\nskipping web e2e: needs node + `npm install playwright`")

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in results.items() if not ok]
    if failed:
        print(f"\n{len(failed)} suite(s) failed: {', '.join(failed)}")
        return 1
    print(f"\nall {len(results)} suite(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
