"""Interactions: (1) widen path draws at the original baseline -- old ink under the new text after a clipped erase?
(2) background sampling (C21') around the CLIPPED rect lands inside the neighbours' bboxes. (3) the refusal is
pre-mutation. (4) P4: how far does the redaction fill bleed past its rect?"""
import os, sys, hashlib
sys.path.insert(0, "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/critique-erase/wt")
os.environ.setdefault("N1_SIDE", "baseline")
import pymupdf as fitz
from engine.parser import parse
from engine.operations import replace_text, delete_block, move_block, _sample_background_color
from engine.errors import RefusedBeforeMutation
from harness import build, render, pix_diff, words

ZOOM = 3

print("== (1) replace_text (widen path, real engine with the N1 prototype, reading =", os.environ["N1_SIDE"], ") on a pitch-13 paragraph")
items = [dict(text=f"{'TARGET' if i == 1 else 'LINE' + str(i)} quick brown gyp {i}", pt=(72, 100 + i * 13)) for i in range(3)]
d, p = build(items); pdf = d.tobytes()
doc, h = parse(pdf); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
print("   target block:", tgt.text, tgt.origin, tgt.direction)
replace_text(h, 0, tgt, "TARGET replaced text")
# ideal: the page without the target line, plus the new text drawn at the same origin
di, pi = build([it for it in items if not it["text"].startswith("TARGET")]); pi.insert_text(tgt.origin, "TARGET replaced text", fontsize=12)
lo, dm = pix_diff(page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray"), pi.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray"))
print(f"   words after: {sorted(w[4] for w in page.get_text('words'))}\n   pixels vs ideal: leftover={lo} damage={dm}")
# the box path (hand-built TextBlock, origin None), same page
doc, h = parse(pdf); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
from dataclasses import replace as dc_replace
tgt_box = dc_replace(tgt, origin=None, direction=None)
replace_text(h, 0, tgt_box, "TARGET replaced text")
lo, dm = pix_diff(page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray"), pi.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray"))
print(f"   box path: words after: {sorted(w[4] for w in page.get_text('words'))}\n   pixels vs ideal: leftover={lo} damage={dm} (box path draws via insert_textbox, so a small diff vs insert_text is expected)")
# delete_block and move_block
for op in ("delete", "move"):
    doc, h = parse(pdf); page = h[0]
    tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
    if op == "delete":
        delete_block(h, 0, tgt)
    else:
        move_block(h, 0, tgt, target_position=(72, 400))
    print(f"   {op}_block: words after: {sorted(w[4] for w in page.get_text('words'))}")

print("\n== (2) background sampling around the clipped rect: neighbours with descenders/ascenders at the sample x")
# target 'xxxx' between lines whose glyph at the rect's horizontal midpoint is a descender 'g' (above) / a tall 'l' (below)
for above_txt, below_txt in (("gggggggggggggggggg", "llllllllllllllllll"), ("xxxxxxxxxxxxxxxxxx", "xxxxxxxxxxxxxxxxxx")):
    items = [dict(text=above_txt, pt=(72, 100)), dict(text="TARGET xxxxxxxxxx", pt=(72, 113)), dict(text=below_txt, pt=(72, 126))]
    d, p = build(items); pdf = d.tobytes(); doc, h = parse(pdf); page = h[0]
    tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
    tb = fitz.Rect(tgt.bbox)
    from engine.operations import _n1_clip
    clipped = _n1_clip(page, tb, tb)
    full_fill = _sample_background_color(page, tb); clip_fill = _sample_background_color(page, clipped)
    print(f"   above={above_txt[:6]}.. below={below_txt[:6]}..: clipped y {clipped.y0:.2f}-{clipped.y1:.2f}; sample fill around FULL rect={tuple(round(v,2) for v in full_fill)}, around CLIPPED rect={tuple(round(v,2) for v in clip_fill)}")
    # what pixel is 3pt above the clipped top, at the midpoint?
    pix = page.get_pixmap(); mx = (tb.x0 + tb.x1) / 2
    print(f"      pixel 3pt above clipped top: {pix.pixel(int(mx), int(clipped.y0 - 3))}, 3pt below clipped bottom: {pix.pixel(int(mx), int(clipped.y1 + 3))}")

print("\n== (3) the refusal is pre-mutation: fingerprint of the page before/after a refused delete_block")
os.environ["N1_SIDE"] = "centre"
import importlib, engine.operations as ops
ops._N1_SIDE = "centre"
d, p = build([dict(text="LINE0 too close gyp", pt=(72, 100)), dict(text="TARGET too close gyp", pt=(72, 102)), dict(text="LINE2 too close gyp", pt=(72, 104))])
pdf = d.tobytes(); doc, h = parse(pdf); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
fp = lambda: (hashlib.sha1(page.read_contents()).hexdigest(), len(list(page.annots())), h.xref_length(), hashlib.sha1(h.tobytes()).hexdigest())
before = fp()
try:
    delete_block(h, 0, tgt); print("   NOT refused")
except RefusedBeforeMutation as e:
    print("   refused:", str(e)[:80])
after = fp()
print("   fingerprint unchanged:", before == after, before[:2], after[:2])
for op in ("replace_widen", "replace_box", "move"):
    doc, h = parse(pdf); page = h[0]; tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
    before = fp()
    try:
        if op == "replace_widen": replace_text(h, 0, tgt, "X")
        elif op == "replace_box": replace_text(h, 0, dc_replace(tgt, origin=None), "X")
        else: move_block(h, 0, tgt, target_position=(72, 400))
        print("  ", op, "NOT refused")
    except RefusedBeforeMutation as e:
        print("  ", op, "refused; fingerprint unchanged:", before == fp())
ops._N1_SIDE = "baseline"

print("\n== (4) P4: fill bleed. A black page; a white redaction fill at exact rect; where does white start?")
d = fitz.open(); p = d.new_page(width=200, height=200)
p.draw_rect(p.rect, color=None, fill=(0, 0, 0))
r = fitz.Rect(50, 100.0, 150, 120.0)
p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=0, graphics=0, text=0)
z = 20
pix = p.get_pixmap(matrix=fitz.Matrix(z, z), colorspace="gray")
col = [pix.pixel(100 * z, y)[0] for y in range(95 * z, 125 * z)]
first_white = next(i for i, v in enumerate(col) if v > 128) / z + 95
last_white = (len(col) - 1 - next(i for i, v in enumerate(reversed(col)) if v > 128)) / z + 95
row = [pix.pixel(x, 110 * z)[0] for x in range(45 * z, 155 * z)]
fw = next(i for i, v in enumerate(row) if v > 128) / z + 45
lw = (len(row) - 1 - next(i for i, v in enumerate(reversed(row)) if v > 128)) / z + 45
print(f"   rect y 100-120: white spans y {first_white:.2f}..{last_white:.2f} (bleed top {100-first_white:.2f}pt, bottom {last_white+1/z-120:.2f}pt); x 50-150: white x {fw:.2f}..{lw+1/z:.2f}")
print("   drawing items after redaction:", [(it["rect"], it.get("width")) for it in p.get_drawings()][-1:])
