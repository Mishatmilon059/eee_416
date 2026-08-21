#!/usr/bin/env python3
"""Generate Bangla pronunciation audio, espeak-ng OR gTTS.

Writes the SAME numbered files to two places:
  web/audio/          -- served by the MVP web app
  sd_card/mp3/        -- copy this folder to the microSD root for DFPlayer Mini

DFPlayer Mini requires 4-digit zero-padded names inside a folder literally named
"mp3" at the card root, and it plays by track NUMBER, not filename. Track number
= letter id + 1, which is what braille_track() in braille_map.h returns.

    python3 tools/gen_audio.py                    # gTTS (default): natural voice
    python3 tools/gen_audio.py --engine espeak     # offline fallback, robotic
    python3 tools/gen_audio.py --list              # show the track table, generate nothing

Two engines, pick with --engine:

  gtts    (default) Google Translate's Bangla voice. Free, no API key, but needs
           outbound internet to translate.google.com -- it will NOT work from a
           network-restricted sandbox (this repo was built in one; see README).
           slow=True is used so a single letter is pronounced the way a person
           actually says it -- holding the vowel -- landing around 2-3s instead
           of espeak's clipped ~1s. A small lead/tail silence pad is added so
           the clip does not feel cut off at the edges.

  espeak  Fully offline, always works, sounds like a formant synthesizer because
          that is what it is. Kept as a fallback for CI / sandboxes / bring-up
          before a real voice is wired in.

Neither is a substitute for real human recordings. Whichever engine you use,
you can swap in real recordings later with NO code changes anywhere -- just
overwrite the numbered files, because everything addresses audio by track
number.

Requires: ffmpeg always. Plus one of: `pip install gTTS` (gtts engine) or
espeak-ng (espeak engine, `apt-get install -y espeak-ng`).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "braille_map.json"
WEB_DIR = ROOT / "web" / "audio"
SD_DIR = ROOT / "sd_card" / "mp3"

VOICE = "bn"
SPEED = 130          # wpm; slower than default 175, these are single letters
AMPLITUDE = 180      # 0-200
MP3_RATE = "44100"
MP3_BITRATE = "64k"  # mono speech; keeps the whole set small

# --- gTTS engine ------------------------------------------------------------
GTTS_LANG = "bn"
GTTS_SLOW = True          # natural, held-vowel pacing instead of a clipped read
GTTS_RETRIES = 3          # transient network hiccups, not a reason to abort the run
GTTS_REQUEST_GAP_S = 0.6  # be polite across ~60 requests; avoids throttling
LEAD_SILENCE_MS = 150     # small pad so the clip does not feel cut off at the start
TAIL_SILENCE_S = 0.15

# Track numbers 51+ are system prompts. Letters occupy 1..50.
SYSTEM_PROMPTS = [
    (51, "correct",       "সঠিক"),
    (52, "wrong",         "ভুল"),
    (53, "try_again",     "আবার চেষ্টা করুন"),
    (54, "hint",          "ইঙ্গিত"),
    (55, "well_done",     "খুব ভালো"),
    (56, "next_letter",   "পরের অক্ষর"),
    (57, "review",        "পুনরাবৃত্তি"),
    (58, "harder",        "এখন কঠিন স্তর"),
    (59, "session_start", "শুরু করা যাক"),
    (60, "session_end",   "অনুশীলন শেষ"),
]


def require(tool):
    if not shutil.which(tool):
        sys.exit(f"error: {tool} not found. Install it first "
                 f"(apt-get install -y {tool}).")


def synth(text, track, out_dirs):
    """espeak-ng -> wav -> mono mp3, written into every out_dir."""
    wav = ROOT / f".tmp_{track:04d}.wav"
    subprocess.run(
        ["espeak-ng", "-v", VOICE, "-s", str(SPEED), "-a", str(AMPLITUDE),
         "-w", str(wav), text],
        check=True, capture_output=True,
    )
    first = out_dirs[0] / f"{track:04d}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
         "-ac", "1", "-ar", MP3_RATE, "-b:a", MP3_BITRATE, str(first)],
        check=True,
    )
    for d in out_dirs[1:]:
        shutil.copy(first, d / f"{track:04d}.mp3")
    wav.unlink(missing_ok=True)
    return first.stat().st_size


def get_duration(path):
    """Seconds, via ffprobe. Returns None rather than raising -- this is only
    used for the summary printout, never for correctness."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def synth_gtts(text, track, out_dirs):
    """gTTS -> mp3 -> normalize + pad -> mono mp3, written into every out_dir.

    gTTS hits translate.google.com over the network, so this raises a clear,
    actionable error (not a stack trace) when that network path is blocked --
    which is the case in a sandboxed/offline environment.
    """
    from gtts import gTTS

    raw = ROOT / f".tmp_{track:04d}_raw.mp3"
    last_err = None
    for attempt in range(GTTS_RETRIES):
        try:
            gTTS(text=text, lang=GTTS_LANG, slow=GTTS_SLOW).save(str(raw))
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt < GTTS_RETRIES - 1:
                time.sleep(2 ** attempt)
    if last_err is not None:
        raise RuntimeError(
            f"gTTS failed for track {track} ({text!r}) after {GTTS_RETRIES} tries: {last_err}\n"
            "gTTS needs outbound internet to translate.google.com. If you're running "
            "this from a network-restricted sandbox, run it from a machine with open "
            "internet instead, or fall back with: python3 tools/gen_audio.py --engine espeak"
        ) from last_err

    first = out_dirs[0] / f"{track:04d}.mp3"
    # Normalize to the DFPlayer-required format and add a small lead/tail pad
    # so the clip doesn't feel clipped at the edges -- cosmetic only, this does
    # not change the pronunciation itself.
    af = f"adelay={LEAD_SILENCE_MS}:all=1,apad=pad_dur={TAIL_SILENCE_S}"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
         "-af", af, "-ac", "1", "-ar", MP3_RATE, "-b:a", MP3_BITRATE, str(first)],
        check=True,
    )
    for d in out_dirs[1:]:
        shutil.copy(first, d / f"{track:04d}.mp3")
    raw.unlink(missing_ok=True)
    time.sleep(GTTS_REQUEST_GAP_S)
    return first.stat().st_size, get_duration(first)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the track table only")
    ap.add_argument("--engine", choices=["gtts", "espeak"], default="gtts",
                    help="gtts: natural voice, needs internet (default). "
                         "espeak: offline fallback, robotic.")
    args = ap.parse_args()

    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    letters = data["letters"]

    if args.list:
        print(f"{'track':>5}  {'file':<10}  {'what':<16}  text")
        for l in letters:
            print(f"{l['id'] + 1:>5}  {l['id'] + 1:04d}.mp3  {l['name']:<16}  {l['char']}")
        for track, name, text in SYSTEM_PROMPTS:
            print(f"{track:>5}  {track:04d}.mp3  {name:<16}  {text}")
        return 0

    require("ffmpeg")
    if args.engine == "espeak":
        require("espeak-ng")
    else:
        try:
            import gtts  # noqa: F401
        except ImportError:
            sys.exit("error: gTTS not installed. Run: pip install gTTS\n"
                     "(or use --engine espeak for the offline fallback)")

    for d in (WEB_DIR, SD_DIR):
        d.mkdir(parents=True, exist_ok=True)

    def gen(text, track):
        if args.engine == "gtts":
            return synth_gtts(text, track, [WEB_DIR, SD_DIR])
        return synth(text, track, [WEB_DIR, SD_DIR]), None

    total = 0
    durations = []
    for l in letters:
        size, dur = gen(l["char"], l["id"] + 1)
        total += size
        if dur is not None:
            durations.append(dur)
    print(f"generated {len(letters)} letter clips (tracks 1-{len(letters)})")

    for track, name, text in SYSTEM_PROMPTS:
        size, dur = gen(text, track)
        total += size
    print(f"generated {len(SYSTEM_PROMPTS)} system prompts "
          f"(tracks {SYSTEM_PROMPTS[0][0]}-{SYSTEM_PROMPTS[-1][0]})")

    voice_desc = (f"gtts {GTTS_LANG} (slow={GTTS_SLOW})" if args.engine == "gtts"
                  else f"espeak-ng {VOICE}")
    manifest = {
        "_comment": "Track number -> meaning. DFPlayer plays by number, not name.",
        "voice": voice_desc,
        "human_recorded": False,
        "letters": {str(l["id"] + 1): {"char": l["char"], "name": l["name"]} for l in letters},
        "prompts": {str(t): n for t, n, _ in SYSTEM_PROMPTS},
    }
    (WEB_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\ntotal {total / 1024:.0f} KB")
    print(f"  web app : web/audio/")
    print(f"  SD card : sd_card/mp3/   <- copy this 'mp3' folder to the card root")
    if durations:
        avg = sum(durations) / len(durations)
        print(f"\nletter clip duration: avg {avg:.2f}s, min {min(durations):.2f}s, "
              f"max {max(durations):.2f}s")
    if args.engine == "espeak":
        print("\nvoice is espeak-ng (robotic). Try --engine gtts for a natural voice, or")
        print("overwrite the numbered files with human recordings -- nothing in the code")
        print("addresses audio by anything but number.")
    else:
        print("\nvoice is gTTS (Google, natural). Still not a human voice -- for the best")
        print("result, overwrite the numbered files with real recordings; nothing in the")
        print("code addresses audio by anything but track number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
