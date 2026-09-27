"""Candidate repair for the rotated-mirror bypass: read MuPDF's real page
ctm (what transformation_matrix computes and then discards at rotation != 0)
and require its linear part to be the rotation PyMuPDF reports, at a positive
scale. Verified here against drift_probe on the 1,024 matrix, the 39 table
rows and the round-3 rows. Reviewer's scratch; not the checkout."""
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402
from pymupdf import mupdf  # noqa: E402

from engine.geometry import TEXT_DRAWING, crop_origin_overhangs, visible_area  # noqa: E402
from tests.geometry_helpers import drift_probe, matrix_cases, matrix_page  # noqa: E402

TOL = 0.01


def mupdf_ctm(page):
    ctm = mupdf.FzMatrix()
    mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)
    return fitz.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f)


def layout_scale(page):
    """The positive scale MuPDF lays the page out at, or None when its ctm is
    not page.rotation at a positive scale, or its boxes disagree with rect."""
    m = mupdf_ctm(page)
    rot = page.rotation
    # linear part per rotation: 0 (u,0,0,-u)  90 (0,u,u,0)  180 (-u,0,0,u)  270 (0,-u,-u,0)
    if rot == 0:
        diag, off, u = (m.a, -m.d), (m.b, m.c), m.a
    elif rot == 90:
        diag, off, u = (m.b, m.c), (m.a, m.d), m.b
    elif rot == 180:
        diag, off, u = (-m.a, m.d), (m.b, m.c), -m.a
    else:
        diag, off, u = (-m.b, -m.c), (m.a, m.d), -m.b
    if u <= 0 or abs(diag[0] - diag[1]) > 1e-6 * u or abs(off[0]) > 1e-9 or abs(off[1]) > 1e-9:
        return None
    visible = visible_area(page)
    w, h = (visible.height, visible.width) if rot in (90, 270) else (visible.width, visible.height)
    if visible.is_empty or w < 1 or h < 1:  # MuPDF swaps a sub-point box for the unit rect
        return None
    if abs(page.rect.width - u * w) > TOL or abs(page.rect.height - u * h) > TOL:
        return None
    return u


def refusal(page, kind):
    u = layout_scale(page)
    if u is None:
        return "incons"
    if abs(u - 1) * max(page.rect.width, page.rect.height) / u > TOL:
        return "unit"
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return "over"
    return None


def agree(pdf_bytes):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    r = refusal(d[0], TEXT_DRAWING)
    d.close()
    drifted, origin = drift_probe(pdf_bytes)
    if r is None and drifted is not False:
        return f"BYPASS gate=None probe={(drifted, origin)}"
    return None


if __name__ == "__main__":
    from round3a import NEW_ROWS, load_table
    bad = []
    n = 0
    for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
        n += 1
        doc = matrix_page(media, crop, unit, rot)
        b = doc.tobytes()
        doc.close()
        d = fitz.open(stream=b, filetype="pdf")
        r = refusal(d[0], TEXT_DRAWING)
        d.close()
        drifted, origin = drift_probe(b)
        if unit == 1:
            if drifted and r != "over":
                bad.append((name, r, origin))
            if not drifted and r is not None:
                bad.append((name, r, origin))
        elif r != "unit":
            bad.append((name, r, origin))
    print(f"matrix: {n} cases, {len(bad)} mismatches", bad[:5])
    for cid, builder, expected in load_table():
        x = agree(builder())
        d = fitz.open(stream=builder(), filetype="pdf")
        r = refusal(d[0], TEXT_DRAWING)
        d.close()
        if x or (expected not in ("any",) and (r or "-") != expected):
            print(f"table {cid}: candidate={r} table={expected} {x or ''}")
    for cid, builder in NEW_ROWS:
        try:
            x = agree(builder())
        except Exception as exc:  # noqa: BLE001
            x = f"EXC {type(exc).__name__}"
        d = fitz.open(stream=builder(), filetype="pdf") if not str(x).startswith("EXC") else None
        r = refusal(d[0], TEXT_DRAWING) if d else "n/a"
        if d:
            d.close()
        print(f"new {cid:34} candidate={r} {x or ''}")
