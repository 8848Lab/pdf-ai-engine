"""Builders for pages with rotation, CropBox, MediaBox and /UserUnit set.

Two jobs, two kinds of builder:

- ``matrix_cases`` / ``matrix_page``: the Codex critic's 1,024-configuration
  generator, ported with fixed parameters from
  docs/superpowers/records/2026-09-26-page-operations/probes/recheck_common.py.
  Page content is written as a RAW content stream, so it never depends on the
  PyMuPDF drawing calls whose behaviour on these pages is under test.
- ``build_page`` (added in Task 3): one page for operation-level tests. Its
  content is drawn on a plain page FIRST, and only then are the boxes,
  /UserUnit and rotation applied. Do not reorder that: drawing after they are
  set is exactly the broken path, and the fixture would be testing itself.
"""
from itertools import product

import pymupdf as fitz

ROTATIONS = (0, 90, 180, 270)
BAND = (0.7, 0.85, 1.0)
BAND_RGB = (178, 216, 255)

_ORIGINS = ((0, 0), (100, 200), (-100, -200), (13.125, -27.375))


def matrix_cases(units=(1,)):
    """Four MediaBox origins x 16 CropBox overhang masks x units x 4 rotations.

    Mask bits: 1 = extends left, 2 = extends bottom, 4 = extends right,
    8 = extends top. With units=(0.5, 1, 1.5, 2) this is 1,024 cases.
    """
    for (ox, oy), mask, unit, rot in product(_ORIGINS, range(16), units, ROTATIONS):
        media = fitz.Rect(ox, oy, ox + 300, oy + 400)
        crop = fitz.Rect(
            ox + (-17.5 if mask & 1 else 20.25),
            oy + (-23.75 if mask & 2 else 20.25),
            ox + 300 + (31.25 if mask & 4 else -20.25),
            oy + 400 + (11.125 if mask & 8 else -20.25),
        )
        yield f"origin=({ox},{oy}) mask={mask} unit={unit} rot={rot}", media, crop, unit, rot


def _pdf_box(rect) -> str:
    return "[" + " ".join(str(v) for v in rect) + "]"


def matrix_page(media, crop, unit, rot) -> fitz.Document:
    """A page with a blue band, text VISIBLE on the band, and text OFFPAGE
    beyond the visible area's right edge. Positions are chosen so that, in
    PyMuPDF page coordinates, the band covers (35..135, 58..88) at any unit.
    """
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_font(fontname="helv")
    doc.xref_set_key(page.xref, "MediaBox", _pdf_box(media))
    doc.xref_set_key(page.xref, "CropBox", _pdf_box(crop))
    doc.xref_set_key(page.xref, "UserUnit", str(unit))
    page = doc.reload_page(page)
    page.set_rotation(rot)
    visible = media & crop
    x, y = visible.x0 + 40 / unit, visible.y1 - 80 / unit
    stream = (
        f"q {BAND[0]} {BAND[1]} {BAND[2]} rg {x - 5 / unit} {y - 8 / unit} "
        f"{100 / unit} {30 / unit} re f Q "
        f"BT /helv {10 / unit} Tf 1 0 0 1 {x} {y} Tm (VISIBLE) Tj ET\n"
        f"BT /helv {10 / unit} Tf 1 0 0 1 {visible.x1 + 40 / unit} {y} Tm (OFFPAGE) Tj ET"
    )
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, stream.encode())
    page.set_contents(xref)
    return doc


def reopen(doc: fitz.Document) -> fitz.Document:
    """Round-trip through bytes so assertions see what a recipient would."""
    reopened = fitz.open(stream=doc.tobytes(garbage=3), filetype="pdf")
    doc.close()
    return reopened


def box_page(*, where="page", indirect=(), **keys):
    """A plain 612x792 page with raw keys written onto it or onto /Pages.

    ``where="parent"`` writes the keys on the parent /Pages node instead, to
    exercise inheritance. That also removes the page's own /Rotate, which
    ``new_page`` writes explicitly as 0 and which would otherwise override
    an inherited value. ``indirect`` names keys to store as ``N 0 R``
    references rather than inline.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    target = page.xref
    if where == "parent":
        target = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
        if "Rotate" in keys:
            doc.xref_set_key(page.xref, "Rotate", "null")
    for key, value in keys.items():
        if key in indirect:
            ref = doc.get_new_xref()
            doc.update_object(ref, value)
            value = f"{ref} 0 R"
        doc.xref_set_key(target, key, value)
    return doc, doc.reload_page(page)
