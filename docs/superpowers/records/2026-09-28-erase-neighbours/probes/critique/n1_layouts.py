"""N1 critique: real layouts. Each case prints today's (unclipped) erase and N1's clipped erase,
compared against the ideal page (built without the target) in exported words and pixels."""
import pymupdf as fitz
from harness import run_case, build, find_target_span, erase, words, render, pix_diff
from n1_proto import n1_clip, Refused

L = lambda i, pitch, text, **kw: dict(text=text, pt=(72, 100 + i * pitch), **kw)

print("== 1. five-line paragraph, 12pt helv, leading 1.0-1.6, target = middle / first / last")
for lead in (1.0, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5, 1.6):
    pitch = 12 * lead
    for which in (2, 0, 4):
        items = [L(i, pitch, f"{'TARGET' if i == which else 'LINE' + str(i)} quick brown fox jumps gyp {i}", target=(i == which)) for i in range(5)]
        run_case(f"leading {lead} pitch {pitch:.1f} target line {which}", items)

print("\n== 2. mixed sizes on adjacent lines")
for above, tgt, below, pitch in ((18, 12, 8, 16), (10, 24, 10, 20), (8, 12, 18, 14), (12, 12, 12, 13)):
    y = 100
    items = [dict(text="ABOVE big line gyp", pt=(72, y), size=above),
             dict(text="TARGET line gyp", pt=(72, y + pitch), size=tgt, target=True),
             dict(text="BELOW line gyp", pt=(72, y + 2 * pitch), size=below)]
    run_case(f"sizes above={above} target={tgt} below={below} pitch={pitch}", items)

print("\n== 3. superscript / subscript")
# 3a: superscript belonging to the TARGET line (must still be removed)
for pitch in (18, 14.4):
    items = [dict(text="ABOVE line gyp", pt=(72, 100)),
             dict(text="TARGET E = mc", pt=(72, 100 + pitch), target=True),
             dict(text="2", pt=(72 + 78, 100 + pitch - 5), size=7),  # superscript of the target line
             dict(text="BELOW line gyp", pt=(72, 100 + 2 * pitch))]
    run_case(f"3a target's own superscript, pitch {pitch}", items)
    run_case(f"3a (side=edges) target's own superscript, pitch {pitch}", items, side="edges")
# 3b: subscript belonging to the line ABOVE, dipping into the target's band
for pitch in (18, 14.4):
    items = [dict(text="ABOVE line H", pt=(72, 100)),
             dict(text="2", pt=(72 + 72, 100 + 3), size=7),  # subscript of the ABOVE line
             dict(text="O and more", pt=(72 + 76, 100)),
             dict(text="TARGET line gyp", pt=(72, 100 + pitch), target=True),
             dict(text="BELOW line gyp", pt=(72, 100 + 2 * pitch))]
    run_case(f"3b neighbour's subscript, pitch {pitch}", items)
# 3c: superscript belonging to the line BELOW reaching up
for pitch in (18, 14.4):
    items = [dict(text="ABOVE line gyp", pt=(72, 100)),
             dict(text="TARGET line gyp", pt=(72, 100 + pitch), target=True),
             dict(text="BELOW x", pt=(72, 100 + 2 * pitch)),
             dict(text="2", pt=(72 + 46, 100 + 2 * pitch - 5), size=7)]
    run_case(f"3c neighbour's superscript, pitch {pitch}", items)

print("\n== 4. drop cap (36pt 'T' spanning three 12pt lines at pitch 14.4), target = 2nd line")
items = [dict(text="T", pt=(72, 100 + 14.4 * 2 - 2), size=36),
         dict(text="he first line of text", pt=(72 + 26, 100)),
         dict(text="TARGET second line", pt=(72 + 26, 100 + 14.4), target=True),
         dict(text="third line of text", pt=(72 + 26, 100 + 28.8)),
         dict(text="fourth line of text", pt=(72, 100 + 43.2))]
run_case("drop cap", items)

print("\n== 5. table rows (10pt text, 13pt row pitch), with and without borders")
for borders in (False, True):
    items = []
    for r in range(4):
        y = 100 + r * 13
        for c, x in enumerate((72, 200, 330)):
            items.append(dict(text=("TARGET" if (r == 1 and c == 1) else f"r{r}c{c}") + " cell gyp", pt=(x + 3, y), size=10, target=(r == 1 and c == 1)))
        if borders:
            items.append(dict(kind="line", a=(70, y - 10.5), b=(460, y - 10.5), width=0.5))
    if borders:
        items.append(dict(kind="line", a=(70, 100 + 3 * 13 + 2.5), b=(460, 100 + 3 * 13 + 2.5), width=0.5))
        for x in (70, 198, 328, 460):
            items.append(dict(kind="line", a=(x, 89.5), b=(x, 141.5), width=0.5))
    run_case(f"table borders={borders}", items)

print("\n== 6. two columns, column B offset by half a pitch (overlaps vertically, not horizontally)")
for pitch in (14.4, 12):
    items = []
    for i in range(4):
        items.append(dict(text=("TARGET" if i == 1 else f"A{i}") + " column text gyp", pt=(72, 100 + i * pitch), target=(i == 1)))
        items.append(dict(text=f"B{i} other column gyp", pt=(320, 100 + pitch / 2 + i * pitch)))
    run_case(f"two columns pitch {pitch}", items)
# 6b: column B starts where column A ends horizontally (touching) -- clipped or not?
items = [dict(text="TARGET column text", pt=(72, 100), target=True), dict(text="B other column", pt=(72 + 100, 100 - 7))]
run_case("6b same-line-ish neighbour overlapping vertically, starting at target x1 + 4", items)

print("\n== 7. rotated page (90/180/270) and a cropped page, paragraph at pitch 13")
for rot in (90, 180, 270):
    items = [L(i, 13, f"{'TARGET' if i == 1 else 'LINE' + str(i)} rotated page gyp", target=(i == 1)) for i in range(3)]
    run_case(f"page rotation {rot}", items, page_rot=rot)
items = [L(i, 13, f"{'TARGET' if i == 1 else 'LINE' + str(i)} cropped page gyp", target=(i == 1)) for i in range(3)]
run_case("cropbox (50,50,500,700)", items, cropbox=(50, 50, 500, 700))
run_case("cropbox (50,50,500,700) + rotation 90", items, cropbox=(50, 50, 500, 700), page_rot=90)

print("\n== 8. ROTATED TEXT: lines written with rotate=90 stacked left-to-right at pitch 13 (neighbours are beside, not above)")
items = [dict(text=f"{'TARGET' if i == 1 else 'LINE' + str(i)} rotated text gyp", pt=(200 + i * 13, 400), rotate=90, target=(i == 1)) for i in range(3)]
run_case("rotated text 90, pitch 13", items)
items = [dict(text=f"{'TARGET' if i == 1 else 'LINE' + str(i)} rotated text gyp", pt=(200 + i * 13, 300), rotate=270, target=(i == 1)) for i in range(3)]
run_case("rotated text 270, pitch 13", items)

print("\n== 9. the real floor: at what kept fraction does the clipped band still remove every target char? (12pt helv, band centred)")
for fk in ("helv", "tiro", "cour"):
    d, p = build([dict(text="TARGET gyp .'^_ Wil", pt=(72, 100), font=fk)])
    s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    tb = fitz.Rect(s["bbox"]); cy = (tb.y0 + tb.y1) / 2
    lo, hi = 0.0, 1.0
    for _ in range(25):
        m = (lo + hi) / 2
        d2, p2 = build([dict(text="TARGET gyp .'^_ Wil", pt=(72, 100), font=fk)])
        h = tb.height * m
        erase(p2, fitz.Rect(tb.x0, cy - h / 2, tb.x1 + 0.05, cy + h / 2))
        if p2.get_text().strip(): lo = m
        else: hi = m
    # and an off-centre band (at the top edge), which N1 produces for a last line / first line
    lo2, hi2 = 0.0, 1.0
    for _ in range(25):
        m = (lo2 + hi2) / 2
        d2, p2 = build([dict(text="TARGET gyp .'^_ Wil", pt=(72, 100), font=fk)])
        erase(p2, fitz.Rect(tb.x0, tb.y0, tb.x1 + 0.05, tb.y0 + tb.height * m))
        if p2.get_text().strip(): lo2 = m
        else: hi2 = m
    print(f"  {fk}: centred band min kept fraction = {hi:.4f}; top-edge band min = {hi2:.4f}")
