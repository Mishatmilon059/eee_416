#!/usr/bin/env python3
"""Check the Supabase backend end to end, before you rely on it for collection.

    python3 tools/test_supabase.py            # read-only checks
    python3 tools/test_supabase.py --write    # also insert and delete a test row

Run this on YOUR machine. It was not runnable in the environment this project
was built in -- supabase.co is blocked there by egress policy -- so this is the
first real confirmation the backend works.

Checks, in the order they will actually bite you:
  1. project reachable, key accepted
  2. `attempts` table exists  (schema.sql actually run?)
  3. RLS lets the publishable key INSERT      -- collection dies without this
  4. RLS lets it SELECT                       -- export_dataset.py needs it
  5. the dedupe index rejects a replayed row  -- the offline queue relies on it
  6. monitoring views exist
  7. web/config.js does NOT contain a secret key
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from export_dataset import creds, load_dotenv  # noqa: E402

failures = []
warnings = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)
    return ok


def request(url, key, method="GET", body=None, extra_headers=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def sample_row(session_id, attempt_index):
    """A structurally valid row: satisfies every CHECK constraint in schema.sql,
    including streak exclusivity."""
    return {
        "user_id": "_SELFTEST", "session_id": session_id, "device_id": "selftest",
        "attempt_index": attempt_index,
        "char_id": 0, "response_time": 1234.5, "press_duration": 150.0,
        "retry_count": 0, "prev_accuracy": 0.5, "prev_mastery": 0.5,
        "hint_count": 0, "session_number": 1, "difficulty_level": 1,
        "time_since_last_practice": 600.0, "prev_confidence": 1,
        "current_streak": 1, "wrong_streak": 0, "prev_mistakes": 0,
        "teaching_action": 2, "confidence_state": 0,
        "expected_pattern": 1, "entered_pattern": 1, "is_correct": True,
        "press_order": "[1]", "source": "web", "is_synthetic": False,
        "spec_version": 1, "braille_map_verified": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="insert and then delete a test row (needs the secret key to clean up)")
    args = ap.parse_args()

    url, key = creds()
    if not url or not key:
        sys.exit("No credentials. Set SUPABASE_URL and SUPABASE_ANON_KEY in .env "
                 "(cp .env.example .env) or fill in web/config.js.")

    env = load_dotenv()
    secret = (env.get("SUPABASE_SERVICE_KEY") or
              env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    kind = "secret" if key.startswith("sb_secret_") else \
           "publishable" if key.startswith("sb_publishable_") else "legacy JWT"
    print(f"project : {url}")
    print(f"key     : {key[:22]}...  ({kind})")
    if kind == "secret":
        warnings.append("tools are using the SECRET key; that bypasses RLS, so "
                        "this run does not prove the publishable key works for "
                        "the browser app")

    print("\n-- 1. reachability --")
    status, body = request(f"{url}/rest/v1/", key)
    if not check("project reachable and key accepted", status in (200, 404),
                 f"HTTP {status}: {body[:200]}"):
        blocked = any(s in body.lower() for s in
                      ("tunnel connection failed", "proxy", "forbidden", "name or service"))
        if status == 0 and blocked:
            print("\n  This looks like a NETWORK/PROXY block, not a bad key: the request")
            print("  never reached Supabase. Corporate networks and sandboxed CI often")
            print("  deny supabase.co outright. Try from an unrestricted connection.")
        elif status in (401, 403):
            print("\n  The project answered but rejected the key. Confirm it is the")
            print("  PUBLISHABLE key from Settings -> API Keys, and that it belongs")
            print("  to this project. A rotated key stops working immediately.")
        else:
            print("\n  Check SUPABASE_URL, the key, and your network.")
        return 1

    print("\n-- 2. schema --")
    status, body = request(f"{url}/rest/v1/attempts?select=id&limit=1", key)
    if status == 404 or "does not exist" in body or 'relation "public.attempts"' in body:
        check("`attempts` table exists", False,
              "run supabase/schema.sql in the Supabase SQL editor first")
        print("\nNothing else can pass until the schema is applied.")
        return 1
    check("`attempts` table exists", status == 200, f"HTTP {status}: {body[:200]}")
    check("publishable key can SELECT (export_dataset.py needs this)",
          status == 200, f"HTTP {status}: {body[:160]}")

    print("\n-- 3. row count --")
    status, body = request(
        f"{url}/rest/v1/attempts?select=id", key,
        extra_headers={"Prefer": "count=exact", "Range": "0-0"})
    print(f"  info  rows currently in `attempts`: "
          f"{body.count('id') if status == 200 else 'unknown'}")

    print("\n-- 4. monitoring views --")
    for view in ("collection_summary", "class_balance", "participant_progress",
                 "character_difficulty"):
        st, bd = request(f"{url}/rest/v1/{view}?limit=1", key)
        check(f"view `{view}` exists", st == 200, f"HTTP {st}")

    if args.write:
        print("\n-- 5. insert path (what collection actually depends on) --")
        sid = f"selftest_{uuid.uuid4().hex[:8]}"
        st, bd = request(f"{url}/rest/v1/attempts", key, "POST",
                         [sample_row(sid, 0)],
                         {"Prefer": "return=minimal"})
        insert_ok = check("publishable key can INSERT", st in (200, 201, 204),
                          f"HTTP {st}: {bd[:240]}")

        if insert_ok:
            # The offline queue re-POSTs rows after a reconnect. schema.sql has a
            # unique index on (session_id, attempt_index) so a replay cannot
            # duplicate a row; storage.js treats the rejection as success.
            st2, bd2 = request(f"{url}/rest/v1/attempts", key, "POST",
                               [sample_row(sid, 0)],
                               {"Prefer": "return=minimal,resolution=ignore-duplicates"})
            check("replayed row is deduped, not duplicated (offline queue relies on this)",
                  st2 in (200, 201, 204, 409), f"HTTP {st2}: {bd2[:200]}")

            st3, bd3 = request(
                f"{url}/rest/v1/attempts?session_id=eq.{sid}&select=id", key)
            n = bd3.count('"id"') if st3 == 200 else -1
            check("exactly one row stored after the replay", n == 1,
                  f"found {n}")

            # clean up -- needs the secret key, since there is no delete policy
            if secret:
                st4, _ = request(
                    f"{url}/rest/v1/attempts?session_id=eq.{sid}", secret, "DELETE")
                check("test row cleaned up", st4 in (200, 204), f"HTTP {st4}")
            else:
                warnings.append(
                    f"could not delete the test rows (session_id={sid}): no secret "
                    "key in .env, and schema.sql grants no delete policy to anon. "
                    "Remove them by hand, or they will appear in your dataset as "
                    "user_id=_SELFTEST")
    else:
        print("\n-- 5. insert path --")
        print("  skipped. Re-run with --write to actually prove insert works;")
        print("  a reachable project with a readable table can still reject writes.")

    print("\n-- 6. secret key must not be client-side --")
    cfg = (ROOT / "web" / "config.js").read_text(encoding="utf-8")
    # Only inspect the actual assignments; the comments in that file mention
    # "service_role" precisely to warn against it.
    assigned = "\n".join(l for l in cfg.splitlines() if l.strip().startswith("export const"))
    check("web/config.js contains no secret key",
          "sb_secret_" not in assigned and not re.search(r"service_role", assigned),
          "a secret key in this file is served to every browser -- remove it and "
          "rotate the key immediately")
    check(".env is gitignored",
          ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").split())

    print("\n" + "=" * 62)
    for w in warnings:
        print(f"WARN  {w}")
    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("\nOK - Supabase backend is ready for collection")
    if not args.write:
        print("     (run with --write to prove the insert path too)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
