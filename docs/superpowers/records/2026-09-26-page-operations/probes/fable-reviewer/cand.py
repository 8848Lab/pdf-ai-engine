import pymupdf as fitz
TOL = 0.01
def visible_area(page):
    mb = page.mediabox
    return page.cropbox & fitz.Rect(mb.x0, 0, mb.x1, mb.height)
def rotation_is_valid(page):
    tm = page.transformation_matrix
    return abs(tm.b) < 1e-9 and abs(tm.c) < 1e-9
def layout_scale(page):
    v = visible_area(page)
    w, h = (v.height, v.width) if page.rotation in (90, 270) else (v.width, v.height)
    if v.is_empty or w <= 0 or h <= 0:
        return None
    sx, sy = page.rect.width / w, page.rect.height / h
    if abs(sx - sy) * max(w, h) > TOL:
        return None
    return sx
def crop_origin_overhangs(page):
    return page.cropbox.x0 < page.mediabox.x0 or page.cropbox.y0 < 0
def refusal(page, kind):
    if not rotation_is_valid(page): return "rotation"
    s = layout_scale(page)
    if s is None: return "uninterpretable"
    tm = page.transformation_matrix
    if not (tm.a > 0 and tm.d < 0): return "uninterpretable"
    v = visible_area(page)
    if abs(s - 1) * max(v.width, v.height) > TOL: return f"unit {s:g}"
    if kind == "text" and crop_origin_overhangs(page): return "overhang"
    return None
