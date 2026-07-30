#!/usr/bin/env python3
"""Read braille_img/ and write verified dot patterns into data/braille_map.json.

    python3 tools/import_braille_images.py            # dry run -- reports, writes nothing
    python3 tools/import_braille_images.py --write    # apply

Images are supplied incrementally (11 vowels now, 39 consonants later), so
verification is tracked PER LETTER, not with one global flag. Each imported
letter gains:

    "verified": true, "source": "braille_img/ri.webp"

and the map-level "verified" becomes true only once all 50 are done.

Filenames are resolved through tools/braille_aliases.json and nothing else.
An unrecognised filename is an error, never a guess -- see the explanation in
that file for why fuzzy matching here is actively dangerous.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from braille_image_reader import (  # noqa: E402
    BrailleImageError, confidence_margin, extract_dots, find_images,
)

MAP_PATH = ROOT / "data" / "braille_map.json"
ALIAS_PATH = ROOT / "tools" / "braille_aliases.json"
IMG_DIR = ROOT / "braille_img"

LOW_MARGIN = 40   # grey levels; below this a dot call was close to the threshold


def dots_to_mask(dots):
    m = 0
    for d in dots:
        m |= 1 << (d - 1)
    return m


def stem_key(path):
    """'11_ka.webp' -> 'ka';  'ri.webp' -> 'ri'."""
    stem = path.stem.lower()
    head, sep, tail = stem.partition("_")
    if sep and head.isdigit():
        return tail
    return stem


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="apply changes (default is a dry run)")
    ap.add_argument("--images", type=Path, default=IMG_DIR)
    args = ap.parse_args()

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    letters = data["letters"]
    by_name = {l["name"]: l for l in letters}

    aliases = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))["aliases"]

    images = find_images(args.images)
    if not images:
        sys.exit(f"no images found in {args.images}")
    print(f"found {len(images)} image(s) in {args.images.relative_to(ROOT)}/\n")

    # --- resolve filenames, refusing to guess ------------------------------
    resolved, unmapped, bad_target = [], [], []
    for p in images:
        key = stem_key(p)
        target = aliases.get(key)
        if target is None:
            unmapped.append(p.name)
        elif target not in by_name:
            bad_target.append(f"{p.name} -> '{target}' (no such letter name)")
        else:
            resolved.append((p, by_name[target]))

    if unmapped or bad_target:
        print("FAIL  cannot resolve every filename, and this importer does not guess.\n")
        for n in unmapped:
            print(f"  no alias entry : {n}")
        for n in bad_target:
            print(f"  bad alias      : {n}")
        print(f"\nAdd the missing entries to {ALIAS_PATH.relative_to(ROOT)} and re-run.")
        print("Guessing here would map a real dot pattern onto the wrong letter, "
              "producing a map that passes every structural check while being wrong.")
        return 1

    # --- extract -----------------------------------------------------------
    results, failures = [], []
    for path, letter in resolved:
        try:
            dots, detail = extract_dots(path, return_detail=True)
        except BrailleImageError as e:
            failures.append(str(e))
            continue
        if not dots:
            failures.append(f"{path.name}: no raised dots detected -- "
                            "every slot read as empty")
            continue
        results.append({
            "path": path, "letter": letter, "dots": dots,
            "margin": confidence_margin(detail), "detail": detail,
        })

    if failures:
        print("FAIL  could not read some images:\n")
        for f in failures:
            print(f"  {f}")
        print("\nNothing written.")
        return 1

    # --- report per letter -------------------------------------------------
    print(f"{'image':<14}{'char':<5}{'name':<8}{'was':<16}{'now':<16}{'':<10}")
    print("-" * 72)
    corrected, confirmed, warnings = [], [], []
    for r in sorted(results, key=lambda r: r["letter"]["id"]):
        l, dots = r["letter"], r["dots"]
        old = l["dots"]
        changed = dots != old
        status = "CORRECTED" if changed else "confirmed"
        (corrected if changed else confirmed).append(r)
        print(f"{r['path'].name:<14}{l['char']:<5}{l['name']:<8}"
              f"{str(old):<16}{str(dots):<16}{status:<10}")

        if r["margin"] < LOW_MARGIN:
            warnings.append(f"{r['path'].name}: closest dot call was only "
                            f"{r['margin']:.0f} grey levels from the threshold "
                            "-- check this one on the verification sheet")
        if len(dots) == 6:
            warnings.append(f"{r['path'].name}: read as all 6 dots raised. That is a "
                            "real pattern (ঢ) but is also what a mis-thresholded "
                            "image produces -- confirm visually")

    print(f"\nconfirmed {len(confirmed)}, corrected {len(corrected)}")
    for r in corrected:
        print(f"  {r['letter']['char']} ({r['letter']['name']}): "
              f"{r['letter']['dots']} -> {r['dots']}")

    for w in warnings:
        print(f"\nWARN  {w}")

    # --- collisions: two tiers, and the distinction matters ----------------
    # A pattern shared between two VERIFIED letters is a real conflict -- one of
    # them must be wrong and only you can say which. A pattern shared between a
    # verified letter and an unverified PLACEHOLDER is expected during an
    # incremental import: the placeholder is a guess and will most likely change
    # when its own image arrives. Blocking on the second kind would stall the
    # import for no reason; ignoring the first would hide a genuine error.
    proposed = {}
    for l in letters:
        proposed[l["id"]] = {
            "letter": l,
            "dots": l["dots"],
            "verified": bool(l.get("verified", False)),
        }
    for r in results:
        proposed[r["letter"]["id"]] = {
            "letter": r["letter"], "dots": r["dots"], "verified": True,
        }

    by_mask = {}
    for entry in proposed.values():
        by_mask.setdefault(dots_to_mask(entry["dots"]), []).append(entry)

    hard, soft = [], []
    for mask, group in sorted(by_mask.items()):
        if len(group) < 2:
            continue
        v = [g for g in group if g["verified"]]
        u = [g for g in group if not g["verified"]]
        names = lambda gs: ", ".join(f"{g['letter']['char']}({g['letter']['name']})" for g in gs)
        if len(v) > 1:
            hard.append(f"pattern {sorted(group[0]['dots'])} claimed by "
                        f"{len(v)} VERIFIED letters: {names(v)}")
        elif v and u:
            soft.append(f"pattern {sorted(group[0]['dots'])}: verified {names(v)} "
                        f"vs unverified placeholder {names(u)}")

    if soft:
        print()
        for s in soft:
            print(f"WARN  {s}")
        print("      Expected during incremental import -- the placeholder is a guess")
        print("      and should change once its own image arrives. The verified")
        print("      letter is written as-is.")

    if hard:
        print()
        for h in hard:
            print(f"FAIL  {h}")
        print("\nTwo verified letters cannot share a dot pattern -- a learner could")
        print("not tell them apart, and neither could the model. Nothing written.")
        return 1

    # --- write -------------------------------------------------------------
    if not args.write:
        n_ver = sum(1 for e in proposed.values() if e["verified"])
        print(f"\nDRY RUN -- nothing written. Would leave {n_ver}/{len(letters)} "
              "letters verified.")
        print("Re-run with --write to apply.")
        return 0

    for r in results:
        l = r["letter"]
        l["dots"] = r["dots"]
        l["verified"] = True
        l["source"] = str(r["path"].relative_to(ROOT)).replace("\\", "/")

    n_ver = sum(1 for l in letters if l.get("verified"))
    data["verified"] = (n_ver == len(letters))
    data["verified_count"] = n_ver
    if n_ver == len(letters):
        data["standard"] = "VERIFIED_FROM_IMAGES"
    data["_warning"] = (
        f"{n_ver} of {len(letters)} letters verified from braille_img/. "
        "Letters with verified=false still carry Bharati PLACEHOLDER patterns "
        "-- supply images for them and re-run tools/import_braille_images.py."
        if n_ver < len(letters) else
        "All 50 letters verified from supplied images."
    )

    MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\nwrote {MAP_PATH.relative_to(ROOT)}")
    print(f"  verified {n_ver}/{len(letters)} letters")
    print("\nNow run:")
    print("  python3 tools/validate_braille_map.py")
    print("  python3 tools/verify_braille_images.py    <- then LOOK at the sheet")
    print("  python3 tools/gen_braille_header.py")
    print("  python3 tools/gen_braille_images.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
