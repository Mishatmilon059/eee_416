#!/usr/bin/env python3
"""Generate Bangla pronunciation audio with espeak-ng.

Writes the SAME numbered files to two places:
  web/audio/          -- served by the MVP web app
  sd_card/mp3/        -- copy this folder to the microSD root for DFPlayer Mini

DFPlayer Mini requires 4-digit zero-padded names inside a folder literally named
"mp3" at the card root, and it plays by track NUMBER, not filename. Track number
= letter id + 1, which is what braille_track() in braille_map.h returns.

    python3 tools/gen_audio.py            # letters + system prompts
    python3 tools/gen_audio.py --list     # show the track table, generate nothing

Voice quality: espeak-ng is intelligible but robotic. To swap in real human
recordings later, just overwrite the numbered files -- no code changes anywhere,
because everything addresses audio by track number.

Requires: espeak-ng, ffmpeg.
"""
import argparse
import json
import shutil
import subprocess
import sys
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the track table only")
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

    require("espeak-ng")
    require("ffmpeg")

    for d in (WEB_DIR, SD_DIR):
        d.mkdir(parents=True, exist_ok=True)

    total = 0
    for l in letters:
        total += synth(l["char"], l["id"] + 1, [WEB_DIR, SD_DIR])
    print(f"generated {len(letters)} letter clips (tracks 1-{len(letters)})")

    for track, name, text in SYSTEM_PROMPTS:
        total += synth(text, track, [WEB_DIR, SD_DIR])
    print(f"generated {len(SYSTEM_PROMPTS)} system prompts "
          f"(tracks {SYSTEM_PROMPTS[0][0]}-{SYSTEM_PROMPTS[-1][0]})")

    manifest = {
        "_comment": "Track number -> meaning. DFPlayer plays by number, not name.",
        "voice": f"espeak-ng {VOICE}",
        "human_recorded": False,
        "letters": {str(l["id"] + 1): {"char": l["char"], "name": l["name"]} for l in letters},
        "prompts": {str(t): n for t, n, _ in SYSTEM_PROMPTS},
    }
    (WEB_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\ntotal {total / 1024:.0f} KB")
    print(f"  web app : web/audio/")
    print(f"  SD card : sd_card/mp3/   <- copy this 'mp3' folder to the card root")
    print("\nvoice is espeak-ng (robotic). Overwrite the numbered files with human")
    print("recordings later -- nothing in the code addresses audio by anything but number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
