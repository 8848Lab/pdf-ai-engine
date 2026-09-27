import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")
import pymupdf as fitz
from pymupdf import mupdf
from engine.geometry import TEXT_DRAWING, OTHER_DRAWING, visible_area, crop_origin_overhangs
from tests.geometry_helpers import drift_probe, matrix_cases, matrix_page

_LAYOUT_TOLERANCE_PT = 0.01
_MAX_COORDINATE_PT = 2 ** 24
_ROTATION_PATTERNS = {0: (1, 0, 0, -1), 90: (0, 1, 1, 0), 180: (-1, 0, 0, 1), 270: (0, -1, -1, 0)}

def page_ctm(page):
    try:
        ctm = mupdf.FzMatrix()
        mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)
    except (AttributeError, TypeError):
        return None
    return fitz.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f)

def layout_orientation(page):
    ctm = page_ctm(page)
    if ctm is None: return None
    linear = (ctm.a, ctm.b, ctm.c, ctm.d)
    for rotation, pattern in _ROTATION_PATTERNS.items():
        scale = max(abs(v) for v in linear)
        if scale <= 0: return None
        if all(abs(v - p * scale) <= 1e-9 * max(1.0, scale) for v, p in zip(linear, pattern)):
            return rotation, scale
    return None

def refusal(page, kind):
    layout = layout_orientation(page)
    if layout is not None and layout[0] != page.rotation:
        return "rot"
    visible = visible_area(page)
    w, h = (visible.height, visible.width) if page.rotation in (90, 270) else (visible.width, visible.height)
    if layout is None or visible.is_empty or w < 1 or h < 1:
        return "incons"
    unit = layout[1]
    if abs(page.rect.width - unit * w) > _LAYOUT_TOLERANCE_PT or abs(page.rect.height - unit * h) > _LAYOUT_TOLERANCE_PT:
        return "incons"
    if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > _LAYOUT_TOLERANCE_PT:
        return "unit"
    if any(abs(v) > _MAX_COORDINATE_PT for box in (page.mediabox, page.cropbox) for v in box):
        return "huge"
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return "over"
    return None

if __name__ == "__main__":
    from round3a import NEW_ROWS, load_table
    bad = 0
    for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
        doc = matrix_page(media, crop, unit, rot); b = doc.tobytes(); doc.close()
        d = fitz.open(stream=b, filetype="pdf"); r = refusal(d[0], TEXT_DRAWING); d.close()
        drifted, _ = drift_probe(b)
        if (unit == 1 and ((drifted and r != "over") or (not drifted and r is not None))) or (unit != 1 and r != "unit"):
            bad += 1; print("MISMATCH", name, r, drifted)
    print("matrix mismatches", bad)
    rows = [(c, bld, e) for c, bld, e in load_table()] + [(c, bld, "?") for c, bld in NEW_ROWS]
    for cid, builder, expected in rows:
        try:
            data = builder(); d = fitz.open(stream=data, filetype="pdf"); r = refusal(d[0], TEXT_DRAWING); d.close()
        except Exception as exc:
            print(f"{cid:34} EXC {type(exc).__name__}"); continue
        drifted, origin = drift_probe(data)
        flag = "BYPASS" if (r is None and drifted is not False) else ""
        mism = "" if expected in ("?", "any") or (r or "-") == expected else f"(table {expected})"
        if flag or mism or expected == "?":
            print(f"{cid:34} gate={r!s:7} drift={drifted!s:5} {flag} {mism}")
