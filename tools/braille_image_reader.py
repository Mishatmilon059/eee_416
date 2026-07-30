"""Read Braille dot patterns out of cell images.

Shared by tools/import_braille_images.py and tools/verify_braille_images.py.

The method, validated against all 11 supplied vowel images and against manual
reading of every one of them:

  1. composite RGBA onto white  (the source images have alpha)
  2. grayscale, threshold to find ink -- this catches BOTH a filled disc and
     the outline of a hollow circle
  3. find the 3 row bands and 2 column bands by projection profile, and take
     each band's centre
  4. sample a small disc at each of the 6 intersections

Step 4 is the whole trick. A raised dot is a solid disc, so its centre is dark.
An unraised dot is drawn as a hollow ring, so its centre is white even though
its outline is ink. Sampling the centre distinguishes them; measuring ink
coverage over the whole slot would not.

Step 3 matters more than it looks. Splitting the bounding box into uniform
sixths seems equivalent and is not: the circles are not laid out at exact
sixths of the ink bounds, so the derived centres drift by close to a dot radius
and land half-on-half-off the disc. That still produced correct answers on
these images, but with a margin of ~7 grey levels instead of ~120 -- correct by
luck, and one slightly different image away from being wrong. Detecting the
actual bands restores the full margin.

Dot numbering is column-major, the international standard:

      1  4
      2  5
      3  6
"""
from pathlib import Path

import numpy as np
from PIL import Image

INK_THRESHOLD = 128      # 0-255; below this counts as ink
FILL_THRESHOLD = 128     # mean centre brightness below this = filled
SAMPLE_RADIUS = 0.32     # fraction of the smaller slot dimension

SUPPORTED_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".bmp", ".gif")


class BrailleImageError(Exception):
    pass


def _band_centres(occupied, expected, lo, hi, fallback_span):
    """Locate `expected` bands of ink along one axis; return their centres.

    `occupied` is a 1-D boolean: does this row (or column) contain any ink?
    A Braille cell produces 3 bands vertically and 2 horizontally, separated by
    blank gaps. Taking each band's midpoint puts the sample squarely on the dot
    rather than near its edge.

    Falls back to an even split of [lo, hi] if the band count is not what we
    expect -- which happens when adjacent circles touch, or an image is noisy.
    The caller still gets an answer, just with the old, weaker centring.
    """
    bands, start = [], None
    for i, on in enumerate(occupied):
        if on and start is None:
            start = i
        elif not on and start is not None:
            bands.append((start, i - 1))
            start = None
    if start is not None:
        bands.append((start, len(occupied) - 1))

    if len(bands) != expected:
        span = (hi - lo + 1) / expected
        return [lo + span * (i + 0.5) for i in range(expected)], fallback_span

    centres = [(a + b) / 2.0 for a, b in bands]
    span = min(b - a + 1 for a, b in bands)
    return centres, span


def load_flat(path):
    """Open any supported image and flatten transparency onto white."""
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("L")


def extract_dots(path, return_detail=False):
    """Return the sorted list of raised dot numbers, e.g. [1, 3, 6].

    Raises BrailleImageError when the image contains no ink at all, which
    means the file is blank or the threshold is wrong -- either way, guessing
    an answer there would silently corrupt the Braille map.
    """
    gray = load_flat(path)
    g = np.asarray(gray, dtype=float)

    ink = g < INK_THRESHOLD
    ys, xs = np.where(ink)
    if len(ys) == 0:
        raise BrailleImageError(f"{Path(path).name}: no ink found -- blank image?")

    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    height, width = y1 - y0 + 1, x1 - x0 + 1

    # A single Braille cell is 2 columns x 3 rows, so it is taller than wide.
    # A wildly different aspect ratio means the image is not one cell (a whole
    # chart, a cropped half, two cells side by side) and the grid split below
    # would silently produce a plausible-looking but wrong pattern.
    aspect = height / width if width else 0
    if not (0.9 <= aspect <= 2.6):
        raise BrailleImageError(
            f"{Path(path).name}: ink bounding box is {width}x{height} "
            f"(aspect {aspect:.2f}); a single 2x3 Braille cell should be roughly "
            "1.0-2.6. Is this one cell, or a whole chart?")

    row_centres, row_span = _band_centres(ink.any(axis=1), 3, y0, y1, height / 3.0)
    col_centres, col_span = _band_centres(ink.any(axis=0), 2, x0, x1, width / 2.0)

    yy, xx = np.ogrid[:g.shape[0], :g.shape[1]]
    radius = min(row_span, col_span) * SAMPLE_RADIUS

    dots, detail = [], []
    for row in range(3):
        for col in range(2):
            cy = row_centres[row]
            cx = col_centres[col]
            mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius ** 2
            mean = float(g[mask].mean()) if mask.any() else 255.0
            filled = mean < FILL_THRESHOLD
            dot = col * 3 + row + 1          # column-major: 1,2,3 | 4,5,6
            if filled:
                dots.append(dot)
            detail.append({"dot": dot, "mean": round(mean, 1), "filled": filled,
                           "cx": round(cx, 1), "cy": round(cy, 1)})

    dots.sort()
    detail.sort(key=lambda d: d["dot"])
    if return_detail:
        return dots, detail
    return dots


def confidence_margin(detail):
    """How far the nearest slot sat from the fill threshold, in grey levels.

    A small margin means some dot was ambiguous -- a faint disc, an anti-aliased
    edge, a bad threshold. Worth surfacing rather than reporting a crisp answer
    that happened to be a coin flip.
    """
    return min(abs(d["mean"] - FILL_THRESHOLD) for d in detail)


def find_images(folder):
    """All supported images in a folder, sorted by name."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith("_"))
