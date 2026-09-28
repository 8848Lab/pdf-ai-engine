"""Things the brief missed: vector-outline text, Type3 fonts, text in Form XObjects, annotation/widget appearance
text, rotated text via the real engine, a pre-existing OCR-layer document; plus the image re-encoding cost of N3(b)
and a deterministic pre-mutation fingerprint, and a two-samples-on-ink background case."""
import os, sys, hashlib
sys.path.insert(0, "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/critique-erase/wt")
os.environ.setdefault("N1_SIDE", "baseline")
import pymupdf as fitz
from engine.parser import parse
from engine.operations import delete_block, replace_text, _sample_background_color, _n1_clip
from engine.errors import RefusedBeforeMutation
import engine.operations as ops
from harness import build
from dataclasses import replace as dc_replace

FETCH = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/fetch/"
RES = FETCH + "ocrmypdf-16.10.0/tests/resources/"


def spans(p):
    return [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"]]


def dark(p, r, z=3):
    return sum(1 for v in p.get_pixmap(matrix=fitz.Matrix(z, z), colorspace="gray", clip=r).samples if v < 128)


print("== (A) deterministic pre-mutation fingerprint on a refused delete (centre reading forces the refusal)")
ops._N1_SIDE = "centre"
d, p = build([dict(text="LINE0 too close gyp", pt=(72, 100)), dict(text="TARGET too close gyp", pt=(72, 102)), dict(text="LINE2 too close gyp", pt=(72, 104))])
pdf = d.tobytes(); doc, h = parse(pdf); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
fp = lambda: (hashlib.sha1(page.read_contents()).hexdigest(), len(list(page.annots())), h.xref_length(), hashlib.sha1("".join(h.xref_object(i) for i in range(1, h.xref_length())).encode()).hexdigest())
b = fp()
try:
    delete_block(h, 0, tgt)
except RefusedBeforeMutation:
    pass
print("   contents/annots/xref-count/objects unchanged after refusal:", b == fp())
ops._N1_SIDE = "baseline"

print("\n== (B) background sampling: two samples on ink (top sample on a 16pt underscore line above; left sample on a same-line word 2pt left)")
items = [dict(text="________________________", pt=(72, 100), size=16), dict(text="left", pt=(72, 113)), dict(text="TARGET xxxxxxxxxx", pt=(72 + 22.7 + 2, 113)), dict(text="xxxxxxxxxxxxxxxxxxxxxx", pt=(72, 126))]
d, p = build(items); doc, h = parse(d.tobytes()); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET")); tb = fitz.Rect(tgt.bbox)
clipped = _n1_clip(page, tb, tb)
pix = page.get_pixmap(); mx = (tb.x0 + tb.x1) / 2
print(f"   clipped y {clipped.y0:.2f}-{clipped.y1:.2f}; samples: top {pix.pixel(int(mx), int(clipped.y0-3))} bottom {pix.pixel(int(mx), int(clipped.y1+3))} left {pix.pixel(int(tb.x0-3), int((clipped.y0+clipped.y1)/2))} right {pix.pixel(int(tb.x1+3), int((clipped.y0+clipped.y1)/2))}")
print(f"   fill around FULL rect = {tuple(round(v,2) for v in _sample_background_color(page, tb))}; around CLIPPED rect = {tuple(round(v,2) for v in _sample_background_color(page, clipped))}")

print("\n== (C) Type3 font page (ocrmypdf type3_font_nomapping.pdf): span bboxes, the 10% rule, N1")
d = fitz.open(RES + "type3_font_nomapping.pdf"); p = d[0]
ss = spans(p)
print("   n spans", len(ss), "first:", [(s["text"][:20], s["font"], round(s["size"], 2), [round(v, 1) for v in s["bbox"]]) for s in ss[:3]])
if ss:
    s = ss[0]; r = fitz.Rect(s["bbox"])
    for frac in (0.05, 0.09, 0.11, 0.2):
        d2 = fitz.open(RES + "type3_font_nomapping.pdf"); p2 = d2[0]
        p2.add_redact_annot(fitz.Rect(r.x0 - 5, r.y0, r.x1 + 5, r.y0 + frac * r.height)); p2.apply_redactions(images=0, graphics=0, text=0)
        print(f"   top band {frac} of span height -> chars left in that span's line: {len([t for t in spans(p2) if abs(t['bbox'][1]-r.y0)<1])} spans; page words {len(p.get_text('words'))}->{len(p2.get_text('words'))}")
    doc, h = parse(d.tobytes()); pg = h[0]
    blk = doc.pages[0].text_blocks[0]
    try:
        delete_block(h, 0, blk); print(f"   delete_block on Type3 block {blk.text[:20]!r}: ok, words {len(p.get_text('words'))}->{len(pg.get_text('words'))}, ink in bbox {dark(p, fitz.Rect(blk.bbox))}->{dark(pg, fitz.Rect(blk.bbox))}")
    except Exception as e:
        print("   delete_block on Type3:", type(e).__name__, str(e)[:100])

print("\n== (D) text inside a Form XObject: does apply_redactions(text=0) reach it? does N1 see it as a neighbour?")
inner = fitz.open(); ip = inner.new_page(width=300, height=60)
ip.insert_text((10, 20), "XOBJ line one gyp", fontsize=12); ip.insert_text((10, 33), "XOBJ line two gyp", fontsize=12)
d = fitz.open(); p = d.new_page()
p.show_pdf_page(fitz.Rect(72, 80, 372, 140), inner, 0)          # form xobject with two tight lines
p.insert_text((72, 160), "PAGE text line", fontsize=12)
ss = spans(p); print("   spans seen:", [(s["text"], [round(v, 1) for v in s["bbox"]]) for s in ss])
t = [s for s in ss if s["text"] == "XOBJ line one gyp"][0]; r = fitz.Rect(t["bbox"])
p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print("   after redacting 'XOBJ line one' with today's rect: spans:", [s["text"] for s in spans(p)], "; ink in its bbox:", dark(p, r))
d = fitz.open(); p = d.new_page(); p.show_pdf_page(fitz.Rect(72, 80, 372, 140), inner, 0)
ss = spans(p); t = [s for s in ss if s["text"] == "XOBJ line one gyp"][0]; r = fitz.Rect(t["bbox"])
clipped = _n1_clip(p, r, r)
p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print(f"   with N1 clip ({clipped.y0:.1f}-{clipped.y1:.1f}): spans: {[s['text'] for s in spans(p)]}; ink in bbox: {dark(p, r)}")
# nested: xobject inside xobject
mid = fitz.open(); mp = mid.new_page(width=300, height=60); mp.show_pdf_page(mp.rect, inner, 0)
d = fitz.open(); p = d.new_page(); p.show_pdf_page(fitz.Rect(72, 80, 372, 140), mid, 0)
ss = spans(p); t = [s for s in ss if s["text"] == "XOBJ line one gyp"][0]; r = fitz.Rect(t["bbox"])
p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print("   nested xobject, today's rect: spans left:", [s["text"] for s in spans(p)], "; ink:", dark(p, r))

print("\n== (E) widget / annotation appearance text (libreoffice-form.pdf, acroform.pdf)")
for fn in (FETCH + "libreoffice-form.pdf", RES + "acroform.pdf"):
    d = fitz.open(fn); p = d[0]
    ws = list(p.widgets()); ss = spans(p)
    print(f"   {fn.split('/')[-1]}: widgets={len(ws)} annots={len(list(p.annots()))} text spans={len(ss)}; widget values: {[ (w.field_name, w.field_value, [round(v,1) for v in w.rect]) for w in ws[:3]]}")
    tw = [w for w in ws if w.field_type_string in ("Text",) and w.rect.height > 5]
    if tw:
        w = tw[0]
        # is the widget's appearance text in the page's text layer?
        inside = [s["text"] for s in ss if fitz.Rect(s["bbox"]).intersects(w.rect)]
        print(f"      spans overlapping widget {w.field_name!r} rect {[round(v,1) for v in w.rect]}: {inside}")
        # a label span next to the widget: find the nearest span to the left/above
        near = sorted(ss, key=lambda s: abs(s["bbox"][3] - w.rect.y1) + max(0, w.rect.x0 - s["bbox"][2]))[:2]
        print(f"      nearest spans: {[(s['text'], [round(v,1) for v in s['bbox']]) for s in near]}")
        # redact the nearest span with today's rect: does the widget survive (count and value)?
        s = near[0]; r = fitz.Rect(s["bbox"])
        try:
            w.field_value = "TYPED VALUE"; w.update()
        except Exception as e:
            print("      could not set value:", e)
        nb = len(list(p.widgets()))
        p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
        ws2 = list(p.widgets())
        print(f"      after redacting {s['text']!r} (rect intersects widget: {r.intersects(w.rect)}): widgets {nb}->{len(ws2)}; value now {[x.field_value for x in ws2 if x.field_name == w.field_name]}")

print("\n== (F) vector-outline 'text' (glyphs drawn as paths) as the neighbour of a real-text target")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 113), "TARGET real text gyp", fontsize=12)
# neighbour lines drawn as paths: a row of small filled shapes with descenders reaching into the target's band
for i in range(20):
    x = 72 + i * 8
    p.draw_rect(fitz.Rect(x, 91.4, x + 5, 100), fill=(0, 0, 0), color=None)       # 'body' of an outlined glyph above
    p.draw_rect(fitz.Rect(x + 1, 100, x + 3, 102.6), fill=(0, 0, 0), color=None)  # its descender, ends at 102.6 (< target y0 100.1? no: overlaps)
    p.draw_rect(fitz.Rect(x, 117.3, x + 5, 126), fill=(0, 0, 0), color=None)      # ascender of an outlined glyph below (target y1 = 116.6)
ss = spans(p); t = ss[0]; r = fitz.Rect(t["bbox"]); print("   target bbox", [round(v, 2) for v in r], "; drawings:", len(p.get_drawings()))
before = dark(p, fitz.Rect(72, 91, 240, 103)) , dark(p, fitz.Rect(72, 117, 240, 127))
clipped = _n1_clip(p, r, r)
p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
after = dark(p, fitz.Rect(72, 91, 240, 103)), dark(p, fitz.Rect(72, 117, 240, 127))
print(f"   N1 clip = {clipped.y0:.2f}-{clipped.y1:.2f} (no text neighbours -> unclipped); outline-neighbour ink above {before[0]}->{after[0]}, below {before[1]}->{after[1]}; drawings left {len(p.get_drawings())}")

print("\n== (G) rotated text through the real engine (rotate=90 lines at pitch 13, 12pt): delete the middle one")
d, p = build([dict(text=f"{'TARGET' if i == 1 else 'LINE' + str(i)} rotated text gyp", pt=(200 + i * 13, 400), rotate=90) for i in range(3)])
doc, h = parse(d.tobytes()); page = h[0]
tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET")); print("   target dir", tgt.direction, "bbox", [round(v, 1) for v in tgt.bbox])
try:
    delete_block(h, 0, tgt); print("   delete_block: words left:", sorted(w[4] for w in page.get_text("words")))
except RefusedBeforeMutation as e:
    print("   delete_block refused:", str(e)[:90])
d, p = build([dict(text=f"{'TARGET' if i == 1 else 'LINE' + str(i)} rotated text gyp", pt=(200 + i * 15, 400), rotate=90) for i in range(3)])
doc, h = parse(d.tobytes()); page = h[0]; tgt = next(b for b in doc.pages[0].text_blocks if b.text.startswith("TARGET"))
delete_block(h, 0, tgt); print("   pitch 15: delete_block: words left:", sorted(w[4] for w in page.get_text("words")))

print("\n== (H) N3(b) cost: two image re-encodes. sandwich.pdf (1-bit CCITT scan) and a JPEG scan")
for label, mk in (("sandwich.pdf", lambda: fitz.open(FETCH + "sandwich.pdf")),):
    d = mk(); p = d[0]; x = p.get_images()[0][0]
    print(f"   {label}: original image xref {x} filter {d.xref_get_key(x, 'Filter')} stream len {len(d.xref_stream_raw(x))} file {len(d.tobytes())}")
    r = fitz.Rect(248.6, 28.0, 397.7, 48.0)
    for n in (1, 2):
        d = mk(); p = d[0]
        for _ in range(n):
            p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)
        x = p.get_images()[0][0]
        print(f"      after {n} redaction(s) with images=2: image filter {d.xref_get_key(x, 'Filter')} stream len {len(d.xref_stream_raw(x))} file {len(d.tobytes(garbage=3, deflate=True))}")
# JPEG scan
src = fitz.open(); sp = src.new_page(width=300, height=120)
for i in range(4): sp.insert_text((10, 30 + i * 13), "scan line with gyp descenders " + str(i), fontsize=12)
pix = sp.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace="rgb"); jpg = pix.tobytes("jpeg", jpg_quality=60)
d = fitz.open(); p = d.new_page(width=300, height=120); p.insert_image(p.rect, stream=jpg); x = p.get_images()[0][0]
print(f"   JPEG scan: filter {d.xref_get_key(x, 'Filter')} stream {len(d.xref_stream_raw(x))}")
for n in (1, 2):
    d = fitz.open(); p = d.new_page(width=300, height=120); p.insert_image(p.rect, stream=jpg)
    for _ in range(n):
        p.add_redact_annot(fitz.Rect(10, 33, 190, 43), fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)
    x = p.get_images()[0][0]
    print(f"      after {n} redaction(s): filter {d.xref_get_key(x, 'Filter')} stream {len(d.xref_stream_raw(x))}")
