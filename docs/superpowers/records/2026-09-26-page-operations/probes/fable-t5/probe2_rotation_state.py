"""Probe 2: rotation state on the exported bytes after a redaction."""
import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz
from engine.export import export
from engine.operations import redact_region
from engine.parser import parse
from tests.geometry_helpers import build_page
from tests.test_page_geometry import _inherited_rotation_page

CROP = "[40 60 580 740]"


def block(doc):
    return next(b for b in doc.pages[0].text_blocks if "LOW-MARKER" in b.text)


def state(doc, page):
    parent = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
    return dict(
        eff=page.rotation,
        page_key=doc.xref_get_key(page.xref, "Rotate"),
        parent_key=doc.xref_get_key(parent, "Rotate"),
    )


def redact_and_export(data):
    doc, handle = parse(data)
    before = state(handle, handle[0])
    tb = block(doc)
    redact_region(handle, 0, tb.bbox)
    out = fitz.open(stream=export(handle), filetype="pdf")
    after = state(out, out[0])
    fills = [fitz.Rect(d["rect"]) for d in out[0].get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)]
    on = len(fills) == 1 and all(abs(a - b) < 1 for a, b in zip(fills[0], fitz.Rect(tb.bbox)))
    return before, after, on, out


print("== explicit page-level /Rotate ==")
for raw in ("90", "180", "270", "-90", "450", "0"):
    before, after, on, out = redact_and_export(build_page(rotate_raw=raw, cropbox=CROP))
    print(f"raw {raw:>4}: before {before}\n           after  {after}  fill on target={on}")

print("\n== indirect /Rotate (N 0 R) ==")
src = fitz.open(); p = src.new_page(width=612, height=792); p.insert_text((72, 700), "LOW-MARKER", fontsize=12)
src.xref_set_key(p.xref, "CropBox", CROP)
ref = src.get_new_xref(); src.update_object(ref, "90"); src.xref_set_key(p.xref, "Rotate", f"{ref} 0 R")
before, after, on, out = redact_and_export(src.tobytes()); src.close()
print(f"before {before}\nafter  {after}  fill on target={on}")

print("\n== inherited /Rotate (parent only) ==")
for raw in ("90", "180", "270"):
    before, after, on, out = redact_and_export(_inherited_rotation_page(raw, cropbox=CROP))
    print(f"raw {raw}: before {before}\n         after  {after}  fill on target={on}")

print("\n== inherited /Rotate, two pages, only page 0 redacted, then a PARENT-level rotate arrives ==")
src = fitz.open()
for _ in range(2):
    p = src.new_page(width=612, height=792); p.insert_text((72, 700), "LOW-MARKER", fontsize=12)
    src.xref_set_key(p.xref, "CropBox", CROP); src.xref_set_key(p.xref, "Rotate", "null")
parent = int(src.xref_get_key(src[0].xref, "Parent")[1].split()[0])
src.xref_set_key(parent, "Rotate", "90")
data = src.tobytes(); src.close()
doc, handle = parse(data)
redact_region(handle, 0, block(doc).bbox)
out = fitz.open(stream=export(handle), filetype="pdf")
print("after redaction:", [state(out, pg) for pg in out])
parent = int(out.xref_get_key(out[0].xref, "Parent")[1].split()[0])
out.xref_set_key(parent, "Rotate", "180")
out2 = fitz.open(stream=out.tobytes(), filetype="pdf")
print("after parent /Rotate -> 180:", [(pg.number, pg.rotation) for pg in out2])

print("\n== same, but a PAGE-level rotate arrives (set_rotation(rotation + 90)) ==")
doc, handle = parse(data)
redact_region(handle, 0, block(doc).bbox)
for pg in handle:
    pg.set_rotation(pg.rotation + 90)
out3 = fitz.open(stream=export(handle), filetype="pdf")
print("after page-level +90:", [(pg.number, pg.rotation, out3.xref_get_key(pg.xref, 'Rotate')) for pg in out3])

print("\n== does the live handle differ from the export? (contained crop, 90) ==")
doc, handle = parse(build_page(rotation=90, cropbox=CROP))
redact_region(handle, 0, block(doc).bbox)
print("live:", state(handle, handle[0]))
