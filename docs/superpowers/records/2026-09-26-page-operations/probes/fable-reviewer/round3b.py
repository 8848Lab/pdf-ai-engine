"""Re-review 2, part B: (1) MuPDF's real page ctm per rotation (what
transformation_matrix hides at rotation != 0); (2) redaction placement on
pages the gate allows for OTHER_DRAWING, done the engine's way:
bbox from get_text at the page's rotation, then at_rotation_zero ->
add_redact_annot + apply_redactions(images=2, graphics=1, text=0)."""
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402
from pymupdf import mupdf  # noqa: E402

from engine.geometry import OTHER_DRAWING, TEXT_DRAWING, at_rotation_zero, drawing_refusal  # noqa: E402
from tests.geometry_helpers import build  # noqa: E402

L = "/MediaBox [0 0 612 792]"


def with_text(page_extra="", pages_extra="", extra_objects=()):
    """standard() plus a content stream drawing VISIBLE at PDF (100, 600)
    and a Helvetica resource. Extras are numbered from 4; contents and font
    come after them."""
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


def mupdf_ctm(page):
    ctm = mupdf.FzMatrix()
    mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)
    return tuple(round(v, 4) for v in (ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f))


def find_bbox(page, word="VISIBLE"):
    d = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP)
    for block in d["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"] == word:
                    return fitz.Rect(span["bbox"])
    return None


def redaction_check(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    other = drawing_refusal(page, 0, OTHER_DRAWING)
    text = drawing_refusal(page, 0, TEXT_DRAWING)
    bbox = find_bbox(page)
    if bbox is None:
        doc.close()
        return dict(other=other, text=text, bbox=None)
    with at_rotation_zero(page):
        page.add_redact_annot(bbox, fill=(0, 0, 0))
        page.apply_redactions(images=2, graphics=1, text=0)
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    p = reopened[0]
    still = find_bbox(p)
    fills = [fitz.Rect(dr["rect"]) for dr in p.get_drawings() if dr.get("fill") is not None]
    reopened.close()
    fill = fills[0] if fills else None
    if fill is None:
        off = None
    else:
        off = max(abs(fill.x0 - bbox.x0), abs(fill.y0 - bbox.y0), abs(fill.x1 - bbox.x1), abs(fill.y1 - bbox.y1))
    return dict(other=other, text=text, bbox=tuple(round(v, 2) for v in bbox), gone=still is None,
                fill=None if fill is None else tuple(round(v, 2) for v in fill), off=off, nfills=len(fills))


ROWS = [
    ("plain", lambda: with_text(L)),
    ("rot90", lambda: with_text(f"{L} /Rotate 90")),
    ("rot180", lambda: with_text(f"{L} /Rotate 180")),
    ("rot270", lambda: with_text(f"{L} /Rotate 270")),
    ("over-all4", lambda: with_text(f"{L} /CropBox [-40 -60 660 820]")),
    ("over-left-rot90", lambda: with_text(f"{L} /Rotate 90 /CropBox [-40 0 612 792]")),
    ("over-top-rot180", lambda: with_text(f"{L} /Rotate 180 /CropBox [0 0 612 830]")),
    ("over-all4-rot270", lambda: with_text(f"{L} /Rotate 270 /CropBox [-40 -60 660 820]")),
    ("negmedia-left", lambda: with_text("/MediaBox [-100 -100 512 692] /CropBox [-140 0 512 692]")),
    ("negmedia-top", lambda: with_text("/MediaBox [-100 -100 512 692] /CropBox [-100 -100 512 720]")),
    ("G1", lambda: with_text(f"{L} /CropBox [4 0 R -60 660 820]", extra_objects=["-40"])),
    ("I1", lambda: with_text("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]")),
    ("I3", lambda: with_text("/CropBox [-40 -60 660 820]")),
    ("N3", lambda: with_text("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["0"])),
    ("crop-inverted", lambda: with_text(f"{L} /CropBox [612 792 -40 -60]")),
    ("media-zero", lambda: with_text("/MediaBox [0 0 0 0]")),
    ("crop-empty", lambda: with_text(f"{L} /CropBox [100 100 100 100]")),
    ("dangling", lambda: with_text(f"{L} /CropBox 99 0 R /UserUnit 99 0 R /Rotate 99 0 R")),
    ("unit1e30", lambda: with_text(f"{L} /UserUnit 1e30")),
    ("unit1.0000001", lambda: with_text(f"{L} /UserUnit 1.0000001")),
    ("unit-1.00001", lambda: with_text(f"{L} /UserUnit 1.00001")),
    ("rot315", lambda: with_text(f"{L} /Rotate 315")),
    ("rot-real-89.6", lambda: with_text(f"{L} /Rotate 89.6")),
    ("media-huge", lambda: with_text("/MediaBox [0 0 1000000000 1000000000]")),
    ("media-huge-offset", lambda: with_text("/MediaBox [1000000 1000000 1000612 1000792]")),
    ("media-tiny-crop-over", lambda: with_text("/MediaBox [0 0 0.5 0.5] /CropBox [-40 -60 660 820]")),
    ("crop-int64-left", lambda: with_text(f"{L} /CropBox [-4294967336 -60 660 820]")),
    ("crop-huge-neg-plain", lambda: with_text(f"{L} /CropBox [-99999999999999999999999999999999999999 -60 660 820]")),
    ("crop-tiny-unit0.5", lambda: with_text(f"{L} /CropBox [100 100 100.5 100.5] /UserUnit 0.5")),
    ("unit-1-rot90", lambda: with_text(f"{L} /UserUnit -1 /Rotate 90")),
    ("unit-1-rot180", lambda: with_text(f"{L} /UserUnit -1 /Rotate 180")),
    ("unit-1-rot270", lambda: with_text(f"{L} /UserUnit -1 /Rotate 270")),
    ("unit-1-rot180-crop", lambda: with_text(f"{L} /CropBox [50 50 500 700] /UserUnit -1 /Rotate 180")),
    ("crop-swapped-x-rot90", lambda: with_text(f"{L} /CropBox [612 -60 -40 792] /Rotate 90")),
    ("media-swapped-rot90", lambda: with_text("/MediaBox [612 792 0 0] /Rotate 90")),
    ("parent-self-nocrop", lambda: build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",
        f"<< /Type /Page /Parent 3 0 R {L} /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length 38 >>\nstream\nBT /F1 12 Tf 100 600 Td (VISIBLE) Tj ET\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ])),
]


if __name__ == "__main__":
    print("=== MuPDF ctm vs transformation_matrix per rotation ===")
    for extra in (f"{L} /Rotate 0", f"{L} /Rotate 90", f"{L} /Rotate 180", f"{L} /Rotate 270",
                  f"{L} /UserUnit -1", f"{L} /UserUnit -1 /Rotate 90", f"{L} /UserUnit -1 /Rotate 180",
                  f"{L} /UserUnit -1 /Rotate 270", f"{L} /UserUnit 2 /Rotate 90", f"{L} /Rotate 135",
                  f"{L} /Rotate 45", f"{L} /CropBox [-40 -60 660 820] /Rotate 90",
                  "/MediaBox [-100 -100 512 692] /Rotate 270"):
        d = fitz.open(stream=with_text(extra), filetype="pdf")
        p = d[0]
        print(f"{extra:50} rot={p.rotation:3} mupdf_ctm={mupdf_ctm(p)} tm={tuple(round(v,4) for v in p.transformation_matrix)}")
        d.close()
    print()
    print("=== redaction placement (engine flow) ===")
    for cid, builder in ROWS:
        try:
            r = redaction_check(builder())
        except Exception as exc:  # noqa: BLE001
            print(f"{cid:24} EXC {type(exc).__name__}: {exc}")
            continue
        flag = ""
        if r.get("bbox") is not None and r["other"] is None and (not r["gone"] or r["off"] is None or r["off"] > 0.5):
            flag = "  <<< ALLOWED FOR OTHER BUT REDACTION MISPLACED"
        print(f"{cid:24} other={'-' if r['other'] is None else 'refused':7} text={'-' if r['text'] is None else 'refused':7} "
              f"bbox={r.get('bbox')} gone={r.get('gone')} fill={r.get('fill')} off={r.get('off')} nfills={r.get('nfills')}{flag}")
