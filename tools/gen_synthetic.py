#!/usr/bin/env python3
"""Generate synthetic training rows by SIMULATING learners, not by sampling features.

    python3 tools/gen_synthetic.py --real dataset/real.csv --n 600 --out dataset/synthetic.csv

Two design decisions here matter more than anything else in this file.

1. SIMULATE, DO NOT SAMPLE.
   Drawing each of the 14 features independently produces incoherent vectors --
   current_streak=7 next to prev_mastery=0.02, or prev_mistakes=40 with
   prev_accuracy=0.99. Those combinations cannot occur in real use, so a model
   trained on them wastes capacity on an impossible region and learns nothing
   useful about the real one. Instead this runs virtual learners through virtual
   sessions using the SAME state machine as the web app, so every vector is
   internally consistent by construction.

2. FIT TO REAL DATA FIRST.
   Timing distributions come from the real CSV when one is supplied. Synthetic
   rows generated before any real data exists use documented priors, which are
   guesses -- the header of the output file says so. Collect the real 40% first,
   then generate the synthetic 60% conditioned on it. Doing it in the other
   order produces a dataset whose feature distribution does not match anything.

Labels come from tools/rule_engine_gen.py, the SAME generated engine the web app
uses, so synthetic and real rows are labelled identically. Every row is stamped
is_synthetic=true; train.py always reports real-only metrics separately.
"""
import argparse
import csv
import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import rule_engine_gen as engine  # noqa: E402

MAP = json.loads((ROOT / "data" / "braille_map.json").read_text(encoding="utf-8"))
LETTERS = MAP["letters"]
MAX_TRIES_PER_PROMPT = 4          # must match MAX_TRIES_PER_PROMPT in web/app.js

CSV_COLUMNS = [
    "created_at", "user_id", "session_id", "device_id", "attempt_index",
    *engine.FEATURE_NAMES,
    "teaching_action", "confidence_state",
    "expected_pattern", "entered_pattern", "is_correct", "press_order",
    "source", "is_synthetic", "spec_version", "braille_map_verified",
]

# Priors used ONLY when no real data is available. Stated explicitly so nobody
# mistakes them for measurements.
PRIORS = {
    "rt_correct_mu": math.log(1900), "rt_correct_sigma": 0.45,
    "rt_wrong_mu": math.log(3400), "rt_wrong_sigma": 0.55,
    "press_mu": math.log(150), "press_sigma": 0.40,
    "base_skill": 0.55,
}


def dots_to_mask(dots):
    m = 0
    for d in dots:
        m |= 1 << (d - 1)
    return m


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------

def fit_from_real(path):
    """Fit lognormal timing params and per-character difficulty from real rows."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("is_synthetic", "")).lower() in ("true", "1"):
                continue
            rows.append(r)
    if not rows:
        return None, 0

    def logstats(values, fallback_mu, fallback_sigma):
        vals = [math.log(max(1.0, float(v))) for v in values if v not in ("", None)]
        if len(vals) < 8:
            return fallback_mu, fallback_sigma
        mu = statistics.fmean(vals)
        sigma = statistics.pstdev(vals) if len(vals) > 1 else fallback_sigma
        return mu, max(0.15, sigma)

    correct_rows = [r for r in rows if str(r["is_correct"]).lower() in ("true", "1")]
    wrong_rows = [r for r in rows if str(r["is_correct"]).lower() not in ("true", "1")]

    fit = {}
    fit["rt_correct_mu"], fit["rt_correct_sigma"] = logstats(
        [r["response_time"] for r in correct_rows], PRIORS["rt_correct_mu"], PRIORS["rt_correct_sigma"])
    fit["rt_wrong_mu"], fit["rt_wrong_sigma"] = logstats(
        [r["response_time"] for r in wrong_rows], PRIORS["rt_wrong_mu"], PRIORS["rt_wrong_sigma"])
    fit["press_mu"], fit["press_sigma"] = logstats(
        [r["press_duration"] for r in rows], PRIORS["press_mu"], PRIORS["press_sigma"])
    fit["base_skill"] = (len(correct_rows) / len(rows)) if rows else PRIORS["base_skill"]

    # per-character accuracy -> relative difficulty
    per_char = {}
    for r in rows:
        cid = int(float(r["char_id"]))
        ok = str(r["is_correct"]).lower() in ("true", "1")
        s = per_char.setdefault(cid, [0, 0])
        s[0] += 1
        s[1] += 1 if ok else 0
    fit["char_accuracy"] = {cid: (v[1] / v[0]) for cid, v in per_char.items() if v[0] >= 3}
    return fit, len(rows)


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------

class VirtualChar:
    __slots__ = ("seen", "correct", "mastery", "streak", "wrong_streak",
                 "mistakes", "last_practice", "last_confidence")

    def __init__(self):
        self.seen = 0
        self.correct = 0
        self.mastery = engine.MASTERY_INITIAL
        self.streak = 0
        self.wrong_streak = 0
        self.mistakes = 0
        self.last_practice = None
        self.last_confidence = 1

    def accuracy(self):
        return 0.0 if self.seen == 0 else self.correct / self.seen


class VirtualLearner:
    """Mirrors LearnerState in web/storage.js. Any change there must land here."""

    def __init__(self, rng, fit, profile):
        self.rng = rng
        self.fit = fit
        self.profile = profile
        self.chars = {}
        self.session_number = 0
        self.difficulty = 1
        # aptitude shifts how quickly this learner's success probability rises
        self.aptitude = rng.gauss(1.0, 0.28)
        self.speed = rng.gauss(1.0, 0.22)

    def char(self, cid):
        if cid not in self.chars:
            self.chars[cid] = VirtualChar()
        return self.chars[cid]

    def success_probability(self, cid, gap_s, retry):
        """Rises with mastery, falls with staleness and per-character difficulty."""
        c = self.char(cid)
        base = 0.10 + 0.80 * c.mastery * max(0.35, self.aptitude)
        char_acc = self.fit.get("char_accuracy", {}).get(cid)
        if char_acc is not None:
            base = 0.55 * base + 0.45 * char_acc      # blend in the measured difficulty
        if gap_s > 86400:                              # forgetting after a day away
            base *= 0.72
        elif gap_s > 21600:
            base *= 0.88
        base += 0.06 * retry                           # a retry on the same prompt is easier
        if self.profile == "struggling":
            base *= 0.55
        elif self.profile == "fast":
            base = min(0.97, base * 1.25)
        return min(0.97, max(0.03, base))

    def response_time(self, correct, gap_s, retry):
        mu = self.fit["rt_correct_mu"] if correct else self.fit["rt_wrong_mu"]
        sigma = self.fit["rt_correct_sigma"] if correct else self.fit["rt_wrong_sigma"]
        rt = math.exp(self.rng.gauss(mu, sigma)) * self.speed
        if gap_s > 86400:
            rt *= 1.35                                  # rusty means slower
        if retry:
            rt *= 0.82                                  # already thinking about it
        if self.profile == "struggling":
            rt *= 1.5
        return min(14990.0, max(120.0, rt))

    def press_duration(self):
        pd = math.exp(self.rng.gauss(self.fit["press_mu"], self.fit["press_sigma"]))
        return min(1990.0, max(20.0, pd * self.speed))


def wrong_mask(rng, dots):
    """A plausible wrong answer: a dropped dot, an extra dot, or a swap."""
    mask = dots_to_mask(dots)
    mode = rng.random()
    if mode < 0.45 and len(dots) > 1:
        return mask & ~(1 << (rng.choice(dots) - 1))            # missed a dot
    if mode < 0.80:
        missing = [d for d in range(1, 7) if d not in dots]
        if missing:
            return mask | (1 << (rng.choice(missing) - 1))      # pressed one extra
    other = rng.choice(LETTERS)["dots"]                          # confused with another letter
    m = dots_to_mask(other)
    return m if m != mask else (mask ^ 1)


def simulate_learner(rng, fit, user_index, profile, sessions, attempts_per_session,
                     char_pool, start_time, stale_bias=False):
    """Run one virtual learner through several sessions spread over days."""
    lrn = VirtualLearner(rng, fit, profile)
    out = []
    clock = start_time
    device = f"synth_dev_{user_index % 3}"
    user_id = f"SYN{user_index:03d}"

    for _ in range(sessions):
        # sessions land on different days, which is what gives feature 10 range
        gap_days = rng.choice([0, 0, 1, 1, 2, 3, 5, 7]) if not stale_bias else rng.choice([2, 3, 5, 7, 10])
        clock += timedelta(days=gap_days, minutes=rng.randint(0, 600))
        lrn.session_number += 1
        session_id = f"syn_{user_id}_{lrn.session_number}"
        attempt_index = 0
        prev_action = None
        prev_cid = None

        while attempt_index < attempts_per_session:
            cid = pick_char(rng, lrn, char_pool, prev_action, prev_cid, stale_bias)
            c = lrn.char(cid)
            letter = LETTERS[cid]
            tries = 0
            hints = 0

            while attempt_index < attempts_per_session:
                clock += timedelta(seconds=rng.uniform(3, 14))
                now_ms = clock.timestamp() * 1000.0
                gap_s = (engine.FEATURE_RANGES[9][3] if c.last_practice is None
                         else max(0.0, (now_ms - c.last_practice) / 1000.0))

                # --- pre-attempt history -------------------------------------
                pre_acc = c.accuracy()
                pre_mastery = c.mastery
                pre_mistakes = c.mistakes
                pre_conf = c.last_confidence

                # --- outcome --------------------------------------------------
                p = lrn.success_probability(cid, gap_s, tries)
                correct = rng.random() < p
                rt = lrn.response_time(correct, gap_s, tries > 0)
                pd = lrn.press_duration()

                expected = dots_to_mask(letter["dots"])
                entered = expected if correct else wrong_mask(rng, letter["dots"])
                if entered == expected and not correct:
                    correct = True                    # keep entered/is_correct consistent

                # --- post-attempt state (same order as web/app.js) ------------
                c.seen += 1
                if correct:
                    c.correct += 1
                    c.streak += 1
                    c.wrong_streak = 0
                else:
                    c.mistakes += 1
                    c.wrong_streak += 1
                    c.streak = 0
                c.mastery = min(1.0, max(0.0, engine.update_mastery(c.mastery, correct)))
                c.last_practice = now_ms

                f = {
                    "char_id": float(cid),
                    "response_time": rt,
                    "press_duration": pd,
                    "retry_count": float(tries),
                    "prev_accuracy": pre_acc,
                    "prev_mastery": pre_mastery,
                    "hint_count": float(hints),
                    "session_number": float(lrn.session_number),
                    "difficulty_level": float(lrn.difficulty),
                    "time_since_last_practice": gap_s,
                    "prev_confidence": float(pre_conf),
                    "current_streak": float(c.streak),
                    "wrong_streak": float(c.wrong_streak),
                    "prev_mistakes": float(pre_mistakes),
                }

                confidence = int(engine.evaluate_confidence(f))
                action = int(engine.evaluate_teaching_action(f))
                c.last_confidence = confidence

                if action == int(engine.TeachingAction.INCREASE_DIFFICULTY):
                    lrn.difficulty = min(5, lrn.difficulty + 1)
                elif action == int(engine.TeachingAction.REVIEW_PREVIOUS):
                    lrn.difficulty = max(1, lrn.difficulty - 1)

                order = list(range(1, 7))
                rng.shuffle(order)
                pressed = [d for d in order if entered & (1 << (d - 1))]

                out.append({
                    "created_at": clock.replace(tzinfo=timezone.utc).isoformat(),
                    "user_id": user_id,
                    "session_id": session_id,
                    "device_id": device,
                    "attempt_index": attempt_index,
                    **{k: f[k] for k in engine.FEATURE_NAMES},
                    "teaching_action": action,
                    "confidence_state": confidence,
                    "expected_pattern": expected,
                    "entered_pattern": entered,
                    "is_correct": correct,
                    "press_order": json.dumps(pressed),
                    "source": "synthetic",
                    "is_synthetic": True,
                    "spec_version": engine.SPEC_VERSION,
                    "braille_map_verified": MAP["verified"],
                })

                attempt_index += 1
                tries += 1
                if action == int(engine.TeachingAction.HINT):
                    hints += 1

                retry_same = (not correct and tries < MAX_TRIES_PER_PROMPT
                              and action in (int(engine.TeachingAction.REPEAT),
                                             int(engine.TeachingAction.HINT)))
                if not retry_same:
                    prev_action, prev_cid = action, cid
                    break

    return out


def pick_char(rng, lrn, pool, prev_action, prev_cid, stale_bias):
    """Mirrors pickLetter() in web/app.js."""
    if prev_action in (int(engine.TeachingAction.REPEAT), int(engine.TeachingAction.HINT)) \
            and prev_cid is not None:
        return prev_cid
    seen = [cid for cid in pool if lrn.char(cid).seen > 0]
    if prev_action == int(engine.TeachingAction.REVIEW_PREVIOUS) and seen:
        weak = [cid for cid in seen if lrn.char(cid).mastery < 0.6]
        return rng.choice(weak or seen)
    if stale_bias and seen and rng.random() < 0.5:
        return min(seen, key=lambda cid: lrn.char(cid).last_practice or 0)
    weights = [0.15 + (1.0 - lrn.char(cid).mastery) for cid in pool]
    total = sum(weights)
    r = rng.random() * total
    for cid, w in zip(pool, weights):
        r -= w
        if r <= 0:
            return cid
    return pool[-1]


# ---------------------------------------------------------------------------

def class_counts(rows):
    ta = [0] * len(engine.TEACHING_ACTION_NAMES)
    cs = [0] * len(engine.CONFIDENCE_STATE_NAMES)
    for r in rows:
        ta[r["teaching_action"]] += 1
        cs[r["confidence_state"]] += 1
    return ta, cs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", type=Path, default=ROOT / "dataset" / "real.csv",
                    help="real CSV to fit distributions from (optional but strongly recommended)")
    ap.add_argument("--out", type=Path, default=ROOT / "dataset" / "synthetic.csv")
    ap.add_argument("--n", type=int, default=600, help="target synthetic rows")
    ap.add_argument("--seed", type=int, default=20260730)
    ap.add_argument("--min-per-class", type=int, default=30,
                    help="keep simulating rare-class scenarios until every class reaches this")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    fit, n_real = (None, 0)
    if args.real.exists():
        fit, n_real = fit_from_real(args.real)
    if fit is None:
        fit = dict(PRIORS)
        fit["char_accuracy"] = {}
        print("!! No real data found at", args.real)
        print("!! Falling back to PRIOR distributions -- these are GUESSES, not")
        print("!! measurements. Collect real sessions first, then regenerate;")
        print("!! synthetic rows fitted to nothing do not represent human behaviour.")
    else:
        print(f"fitted to {n_real} real rows from {args.real.name}")
        print(f"  response_time  correct : median {math.exp(fit['rt_correct_mu']):.0f} ms "
              f"(sigma {fit['rt_correct_sigma']:.2f})")
        print(f"  response_time  wrong   : median {math.exp(fit['rt_wrong_mu']):.0f} ms "
              f"(sigma {fit['rt_wrong_sigma']:.2f})")
        print(f"  press_duration         : median {math.exp(fit['press_mu']):.0f} ms")
        print(f"  overall accuracy       : {fit['base_skill']:.3f}")
        print(f"  per-character fits     : {len(fit['char_accuracy'])} characters")

    pool = [l["id"] for l in LETTERS]
    rows = []
    start = datetime(2026, 3, 1, 9, 0, 0)

    # main population
    profiles = ["normal", "normal", "normal", "fast", "struggling"]
    idx = 0
    while len(rows) < args.n and idx < 400:
        rows += simulate_learner(rng, fit, idx, profiles[idx % len(profiles)],
                                 sessions=rng.randint(3, 6),
                                 attempts_per_session=rng.randint(15, 25),
                                 char_pool=pool, start_time=start)
        idx += 1

    # --- top up starved classes -------------------------------------------
    # The scenario must be able to PRODUCE the starved class. INCREASE_DIFFICULTY
    # needs prev_mastery>=0.70 with a 3-streak and WORD_PRACTICE needs >=0.85
    # with a 5-streak, so simulating more struggling learners can never yield
    # either one no matter how long it runs. High-mastery classes need a strong
    # learner drilling a SMALL character pool, so the same characters recur often
    # enough for mastery and streaks to build.
    TA = engine.TeachingAction
    CS = engine.ConfidenceState
    HIGH_MASTERY = {int(TA.INCREASE_DIFFICULTY), int(TA.WORD_PRACTICE)}

    def scenario_for(kind, class_id):
        """(profile, char_pool, stale_bias) able to actually trigger this class."""
        if kind == "ta" and class_id in HIGH_MASTERY:
            size = 3 if class_id == int(TA.WORD_PRACTICE) else 6
            return "fast", rng.sample(pool, size), False
        if kind == "cs" and class_id == int(CS.CONFIDENT):
            return "fast", rng.sample(pool, 6), False
        return "struggling", pool, True

    for _ in range(400):
        ta, cs = class_counts(rows)
        starved = [("ta", i) for i, v in enumerate(ta) if v < args.min_per_class] + \
                  [("cs", i) for i, v in enumerate(cs) if v < args.min_per_class]
        if not starved:
            break
        kind, class_id = starved[0]
        profile, char_pool, stale = scenario_for(kind, class_id)
        rows += simulate_learner(rng, fit, idx, profile,
                                 sessions=rng.randint(4, 8),
                                 attempts_per_session=rng.randint(18, 30),
                                 char_pool=char_pool, start_time=start, stale_bias=stale)
        idx += 1

    # Trim toward the requested size, but never below full class coverage: drop
    # rows only from classes that are still comfortably above the floor.
    if len(rows) > args.n:
        rng.shuffle(rows)
        kept, per_ta, per_cs = [], [0] * len(ta), [0] * len(cs)
        # first pass: guarantee the floor for every class
        for r in rows:
            if per_ta[r["teaching_action"]] < args.min_per_class or \
               per_cs[r["confidence_state"]] < args.min_per_class:
                kept.append(r)
                per_ta[r["teaching_action"]] += 1
                per_cs[r["confidence_state"]] += 1
        # second pass: fill up to n with whatever is left
        for r in rows:
            if len(kept) >= args.n:
                break
            if r not in kept:
                kept.append(r)
        rows = kept
        rows.sort(key=lambda r: (r["user_id"], r["session_id"], r["attempt_index"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    ta, cs = class_counts(rows)
    print(f"\nwrote {len(rows)} synthetic rows to {args.out.relative_to(ROOT)}")
    print(f"simulated learners: {idx}")
    print("\nteaching action:")
    for i, name in enumerate(engine.TEACHING_ACTION_NAMES):
        flag = "" if ta[i] >= args.min_per_class else "   <-- STARVED"
        print(f"  {name:<22} {ta[i]:>6}{flag}")
    print("confidence state:")
    for i, name in enumerate(engine.CONFIDENCE_STATE_NAMES):
        flag = "" if cs[i] >= args.min_per_class else "   <-- STARVED"
        print(f"  {name:<22} {cs[i]:>6}{flag}")

    if n_real == 0:
        print("\n!! REMINDER: these rows are fitted to priors, not to real users.")
        print("!! Regenerate after collecting real sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
