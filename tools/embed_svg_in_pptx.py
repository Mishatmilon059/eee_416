#!/usr/bin/env python3
"""Attach the SVG source to every diagram image in the deck, so PowerPoint can
convert the pictures back into editable shapes.

    python3 tools/embed_svg_in_pptx.py

Why this step exists
--------------------
pptxgenjs can only insert a raster image. A PNG in a slide is a flat picture:
you can move and scale it, but you cannot recolour a box or retype a label.

PowerPoint's own answer is a dual-encoded picture: the PNG stays as the visible
fallback, and the original SVG rides along inside an extension element. Any
PowerPoint from 2016 onwards then offers right-click > "Convert to Shape",
which rebuilds every rectangle, arrow and text run as a native object.

This script writes exactly that structure:

    <a:blip r:embed="PNG">
      <a:extLst>
        <a:ext uri="{96DAC541-...}">
          <asvg:svgBlip r:embed="SVG"/>
        </a:ext>
      </a:extLst>
    </a:blip>

The magic uri is Microsoft's registered identifier for the SVG extension; older
readers that do not know it simply ignore the block and display the PNG. So the
deck stays openable everywhere and becomes editable where it can be.

The XML is edited as text on purpose. Round-tripping OOXML through a generic
XML library rewrites namespace prefixes and corrupts the package -- and the
change needed here is a single, well-anchored insertion.
"""
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PPTX = ROOT / "docs" / "BraillePresentation.pptx"
DIA = ROOT / "docs" / "diagrams"
WORK = ROOT / ".pptx_work"

SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Slide order in build_deck.js: slide1 = title, slides 2..13 = the 12 diagrams.
DIAGRAMS = [
    "01_system_overview", "02_phase1_simulation", "03_features_and_labels",
    "04_data_pipeline", "05_model_architecture", "06_esp32_fit",
    "07_training_to_deployment", "08_hardware_architecture",
    "09_classroom_interaction", "10_teaching_actions",
    "11_teacher_mobile_app", "12_status_and_roadmap",
]
FIRST_DIAGRAM_SLIDE = 2


def next_rel_id(rels_xml):
    used = {int(n) for n in re.findall(r'Id="rId(\d+)"', rels_xml)}
    i = 1
    while i in used:
        i += 1
    return f"rId{i}"


def main():
    if not PPTX.exists():
        sys.exit(f"{PPTX.relative_to(ROOT)} not found -- run node tools/build_deck.js first")

    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    with zipfile.ZipFile(PPTX) as z:
        z.extractall(WORK)

    media = WORK / "ppt" / "media"
    media.mkdir(parents=True, exist_ok=True)

    patched, skipped = 0, []
    for idx, name in enumerate(DIAGRAMS):
        slide_no = FIRST_DIAGRAM_SLIDE + idx
        slide = WORK / "ppt" / "slides" / f"slide{slide_no}.xml"
        rels = WORK / "ppt" / "slides" / "_rels" / f"slide{slide_no}.xml.rels"
        svg_src = DIA / f"{name}.svg"

        if not (slide.exists() and rels.exists() and svg_src.exists()):
            skipped.append(f"slide{slide_no} ({name}): missing file")
            continue

        slide_xml = slide.read_text(encoding="utf-8")
        rels_xml = rels.read_text(encoding="utf-8")

        # locate the picture's existing PNG relationship
        m = re.search(r'<a:blip r:embed="(rId\d+)">', slide_xml)
        if not m:
            skipped.append(f"slide{slide_no} ({name}): no <a:blip> found")
            continue
        png_rid = m.group(1)

        if SVG_EXT_URI in slide_xml:
            skipped.append(f"slide{slide_no} ({name}): already has an svgBlip")
            continue

        # copy the SVG in beside the PNG and register it
        svg_name = f"{name}.svg"
        shutil.copy(svg_src, media / svg_name)
        svg_rid = next_rel_id(rels_xml)
        rels_xml = rels_xml.replace(
            "</Relationships>",
            f'<Relationship Id="{svg_rid}" Type="{REL_NS}/image" '
            f'Target="../media/{svg_name}"/></Relationships>')
        rels.write_text(rels_xml, encoding="utf-8")

        # attach the SVG to the existing blip, keeping the PNG as fallback
        ext = (f'<a:extLst><a:ext uri="{SVG_EXT_URI}">'
               f'<asvg:svgBlip xmlns:asvg="{SVG_NS}" r:embed="{svg_rid}"/>'
               f'</a:ext></a:extLst>')
        slide_xml = slide_xml.replace(
            f'<a:blip r:embed="{png_rid}"></a:blip>',
            f'<a:blip r:embed="{png_rid}">{ext}</a:blip>', 1)
        slide.write_text(slide_xml, encoding="utf-8")
        patched += 1

    # repack -- zip from inside the directory, and never append to an old archive
    out = PPTX
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(WORK.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(WORK).as_posix())
    shutil.rmtree(WORK)

    print(f"attached SVG to {patched}/{len(DIAGRAMS)} diagram slides")
    for s in skipped:
        print(f"  skipped: {s}")
    print(f"\n{out.relative_to(ROOT)}  ({out.stat().st_size / 1024:.0f} KB)")
    print("\nIn PowerPoint: right-click a diagram > Convert to Shape,")
    print("and every box, arrow and label becomes editable.")
    return 0 if patched == len(DIAGRAMS) else 1


if __name__ == "__main__":
    sys.exit(main())
