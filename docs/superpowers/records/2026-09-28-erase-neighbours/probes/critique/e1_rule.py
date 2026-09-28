"""E1 critique: what exactly is MuPDF's removal rule for a glyph under apply_redactions(text=0)?
Area-based or height-based? Per-glyph outline bbox or font line box? Same for every font/size/rotation?"""
import pymupdf as fitz

FONTS = {
    "helv": None, "tiro": None, "cour": None,
    "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "LiberationSerif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "cjk": "cjk",  # builtin Droid Sans Fallback
}


def make(fontkey, text, size=12, rotate=0, page_rot=0, pt=(72, 100)):
    d = fitz.open(); p = d.new_page()
    path = FONTS[fontkey]
    if path is None:
        p.insert_text(pt, text, fontsize=size, fontname=fontkey, rotate=rotate)
    elif path == "cjk":
        p.insert_font(fontname="F1", fontbuffer=fitz.Font("cjk").buffer)
        p.insert_text(pt, text, fontsize=size, fontname="F1", rotate=rotate)
    else:
        p.insert_font(fontname="F1", fontfile=path)
        p.insert_text(pt, text, fontsize=size, fontname="F1", rotate=rotate)
    if page_rot:
        p.set_rotation(page_rot)
    return d, p


def chars(p):
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                for c in s["chars"]:
                    out.append((c["c"], fitz.Rect(c["bbox"])))
    return out


def span_bbox(p):
    return [fitz.Rect(s["bbox"]) for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]


def text_after(fontkey, text, rect, **kw):
    d, p = make(fontkey, text, **kw)
    p.add_redact_annot(rect); p.apply_redactions(images=0, graphics=0, text=0)
    return p.get_text().strip()


def bisect(fontkey, text, rect_of, lo, hi, survive_text=None, **kw):
    """find the smallest overlap at which the text changes."""
    base = text_after(fontkey, text, fitz.Rect(0, 0, 1, 1), **kw)
    for _ in range(30):
        m = (lo + hi) / 2
        if text_after(fontkey, text, rect_of(m), **kw) == base: lo = m
        else: hi = m
    return hi


print("== A. vertical threshold as ratio of SPAN bbox height (line box), per font, sizes 8/12/24")
for fk in FONTS:
    for size in (8, 12, 24):
        d, p = make(fk, "WORD", size=size); sb = span_bbox(p)
        for side in ("top", "bottom"):
            if side == "bottom":
                rf = lambda m: fitz.Rect(sb.x0 - 10, sb.y1 - m, sb.x1 + 10, sb.y1 + 30)
            else:
                rf = lambda m: fitz.Rect(sb.x0 - 10, sb.y0 - 30, sb.x1 + 10, sb.y0 + m)
            t = bisect(fk, "WORD", rf, 0, sb.height, size=size)
            print(f"  {fk:16s} {size:2d}pt {side:6s} thresh={t:6.3f}  spanH={sb.height:6.3f} ratio={t/sb.height:.4f}")

GL = ".'_^Wilfg"
print("\n== B. per-glyph: does the CHAR bbox (rawdict) differ by glyph, and does removal depend on the glyph's outline?")
for fk in ("helv", "DejaVuSans"):
    d, p = make(fk, ".'_^Wilfg", size=12)
    for c, r in chars(p):
        print(f"  {fk} {c!r} char bbox y {r.y0:.2f}-{r.y1:.2f} h={r.height:.2f} x {r.x0:.2f}-{r.x1:.2f} w={r.width:.2f}")
    sb = span_bbox(p)
    # a band of exactly 15% of the span height at the vertical centre
    for frac in (0.10, 0.101, 0.15, 0.2):
        cy = (sb.y0 + sb.y1) / 2; h = sb.height * frac
        r = fitz.Rect(sb.x0 - 5, cy - h / 2, sb.x1 + 5, cy + h / 2)
        print(f"  {fk} centre band {frac:.3f} of span height -> left: {text_after(fk, GL, r)!r}")
    # a band at the very top: 11% of span height -- '.' and '_' have no outline there
    r = fitz.Rect(sb.x0 - 5, sb.y0, sb.x1 + 5, sb.y0 + 0.11 * sb.height)
    print(f"  {fk} top band 11% -> left: {text_after(fk, GL, r)!r}")
    r = fitz.Rect(sb.x0 - 5, sb.y1 - 0.11 * sb.height, sb.x1 + 5, sb.y1)
    print(f"  {fk} bottom band 11% -> left: {text_after(fk, GL, r)!r}")

print("\n== C. horizontal threshold per glyph width (W, i, l, fi ligature), helv 12pt")
for fk, txt in (("helv", "W"), ("helv", "i"), ("helv", "l"), ("helv", "M"), ("DejaVuSans", "W"), ("DejaVuSans", "i")):
    d, p = make(fk, txt); sb = span_bbox(p)
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y0 - 5, sb.x0 + m, sb.y1 + 5)
    t = bisect(fk, txt, rf, 0, sb.width)
    print(f"  {fk} {txt!r} left thresh={t:.3f} of width {sb.width:.3f} ratio={t/sb.width:.4f}")
# ligature: insert the U+FB01 'fi' ligature with a font that has it
d, p = make("LiberationSerif", "ﬁx")
cs = chars(p); print("  LiberationSerif ligature chars:", [(c, round(r.width, 2)) for c, r in cs])
sb = span_bbox(p)
rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y0 - 5, sb.x0 + m, sb.y1 + 5)
t = bisect("LiberationSerif", "ﬁx", rf, 0, sb.width)
print(f"  ligature left thresh={t:.3f} of span width {sb.width:.3f} (first char w={cs[0][1].width:.3f}) ratio_to_char={t/cs[0][1].width:.4f}")

print("\n== D. area vs height: a CORNER rect covering half the glyph width -- threshold in height")
for fk in ("helv", "DejaVuSans", "cjk"):
    txt = "W" if fk != "cjk" else "漢"
    d, p = make(fk, txt); sb = span_bbox(p)
    cx = (sb.x0 + sb.x1) / 2
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y1 - m, cx, sb.y1 + 30)  # bottom-left quarter-ish
    t = bisect(fk, txt, rf, 0, sb.height)
    print(f"  {fk} half-width corner: height thresh={t:.3f} ratio={t/sb.height:.4f} (area-based would be 0.20, height-based 0.10)")
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y1 - m, sb.x0 + 0.25 * sb.width, sb.y1 + 30)
    t = bisect(fk, txt, rf, 0, sb.height)
    print(f"  {fk} quarter-width corner: height thresh={t:.3f} ratio={t/sb.height:.4f} (area-based would be 0.40)")
    # thin vertical strip full height: width threshold
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y0 - 30, sb.x0 + m, sb.y1 + 30)
    t = bisect(fk, txt, rf, 0, sb.width)
    print(f"  {fk} full-height strip: width thresh={t:.3f} of {sb.width:.3f} ratio={t/sb.width:.4f}")
    # a tiny rect fully INSIDE the glyph box (centre): area threshold?
    for side in (0.2, 0.3, 0.32, 0.4):
        cy = (sb.y0 + sb.y1) / 2
        r = fitz.Rect(cx - side * sb.width / 2, cy - side * sb.height / 2, cx + side * sb.width / 2, cy + side * sb.height / 2)
        print(f"     inner square side {side} (area {side*side:.3f}) -> {text_after(fk, txt, r)!r}")

print("\n== E. rotated text (insert_text rotate=90) and rotated page")
for rot, prot in ((90, 0), (0, 90), (270, 0)):
    d, p = make("helv", "WORD", rotate=rot, page_rot=prot, pt=(200, 300)); sb = span_bbox(p)
    print(f"  rotate={rot} page_rot={prot} span bbox {tuple(round(v,2) for v in sb)} dir", [l["dir"] for b in p.get_text("dict")["blocks"] for l in b["lines"]])
    # strip along the bbox's short axis and long axis
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y0 - 30, sb.x0 + m, sb.y1 + 30)
    t = bisect("helv", "WORD", rf, 0, sb.width, rotate=rot, page_rot=prot, pt=(200, 300))
    print(f"     left strip thresh={t:.3f} of width {sb.width:.3f} ratio={t/sb.width:.4f}")
    rf = lambda m: fitz.Rect(sb.x0 - 30, sb.y0 - 30, sb.x1 + 30, sb.y0 + m)
    t = bisect("helv", "WORD", rf, 0, sb.height, rotate=rot, page_rot=prot, pt=(200, 300))
    print(f"     top strip thresh={t:.3f} of height {sb.height:.3f} ratio={t/sb.height:.4f}")
