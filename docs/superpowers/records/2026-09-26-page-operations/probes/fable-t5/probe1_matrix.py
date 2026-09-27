"""Probe 1: every erase caller x every rotation x every crop, asserted on exported bytes."""
import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz
from engine.export import export
from engine.operations import delete_block, move_block, redact_region, replace_text
from engine.parser import parse
from tests.geometry_helpers import ROTATIONS, build_page

CROPS = {
    "contained": dict(cropbox="[40 60 580 740]"),
    "oversized": dict(cropbox="[-40 -60 660 820]"),
    "left_overhang": dict(cropbox="[-40 60 580 740]"),
    "top_overhang": dict(cropbox="[40 60 580 840]"),
    "neg_mediabox": dict(mediabox="[-100 -200 512 592]"),
    "neg_mediabox+contained_crop": dict(mediabox="[-100 -200 512 592]", cropbox="[-60 -140 472 552]"),
}
BLACK, WHITE = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP


def spans(page):
    text = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=FLAGS)
    return [(s["text"], fitz.Rect(s["bbox"])) for b in text["blocks"] for l in b.get("lines", []) for s in l["spans"]]


def same(a, b, tol=0.01):
    return a is not None and len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def on(rect, target):
    return all(abs(a - b) < 1 for a, b in zip(rect, target))


def block(doc):
    return next(b for b in doc.pages[0].text_blocks if "LOW-MARKER" in b.text)


def run(op, rotation, crop):
    doc, handle = parse(build_page(rotation=rotation, **CROPS[crop]))
    tb = block(doc)
    target = fitz.Rect(tb.bbox)
    if op == "redact_region":
        redact_region(handle, 0, tb.bbox); colour = BLACK
    elif op == "delete_block":
        delete_block(handle, 0, tb); colour = WHITE
    elif op == "replace_text":
        replace_text(handle, 0, tb, "NEW-TEXT"); colour = WHITE
    elif op == "move_block":
        move_block(handle, 0, tb, offset=(0, -300)); colour = WHITE
    out = fitz.open(stream=export(handle), filetype="pdf")
    page = out[0]
    sp = spans(page)
    marker_at_source = [r for t, r in sp if "LOW-MARKER" in t and r.intersects(target)]
    marker_anywhere = [r for t, r in sp if "LOW-MARKER" in t]
    fills = [fitz.Rect(d["rect"]) for d in page.get_drawings() if same(d.get("fill"), colour)]
    all_fills = [d for d in page.get_drawings() if d.get("fill") is not None]
    problems = []
    if marker_at_source:
        problems.append(f"marker still at source {marker_at_source}")
    if op == "move_block" and not marker_anywhere:
        problems.append("moved text missing")
    if op == "replace_text" and not any("NEW-TEXT" in t for t, _ in sp):
        problems.append("replacement text missing")
    if len(fills) != 1:
        problems.append(f"{len(fills)} fills of colour {colour}: {fills}")
    elif not on(fills[0], target):
        problems.append(f"fill at {tuple(round(v, 2) for v in fills[0])} vs target {tuple(round(v, 2) for v in target)}")
    if len(all_fills) != 1:
        problems.append(f"{len(all_fills)} filled drawings total")
    if page.rotation != rotation:
        problems.append(f"exported rotation {page.rotation} != {rotation}")
    if len(list(page.annots())) or out.xref_get_key(page.xref, "Annots")[0] not in ("null", "array"):
        problems.append(f"annots remain: {out.xref_get_key(page.xref, 'Annots')}")
    if out.xref_get_key(page.xref, "Annots")[0] == "array" and out.xref_get_key(page.xref, "Annots")[1] != "[]":
        problems.append(f"non-empty /Annots {out.xref_get_key(page.xref, 'Annots')}")
    out.close(); handle.close()
    return problems


failed = 0
total = 0
for op in ("redact_region", "delete_block", "replace_text", "move_block"):
    for crop in CROPS:
        row = []
        for rotation in ROTATIONS:
            total += 1
            try:
                problems = run(op, rotation, crop)
            except Exception as exc:  # noqa: BLE001
                problems = [f"RAISED {type(exc).__name__}: {exc}"]
            if problems:
                failed += 1
                row.append(f"{rotation}: FAIL {problems}")
            else:
                row.append(f"{rotation}: ok")
        print(f"{op:14s} {crop:28s} " + " | ".join(row))
print(f"\n{total - failed}/{total} cells pass")
