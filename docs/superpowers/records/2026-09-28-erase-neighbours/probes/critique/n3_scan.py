"""N3 critique: image-backed (scanned) targets. Options (a) full rect and (b) clipped text removal + full-rect
pixel blank (two redactions), measured on sandwich.pdf and on a synthetic scan with an OCR layer at tight leading.
Also: does text=1 keep text? does the second apply_redactions interact with the first?"""
import pymupdf as fitz
from n1_proto import n1_clip, Refused

FETCH = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/fetch/"
ZOOM = 3


def spans(p):
    return [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"]]


def gray(p, clip=None):
    return p.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=clip)


def dark_count(pix):
    return sum(1 for v in pix.samples if v < 128)


def changed(a, b):
    return sum(1 for x, y in zip(a.samples, b.samples) if abs(x - y) > 40)


def option_a(p, full):
    p.add_redact_annot(full, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)


def option_b(p, clipped, full):
    p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
    p.add_redact_annot(full, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)


def measure(make_doc, tgt_pred, label):
    print(f"--- {label}")
    d0 = make_doc(); p0 = d0[0]
    ss = spans(p0)
    tgt = [s for s in ss if tgt_pred(s)][0]
    tb = fitz.Rect(tgt["bbox"]); full = fitz.Rect(tb.x0, tb.y0, tb.x1 + 0.05, tb.y1)
    try:
        clipped, kept, cl = n1_clip(p0, full, tb)
    except Refused as e:
        print("   N1 refused:", e); return
    nb = [fitz.Rect(s["bbox"]) for s, _ in [(s, 0) for s in ss] if any(x[1] == s["text"] for x in cl)]
    nb_words = set(w[4] for w in p0.get_text("words") if any(fitz.Rect(w[:4]).intersects(r) and fitz.Rect(w[:4]).y0 >= r.y0 - 1 and fitz.Rect(w[:4]).y1 <= r.y1 + 1 for r in nb))
    print(f"   target {tgt['text']!r} bbox {tuple(round(v,1) for v in tb)}; clipped y {clipped.y0:.1f}-{clipped.y1:.1f} kept={kept:.2f}; neighbours={[c[1][:25] for c in cl]}")
    base_full = gray(p0, full); base_nb = [gray(p0, r) for r in nb]
    strips = [fitz.Rect(full.x0, full.y0, full.x1, clipped.y0), fitz.Rect(full.x0, clipped.y1, full.x1, full.y1)]
    strips = [s for s in strips if s.height > 0.01]
    base_strips = [gray(p0, s) for s in strips]
    n_words0 = len(p0.get_text("words"))
    for name, fn in (("(a) full rect", lambda p: option_a(p, full)), ("(b) clipped text + full pixels", lambda p: option_b(p, clipped, full))):
        d = make_doc(); p = d[0]; fn(p)
        words_after = set(w[4] for w in p.get_text("words"))
        tgt_left = [s["text"] for s in spans(p) if abs(s["bbox"][1] - tb.y0) < 0.5 and s["bbox"][0] < tb.x1 and s["bbox"][2] > tb.x0]
        nb_lost = sorted(w for w in nb_words if w not in words_after)
        ink_in_full = dark_count(gray(p, full))
        ink_in_strips = sum(dark_count(gray(p, s)) for s in strips)
        nb_changed = sum(changed(gray(p, r), b) for r, b in zip(nb, base_nb))
        print(f"   {name:32s}: words {n_words0}->{len(p.get_text('words'))}; target text left={tgt_left}; neighbour OCR words lost={nb_lost[:8]}{'...' if len(nb_lost)>8 else ''} ({len(nb_lost)}); "
              f"dark px in full rect {dark_count(base_full)}->{ink_in_full}; in the clipped-off strips {sum(dark_count(b) for b in base_strips)}->{ink_in_strips}; neighbour-bbox px changed={nb_changed}; drawings={len(p.get_drawings())} images={len(p.get_images())}")


print("== sandwich.pdf structure")
d = fitz.open(FETCH + "sandwich.pdf"); p = d[0]
print("   pages", d.page_count, "rect", p.rect, "rot", p.rotation, "images", p.get_image_info()[:1], "n spans", len(spans(p)))
ss = spans(p)
for s in ss[:6]:
    print("   ", repr(s["text"][:40]), s["font"], round(s["size"], 1), [round(v, 1) for v in s["bbox"]], "flags", s["flags"])
# pick a line in the middle of a paragraph: the span whose bbox overlaps its neighbours vertically
cands = []
for i, s in enumerate(ss):
    r = fitz.Rect(s["bbox"])
    ov = [t for t in ss if t is not s and fitz.Rect(t["bbox"]).intersects(r) and abs(t["bbox"][1] - r.y0) > 2]
    if len(ov) >= 2 and len(s["text"]) > 10:
        cands.append((s, len(ov)))
print("   spans with >=2 vertically overlapping neighbours:", len(cands), "of", len(ss))
if cands:
    s = cands[len(cands) // 2][0]
    measure(lambda: fitz.open(FETCH + "sandwich.pdf"), lambda t: t["text"] == s["text"] and abs(t["bbox"][1] - s["bbox"][1]) < 0.01, "sandwich.pdf, span " + repr(s["text"][:30]))
    s = cands[0][0]
    measure(lambda: fitz.open(FETCH + "sandwich.pdf"), lambda t: t["text"] == s["text"] and abs(t["bbox"][1] - s["bbox"][1]) < 0.01, "sandwich.pdf, span " + repr(s["text"][:30]))
else:
    print("   sandwich.pdf has no overlapping OCR lines; using its first long span anyway")
    s = [s for s in ss if len(s["text"]) > 10][0]
    measure(lambda: fitz.open(FETCH + "sandwich.pdf"), lambda t: t["text"] == s["text"], "sandwich.pdf, span " + repr(s["text"][:30]))

print("\n== synthetic scan: 12pt paragraph at pitch 13 rendered at 300dpi, placed as an image, invisible OCR text on top")
LINES = ["ABOVE line with gyp descenders", "TARGET line with gyp descenders", "BELOW line with gyp descenders", "FOURTH line gyp"]


def make_scan():
    src = fitz.open(); sp = src.new_page(width=300, height=120)
    for i, t in enumerate(LINES):
        sp.insert_text((10, 30 + i * 13), t, fontsize=12)
    pix = sp.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace="gray")
    d = fitz.open(); p = d.new_page(width=300, height=120)
    p.insert_image(p.rect, pixmap=pix)
    # OCR layer: invisible text at the same positions
    for i, t in enumerate(LINES):
        p.insert_text((10, 30 + i * 13), t, fontsize=12, render_mode=3)
    return d


measure(make_scan, lambda s: s["text"].startswith("TARGET"), "synthetic scan, pitch 13")

print("\n== does text=1 keep text? does a second apply_redactions interact with the first?")
d = make_scan(); p = d[0]
ss = spans(p); tb = fitz.Rect([s for s in ss if s["text"].startswith("TARGET")][0]["bbox"])
n0 = len(p.get_text("words"))
p.add_redact_annot(tb, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)
print(f"   text=1 alone on the full target rect: words {n0} -> {len(p.get_text('words'))}; target still in layer: {any(s['text'].startswith('TARGET') for s in spans(p))}; image px blanked in rect: dark {dark_count(gray(p, tb))}")
d = make_scan(); p = d[0]
full = fitz.Rect(tb); clipped, kept, cl = n1_clip(p, full, tb)
p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
w1 = len(p.get_text("words")); dr1 = len(p.get_drawings()); im1 = p.get_images()
p.add_redact_annot(full, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)
w2 = len(p.get_text("words")); dr2 = len(p.get_drawings()); im2 = p.get_images()
print(f"   sequence (b): words after 1st {w1}, after 2nd {w2}; drawings after 1st {dr1} (the fill), after 2nd {dr2}; images {len(im1)} -> {len(im2)} xrefs {[i[0] for i in im1]} -> {[i[0] for i in im2]}")
print(f"   reversed order (full text=1 first, then clipped text=0):")
d = make_scan(); p = d[0]
p.add_redact_annot(full, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=0, text=1)
p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print(f"      words {n0} -> {len(p.get_text('words'))}; target left: {any(s['text'].startswith('TARGET') for s in spans(p))}; drawings {len(p.get_drawings())}")
print("   is the first fill (a drawing) removed by the second call's graphics=1 if used? (brief says graphics=0 for the second)")
d = make_scan(); p = d[0]
p.add_redact_annot(clipped, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
p.add_redact_annot(full, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=1)
print(f"      with graphics=1 on the 2nd: drawings {len(p.get_drawings())}, words {len(p.get_text('words'))}")
# and does the first call's fill=None / fill=False avoid painting?
d = make_scan(); p = d[0]
try:
    p.add_redact_annot(clipped, fill=False); p.apply_redactions(images=0, graphics=0, text=0)
    print(f"   fill=False: drawings {len(p.get_drawings())}, words {len(p.get_text('words'))}, dark px in clipped {dark_count(gray(p, clipped))}")
except Exception as e:
    print("   fill=False ->", type(e).__name__, e)
