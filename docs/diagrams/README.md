# Presentation diagrams

12 architecture diagrams covering the project end to end, plus a slide deck
built from them.

**Everything here is on a pure white background** (`#FFFFFF`), with no
transparency and no gradients, so it drops straight into slides, a poster, or a
printed report without a coloured box appearing around it.

| File | Use it for |
|---|---|
| `NN_name.svg` | **Editing.** Vector — infinitely scalable, every element editable |
| `NN_name.png` | Dropping into Word, a poster, or anything that cannot take vector |
| `../BraillePresentation.pptx` | The finished 15-slide deck |

---

## Editing a diagram in PowerPoint

The deck already contains the SVG behind every diagram, so you do not need
these files to edit it:

1. Right-click any diagram in the deck
2. **Convert to Shape** (PowerPoint 2016 or newer)
3. Every box, arrow and label is now a native PowerPoint object — recolour it,
   retype it, move it, delete it

If PowerPoint asks whether to convert to a Microsoft Office drawing, say yes.

To place a diagram in a *different* deck: **Insert → Pictures**, choose the
`.svg`, then Convert to Shape as above.

The title slide, the limitations slide and the next-steps slide are built from
native PowerPoint shapes already — edit those directly, no conversion needed.
Every slide also carries **speaker notes** with the spoken version of the point.

---

## The figures

| # | File | Covers |
|---|---|---|
| 01 | `01_system_overview` | All five stages and what flows between them |
| 02 | `02_phase1_simulation` | The data-collection loop; why simulate before building |
| 03 | `03_features_and_labels` | The 14 inputs, the 6+3 outputs, the timing contract |
| 04 | `04_data_pipeline` | Sessions → database → CSV → synthetic; the 40/60 mix |
| 05 | `05_model_architecture` | Layer sizes, per-layer parameters, measured results |
| 06 | `06_esp32_fit` | Memory bar, latency, flash, why offline is the point |
| 07 | `07_training_to_deployment` | Five steps, the golden-vector check, one source of truth |
| 08 | `08_hardware_architecture` | ESP32 plus four peripherals, pin map, power warnings |
| 09 | `09_classroom_interaction` | Speaker → buttons → the correct and wrong branches |
| 10 | `10_teaching_actions` | All six actions, the rule that fires each, their origin |
| 11 | `11_teacher_mobile_app` | Phone mockup and six capability cards |
| 12 | `12_status_and_roadmap` | Built / partly done / not started, and the critical path |

---

## Regenerating

Every number on these diagrams is read live from `models/metrics.json` and
`data/braille_map.json`. Retrain the model or verify more Braille characters,
re-run these two commands, and the figures update themselves — a slide cannot
drift away from what the repository actually contains.

```bash
python3 tools/gen_diagrams.py        # 12 SVG + 12 PNG
node    tools/build_deck.js          # the .pptx, with PNG images
python3 tools/embed_svg_in_pptx.py   # attaches the SVGs -> makes them editable
python3 tools/test_deck.py           # QA
```

`embed_svg_in_pptx.py` is not optional. Without it the deck contains flat
pictures and **Convert to Shape does nothing** — pptxgenjs cannot write the
dual PNG+SVG picture that PowerPoint needs.

---

## Two rules if you edit `tools/gen_diagrams.py`

Both of these fail *silently as empty boxes* in the exported PNG, so they are
easy to reintroduce and easy to miss.

**1. Bangla text needs a Bengali font.** Arial has no Bengali glyphs at all.
Always pass `font=FONT_BN`:

```python
s.text(x, y, "সঠিক", 17, "bold", INK, font=FONT_BN)   # correct
s.text(x, y, "সঠিক", 17, "bold", INK)                  # renders as ▯▯▯▯
```

**2. No emoji.** The rasteriser has no emoji font. Use a drawn shape, or a
digit in a coloured circle, as the existing diagrams do.

The same applies to typographic characters outside Latin-1 — `⋮` rendered as a
box until it was replaced with three drawn circles.

---

## Style

- Canvas 1600 × 900 (16:9), content in a fixed 150–800 vertical band so no
  figure has an empty bottom third
- One colour per pipeline stage, so a reader can follow one stage across
  figures by colour alone: blue = simulation, violet = data, teal = model,
  orange = hardware, rose = app
- `BUILT` and `PLANNED` badges are deliberate. Three stages do not exist yet,
  and showing them identically to the finished ones would misrepresent the
  project to anyone reading the deck.
