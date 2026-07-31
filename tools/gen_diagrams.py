#!/usr/bin/env python3
"""Generate the presentation diagrams as SVG (editable) + PNG (drop-in).

    python3 tools/gen_diagrams.py

Output: docs/diagrams/NN_name.svg and .png, all on a pure white background.

Figures are numbered in presentation order and follow the real pipeline:
simulation -> database -> CSV -> TinyML training -> ESP32 deployment ->
classroom use -> teacher analytics.

Two rendering rules learned the hard way, both visible as empty boxes if broken:
  * Bangla text MUST carry font-family "Noto Sans Bengali" (FONT_BN). Arial has
    no Bengali glyphs and silently renders every character as tofu.
  * No emoji anywhere. The rasteriser has no emoji font, so they become boxes
    too. Icons are drawn as shapes or plain ASCII instead.

Status badges ("BUILT" / "PLANNED") are deliberate. Three of these stages do not
exist yet, and a deck that shows them identically to the finished ones would
misrepresent the project to anyone reading it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from svgkit import (APP, BAD, DATA, FONT_BN, HW, INK, LINE, MODEL, MUTED, OK,
                    SIM, TINT, WARN, WHITE, Svg)

OUT = ROOT / "docs" / "diagrams"

# Real measured figures, read from the repo so the slides cannot drift from it.
M = json.loads((ROOT / "models" / "metrics.json").read_text())
BMAP = json.loads((ROOT / "data" / "braille_map.json").read_text())
N_VERIFIED = sum(1 for l in BMAP["letters"] if l.get("verified"))
PARAMS = M["params"]
TFLITE_B = M["tflite_bytes"]
TEACH_ACC = M["test"]["teaching_combined"]
CONF_ACC = M["test"]["confidence_combined"]

BUILT, PLANNED = "BUILT", "PLANNED"

# Vertical rhythm: every diagram fills this band so no slide has a dead half.
TOP, BOTTOM = 150, 800


# ===========================================================================
def d01_overview():
    s = Svg(title="System overview")
    s.header("AI-Assisted Bangla Braille Tutor",
             "Complete pipeline: simulation to data to TinyML to offline hardware to analytics")

    stages = [
        ("1", "SIMULATION", SIM, BUILT,
         ["Web app teaches Braille", "and records every", "attempt a learner makes"]),
        ("2", "DATABASE", DATA, BUILT,
         ["Supabase stores 14", "features and 2 labels", "for every attempt"]),
        ("3", "TinyML MODEL", MODEL, BUILT,
         [f"{PARAMS:,} parameters", f"{TFLITE_B:,} bytes after", "int8 quantization"]),
        ("4", "ESP32 DEVICE", HW, PLANNED,
         ["Runs fully offline.", "Speaker, 6 buttons", "and 6 vibration motors"]),
        ("5", "MOBILE APP", APP, PLANNED,
         ["Teacher sees progress,", "learning curves and", "AI suggestions"]),
    ]

    bw, bh, gap = 265, 300, 20
    x0, y = 60, TOP + 30
    for i, (num, name, color, status, body) in enumerate(stages):
        x = x0 + i * (bw + gap)
        s.rect(x, y, bw, bh, fill=TINT[color], stroke=color, sw=2.5)
        s.circle(x + 36, y + 46, 22, fill=color, stroke=color)
        s.text(x + 36, y + 54, num, 21, "bold", WHITE, "middle")
        s.text(x + 68, y + 54, name, 17.5, "bold", INK)
        s.lines(x + 20, y + 108, body, 14.5, 24, INK)
        s.badge(x + bw - 16, y + bh - 42, status)

        if i < len(stages) - 1:
            s.arrow(x + bw + 3, y + bh / 2, x + bw + gap - 4, y + bh / 2, color=LINE, sw=3)

    # what travels along each hop
    flows = ["real learner attempts", "CSV export", "model.tflite → C header", "session logs (SD card)"]
    for i, f in enumerate(flows):
        x = x0 + (i + 1) * (bw + gap) - gap / 2
        s.text(x, y + bh + 34, f, 12.5, "normal", MUTED, "middle")

    # feedback loop back to training
    ly = y + bh + 92
    s.path(f"M {x0 + 4 * (bw + gap) + bw / 2} {y + bh + 50} L {x0 + 4 * (bw + gap) + bw / 2} {ly} "
           f"L {x0 + 2 * (bw + gap) + bw / 2} {ly} L {x0 + 2 * (bw + gap) + bw / 2} {y + bh + 8}",
           stroke=MUTED, sw=2.5, dash="7 6")
    s.text(x0 + 3 * (bw + gap), ly - 12,
           "continuous learning — retrain on new data, redeploy", 14, "bold", MUTED, "middle")

    s.legend(60, BOTTOM - 10, [("Built and tested", OK), ("Planned / not built yet", WARN)])
    s.footnote("All figures are measured from the current build, not estimates.")
    return s, "01_system_overview"


# ===========================================================================
def d02_simulation():
    s = Svg(title="Phase 1 — simulation and data collection")
    s.header("Phase 1 — Simulation captures real learner behaviour",
             "The web app is a measuring instrument first and a tutor second",
             BUILT, OK)

    s.rect(60, TOP, 500, BOTTOM - TOP, fill=WHITE, stroke=LINE, sw=2, dash="7 6")
    s.text(80, TOP + 32, "IN THE BROWSER", 14, "bold", MUTED)

    steps = [
        ("Audio prompt", "the app speaks a Bangla letter", SIM),
        ("Learner responds", "presses 6 keys = 6 Braille dots", SIM),
        ("System scores it", "entered pattern vs expected", SIM),
        ("Rule engine decides", "teaching action + confidence", MODEL),
    ]
    for i, (t, sub, c) in enumerate(steps):
        y = TOP + 60 + i * 145
        s.rect(90, y, 440, 105, fill=TINT[c], stroke=c, sw=2)
        s.circle(126, y + 52, 21, fill=c, stroke=c)
        s.text(126, y + 60, str(i + 1), 19, "bold", WHITE, "middle")
        s.text(162, y + 44, t, 18, "bold", INK)
        s.text(162, y + 72, sub, 14, "normal", MUTED)
        if i < 3:
            s.arrow(310, y + 107, 310, y + 143, color=LINE, sw=2.5)

    # recorded fields
    s.rect(600, TOP, 480, 340, fill=TINT[DATA], stroke=DATA, sw=2.5)
    s.text(624, TOP + 38, "RECORDED PER ATTEMPT", 15, "bold", DATA)
    rec = ["response time", "press duration", "retry count", "hint count",
           "prev accuracy", "prev mastery", "current streak", "wrong streak",
           "time since practice", "session number", "difficulty level", "prev mistakes",
           "character id", "prev confidence"]
    for i, r in enumerate(rec):
        s.text(624 + (i % 2) * 228, TOP + 78 + (i // 2) * 30, "•  " + r, 14, "normal", INK)
    s.rect(624, TOP + 285, 432, 38, fill=WHITE, stroke=DATA, sw=1.5, r=8)
    s.text(840, TOP + 310, "14 features  +  2 labels  =  1 row", 15.5, "bold", DATA, "middle")

    # braille cell
    s.rect(600, TOP + 370, 480, BOTTOM - TOP - 370, fill=WHITE, stroke=LINE, sw=2)
    s.text(624, TOP + 404, "VIRTUAL BRAILLE CELL", 14, "bold", MUTED)
    s.braille_cell(680, TOP + 450, [1, 3, 6], dot_r=16, gap_x=52, gap_y=48, labels=True)
    s.lines(790, TOP + 452, [
        "The 6 dots on screen map", "one-to-one onto the 6",
        "vibration motors on the", "hardware build.",
    ], 15, 25, INK)

    s.rect(1120, TOP, 420, BOTTOM - TOP, fill=TINT[OK], stroke=OK, sw=2.5)
    s.text(1144, TOP + 38, "WHY SIMULATE FIRST", 15, "bold", OK)
    s.lines(1144, TOP + 78, [
        "No hardware is needed to",
        "start collecting real",
        "learner behaviour.",
        "",
        "Volunteers practise with",
        "eyes closed, so the timing",
        "and hesitation recorded",
        "are genuine.",
        "",
        "The same rule engine that",
        "runs here is generated",
        "into the ESP32 firmware,",
        "so the two can never",
        "drift apart.",
        "",
        "Collection can begin weeks",
        "before any component",
        "arrives.",
    ], 15, 26, INK)

    s.footnote("Every row is written to local storage first, then synced — a dropped connection never loses data or interrupts a session.")
    return s, "02_phase1_simulation"


# ===========================================================================
def d03_features():
    s = Svg(title="Features and labels")
    s.header("What the model sees, and what it predicts",
             "14 numeric inputs, two simultaneous outputs", BUILT, OK)

    groups = [
        ("SAMPLED BEFORE THE ATTEMPT", ["character id", "prev accuracy", "prev mastery",
                                        "prev mistakes", "prev confidence", "session number",
                                        "difficulty level", "time since last practice"], DATA),
        ("MEASURED DURING", ["response time", "press duration",
                             "retry count", "hint count"], SIM),
        ("READ AFTER SCORING", ["current streak", "wrong streak"], OK),
    ]
    x = 60
    for name, items, color in groups:
        w = 320 if len(items) > 4 else 250
        s.rect(x, TOP, w, 330, fill=TINT[color], stroke=color, sw=2.5)
        s.text(x + 18, TOP + 36, name, 14, "bold", color)
        for i, it in enumerate(items):
            s.text(x + 18, TOP + 76 + i * 30, "•  " + it, 15, "normal", INK)
        x += w + 26

    # key insight band
    s.rect(60, TOP + 360, 916, 290, fill=TINT[WARN], stroke=WARN, sw=2.5)
    s.text(84, TOP + 398, "KEY DESIGN POINT", 16, "bold", WARN)
    s.text(84, TOP + 428, "There is deliberately no \"is correct\" input.", 17, "bold", INK)
    s.lines(84, TOP + 464, [
        "The two streaks are read AFTER the answer is scored, so correctness is",
        "already implied by them:",
    ], 15, 24, INK)
    s.rect(84, TOP + 508, 420, 40, fill=WHITE, stroke=OK, sw=2, r=8)
    s.text(294, TOP + 534, "current streak > 0   →   answer was RIGHT", 14.5, "bold", OK, "middle")
    s.rect(520, TOP + 508, 420, 40, fill=WHITE, stroke=BAD, sw=2, r=8)
    s.text(730, TOP + 534, "wrong streak > 0   →   answer was WRONG", 14.5, "bold", BAD, "middle")
    s.lines(84, TOP + 578, [
        "Exactly one is ever non-zero. This lets the network reproduce every rule the",
        "engine applies — had the streaks been read before scoring, the engine would",
        "branch on information the model cannot see, and accuracy would cap out for",
        "reasons that look like a training bug but are not.",
    ], 14.5, 21, INK)

    # outputs
    s.rect(1006, TOP, 534, 300, fill=TINT[MODEL], stroke=MODEL, sw=2.5)
    s.text(1030, TOP + 36, "OUTPUT 1 — TEACHING ACTION", 15, "bold", MODEL)
    s.text(1030, TOP + 60, "6 classes", 13.5, "normal", MUTED)
    acts = ["Repeat", "Hint", "Normal practice",
            "Increase difficulty", "Review previous", "Word practice"]
    for i, a in enumerate(acts):
        cx, cy = 1030 + (i % 2) * 258, TOP + 82 + (i // 2) * 68
        s.rect(cx, cy, 242, 52, fill=WHITE, stroke=MODEL, sw=1.5, r=10)
        s.text(cx + 121, cy + 33, a, 15, "bold", INK, "middle")

    s.rect(1006, TOP + 330, 534, 175, fill=TINT[APP], stroke=APP, sw=2.5)
    s.text(1030, TOP + 366, "OUTPUT 2 — CONFIDENCE STATE", 15, "bold", APP)
    s.text(1030, TOP + 390, "3 classes", 13.5, "normal", MUTED)
    for i, c in enumerate(["Confident", "Hesitant", "Guessing"]):
        cx = 1030 + i * 172
        s.rect(cx, TOP + 408, 158, 48, fill=WHITE, stroke=APP, sw=1.5, r=10)
        s.text(cx + 79, TOP + 439, c, 15, "bold", INK, "middle")
    s.text(1030, TOP + 486, "Inferred from speed, retries and hesitation.", 14, "normal", MUTED)

    s.rect(1006, TOP + 535, 534, 115, fill=WHITE, stroke=LINE, sw=2)
    s.lines(1030, TOP + 573, [
        "Both heads share one trunk: a single",
        "network gives two answers from one",
        "inference. That is what keeps it small",
        "enough for a microcontroller.",
    ], 14.5, 24, MUTED)

    s.footnote("Feature scaling uses fixed ranges from the spec, never dataset statistics — so retraining can never desynchronise the device from the model.")
    return s, "03_features_and_labels"


# ===========================================================================
def d04_data_pipeline():
    s = Svg(title="Data pipeline")
    s.header("From learner sessions to a training set",
             "Real data first — synthetic data is fitted to it, never invented before it",
             BUILT, OK)

    s.card(60, TOP, 340, 230, "1.  Learner sessions", [
        "10–20 volunteers",
        "Short sessions, spread",
        "across several days",
        "",
        "Target: about 400 real rows",
    ], SIM)
    s.arrow(405, TOP + 115, 455, TOP + 115, color=LINE, sw=3)

    s.card(460, TOP, 340, 230, "2.  Supabase database", [
        "One flat 'attempts' table",
        "Append-only, deduplicated",
        "Live class-balance views",
        "",
        "Both laptops write to it",
    ], DATA)
    s.arrow(805, TOP + 115, 855, TOP + 115, color=LINE, sw=3)

    s.card(860, TOP, 340, 230, "3.  CSV export", [
        "Merges every source",
        "Audits the result",
        "Flags starved classes",
        "",
        "→ dataset/real.csv",
    ], DATA)

    s.card(460, TOP + 275, 740, 215, "4.  Synthetic generation — fitted to the real data", [
        "Timing distributions are measured from the real rows, then virtual learners",
        "are simulated through the SAME state machine the web app uses.",
        "",
        "Every generated row is internally consistent because it came from a simulated",
        "session — not from sampling 14 numbers independently, which would produce",
        "impossible combinations the model would waste capacity learning.",
    ], MODEL)
    s.elbow(1030, TOP + 233, 830, TOP + 273, color=MODEL, sw=2.5, via_y=TOP + 254)

    # target mix
    s.rect(60, TOP + 275, 340, 215, fill=WHITE, stroke=LINE, sw=2)
    s.text(84, TOP + 311, "TARGET MIX", 15, "bold", MUTED)
    s.rect(84, TOP + 335, 120, 54, fill=TINT[SIM], stroke=SIM, sw=2, r=8)
    s.text(144, TOP + 369, "40% real", 17, "bold", SIM, "middle")
    s.rect(216, TOP + 335, 160, 54, fill=TINT[MODEL], stroke=MODEL, sw=2, r=8)
    s.text(296, TOP + 369, "60% synthetic", 17, "bold", MODEL, "middle")
    s.lines(84, TOP + 418, [
        "Synthetic data fills the rare",
        "teaching actions that seldom",
        "occur in natural practice.",
    ], 14, 22, MUTED)

    s.rect(1230, TOP, 310, 490, fill=TINT[WARN], stroke=WARN, sw=2.5)
    s.text(1254, TOP + 36, "ORDER MATTERS", 15, "bold", WARN)
    s.lines(1254, TOP + 76, [
        "Generating synthetic data",
        "BEFORE collecting real data",
        "produces rows fitted to",
        "nothing — a distribution",
        "that exists nowhere.",
        "",
        "The generator refuses to",
        "pretend. With no real file",
        "it falls back to documented",
        "priors and says so loudly",
        "in its output.",
        "",
        "Every synthetic row is",
        "flagged, and training always",
        "reports real-only accuracy",
        "separately from combined.",
    ], 14.5, 25, INK)

    s.rect(60, TOP + 520, 1480, 130, fill=WHITE, stroke=INK, sw=2.5)
    s.text(84, TOP + 556, "FILLING THE RARE CLASSES HONESTLY", 16, "bold", INK)
    s.lines(84, TOP + 588, [
        "\"Increase difficulty\" needs high mastery and a long correct streak, so simulating more struggling learners can never produce it,",
        "however long it runs. Those classes are topped up with a strong learner drilling a small set of letters — a scenario that genuinely triggers them.",
    ], 14.5, 23, MUTED)

    s.footnote("No label is ever edited after the fact. Rare classes are produced by scenarios that legitimately cause them.")
    return s, "04_data_pipeline"


# ===========================================================================
def d05_model():
    s = Svg(title="TinyML model architecture")
    s.header("TinyML model architecture",
             f"Multi-task network — {PARAMS:,} trainable parameters", BUILT, OK)

    def dots_col(x, y, n, color, spacing=26):
        for i in range(n):
            s.circle(x, y + i * spacing, 8, fill=color, stroke=color)
        # three small dots to indicate "more units" -- drawn, never a glyph
        for i in range(3):
            s.circle(x, y + n * spacing + 10 + i * 11, 2.6, fill=color, stroke=color)

    y0 = TOP + 20
    LH = 380

    def layer(x, w, title, sub, color, nodes, params=None):
        s.rect(x, y0, w, LH, fill=TINT[color], stroke=color, sw=2.5)
        s.text(x + w / 2, y0 + 42, title, 19, "bold", INK, "middle")
        s.text(x + w / 2, y0 + 68, sub, 14, "normal", MUTED, "middle")
        dots_col(x + w / 2, y0 + 106, nodes, color)
        if params:
            s.text(x + w / 2, y0 + LH - 22, params, 14, "bold", color, "middle")

    layer(60, 215, "INPUT", "14 features", DATA, 7)
    s.arrow(280, y0 + LH / 2, 330, y0 + LH / 2, color=LINE, sw=3)
    layer(335, 215, "DENSE 32", "ReLU", MODEL, 7, "480 params")
    s.arrow(555, y0 + LH / 2, 605, y0 + LH / 2, color=LINE, sw=3)
    layer(610, 215, "DENSE 16", "ReLU", MODEL, 6, "528 params")

    # split into two heads
    mid = y0 + LH / 2
    s.path(f"M 830 {mid} L 875 {mid} L 875 {y0 + 80} L 915 {y0 + 80}", stroke=LINE, sw=3)
    s.path(f"M 830 {mid} L 875 {mid} L 875 {y0 + 290} L 915 {y0 + 290}", stroke=LINE, sw=3)

    s.rect(920, y0 + 30, 265, 100, fill=TINT[APP], stroke=APP, sw=2.5)
    s.text(1052, y0 + 66, "DENSE 3 — softmax", 16.5, "bold", INK, "middle")
    s.text(1052, y0 + 92, "confidence state", 14, "normal", MUTED, "middle")
    s.text(1052, y0 + 114, "51 params", 13.5, "bold", APP, "middle")

    s.rect(920, y0 + 240, 265, 100, fill=TINT[MODEL], stroke=MODEL, sw=2.5)
    s.text(1052, y0 + 276, "DENSE 6 — softmax", 16.5, "bold", INK, "middle")
    s.text(1052, y0 + 302, "teaching action", 14, "normal", MUTED, "middle")
    s.text(1052, y0 + 324, "102 params", 13.5, "bold", MODEL, "middle")

    # measured numbers
    s.rect(1225, y0, 315, LH, fill=WHITE, stroke=LINE, sw=2)
    s.text(1249, y0 + 38, "MEASURED", 15, "bold", MUTED)
    rows = [
        ("Trainable parameters", f"{PARAMS:,}"),
        ("Float32 model", "~4.6 KB"),
        ("After int8 quantization", f"{TFLITE_B:,} B"),
        ("Teaching accuracy", f"{TEACH_ACC*100:.1f}%"),
        ("Confidence accuracy", f"{CONF_ACC*100:.1f}%"),
        ("TFLite vs Keras match", "100%"),
        ("Inference time", "< 1 ms"),
        ("Training time", "< 30 s, CPU"),
    ]
    for i, (k, v) in enumerate(rows):
        yy = y0 + 82 + i * 38
        s.text(1249, yy, k, 14, "normal", INK)
        s.text(1516, yy, v, 14.5, "bold", MODEL, "end")
        if i < len(rows) - 1:
            s.line(1249, yy + 13, 1516, yy + 13, stroke="#EEF1F5", sw=1)

    # honesty band
    by = y0 + LH + 30
    s.rect(60, by, 1480, 145, fill=TINT[WARN], stroke=WARN, sw=2.5)
    s.text(84, by + 36, "WHAT THIS MODEL ACTUALLY DOES — state this plainly in the report", 16.5, "bold", WARN)
    s.lines(84, by + 70, [
        f"The training labels are produced by a hand-written rule engine, so the network learns to REPRODUCE that engine — measured at {TEACH_ACC*100:.1f}% agreement.",
        f"That is a real TinyML achievement: an adaptive teaching policy compressed into {PARAMS:,} parameters that run offline on a low-cost microcontroller.",
        "It is not autonomous discovery of teaching strategy and must not be described that way. The interesting evidence is where the model disagrees with the engine.",
    ], 15, 26, INK)

    s.footnote("Quantization to int8 changed zero predictions on the test set — the deployed model is exactly the validated model.")
    return s, "05_model_architecture"


# ===========================================================================
def d06_esp32_fit():
    s = Svg(title="ESP32 fit — memory, latency, offline")
    s.header("Does it fit on the ESP32?",
             "Memory, latency and offline operation — measured, not estimated", BUILT, OK)

    # memory
    s.rect(60, TOP, 940, 270, fill=WHITE, stroke=LINE, sw=2)
    s.text(84, TOP + 38, "SRAM USAGE — 520 KB available", 16, "bold", MUTED)
    bar_x, bar_y, bar_w, bar_h = 84, TOP + 66, 892, 62
    s.rect(bar_x, bar_y, bar_w, bar_h, fill="#F3F5F8", stroke=LINE, sw=2, r=8)
    model_w = bar_w * (TFLITE_B / 1024) / 520
    arena_w = bar_w * 8 / 520
    s.rect(bar_x, bar_y, model_w + arena_w, bar_h, fill=MODEL, stroke=MODEL, sw=0, r=8)
    s.text(bar_x + bar_w - 18, bar_y + 38, "free  ·  506 KB", 16, "bold", MUTED, "end")
    s.legend(84, TOP + 162, [(f"Model {TFLITE_B:,} B", MODEL), ("Tensor arena 8 KB", HW),
                             ("Free 506 KB", MUTED)])
    s.text(84, TOP + 218, "TOTAL USED", 14, "bold", MUTED)
    s.text(300, TOP + 224, "13.8 KB   =   2.7% of SRAM", 26, "bold", MODEL)

    # why offline
    s.rect(60, TOP + 300, 940, 350, fill=TINT[OK], stroke=OK, sw=2.5)
    s.text(84, TOP + 338, "WHY OFFLINE INFERENCE IS THE WHOLE POINT", 16.5, "bold", OK)
    reasons = [
        ("No internet needed", "Works in any classroom or village school, with no connectivity at all."),
        ("No recurring cost", "No server, no API bill, no subscription for the school to maintain."),
        ("Instant response", "Sub-millisecond decision — no round trip to a remote service."),
        ("Data stays local", "Learner records are written to an SD card, never uploaded."),
        ("Runs on batteries", "With the radio switched off, power is dominated by the motors."),
    ]
    for i, (t, d) in enumerate(reasons):
        y = TOP + 380 + i * 52
        s.circle(102, y - 5, 7, fill=OK, stroke=OK)
        s.text(124, y, t, 15, "bold", INK)
        s.text(330, y, d, 14.5, "normal", MUTED)

    # stat cards
    stats = [
        ("LATENCY", "< 1 ms", "per inference",
         ["Two small dense layers.", "The audio prompt takes", "about 1000x longer."], MODEL),
        ("FLASH", "~30 KB", "model + runtime",
         ["The ESP32 has 4 MB.", "Ample room for the model,", "audio index and logs."], HW),
        ("NETWORK", "NONE", "fully offline",
         ["WiFi and Bluetooth are", "switched off in firmware.", "No cloud, no data leaves."], OK),
    ]
    for i, (label, big, sub, body, color) in enumerate(stats):
        y = TOP + i * 172
        s.rect(1030, y, 510, 156, fill=TINT[color], stroke=color, sw=2.5)
        s.text(1054, y + 36, label, 14, "bold", color)
        s.text(1054, y + 86, big, 40, "bold", INK)
        s.text(1054, y + 116, sub, 14, "normal", MUTED)
        s.lines(1256, y + 58, body, 13.5, 22, INK)

    s.footnote("Golden test vectors from training are replayed on the device at boot — if the ESP32 disagrees with the desktop, it refuses to trust the model.")
    return s, "06_esp32_fit"


# ===========================================================================
def d07_deploy():
    s = Svg(title="Training to deployment")
    s.header("From CSV to a microcontroller",
             "Five automated steps — no hand-copied numbers anywhere", BUILT, OK)

    steps = [
        ("CSV dataset", ["real + synthetic", "rows, audited"], DATA, "export_dataset.py"),
        ("Keras model", [f"{PARAMS:,} parameters", "trained on CPU"], MODEL, "train.py"),
        ("TFLite int8", [f"{TFLITE_B:,} bytes", "quantized"], MODEL, "converter"),
        ("C header", ["model_data.h", "compiled in"], HW, "tflite_to_header.py"),
        ("ESP32 flash", ["runs offline", "in under 1 ms"], HW, "Arduino IDE"),
    ]
    bw, gap = 262, 30
    for i, (title, body, color, tool) in enumerate(steps):
        x = 60 + i * (bw + gap)
        s.rect(x, TOP + 20, bw, 210, fill=TINT[color], stroke=color, sw=2.5)
        s.circle(x + bw / 2, TOP + 62, 22, fill=color, stroke=color)
        s.text(x + bw / 2, TOP + 70, str(i + 1), 20, "bold", WHITE, "middle")
        s.text(x + bw / 2, TOP + 122, title, 18, "bold", INK, "middle")
        for j, ln in enumerate(body):
            s.text(x + bw / 2, TOP + 152 + j * 22, ln, 14, "normal", MUTED, "middle")
        s.text(x + bw / 2, TOP + 212, tool, 12.5, "bold", color, "middle")
        if i < len(steps) - 1:
            s.arrow(x + bw + 4, TOP + 125, x + bw + gap - 5, TOP + 125, color=LINE, sw=3)

    # safety net
    s.rect(60, TOP + 275, 740, 375, fill=TINT[OK], stroke=OK, sw=2.5)
    s.text(84, TOP + 313, "HOW WE KNOW THE DEVICE RUNS THE RIGHT MODEL", 16.5, "bold", OK)
    s.lines(84, TOP + 350, [
        "During training, 12 test cases are saved together with the answers",
        "the desktop computed for them. Those cases are compiled into the",
        "firmware itself.",
        "",
        "At every boot the ESP32 runs all 12 and compares the results.",
    ], 15.5, 27, INK)
    s.rect(84, TOP + 500, 330, 50, fill=WHITE, stroke=OK, sw=2, r=8)
    s.text(249, TOP + 531, "match  →  use the model", 15.5, "bold", OK, "middle")
    s.rect(438, TOP + 500, 338, 50, fill=WHITE, stroke=BAD, sw=2, r=8)
    s.text(607, TOP + 531, "mismatch  →  fall back to rules", 15.5, "bold", BAD, "middle")
    s.lines(84, TOP + 585, [
        "Without this check a stale or corrupted model would run silently, and every",
        "session recorded afterwards would be measuring an unknown function.",
    ], 14, 23, MUTED)

    # generated not copied
    s.rect(830, TOP + 275, 710, 375, fill=TINT[WARN], stroke=WARN, sw=2.5)
    s.text(854, TOP + 313, "ONE SOURCE OF TRUTH — NOTHING HAND-COPIED", 16.5, "bold", WARN)
    s.lines(854, TOP + 350, [
        "The teaching rules, the 14 feature definitions and the scaling",
        "ranges are written ONCE, then code-generated into three languages:",
    ], 15, 25, INK)
    for i, (lang, where) in enumerate([("JavaScript", "the web app"),
                                       ("C", "the ESP32 firmware"),
                                       ("Python", "training + synthetic data")]):
        y = TOP + 410 + i * 56
        s.rect(854, y, 250, 42, fill=WHITE, stroke=WARN, sw=1.5, r=21)
        s.text(979, y + 28, lang, 15, "bold", INK, "middle")
        s.text(1130, y + 28, "→   " + where, 15, "normal", MUTED)
    s.rect(854, TOP + 585, 660, 44, fill=WHITE, stroke=WARN, sw=2, r=8)
    s.text(1184, TOP + 613, "A test pushes 3,000 cases through all three and proves they agree",
           14.5, "bold", WARN, "middle")

    s.footnote("This removes the failure where the browser and the device compute features slightly differently — invisible until integration, expensive to find then.")
    return s, "07_training_to_deployment"


# ===========================================================================
def d08_hardware():
    s = Svg(title="Hardware architecture")
    s.header("Hardware architecture",
             "ESP32 with spoken output, 6-key Braille input and 6-motor tactile feedback",
             PLANNED, WARN)

    # MCU
    s.rect(600, TOP + 140, 400, 270, fill=TINT[HW], stroke=HW, sw=3)
    s.text(800, TOP + 190, "ESP32-WROOM-32", 23, "bold", INK, "middle")
    s.text(800, TOP + 218, "240 MHz dual core", 14.5, "normal", MUTED, "middle")
    s.text(800, TOP + 242, "520 KB SRAM  ·  4 MB flash", 14.5, "normal", MUTED, "middle")
    s.rect(650, TOP + 264, 300, 50, fill=WHITE, stroke=MODEL, sw=2, r=8)
    s.text(800, TOP + 295, f"TFLite Micro  ·  {TFLITE_B:,} B model", 14.5, "bold", MODEL, "middle")
    s.rect(650, TOP + 326, 300, 50, fill=WHITE, stroke=OK, sw=2, r=8)
    s.text(800, TOP + 357, "WiFi OFF  ·  Bluetooth OFF", 14.5, "bold", OK, "middle")

    periph = [
        (90, TOP, "DFPlayer Mini + speaker", "AUDIO OUT",
         ["Speaks the Bangla letter", "60 audio clips on microSD", "UART2  ·  GPIO 16, 17"]),
        (90, TOP + 285, "6 push buttons", "INPUT",
         ["One per Braille dot", "Perkins keyboard layout", "GPIO 32, 33, 25, 26, 27, 14"]),
        (1110, TOP, "6 coin vibration motors", "TACTILE OUT",
         ["Driven by a ULN2803A", "Built-in flyback diodes", "GPIO 13, 4, 21, 22, 2, 15"]),
        (1110, TOP + 285, "microSD card", "STORAGE",
         ["Logs every attempt as CSV", "Same columns as the web app", "SPI  ·  GPIO 18, 19, 23, 5"]),
    ]
    for x, y, title, tag, body in periph:
        s.rect(x, y, 400, 265, fill=WHITE, stroke=LINE, sw=2)
        s.text(x + 20, y + 40, title, 17.5, "bold", INK)
        s.chip(x + 20, y + 58, tag, HW, 12, 10, 24)
        s.lines(x + 20, y + 130, body, 14, 26, MUTED)

    s.arrow(495, TOP + 130, 595, TOP + 220, color=HW, sw=2.5)
    s.arrow(495, TOP + 410, 595, TOP + 330, color=HW, sw=2.5)
    s.arrow(1005, TOP + 220, 1105, TOP + 130, color=HW, sw=2.5)
    s.arrow(1005, TOP + 330, 1105, TOP + 410, color=HW, sw=2.5)

    s.rect(60, TOP + 580, 720, 165, fill=TINT[BAD], stroke=BAD, sw=2.5)
    s.text(84, TOP + 618, "POWER — the most common way this build fails", 16.5, "bold", BAD)
    s.lines(84, TOP + 652, [
        "6 motors ≈ 480 mA  +  ESP32 ≈ 80 mA  +  audio ≈ 200 mA   →   about 800 mA peak.",
        "",
        "Use a 5 V 2 A supply and a 1000 µF capacitor on the motor rail. A weak supply",
        "browns out the regulator and reboots the board — which looks exactly like a",
        "firmware crash, and is not one.",
    ], 14.5, 22, INK)

    s.rect(820, TOP + 580, 720, 165, fill=TINT[WARN], stroke=WARN, sw=2.5)
    s.text(844, TOP + 618, "USE A ULN2803A, NOT BARE TRANSISTORS", 16.5, "bold", WARN)
    s.lines(844, TOP + 652, [
        "Coin motors are inductive. Driving them from a GPIO pin, or from a transistor",
        "with no flyback path, destroys the pin.",
        "",
        "The ULN2803A packs 8 channels with the flyback diodes already inside.",
        "One chip, and tie its COM pin to +5 V.",
    ], 14.5, 22, INK)

    return s, "08_hardware_architecture"


# ===========================================================================
def d09_interaction():
    s = Svg(title="Real classroom interaction loop")
    s.header("How a student actually uses the device",
             "One practice cycle, from spoken prompt to adaptive response", PLANNED, WARN)

    boxes = [
        ("Speaker says a letter", ["The device speaks a", "Bangla letter aloud."], HW),
        ("Student feels the cell", ["Reads the raised Braille", "reference by touch."], HW),
        ("Student presses buttons", ["Enters the dot pattern", "they believe is correct."], SIM),
        ("Device scores it", ["Compares the entered", "pattern to the expected."], MODEL),
    ]
    bw = 320
    for i, (title, body, color) in enumerate(boxes):
        x = 60 + i * (bw + 28)
        s.rect(x, TOP, bw, 175, fill=TINT[color], stroke=color, sw=2.5)
        s.circle(x + 36, TOP + 44, 20, fill=color, stroke=color)
        s.text(x + 36, TOP + 51, str(i + 1), 18, "bold", WHITE, "middle")
        s.text(x + 68, TOP + 51, title, 16, "bold", INK)
        s.lines(x + 22, TOP + 96, body, 14.5, 24, MUTED)
        if i < 3:
            s.arrow(x + bw + 3, TOP + 87, x + bw + 24, TOP + 87, color=LINE, sw=3)

    # physical reference cell
    s.rect(1452, TOP, 88, 175, fill=WHITE, stroke=LINE, sw=2)
    s.text(1496, TOP + 28, "REFERENCE", 11, "bold", MUTED, "middle")
    s.braille_cell(1478, TOP + 62, [1, 3], dot_r=10, gap_x=36, gap_y=34)
    s.text(1496, TOP + 165, "raised cell", 11, "normal", MUTED, "middle")

    s.text(60, TOP + 232, "THE MODEL DECIDES WHAT HAPPENS NEXT", 18, "bold", INK)
    s.text(60, TOP + 258, "14 features go in, a teaching action comes out — in under a millisecond, with no internet connection.",
           15, "normal", MUTED)

    # correct
    s.rect(60, TOP + 285, 720, 365, fill=TINT[OK], stroke=OK, sw=2.5)
    s.text(84, TOP + 323, "IF THE ANSWER IS CORRECT", 16.5, "bold", OK)
    corr = [
        ("Audio", "সঠিক", "— \"correct\" is spoken"),
        ("Motors", None, "all six buzz briefly as a reward"),
        ("Model", None, "mastery rises, correct streak increases"),
        ("Next", None, "a harder letter, or move on to word practice"),
    ]
    for i, (k, bn, v) in enumerate(corr):
        y = TOP + 360 + i * 68
        s.rect(84, y, 122, 40, fill=WHITE, stroke=OK, sw=1.5, r=20)
        s.text(145, y + 27, k, 14, "bold", OK, "middle")
        if bn:
            s.text(226, y + 27, bn, 17, "bold", INK, font=FONT_BN)
            s.text(300, y + 27, v, 15, "normal", INK)
        else:
            s.text(226, y + 27, v, 15, "normal", INK)

    # wrong
    s.rect(820, TOP + 285, 720, 365, fill=TINT[BAD], stroke=BAD, sw=2.5)
    s.text(844, TOP + 323, "IF THE ANSWER IS WRONG", 16.5, "bold", BAD)
    wrong = [
        ("Audio", "ভুল", "— then the letter is spoken again"),
        ("Motors", None, "the CORRECT dots buzz one at a time"),
        ("Model", None, "mastery falls, wrong streak increases"),
        ("Next", None, "the model picks: repeat, hint, or go back"),
    ]
    for i, (k, bn, v) in enumerate(wrong):
        y = TOP + 360 + i * 68
        s.rect(844, y, 122, 40, fill=WHITE, stroke=BAD, sw=1.5, r=20)
        s.text(905, y + 27, k, 14, "bold", BAD, "middle")
        if bn:
            s.text(986, y + 27, bn, 17, "bold", INK, font=FONT_BN)
            s.text(1040, y + 27, v, 15, "normal", INK)
        else:
            s.text(986, y + 27, v, 15, "normal", INK)

    s.footnote("Feeling the correct pattern immediately after a mistake is the core teaching mechanism — the motors let a learner check their own answer by touch.")
    return s, "09_classroom_interaction"


# ===========================================================================
def d10_actions():
    s = Svg(title="Teaching actions and their origin")
    s.header("The six teaching actions, and where they come from",
             "Written as explicit rules first, then learned by the network", BUILT, OK)

    actions = [
        ("REPEAT", "The answer was wrong, but the learner is not stuck yet.",
         "wrong streak >= 1", BAD),
        ("HINT", "Two or more retries with no hint used — reveal the dot count.",
         "retries >= 2  and  hints = 0", WARN),
        ("NORMAL PRACTICE", "Nothing unusual is happening. Continue as normal.",
         "default case", MUTED),
        ("INCREASE DIFFICULTY", "Doing well on this letter — raise the tier.",
         "mastery >= 0.70  and  streak >= 3", OK),
        ("REVIEW PREVIOUS", "Stuck, or a partly-learned letter has gone stale.",
         "wrong streak >= 3, or stale and weak", SIM),
        ("WORD PRACTICE", "The letter is solid — start using it inside words.",
         "mastery >= 0.85  and  streak >= 5", MODEL),
    ]
    for i, (name, why, rule, color) in enumerate(actions):
        x = 60 + (i % 2) * 760
        y = TOP + (i // 2) * 148
        s.rect(x, y, 720, 128, fill=TINT[color], stroke=color, sw=2.5)
        s.text(x + 20, y + 36, name, 18, "bold", INK)
        s.text(x + 20, y + 64, why, 14.5, "normal", MUTED)
        s.rect(x + 20, y + 80, 430, 32, fill=WHITE, stroke=color, sw=1.5, r=16)
        s.text(x + 235, y + 102, rule, 13.5, "bold", color, "middle")

    y = TOP + 3 * 148
    s.rect(60, y, 1480, 152, fill=WHITE, stroke=INK, sw=2.5)
    s.text(84, y + 38, "WHERE THESE DECISIONS COME FROM", 16.5, "bold", INK)
    s.circle(100, y + 74, 13, fill=SIM, stroke=SIM)
    s.text(100, y + 79, "1", 14, "bold", WHITE, "middle")
    s.text(126, y + 79, "The rules are hand-written from teaching principles, and applied live while data is collected.", 15, "normal", INK)
    s.circle(100, y + 112, 13, fill=MODEL, stroke=MODEL)
    s.text(100, y + 117, "2", 14, "bold", WHITE, "middle")
    s.text(126, y + 117, f"The network is trained on those decisions and reproduces them at {TEACH_ACC*100:.1f}% — small enough to run on the ESP32.", 15, "normal", INK)

    s.footnote(f"The model does not invent teaching strategy. It compresses an explicit policy into {PARAMS:,} parameters so it can run offline on a microcontroller.")
    return s, "10_teaching_actions"


# ===========================================================================
def d11_mobile():
    s = Svg(title="Teacher mobile app")
    s.header("Teacher app — turning sessions into insight",
             "Every student has a profile; the teacher sees progress, not raw rows",
             PLANNED, WARN)

    # phone
    px, py, pw, ph = 90, TOP, 330, 650
    s.rect(px, py, pw, ph, fill=WHITE, stroke=INK, sw=3, r=32)
    s.rect(px + 22, py + 45, pw - 44, ph - 68, fill=WHITE, stroke=LINE, sw=1.5, r=8)
    s.circle(px + 165, py + 24, 6, fill=LINE, stroke=LINE)

    s.text(px + 44, py + 82, "রাহিম", 19, "bold", INK, font=FONT_BN)
    s.text(px + 110, py + 82, "·  Class 4", 15, "normal", MUTED)
    s.text(px + 44, py + 106, "42 sessions  ·  18 distinct days", 12.5, "normal", MUTED)

    s.rect(px + 44, py + 122, 242, 78, fill=TINT[OK], stroke=OK, sw=1.5, r=8)
    s.text(px + 60, py + 150, "MASTERY", 11.5, "bold", OK)
    s.text(px + 60, py + 182, "31 / 50 letters", 21, "bold", INK)

    s.text(px + 44, py + 232, "LEARNING CURVE", 11.5, "bold", MUTED)
    pts = [(0, 60), (1, 53), (2, 47), (3, 40), (4, 31), (5, 26), (6, 19), (7, 14)]
    path = " ".join(f"{'M' if i == 0 else 'L'} {px + 44 + p[0]*34} {py + 330 - (60-p[1])*1.25}"
                    for i, p in enumerate(pts))
    s.path(path, stroke=SIM, sw=3, marker=False)
    for p in pts:
        s.circle(px + 44 + p[0] * 34, py + 330 - (60 - p[1]) * 1.25, 4, fill=SIM, stroke=SIM)
    s.line(px + 44, py + 338, px + 286, py + 338, stroke=LINE, sw=1.5)
    s.text(px + 44, py + 358, "response time falling over 8 weeks", 11, "normal", MUTED)

    s.rect(px + 44, py + 374, 242, 68, fill=TINT[BAD], stroke=BAD, sw=1.5, r=8)
    s.text(px + 60, py + 400, "NEEDS ATTENTION", 11.5, "bold", BAD)
    s.text(px + 60, py + 428, "ঝ    ণ    ঢ", 18, "bold", INK, font=FONT_BN)
    s.text(px + 160, py + 428, "40% accuracy", 12.5, "normal", MUTED)

    s.rect(px + 44, py + 456, 242, 74, fill=TINT[MODEL], stroke=MODEL, sw=1.5, r=8)
    s.text(px + 60, py + 482, "AI SUGGESTION", 11.5, "bold", MODEL)
    s.text(px + 60, py + 506, "Revisit ঝ before", 12.5, "normal", INK, font=FONT_BN)
    s.text(px + 60, py + 524, "introducing new letters", 12.5, "normal", INK)

    s.rect(px + 44, py + 544, 242, 58, fill=WHITE, stroke=LINE, sw=1.5, r=8)
    s.text(px + 60, py + 568, "LAST PRACTISED", 11.5, "bold", MUTED)
    s.text(px + 60, py + 590, "2 days ago", 13.5, "bold", INK)

    feats = [
        ("Student profiles", ["One profile per learner, built entirely",
                              "from their own session history."], APP),
        ("Learning curve", ["Accuracy and response time over weeks —",
                            "is this child actually improving?"], SIM),
        ("Weak characters", ["Which letters are failing, ranked, so",
                             "teaching time goes where it counts."], BAD),
        ("Confidence trend", ["Confident / hesitant / guessing over time.",
                              "Catches guessing before it becomes habit."], WARN),
        ("AI suggestions", ["The model's recommended next action,",
                            "written in plain language for the teacher."], MODEL),
        ("Class overview", ["Every student at a glance — spot who has",
                            "not practised at all this week."], OK),
    ]
    for i, (t, body, color) in enumerate(feats):
        x = 470 + (i % 2) * 545
        y = TOP + (i // 3) * 0 + (i % 3) * 0
        col, row = i % 2, i // 2
        x = 470 + col * 545
        y = TOP + row * 222
        s.rect(x, y, 520, 196, fill=TINT[color], stroke=color, sw=2.5)
        s.text(x + 22, y + 42, t, 18, "bold", INK)
        s.lines(x + 22, y + 80, body, 14.5, 24, MUTED)
        s.badge(x + 498, y + 150, PLANNED, WARN)

    s.footnote("Data reaches the app either from the device's SD card or from the same database the web app already writes to — no new pipeline is needed.")
    return s, "11_teacher_mobile_app"


# ===========================================================================
def d12_status():
    s = Svg(title="Project status and roadmap")
    s.header("Where the project stands today",
             "Honest status of every stage — built, partly done, or not started")

    # (text, is_continuation) -- a continuation line is indented and gets no
    # bullet. Deciding that from the text itself proved unreliable.
    B, C, GAP = "bullet", "cont", None
    cols = [
        ("BUILT AND TESTED", OK, [
            (B, "Web simulation app"),
            (B, "Supabase database and schema"),
            (B, "Rule engine in three languages"),
            (B, "Synthetic data generator"),
            (B, "Training pipeline"),
            (B, "int8 TFLite conversion"),
            (B, "ESP32 firmware (written)"),
            (B, "Six hardware bring-up sketches"),
            (B, "Four automated test suites"),
            (B, "Braille image importer"),
        ]),
        ("PARTLY DONE", WARN, [
            (B, f"Braille map: {N_VERIFIED} of 50 letters"),
            (C, "verified from reference images"),
            (GAP, ""),
            (B, "Audio: 60 clips generated by"),
            (C, "speech synthesis — usable now,"),
            (C, "but should be re-recorded by a"),
            (C, "human speaker before any demo"),
        ]),
        ("NOT STARTED", BAD, [
            (B, "Real learner data collection"),
            (C, "— this is the critical path"),
            (GAP, ""),
            (B, "Physical hardware assembly"),
            (GAP, ""),
            (B, "Teacher mobile app"),
            (GAP, ""),
            (B, "39 consonant reference images"),
        ]),
    ]
    for i, (title, color, items) in enumerate(cols):
        x = 60 + i * 500
        s.rect(x, TOP, 460, 450, fill=TINT[color], stroke=color, sw=2.5)
        s.text(x + 22, TOP + 40, title, 16.5, "bold", color)
        for row, (kind, txt) in enumerate(items):
            if kind is GAP:
                continue
            prefix, indent = ("•  ", 0) if kind == B else ("", 20)
            s.text(x + 22 + indent, TOP + 82 + row * 32, prefix + txt, 14.5, "normal", INK)

    s.rect(60, TOP + 480, 1480, 170, fill=WHITE, stroke=INK, sw=2.5)
    s.text(84, TOP + 518, "THE CRITICAL PATH", 17, "bold", INK)
    s.lines(84, TOP + 554, [
        "Data collection needs CALENDAR TIME, not effort. Each learner must practise on different days, or two of the",
        "14 features — session number and time since last practice — carry no signal whatsoever.",
        "",
        "Everything else (hardware, the mobile app, the remaining reference images) can proceed in parallel. Start collecting first.",
    ], 15.5, 27, INK)

    return s, "12_status_and_roadmap"


# ===========================================================================
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    builders = [d01_overview, d02_simulation, d03_features, d04_data_pipeline,
                d05_model, d06_esp32_fit, d07_deploy, d08_hardware,
                d09_interaction, d10_actions, d11_mobile, d12_status]

    made = []
    for b in builders:
        svg, name = b()
        svg.save(OUT / f"{name}.svg")
        made.append(name)

    try:
        import cairosvg
        for name in made:
            cairosvg.svg2png(url=str(OUT / f"{name}.svg"),
                             write_to=str(OUT / f"{name}.png"),
                             output_width=2400, output_height=1350,
                             background_color="white")
        extra = "  + PNG at 2400x1350"
    except ImportError:
        extra = "  (cairosvg not installed -- SVG only)"

    print(f"wrote {len(made)} diagram(s) to {OUT.relative_to(ROOT)}/{extra}")
    for name in made:
        print(f"  {name}")
    print("\nAll on a pure white background.")
    print("SVG is fully editable: in PowerPoint use Insert > Picture, then")
    print("right-click > Convert to Shape to edit every box and label.")


if __name__ == "__main__":
    main()
