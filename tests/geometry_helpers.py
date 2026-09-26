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


_INHERITABLE = ("MediaBox", "CropBox", "Rotate")


def box_page(*, where="page", indirect=(), **keys):
    """A plain 612x792 page with raw keys written onto it or onto /Pages.

    ``where="parent"`` writes the keys on the parent /Pages node instead, to
    exercise inheritance. That also nulls the page's own copy of each
    inheritable key being written (/MediaBox, /CropBox, /Rotate) -- ``new_page``
    writes explicit page-level values for /MediaBox and /Rotate, which would
    otherwise override an inherited one. /UserUnit is not inheritable in
    PyMuPDF, so it is never nulled here regardless of ``where``. ``indirect``
    names keys to store as ``N 0 R`` references rather than inline.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    target = page.xref
    if where == "parent":
        target = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
        for key in _INHERITABLE:
            if key in keys:
                doc.xref_set_key(page.xref, key, "null")
    for key, value in keys.items():
        if key in indirect:
            ref = doc.get_new_xref()
            doc.update_object(ref, value)
            value = f"{ref} 0 R"
        doc.xref_set_key(target, key, value)
    return doc, doc.reload_page(page)


def drift_probe(pdf_bytes: bytes):
    """Draw PROBE at (100, 140) the way the editor draws text, re-open the
    bytes, and return (drifted, origin). drifted is None if the text cannot
    be found at all (a page PyMuPDF cannot lay out)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc[0].insert_text((100, 140), "PROBE", fontsize=10)
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    text = reopened[0].get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    origin = next(
        (span["origin"] for block in text["blocks"] for line in block.get("lines", [])
         for span in line["spans"] if span["text"] == "PROBE"),
        None,
    )
    reopened.close()
    if origin is None:
        return None, None
    return abs(origin[0] - 100) > 0.01 or abs(origin[1] - 140) > 0.01, tuple(origin)


def build(objects: list) -> bytes:
    """A raw one-off PDF from object bodies. objects[0] is object 1 0 obj;
    the trailer's /Root is always 1 0 R. Full manual control, for a graph
    ``standard`` can't express (e.g. a page dict with more than one /Parent
    key, which would collide with ``standard``'s own).
    """
    body = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref_offset = len(body)
    n = len(objects) + 1
    xref = f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return body + xref + trailer


def standard(page_extra="", pages_extra="", extra_objects=()):
    """The standard three-object document (Catalog=1, Pages=2, Page=3, extra
    objects numbered from 4) used by the fix-round-2 adversarial table.
    ``page_extra``/``pages_extra`` are raw PDF dict entries spliced into the
    Page/Pages dicts (the Page dict already has /Parent 2 0 R; do not repeat
    /Parent in ``page_extra`` -- use ``build`` directly for that).
    """
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [3 0 R] /Count 1 {pages_extra} >>",
        f"<< /Type /Page /Parent 2 0 R {page_extra} >>",
        *extra_objects,
    ]
    return build(objs)


def with_text(page_extra="", pages_extra="", extra_objects=()):
    """``standard()`` plus a content stream drawing VISIBLE at PDF (100, 600)
    and a Helvetica font resource, for the fix-round-3 redaction-placement
    check (Test B needs no drawable content; this does). Extras are numbered
    from 4 as usual; the content stream and font objects come after them.
    """
    n_extra = len(extra_objects)
    contents = 4 + n_extra
    font = contents + 1
    stream = b"BT /F1 12 Tf 100 600 Td (VISIBLE) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [3 0 R] /Count 1 {pages_extra} >>",
        f"<< /Type /Page /Parent 2 0 R /Contents {contents} 0 R "
        f"/Resources << /Font << /F1 {font} 0 R >> >> {page_extra} >>",
        *extra_objects,
        f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    return build(objs)


def find_span_bbox(page: fitz.Page, word: str) -> fitz.Rect | None:
    """The bbox of the first span reading exactly ``word``, or None."""
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    text = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    for block in text["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"] == word:
                    return fitz.Rect(span["bbox"])
    return None
