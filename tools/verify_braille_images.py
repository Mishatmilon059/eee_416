#!/usr/bin/env python3
"""Build a side-by-side QA sheet: your source image vs what the importer read.

    python3 tools/verify_braille_images.py

Writes assets/braille/_verification_sheet.png -- for every letter that has a
source image, three things in a row:

    [ your image ]  [ what the map now says ]  dots + status

Look at it. The importer reporting "confirmed" only means its own reading
matched its own stored value; this sheet is what lets you check the reading
against the picture with your own eyes. Machine agreement is not verification.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from braille_image_reader import confidence_margin, extract_dots, load_flat  # noqa: E402

MAP_PATH = ROOT / "data" / "braille_map.json"
OUT = ROOT / "assets" / "braille" / "_verification_sheet.png"

CELL_W, CELL_H = 120, 168
PAD = 16
LABEL_H = 46
ROW_H = CELL_H + LABEL_H + PAD
DOT_R = 20

DOT_POS = {
    1: (34, 30), 2: (34, 84), 3: (34, 138),
    4: (86, 30), 5: (86, 84), 6: (86, 138),
}


# Bengali glyphs need a font that actually covers the script; PIL's built-in
# bitmap font does not, and would draw every Bangla character as a tofu box.
# If no such font is installed we drop the Bangla character rather than print
# a row of boxes -- the roman name and id still identify the letter.
BENGALI_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf",
    "/usr/share/fonts/truetype/fonts-beng-extra/MuktiNarrow.ttf",
    "/Library/Fonts/Bangla MN.ttc",                        # macOS
    "C:/Windows/Fonts/Nirmala.ttf",                        # Windows
]


def load_bengali_font(size=17):
    for path in BENGALI_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def render_cell(dots):
    """Draw the cell the way the app and firmware understand it."""
    img = Image.new("RGB", (CELL_W, CELL_H), "white")
    d = ImageDraw.Draw(img)
    raised = set(dots)
    for dot in range(1, 7):
        cx, cy = DOT_POS[dot]
        box = [cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R]
        if dot in raised:
            d.ellipse(box, fill="#111111")
        else:
            d.ellipse(box, fill="white", outline="#bbbbbb", width=2)
    return img


def main():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    letters = [l for l in data["letters"] if l.get("source")]
    if not letters:
        sys.exit("no letters have a 'source' image yet -- "
                 "run tools/import_braille_images.py --write first")

    cols = 3
    rows = (len(letters) + cols - 1) // cols
    col_w = CELL_W * 2 + PAD * 3
    W = cols * col_w + PAD
    H = rows * ROW_H + PAD + 40
    sheet = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sheet)

    n_ver = sum(1 for l in data["letters"] if l.get("verified"))
    draw.text((PAD, 12),
              f"Braille verification -- left: your source image, right: what the map now holds"
              f"    ({n_ver}/{len(data['letters'])} letters verified)",
              fill="black")

    bn_font = load_bengali_font()
    if bn_font is None:
        print("note: no Bengali font found -- labels show roman names only")

    mismatches = []
    for i, letter in enumerate(letters):
        src_path = ROOT / letter["source"]
        ox = PAD + (i % cols) * col_w
        oy = 40 + PAD + (i // cols) * ROW_H

        # left: the source image, flattened onto white
        if src_path.exists():
            src = load_flat(src_path).convert("RGB").resize((CELL_W, CELL_H), Image.LANCZOS)
            re_read = extract_dots(src_path)
        else:
            src = Image.new("RGB", (CELL_W, CELL_H), "#f4f4f4")
            ImageDraw.Draw(src).text((10, CELL_H // 2), "missing", fill="#999999")
            re_read = None
        sheet.paste(src, (ox, oy))
        draw.rectangle([ox - 1, oy - 1, ox + CELL_W, oy + CELL_H], outline="#dddddd")

        # right: the cell rendered from the map
        rx = ox + CELL_W + PAD
        sheet.paste(render_cell(letter["dots"]), (rx, oy))
        draw.rectangle([rx - 1, oy - 1, rx + CELL_W, oy + CELL_H], outline="#dddddd")

        # a live re-read that disagrees with the stored value means the map and
        # the image have drifted apart -- the whole point of this sheet
        agree = (re_read == letter["dots"]) if re_read is not None else False
        if not agree:
            mismatches.append(letter["name"])
            draw.rectangle([ox - 3, oy - 3, rx + CELL_W + 2, oy + CELL_H + 2],
                           outline="#cc2222", width=3)

        dots_txt = "-".join(str(d) for d in letter["dots"])
        status = "match" if agree else "MISMATCH"
        if bn_font:
            draw.text((ox, oy + CELL_H + 4), letter["char"], fill="black", font=bn_font)
            draw.text((ox + 26, oy + CELL_H + 8),
                      f"{letter['name']}  (id {letter['id']})", fill="black")
        else:
            draw.text((ox, oy + CELL_H + 8),
                      f"{letter['name']}  (id {letter['id']})", fill="black")
        draw.text((ox, oy + CELL_H + 24),
                  f"dots {dots_txt}   {Path(letter['source']).name}   [{status}]",
                  fill="#cc2222" if not agree else "#555555")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)

    print(f"wrote {OUT.relative_to(ROOT)}  ({len(letters)} letters with images)")
    print(f"verified {n_ver}/{len(data['letters'])} letters")
    if mismatches:
        print(f"\nFAIL  {len(mismatches)} letter(s) re-read differently than stored: "
              f"{', '.join(mismatches)}")
        print("      The map and the source images disagree. Re-run the importer.")
        return 1
    print("\nevery stored pattern re-reads identically from its source image")
    print("Now OPEN the sheet and check the pictures yourself -- the importer")
    print("agreeing with itself is not the same as it being right.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
