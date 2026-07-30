#!/usr/bin/env python3
"""Pull collected rows out of Supabase (and/or local CSVs) into one training CSV.

    python3 tools/export_dataset.py --out dataset/real.csv
    python3 tools/export_dataset.py --merge downloads/*.csv --out dataset/real.csv

Reads SUPABASE_URL and SUPABASE_ANON_KEY from the environment, or from
web/config.js if you already filled those in there.

Also runs the sanity checks that matter before training, because every one of
these has a habit of surfacing at training time when it is far too late to
re-collect:
  - are all 9 classes populated?
  - did sessions actually happen on different days?
  - are any rows carrying an unverified Braille map?
  - do the streak/correctness invariants hold?
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import rule_engine_gen as engine  # noqa: E402

CSV_COLUMNS = [
    "created_at", "user_id", "session_id", "device_id", "attempt_index",
    *engine.FEATURE_NAMES,
    "teaching_action", "confidence_state",
    "expected_pattern", "entered_pattern", "is_correct", "press_order",
    "source", "is_synthetic", "spec_version", "braille_map_verified",
]
PAGE = 1000


def load_dotenv(path=None):
    """Read .env into a dict. Deliberately not exported into os.environ, so a
    secret key cannot leak into a subprocess that had no business seeing it."""
    path = path or (ROOT / ".env")
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def creds():
    """Resolution order: environment, then .env, then web/config.js.

    The secret key is preferred when present because it bypasses RLS -- needed
    if you tighten the select policy in schema.sql. It must only ever come from
    the environment or .env, never from web/config.js, which is served to
    every browser.
    """
    env = load_dotenv()

    def pick(name):
        return (os.environ.get(name, "").strip() or env.get(name, "").strip())

    url = pick("SUPABASE_URL")
    key = pick("SUPABASE_SERVICE_KEY") or pick("SUPABASE_SERVICE_ROLE_KEY") \
        or pick("SUPABASE_ANON_KEY")
    if url and key:
        return url.rstrip("/"), key
    cfg = ROOT / "web" / "config.js"
    if cfg.exists():
        txt = cfg.read_text(encoding="utf-8")
        m_url = re.search(r'SUPABASE_URL\s*=\s*"([^"]*)"', txt)
        m_key = re.search(r'SUPABASE_ANON_KEY\s*=\s*"([^"]*)"', txt)
        if m_url and m_key and m_url.group(1) and m_key.group(1):
            return m_url.group(1).rstrip("/"), m_key.group(1)
    return None, None


def fetch_supabase(url, key):
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"select": "*", "order": "id.asc",
                                    "limit": PAGE, "offset": offset})
        req = urllib.request.Request(
            f"{url}/rest/v1/attempts?{q}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                page = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            sys.exit(f"Supabase returned {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        except urllib.error.URLError as e:
            sys.exit(f"Could not reach Supabase: {e.reason}")
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def norm_bool(v):
    return str(v).strip().lower() in ("true", "t", "1", "yes")


def dedupe(rows):
    """Same (session_id, attempt_index) can arrive from both Supabase and a
    manual CSV export of the same session."""
    seen, out = set(), []
    for r in rows:
        k = (r.get("session_id"), str(r.get("attempt_index")), norm_bool(r.get("is_synthetic")))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def audit(rows):
    problems, warnings = [], []
    ta = Counter(int(float(r["teaching_action"])) for r in rows)
    cs = Counter(int(float(r["confidence_state"])) for r in rows)
    real = [r for r in rows if not norm_bool(r["is_synthetic"])]

    print(f"\nrows total     : {len(rows)}")
    print(f"  real         : {len(real)}")
    print(f"  synthetic    : {len(rows) - len(real)}")
    if rows:
        pct = 100 * len(real) / len(rows)
        print(f"  real share   : {pct:.0f}%  (plan targets ~40%)")

    users = {r["user_id"] for r in real}
    sessions = {r["session_id"] for r in real}
    days = {str(r["created_at"])[:10] for r in real}
    print(f"participants   : {len(users)}")
    print(f"sessions       : {len(sessions)}")
    print(f"distinct days  : {len(days)}")

    print("\nteaching action:")
    for i, name in enumerate(engine.TEACHING_ACTION_NAMES):
        n = ta.get(i, 0)
        print(f"  {name:<22} {n:>6}" + ("" if n >= 30 else "   <-- under 30"))
        if n == 0:
            problems.append(f"teaching_action {name} has ZERO examples")
        elif n < 30:
            warnings.append(f"teaching_action {name} has only {n} examples")
    print("confidence state:")
    for i, name in enumerate(engine.CONFIDENCE_STATE_NAMES):
        n = cs.get(i, 0)
        print(f"  {name:<22} {n:>6}" + ("" if n >= 30 else "   <-- under 30"))
        if n == 0:
            problems.append(f"confidence_state {name} has ZERO examples")
        elif n < 30:
            warnings.append(f"confidence_state {name} has only {n} examples")

    # invariants
    bad_streak = [r for r in rows
                  if float(r["current_streak"]) > 0 and float(r["wrong_streak"]) > 0]
    if bad_streak:
        problems.append(f"{len(bad_streak)} rows have both streaks non-zero "
                        "(violates the spec timing contract)")
    bad_derive = [r for r in rows
                  if (float(r["current_streak"]) > 0) != norm_bool(r["is_correct"])]
    if bad_derive:
        problems.append(f"{len(bad_derive)} rows where current_streak disagrees with is_correct")

    unverified = [r for r in real if not norm_bool(r["braille_map_verified"])]
    if unverified:
        warnings.append(f"{len(unverified)} real rows were collected against an "
                        "UNVERIFIED Braille map")

    specs = {str(r["spec_version"]) for r in rows}
    if len(specs) > 1:
        problems.append(f"rows span multiple spec versions {sorted(specs)} -- "
                        "labels are not comparable across a spec change")

    if len(real) and len(days) < 3:
        warnings.append(f"real rows span only {len(days)} distinct day(s); "
                        "session_number and time_since_last_practice carry little signal")

    return problems, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dataset" / "real.csv")
    ap.add_argument("--merge", type=Path, nargs="*", default=[],
                    help="extra CSVs to fold in (e.g. per-laptop browser exports)")
    ap.add_argument("--include-synthetic", action="store_true",
                    help="keep synthetic rows in the output (default: real only)")
    ap.add_argument("--no-remote", action="store_true", help="skip Supabase, local CSVs only")
    args = ap.parse_args()

    rows = []
    if not args.no_remote:
        url, key = creds()
        if url and key:
            print(f"fetching from {url} ...")
            rows += fetch_supabase(url, key)
            print(f"  {len(rows)} rows from Supabase")
        else:
            print("no Supabase credentials found (env SUPABASE_URL/SUPABASE_ANON_KEY "
                  "or web/config.js) -- local CSVs only")

    for p in args.merge:
        got = read_csv(p)
        rows += got
        print(f"  {len(got)} rows from {p}")

    if not rows:
        sys.exit("\nNo rows found. Collect some sessions first, or pass --merge with "
                 "CSVs exported from the app.")

    rows = dedupe(rows)
    if not args.include_synthetic:
        rows = [r for r in rows if not norm_bool(r["is_synthetic"])]

    rows.sort(key=lambda r: (str(r.get("created_at")), str(r.get("session_id")),
                             int(float(r.get("attempt_index", 0)))))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CSV_COLUMNS})

    problems, warnings = audit(rows)
    print(f"\nwrote {len(rows)} rows to {args.out.relative_to(ROOT)}")

    for w_ in warnings:
        print(f"WARN  {w_}")
    for p_ in problems:
        print(f"FAIL  {p_}")
    if problems:
        print(f"\n{len(problems)} blocking problem(s) -- fix before training")
        return 1
    print("\nOK - dataset passes pre-training checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
