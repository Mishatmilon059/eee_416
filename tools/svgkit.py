"""Minimal SVG builder for the presentation diagrams.

Everything is drawn on a PURE WHITE background (#FFFFFF) with no gradients and
no transparency, so the diagrams drop straight into slides, posters, or a
printed report without a coloured box appearing around them.

SVG rather than PNG because SVG stays editable: PowerPoint can insert an SVG and
"Convert to Shape", after which every box and arrow is a native object you can
recolour, move, or retype. Rasterised PNGs are exported alongside for tools that
cannot take vector input.
"""

W, H = 1600, 900          # 16:9, matches slide aspect

# Palette -- one hue per pipeline stage, so a reader can follow a stage across
# diagrams by colour alone.
INK = "#111827"           # near-black body text
MUTED = "#6B7280"         # captions, secondary labels
LINE = "#CBD5E1"          # connectors, borders
WHITE = "#FFFFFF"

SIM = "#2563EB"           # blue    -- simulation / web app
DATA = "#7C3AED"          # violet  -- data + database
MODEL = "#0D9488"         # teal    -- AI / TinyML
HW = "#EA580C"            # orange  -- ESP32 / hardware
APP = "#DB2777"           # rose    -- mobile app
OK = "#059669"            # green   -- built / correct
WARN = "#D97706"          # amber   -- planned / caution
BAD = "#DC2626"           # red     -- wrong / error

# 12% tints, precomputed as solid hex -- no alpha anywhere, so the白 background
# survives every export path.
TINT = {
    SIM: "#EFF4FE", DATA: "#F5F0FE", MODEL: "#EDFAF8",
    HW: "#FEF3EC", APP: "#FDF0F6", OK: "#ECFAF4",
    WARN: "#FEF6EC", BAD: "#FEF0F0", MUTED: "#F6F7F9",
}

FONT = "Arial, Helvetica, sans-serif"
FONT_BN = "'Noto Sans Bengali', 'Lohit Bengali', Arial, sans-serif"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class Svg:
    def __init__(self, w=W, h=H, title=""):
        self.w, self.h = w, h
        self.parts = []
        self.title = title

    # --- primitives -------------------------------------------------------
    def rect(self, x, y, w, h, fill=WHITE, stroke=LINE, sw=2, r=12, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
        return self

    def text(self, x, y, s, size=18, weight="normal", fill=INK, anchor="start",
             font=FONT, italic=False):
        st = ' font-style="italic"' if italic else ""
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{st}>'
            f'{esc(s)}</text>')
        return self

    def lines(self, x, y, rows, size=15, lh=21, fill=MUTED, anchor="start", weight="normal"):
        for i, r in enumerate(rows):
            self.text(x, y + i * lh, r, size, weight, fill, anchor)
        return self

    def line(self, x1, y1, x2, y2, stroke=LINE, sw=2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round"{d}/>')
        return self

    def circle(self, cx, cy, r, fill=WHITE, stroke=LINE, sw=2):
        self.parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}"/>')
        return self

    def path(self, d, stroke=LINE, sw=2, fill="none", dash=None, marker=True):
        m = ' marker-end="url(#arrow)"' if marker else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round"{da}{m}/>')
        return self

    # --- composites -------------------------------------------------------
    def card(self, x, y, w, h, title, body=None, color=SIM, badge=None, icon=None,
             title_size=19, fill=None):
        """A titled box. The 4px colour band at the top is the only decoration."""
        self.rect(x, y, w, h, fill=fill or TINT.get(color, WHITE), stroke=color, sw=2)
        ty = y + 30
        if icon:
            self.circle(x + 26, ty - 6, 13, fill=color, stroke=color)
            self.text(x + 26, ty - 1, icon, 13, "bold", WHITE, "middle")
            self.text(x + 48, ty, title, title_size, "bold", INK)
        else:
            self.text(x + 16, ty, title, title_size, "bold", INK)
        if badge:
            self.badge(x + w - 14, y + 14, badge)
        if body:
            self.lines(x + 16, ty + 26, body, 14, 20, MUTED)
        return self

    def badge(self, right_x, y, text, color=None):
        """Small status pill, right-aligned to right_x."""
        color = color or (OK if text.lower().startswith("built") else WARN)
        w = 10 + len(text) * 7.2
        self.rect(right_x - w, y, w, 22, fill=TINT.get(color, WHITE), stroke=color, sw=1.5, r=11)
        self.text(right_x - w / 2, y + 15.5, text, 11.5, "bold", color, "middle")
        return self

    def arrow(self, x1, y1, x2, y2, color=LINE, sw=2.5, label=None,
              label_size=13, dash=None, label_dy=-9):
        self.path(f"M {x1} {y1} L {x2} {y2}", stroke=color, sw=sw, dash=dash)
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.text(mx, my + label_dy, label, label_size, "bold", color, "middle")
        return self

    def elbow(self, x1, y1, x2, y2, color=LINE, sw=2.5, label=None, via_y=None):
        """Right-angled connector: down/up, across, then into the target."""
        vy = via_y if via_y is not None else (y1 + y2) / 2
        self.path(f"M {x1} {y1} L {x1} {vy} L {x2} {vy} L {x2} {y2}", stroke=color, sw=sw)
        if label:
            self.text((x1 + x2) / 2, vy - 9, label, 13, "bold", color, "middle")
        return self

    def chip(self, x, y, text, color=MUTED, size=13, pad=11, h=26):
        w = pad * 2 + len(text) * (size * 0.56)
        self.rect(x, y, w, h, fill=TINT.get(color, WHITE), stroke=color, sw=1.5, r=h / 2)
        self.text(x + w / 2, y + h * 0.68, text, size, "bold", color, "middle")
        return w

    def header(self, title, subtitle=None, tag=None, tag_color=MUTED):
        self.text(60, 66, title, 34, "bold", INK)
        if subtitle:
            self.text(60, 96, subtitle, 16.5, "normal", MUTED)
        if tag:
            self.chip(self.w - 60 - (22 + len(tag) * 7.6), 44, tag, tag_color, 13)
        return self

    def footnote(self, text, y=None):
        self.text(60, y or self.h - 34, text, 13, "normal", MUTED, italic=True)
        return self

    def legend(self, x, y, items, size=13):
        """items: [(label, color), ...] laid out horizontally."""
        cx = x
        for label, color in items:
            self.circle(cx + 7, y, 7, fill=color, stroke=color)
            self.text(cx + 20, y + 4.5, label, size, "normal", MUTED)
            cx += 26 + len(label) * (size * 0.55)
        return self

    def braille_cell(self, x, y, dots, dot_r=13, gap_x=38, gap_y=38,
                     on=INK, off=WHITE, stroke=LINE, labels=False):
        """A 2x3 Braille cell. dots is a list from 1..6; column-major layout."""
        pos = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}
        for d in range(1, 7):
            c, r = pos[d]
            cx, cy = x + c * gap_x, y + r * gap_y
            filled = d in dots
            self.circle(cx, cy, dot_r, fill=on if filled else off,
                        stroke=on if filled else stroke, sw=2)
            if labels and not filled:
                self.text(cx, cy + 4, str(d), 11, "normal", LINE, "middle")
        return self

    # --- output -----------------------------------------------------------
    def render(self):
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'<title>{esc(self.title)}</title>\n'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>\n'
            f'<rect width="{self.w}" height="{self.h}" fill="{WHITE}"/>\n'
            + "\n".join(self.parts) + "\n</svg>\n")

    def save(self, path):
        from pathlib import Path
        Path(path).write_text(self.render(), encoding="utf-8")
        return path
