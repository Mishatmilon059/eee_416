#!/usr/bin/env python3
"""Validate data/braille_map.json.

Run this after ANY edit to the Braille map -- especially after swapping in the
verified Bangladesh chart. A duplicate dot pattern means two different letters
are indistinguishable to a learner (and to the model), which silently corrupts
every row of collected data.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "braille_map.json"

EXPECTED_TOTAL = 50
EXPECTED_VOWELS = 11
EXPECTED_CONSONANTS = 39


def dots_to_mask(dots):
    """[1,3] -> 0b000101. Bit i (0-indexed) set means dot i+1 is raised."""
    mask = 0
    for d in dots:
        mask |= 1 << (d - 1)
    return mask


def main():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    letters = data["letters"]
    errors = []
    warnings = []

    # --- count checks ---
    if len(letters) != EXPECTED_TOTAL:
        errors.append(f"expected {EXPECTED_TOTAL} letters, found {len(letters)}")

    cats = Counter(l["category"] for l in letters)
    if cats["vowel"] != EXPECTED_VOWELS:
        errors.append(f"expected {EXPECTED_VOWELS} vowels, found {cats['vowel']}")
    if cats["consonant"] != EXPECTED_CONSONANTS:
        errors.append(f"expected {EXPECTED_CONSONANTS} consonants, found {cats['consonant']}")

    # --- id checks ---
    ids = [l["id"] for l in letters]
    if ids != list(range(len(letters))):
        errors.append("ids must be contiguous 0..N-1 in file order (firmware indexes by id)")

    # --- dot validity ---
    for l in letters:
        if not l["dots"]:
            errors.append(f"id {l['id']} ({l['char']}): empty dot pattern")
        for d in l["dots"]:
            if d not in (1, 2, 3, 4, 5, 6):
                errors.append(f"id {l['id']} ({l['char']}): invalid dot {d}")
        if len(set(l["dots"])) != len(l["dots"]):
            errors.append(f"id {l['id']} ({l['char']}): repeated dot in {l['dots']}")
        if l["dots"] != sorted(l["dots"]):
            warnings.append(f"id {l['id']} ({l['char']}): dots not sorted {l['dots']}")

    # --- duplicate patterns: the important one ---
    by_mask = {}
    for l in letters:
        m = dots_to_mask(l["dots"])
        by_mask.setdefault(m, []).append(l)
    for mask, group in sorted(by_mask.items()):
        if len(group) > 1:
            names = ", ".join(f"{g['char']}({g['name']})" for g in group)
            errors.append(f"DUPLICATE pattern {sorted(group[0]['dots'])}: {names}")

    # --- audio filename checks (DFPlayer needs 4-digit zero-padded) ---
    audio = [l["audio"] for l in letters]
    if len(set(audio)) != len(audio):
        errors.append("duplicate audio filenames")
    for l in letters:
        expected = f"{l['id'] + 1:04d}.mp3"
        if l["audio"] != expected:
            errors.append(f"id {l['id']}: audio should be {expected}, got {l['audio']}")

    # --- report ---
    print(f"letters      : {len(letters)}")
    print(f"vowels       : {cats['vowel']}")
    print(f"consonants   : {cats['consonant']}")
    print(f"unique dots  : {len(by_mask)}")
    print(f"standard     : {data['standard']}")
    print(f"verified     : {data['verified']}")

    if not data["verified"]:
        print("\n  !! braille_map.json is NOT verified against the Bangladesh")
        print("     National Braille code. Do not show to real learners yet.")

    for w in warnings:
        print(f"\nWARN  {w}")
    if errors:
        print()
        for e in errors:
            print(f"FAIL  {e}")
        print(f"\n{len(errors)} error(s)")
        return 1

    print("\nOK - all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
