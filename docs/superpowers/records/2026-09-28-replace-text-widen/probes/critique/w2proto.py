"""A faithful prototype of the brief's W2 right-limit rule set, so it can be
run against realistic pages. Follows the brief's text literally."""
import sys
sys.path.insert(0, "/home/user/pdf-ai-engine")
import pymupdf as fitz  # noqa: E402
from engine.geometry import unrotated_bounds  # noqa: E402


def overlaps_band(y0, y1, b):
    return b.y1 > y0 and b.y0 < y1


def drawing_edges(item):
    """Decompose a drawing item into segments (as rects). Rectangles become
    their four edges; other paths are taken as their individual items."""
    segs = []
    for it in item["items"]:
        kind = it[0]
        if kind == "re":
            r = it[1]
            segs += [fitz.Rect(r.x0, r.y0, r.x1, r.y0), fitz.Rect(r.x0, r.y1, r.x1, r.y1),
                     fitz.Rect(r.x0, r.y0, r.x0, r.y1), fitz.Rect(r.x1, r.y0, r.x1, r.y1)]
        elif kind == "l":
            p, q = it[1], it[2]
            segs.append(fitz.Rect(min(p.x, q.x), min(p.y, q.y), max(p.x, q.x), max(p.y, q.y)))
        elif kind == "c":
            pts = it[1:5]
            segs.append(fitz.Rect(min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts)))
        elif kind == "qu":
            q = it[1]
            segs.append(q.rect)
    return segs


def right_limit(page, target_bbox, size, explain=False):
    tx0, ty0, tx1, ty1 = target_bbox
    gap = max(1.0, 0.25 * size)
    notes = []
    candidates = []
    # 1. obstacles
    tdict = page.get_text("dict")
    all_spans = []
    for b in tdict["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                all_spans.append((fitz.Rect(s["bbox"]), s["text"]))
    def is_target(r):
        return max(abs(a - b) for a, b in zip(tuple(r), target_bbox)) < 0.05
    for r, text in all_spans:
        if is_target(r):
            continue
        if r.x0 >= tx1 - 1e-6 and overlaps_band(ty0, ty1, r):
            candidates.append((r.x0 - gap, f"span {text!r} @x0={r.x0:.1f}"))
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.x0 >= tx1 - 1e-6 and overlaps_band(ty0, ty1, r):
            candidates.append((r.x0 - gap, f"image @x0={r.x0:.1f}"))
    for item in page.get_drawings():
        for seg in drawing_edges(item):
            if seg.x0 >= tx1 - 1e-6 and overlaps_band(ty0, ty1, fitz.Rect(seg.x0, seg.y0 - 1e-6, seg.x1, seg.y1 + 1e-6)):
                candidates.append((seg.x0 - gap, f"drawing edge {tuple(round(v,1) for v in seg)}"))
    # 2. column edge
    lh = ty1 - ty0
    col = None
    for r, text in all_spans:
        if abs(r.x0 - tx0) <= 2 and (abs(r.y0 - ty0) <= 2 * lh) and not is_target(r):
            col = max(col or 0, r.x1)
    if col is not None:
        col = max(col, tx1)
        candidates.append((col, f"column edge (neighbour lines) {col:.1f}"))
    # 3. page margin
    bounds = unrotated_bounds(page)
    min_x0 = min((r.x0 for r, _ in all_spans), default=bounds.x0 + 18)
    left_margin = max(18.0, min_x0 - bounds.x0)
    candidates.append((bounds.x1 - left_margin, f"page right margin {bounds.x1 - left_margin:.1f} (left margin {left_margin:.1f})"))
    R, why = min(candidates, key=lambda c: c[0])
    if R < tx1:
        notes.append(f"clamped: R {R:.1f} < own x1 {tx1:.1f}, using own x1")
        R = tx1
        why = "own right edge (" + why + ")"
    if explain:
        return R, why, sorted(candidates)
    return R, why
