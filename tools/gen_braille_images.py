#!/usr/bin/env python3
"""Render all 50 Bangla letters as Braille cell images from data/braille_map.json.

Produces assets/braille/<id>_<name>.svg and .png, plus a contact-sheet PNG.

These are GENERATED, not scraped. That matters: they are guaranteed consistent
with the dot data the web app and the firmware actually use, so a corrected
Braille chart updates the reference images automatically instead of leaving
stale pictures that disagree with the code.

    python3 tools/gen_braille_images.py
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "data" / "braille_map.json"
OUT_DIR = ROOT / "assets" / "braille"

# Cell geometry. Dots are numbered column-major:  1 4
#                                                 2 5
#                                                 3 6
CELL_W, CELL_H = 160, 240
MARGIN_X, MARGIN_Y = 40, 40
DOT_R = 22
COL_GAP = CELL_W - 2 * MARGIN_X
ROW_GAP = (CELL_H - 2 * MARGIN_Y) // 2

RAISED_FILL = "#1a1a1a"
FLAT_FILL = "#ffffff"
FLAT_STROKE = "#c8c8c8"
BG = "#ffffff"

DOT_POS = {
    1: (MARGIN_X, MARGIN_Y),
    2: (MARGIN_X, MARGIN_Y + ROW_GAP),
    3: (MARGIN_X, MARGIN_Y + 2 * ROW_GAP),
    4: (MARGIN_X + COL_GAP, MARGIN_Y),
    5: (MARGIN_X + COL_GAP, MARGIN_Y + ROW_GAP),
    6: (MARGIN_X + COL_GAP, MARGIN_Y + 2 * ROW_GAP),
}


def make_svg(letter):
    raised = set(letter["dots"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CELL_W}" height="{CELL_H}" '
        f'viewBox="0 0 {CELL_W} {CELL_H}" role="img" '
        f'aria-label="Bangla {letter["char"]} ({letter["name"]}), Braille dots '
        f'{"-".join(str(d) for d in letter["dots"])}">',
        f'<rect width="{CELL_W}" height="{CELL_H}" fill="{BG}"/>',
    ]
    for dot in range(1, 7):
        cx, cy = DOT_POS[dot]
        if dot in raised:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{DOT_R}" fill="{RAISED_FILL}"/>')
        else:
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{DOT_R}" fill="{FLAT_FILL}" '
                f'stroke="{FLAT_STROKE}" stroke-width="2" stroke-dasharray="4 4"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def draw_cell(draw, ox, oy, dots, scale=1.0):
    raised = set(dots)
    r = DOT_R * scale
    for dot in range(1, 7):
        cx, cy = DOT_POS[dot]
        cx, cy = ox + cx * scale, oy + cy * scale
        box = [cx - r, cy - r, cx + r, cy + r]
        if dot in raised:
            draw.ellipse(box, fill=RAISED_FILL)
        else:
            draw.ellipse(box, fill=FLAT_FILL, outline=FLAT_STROKE, width=max(1, int(2 * scale)))


def make_png(letter):
    img = Image.new("RGB", (CELL_W, CELL_H), BG)
    draw_cell(ImageDraw.Draw(img), 0, 0, letter["dots"])
    return img


def make_contact_sheet(letters, cols=10):
    """One PNG with all 50 cells -- print it and check against your chart."""
    scale = 0.5
    cw, ch = int(CELL_W * scale), int(CELL_H * scale) + 18
    rows = (len(letters) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), BG)
    draw = ImageDraw.Draw(sheet)
    for i, letter in enumerate(letters):
        ox, oy = (i % cols) * cw, (i // cols) * ch
        draw_cell(draw, ox, oy, letter["dots"], scale)
        label = f"{letter['id']} {letter['name']}"
        draw.text((ox + 4, oy + int(CELL_H * scale) + 2), label, fill="#444444")
    return sheet


def main():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    letters = data["letters"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for letter in letters:
        stem = f"{letter['id']:02d}_{letter['name']}"
        (OUT_DIR / f"{stem}.svg").write_text(make_svg(letter), encoding="utf-8")
        make_png(letter).save(OUT_DIR / f"{stem}.png")

    make_contact_sheet(letters).save(OUT_DIR / "_contact_sheet.png")

    # index.json lets anything enumerate the assets without re-parsing the map
    index = [
        {
            "id": l["id"], "char": l["char"], "name": l["name"], "dots": l["dots"],
            "svg": f"{l['id']:02d}_{l['name']}.svg", "png": f"{l['id']:02d}_{l['name']}.png",
        }
        for l in letters
    ]
    (OUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    print(f"wrote {len(letters)} SVG + {len(letters)} PNG to assets/braille/")
    print("wrote assets/braille/_contact_sheet.png  <- print this to check against your chart")
    if not data["verified"]:
        print("\n  !! rendered from the UNVERIFIED placeholder mapping")


if __name__ == "__main__":
    main()
