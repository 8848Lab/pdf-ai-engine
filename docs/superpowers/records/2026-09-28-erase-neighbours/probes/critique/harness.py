"""Layout harness: build a page from items, one of which is the TARGET; erase the target with
today's rect (unclipped) and with N1's clipped rect; compare against the IDEAL page (built
without the target) in both the exported text and the pixels."""
import pymupdf as fitz
from n1_proto import n1_clip, Refused

ZOOM = 3
import os
SIDE = os.environ.get("N1_SIDE", "centre")


def build(items, omit_target=False, page_rot=0, cropbox=None, size=(612, 792)):
    d = fitz.open(); p = d.new_page(width=size[0], height=size[1])
    if cropbox:
        p.set_cropbox(fitz.Rect(cropbox))
    for it in items:
        if it.get("target") and omit_target:
            continue
        kind = it.get("kind", "text")
        if kind == "text":
            kw = dict(fontsize=it.get("size", 12), fontname=it.get("font", "helv"), rotate=it.get("rotate", 0))
            if it.get("fontfile"):
                p.insert_font(fontname=it["font"], fontfile=it["fontfile"])
            p.insert_text(it["pt"], it["text"], **kw)
        elif kind == "rect":
            p.draw_rect(fitz.Rect(it["rect"]), color=it.get("color", (0, 0, 0)), width=it.get("width", 0.8), fill=it.get("fill"))
        elif kind == "line":
            p.draw_line(fitz.Point(it["a"]), fitz.Point(it["b"]), color=(0, 0, 0), width=it.get("width", 0.8))
    if page_rot:
        p.set_rotation(page_rot)
    return d, p


def find_target_span(p, items):
    t = [it for it in items if it.get("target")][0]
    key = t["text"].split()[0] if t["text"].split() else t["text"]
    cands = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].startswith(key) and abs(s["size"] - t.get("size", 12)) < 0.01:
                    cands.append(s)
    assert cands, f"target {key!r} not found"
    return cands[0]


def words(p):
    return sorted(w[4] for w in p.get_text("words"))


def render(p):
    return p.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray")


def pix_diff(after, ideal):
    """(leftover, damage): pixels dark in `after` but light in `ideal`, and vice versa."""
    a = after.samples; b = ideal.samples
    assert len(a) == len(b)
    leftover = sum(1 for x, y in zip(a, b) if x < 128 <= y)
    damage = sum(1 for x, y in zip(a, b) if y < 128 <= x)
    return leftover, damage


def erase(p, rect, fill=(1, 1, 1), text=0, images=2, graphics=1):
    p.add_redact_annot(rect, fill=fill)
    p.apply_redactions(images=images, graphics=graphics, text=text)


def run_case(name, items, pad=0.05, side=None, quiet=False, **bkw):
    side = side or SIDE
    d_ideal, p_ideal = build(items, omit_target=True, **bkw)
    ideal_words = words(p_ideal); ideal_pix = render(p_ideal)
    res = {}
    for mode in ("today", "n1"):
        d, p = build(items, **bkw)
        s = find_target_span(p, items)
        tb = fitz.Rect(s["bbox"])
        rect = fitz.Rect(tb.x0, tb.y0, tb.x1 + pad, tb.y1)
        kept = 1.0; clippers = []
        if mode == "n1":
            try:
                rect, kept, clippers = n1_clip(p, rect, tb, side=side)
            except Refused as e:
                res[mode] = f"REFUSED ({e})"
                continue
        erase(p, rect)
        w = words(p)
        missing = [x for x in ideal_words if x not in w]
        extra = [x for x in w if x not in ideal_words]
        lo, dm = pix_diff(render(p), ideal_pix)
        res[mode] = f"kept={kept:.2f} text: missing_neighbour_words={missing} leftover_words={extra} pixels: leftover={lo} damage={dm}" + (f" clip={clippers}" if clippers else "")
    if not quiet:
        print(f"--- {name}")
        for k, v in res.items():
            print(f"   {k:5s}: {v}")
    return res
