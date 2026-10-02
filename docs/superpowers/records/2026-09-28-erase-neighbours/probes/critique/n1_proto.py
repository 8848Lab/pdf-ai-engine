"""Prototype of the brief's N1 clip, written literally from its text:

  - start from today's rect (target bbox + precision pad)
  - every OTHER text span whose bbox overlaps the rect horizontally and vertically:
      above the target's centre line -> raise y0 to its y1
      below                          -> lower y1 to its y0
  - if the clipped rect keeps < 15% of the target's own bbox height -> refuse before mutation.

`side` selects how "above/below the centre line" is read, since the brief does not say:
  "centre"  : the neighbour's own centre vs the target's centre (default)
  "edges"   : neighbour.y1 <= target centre -> above; neighbour.y0 >= centre -> below; else both/undecidable
"""
import pymupdf as fitz

FLOOR = 0.15


class Refused(ValueError):
    pass


def other_spans(page, target_bbox, tol=0.05):
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                r = fitz.Rect(span["bbox"])
                if max(abs(a - b) for a, b in zip(tuple(r), tuple(target_bbox))) < tol:
                    continue
                out.append((r, span))
    return out


def n1_clip(page, rect, target_bbox, side="centre", floor=FLOOR, spans=None):
    target_bbox = fitz.Rect(target_bbox)
    y0, y1 = rect.y0, rect.y1
    cy = (target_bbox.y0 + target_bbox.y1) / 2
    clippers = []
    # the target's own baseline and size, from the page span matching its bbox
    target_baseline, target_size = cy, target_bbox.height / 1.37
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if max(abs(a - b) for a, b in zip(span["bbox"], tuple(target_bbox))) < 0.05:
                    target_baseline, target_size = span["origin"][1], span["size"]
    for r, span in (spans if spans is not None else other_spans(page, target_bbox)):
        if not (r.x1 > rect.x0 and r.x0 < rect.x1 and r.y1 > rect.y0 and r.y0 < rect.y1):
            continue
        if side == "wf1":
            oy = span["origin"][1]
            if abs(oy - target_baseline) <= 0.5 * target_size:
                continue  # W-F1: same-line neighbour -> left to the horizontal pad rule
            above = (r.y0 + r.y1) / 2 < cy
        elif side == "baseline":
            oy = span["origin"][1]
            if target_bbox.y0 <= oy <= target_bbox.y1:
                continue  # same-line neighbour: left to the horizontal pad rule
            above = (r.y0 + r.y1) / 2 < cy
        elif side == "centre":
            above = (r.y0 + r.y1) / 2 < cy
        else:
            above = r.y1 <= cy
            if not above and r.y0 < cy:  # straddles: treat as above if it starts higher than target
                above = r.y0 < target_bbox.y0
        if above:
            if r.y1 > y0:
                y0 = r.y1; clippers.append(("above", span["text"], round(r.y1, 2)))
        else:
            if r.y0 < y1:
                y1 = r.y0; clippers.append(("below", span["text"], round(r.y0, 2)))
    kept = (y1 - y0) / target_bbox.height if target_bbox.height else 0
    if kept < floor:
        raise Refused(f"kept {kept:.3f} < {floor}: lines overlap too closely; clippers={clippers}")
    return fitz.Rect(rect.x0, y0, rect.x1, y1), kept, clippers
