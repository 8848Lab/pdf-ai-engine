"""N2 (P1) critique: the owner's form notch, underlines, table borders, strike-throughs, highlight rects.
Prototype of N2 literally from the brief: a drawn horizontal segment crossing the rect within its top or
bottom 15%, extending beyond the target on both sides or starting left of it, clips the rect to stop just
short of the stroke."""
import sys
sys.path.insert(0, "/home/user/pdf-ai-engine")
import pymupdf as fitz
from engine.operations import _drawing_edges
from harness import build, erase, render, pix_diff, words
from n1_proto import n1_clip, Refused

EPS = 0.05


def n2_clip(page, rect, tb, frac=0.15):
    y0, y1 = rect.y0, rect.y1
    h = tb.height
    top_band = (rect.y0, rect.y0 + frac * h)
    bot_band = (rect.y1 - frac * h, rect.y1)
    hits = []
    for item in page.get_drawings():
        w = item.get("width") or 0.0
        for seg in _drawing_edges(item):
            if seg.height > 1.0:  # not horizontal
                continue
            if not (seg.x1 > rect.x0 and seg.x0 < rect.x1):
                continue
            layout = (seg.x0 < tb.x0 and seg.x1 > tb.x1) or seg.x0 < tb.x0
            if not layout:
                continue
            s0, s1 = seg.y0 - w / 2, seg.y1 + w / 2  # the stroke's extent
            if s1 > top_band[0] and s0 < top_band[1]:
                y0 = max(y0, s1 + EPS); hits.append(("top", round(seg.y0, 2), w))
            elif s1 > bot_band[0] and s0 < bot_band[1]:
                y1 = min(y1, s0 - EPS); hits.append(("bottom", round(seg.y0, 2), w))
    kept = (y1 - y0) / h
    if kept < frac:
        raise Refused(f"N2 kept {kept:.3f}")
    return fitz.Rect(rect.x0, y0, rect.x1, y1), kept, hits


def run(name, items, use_n1=True, use_n2=True, pad=0.05):
    d_i, p_i = build(items, omit_target=True); iw = words(p_i); ip = render(p_i)
    out = {}
    for mode in ("today", "n1+n2" if use_n1 else "n2"):
        d, p = build(items)
        t = [it for it in items if it.get("target")][0]
        s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"] if s["text"] == t["text"]][0]
        tb = fitz.Rect(s["bbox"]); rect = fitz.Rect(tb.x0, tb.y0, tb.x1 + pad, tb.y1)
        info = ""
        if mode != "today":
            try:
                if use_n1:
                    rect, k1, c1 = n1_clip(p, rect, tb); info += f" n1kept={k1:.2f}"
                if use_n2:
                    rect, k2, hits = n2_clip(p, rect, tb); info += f" n2kept={k2:.2f} hits={hits}"
            except Refused as e:
                out[mode] = f"REFUSED {e}"; continue
        erase(p, rect)
        lo, dm = pix_diff(render(p), ip)
        w = words(p)
        out[mode] = f"rect y {rect.y0:.2f}-{rect.y1:.2f} text missing={[x for x in iw if x not in w]} leftover={[x for x in w if x not in iw]} pixels leftover={lo} damage={dm}{info}"
        # drawings left after
        out[mode] += f" drawings_after={len(p.get_drawings())}"
    print(f"--- {name}")
    for k, v in out.items():
        print(f"   {k:6s}: {v}")


print("== 1. the owner's form: label (72,100), box (160,86,400,106) w=0.8, value 'Jo Lee' 14pt at (164,100)")
form = [dict(text="Student Name:", pt=(72, 100)),
        dict(kind="rect", rect=(160, 86, 400, 106), width=0.8),
        dict(text="Jo Lee", pt=(164, 100), size=14, target=True)]
d, p = build(form)
s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"] if s["text"] == "Jo Lee"][0]
print("   value bbox:", tuple(round(v, 2) for v in s["bbox"]), "box top stroke 85.6-86.4; 15% of h =", round(0.15 * (s["bbox"][3] - s["bbox"][1]), 2))
run("owner's form (N2 only, no text neighbours)", form)
# the same form, 12pt value (bbox inside the box) -- no notch expected either way
run("form with a 12pt value", [form[0], form[1], dict(text="Jo Lee", pt=(164, 100), size=12, target=True)])
# a taller value: 18pt, whose bbox reaches 2.35pt above the border, top 15% band = 3.7pt
run("form with an 18pt value", [form[0], form[1], dict(text="Jo Lee", pt=(164, 101), size=18, target=True)])
# a much taller value (24pt) where the border crosses BELOW the top 15% band of the rect
run("form with a 24pt value (border crosses at 21% from the top)", [form[0], form[1], dict(text="Jo Lee", pt=(164, 102), size=24, target=True)])

print("\n== 2. underlines")
d, p = build([dict(text="underlined target", pt=(72, 100))])
s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]; x1 = s["bbox"][2]
run("underline exactly the target's width at baseline+1.5 (loose leading)",
    [dict(text="underlined target", pt=(72, 100), target=True), dict(kind="line", a=(72, 101.5), b=(x1, 101.5), width=0.6)])
run("underline exactly the target's width, TIGHT leading (pitch 13)",
    [dict(text="above line gyp", pt=(72, 87)), dict(text="underlined target", pt=(72, 100), target=True), dict(kind="line", a=(72, 101.5), b=(x1, 101.5), width=0.6), dict(text="below line gyp", pt=(72, 113))])
run("underline wider than the target (starts 10pt left), at baseline+1.5",
    [dict(text="underlined target", pt=(72, 100), target=True), dict(kind="line", a=(62, 101.5), b=(x1 + 10, 101.5), width=0.6)])
run("underline exactly the target's width at baseline+2.5 (bottom 15% band starts at y1-2.47)",
    [dict(text="underlined target", pt=(72, 100), target=True), dict(kind="line", a=(72, 102.5), b=(x1, 102.5), width=0.6)])

print("\n== 3. table borders (10pt text, 13pt row pitch, rules 0.5pt)")
items = []
for r in range(4):
    y = 100 + r * 13
    for c, x in enumerate((72, 200, 330)):
        items.append(dict(text=("TARGET" if (r == 1 and c == 1) else f"r{r}c{c}") + " cell gyp", pt=(x + 3, y), size=10, target=(r == 1 and c == 1)))
    items.append(dict(kind="line", a=(70, y - 10.5), b=(460, y - 10.5), width=0.5))
items.append(dict(kind="line", a=(70, 100 + 3 * 13 + 2.5), b=(460, 100 + 3 * 13 + 2.5), width=0.5))
for x in (70, 198, 328, 460):
    items.append(dict(kind="line", a=(x, 89.5), b=(x, 141.5), width=0.5))
run("table with borders", items)
# a table drawn as filled/stroked RECTANGLES per cell (LibreOffice style) rather than lines
items2 = [it for it in items if it.get("kind") != "line"]
for r in range(4):
    for x0, x1 in ((70, 198), (198, 328), (328, 460)):
        items2.append(dict(kind="rect", rect=(x0, 89.5 + r * 13, x1, 89.5 + (r + 1) * 13), width=0.5))
run("table drawn as cell rectangles", items2)

print("\n== 4. strike-throughs through the target (must still be removed)")
d, p = build([dict(text="struck target", pt=(72, 100))])
s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]; x1 = s["bbox"][2]
run("strike-through exactly the target's width at baseline-4",
    [dict(text="struck target", pt=(72, 100), target=True), dict(kind="line", a=(72, 96), b=(x1, 96), width=0.8)])
run("strike-through 2pt wider than the target on both sides",
    [dict(text="struck target", pt=(72, 100), target=True), dict(kind="line", a=(70, 96), b=(x1 + 2, 96), width=0.8)])
run("strike-through exactly the target's width, TIGHT leading (pitch 12)",
    [dict(text="above gyp", pt=(72, 88)), dict(text="struck target", pt=(72, 100), target=True), dict(kind="line", a=(72, 96), b=(x1, 96), width=0.8), dict(text="below gyp", pt=(72, 112))])

print("\n== 5. highlight rectangle behind the target")
for name, hl in (("highlight = bbox exactly", (72, 87.1, x1, 103.59)),
                 ("highlight inset (cap-height: baseline-9 .. baseline+2.5)", (72, 91, x1, 102.5)),
                 ("highlight 2pt larger all round", (70, 85.1, x1 + 2, 105.59)),
                 ("highlight 5pt larger all round", (67, 82.1, x1 + 5, 108.59))):
    run(name, [dict(kind="rect", rect=hl, color=None, fill=(1, 1, 0), width=0), dict(text="struck target", pt=(72, 100), target=True)])
