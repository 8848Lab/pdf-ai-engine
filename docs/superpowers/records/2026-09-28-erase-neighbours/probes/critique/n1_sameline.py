"""Three follow-ups: (a) why did a centred band of ~0 height remove the whole line? (b) N1 literal on the
existing 'adjacent span on the same line' fixture (bold label + body); (c) does get_text('dict') put a
superscript in the same line as the target?"""
import pymupdf as fitz
from harness import build, erase
from n1_proto import n1_clip, Refused

print("== (a) centred bands of small height, 12pt helv, and degenerate rects")
d, p = build([dict(text="TARGET gyp", pt=(72, 100))])
s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
tb = fitz.Rect(s["bbox"]); cy = (tb.y0 + tb.y1) / 2
for frac in (0.0, 0.001, 0.01, 0.05, 0.09, 0.099, 0.101, 0.11):
    d2, p2 = build([dict(text="TARGET gyp", pt=(72, 100))])
    h = tb.height * frac
    r = fitz.Rect(tb.x0, cy - h / 2, tb.x1, cy + h / 2)
    try:
        erase(p2, r); left = repr(p2.get_text().strip())
    except Exception as e:
        left = f"EXC {type(e).__name__}: {e}"
    print(f"   centred frac {frac:<6} rect h={r.height:.3f} -> {left}")
# same, but band placed at 30% from the top (not centred), with heights 5%, 9%, 11%
for frac in (0.05, 0.09, 0.11):
    d2, p2 = build([dict(text="TARGET gyp", pt=(72, 100))])
    y = tb.y0 + 0.3 * tb.height; h = tb.height * frac
    erase(p2, fitz.Rect(tb.x0, y, tb.x1, y + h))
    print(f"   band at 30% from top, frac {frac} -> {p2.get_text().strip()!r}")
# a rect fully inside the glyph box vertically AND horizontally, tiny: 2% x 2% at the centre
for side in (0.02, 0.05, 0.09, 0.11):
    d2, p2 = build([dict(text="W", pt=(72, 100))])
    s = [s for b in p2.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    b = fitz.Rect(s["bbox"]); cx = (b.x0 + b.x1) / 2; cy = (b.y0 + b.y1) / 2
    w = b.width * side / 2; h = b.height * side / 2
    erase(p2, fitz.Rect(cx - w, cy - h, cx + w, cy + h))
    print(f"   inner square side {side} (both axes) centred on W -> {p2.get_text().strip()!r}")
# a rect fully inside the glyph box, offset from the centre: 5% x 5% at 30%/30%
d2, p2 = build([dict(text="W", pt=(72, 100))])
s = [s for b in p2.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
b = fitz.Rect(s["bbox"])
x = b.x0 + 0.3 * b.width; y = b.y0 + 0.3 * b.height
erase(p2, fitz.Rect(x, y, x + 0.05 * b.width, y + 0.05 * b.height))
print(f"   inner 5%x5% square at 30%/30% (not containing the centre) -> {p2.get_text().strip()!r}")
d2, p2 = build([dict(text="W", pt=(72, 100))])
x = b.x0 + 0.48 * b.width; y = b.y0 + 0.48 * b.height
erase(p2, fitz.Rect(x, y, x + 0.04 * b.width, y + 0.04 * b.height))
print(f"   inner 4%x4% square containing the centre -> {p2.get_text().strip()!r}")

print("\n== (b) N1 literal on a bold label immediately followed by body text on the same line")
d, p = build([dict(text="WARNING:", pt=(72, 100), font="hebo"), ])
s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
x1 = s["bbox"][2]
for gap in (0.0, 0.03, 0.2, 2.0):
    d, p = build([dict(text="WARNING:", pt=(72, 100), font="hebo"), dict(text="do not touch the body", pt=(x1 + gap, 100))])
    spans = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]]
    tgt = [s for s in spans if s["text"].startswith("WARNING")][0]
    tb = fitz.Rect(tgt["bbox"]); rect = fitz.Rect(tb.x0, tb.y0, tb.x1 + 0.05, tb.y1)
    for side in ("centre", "edges"):
        try:
            r, kept, cl = n1_clip(p, rect, tb, side=side); out = f"kept={kept:.2f} clip={cl}"
        except Refused as e:
            out = f"REFUSED: {e}"
        print(f"   gap {gap}pt side={side}: n_lines_in_dict={sum(len(b['lines']) for b in p.get_text('dict')['blocks'])} -> {out}")

print("\n== (c) is a superscript grouped into the target's line by get_text('dict')?")
d, p = build([dict(text="TARGET E = mc", pt=(72, 100)), dict(text="2", pt=(72 + 78, 95), size=7)])
for b in p.get_text("dict")["blocks"]:
    for l in b["lines"]:
        print("   line:", [(s["text"], s["size"], tuple(round(v, 1) for v in s["bbox"])) for s in l["spans"]])
print("   words:", p.get_text("words"))
