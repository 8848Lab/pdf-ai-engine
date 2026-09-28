"""Type3: where is MuPDF's glyph box relative to the span bbox? Shared Form XObject placed twice: does redacting
one placement change the other? Redacting a widget's own appearance text."""
import pymupdf as fitz

FETCH = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/fetch/"
RES = FETCH + "ocrmypdf-16.10.0/tests/resources/"


def spans(p):
    return [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"]]


def dark(p, r, z=4):
    return sum(1 for v in p.get_pixmap(matrix=fitz.Matrix(z, z), colorspace="gray", clip=r).samples if v < 128)


print("== Type3 (type3_font_nomapping.pdf): bisect the top/bottom/left band needed to remove the glyphs")
d = fitz.open(RES + "type3_font_nomapping.pdf"); p = d[0]
s = spans(p)[0]; r = fitz.Rect(s["bbox"]); print("   span bbox", [round(v, 2) for v in r], "size", s["size"], "origin", s["origin"], "ascender/descender", s.get("ascender"), s.get("descender"))
print("   chars:", [(c["c"], [round(v, 2) for v in c["bbox"]]) for b in p.get_text("rawdict")["blocks"] for l in b["lines"] for sp in l["spans"] for c in sp["chars"]])
print("   ink rows (y with dark px) in bbox +-5pt:", [y for y in range(int(r.y0) - 5, int(r.y1) + 6) if dark(p, fitz.Rect(r.x0 - 5, y, r.x1 + 5, y + 1)) > 0])
print("   Type3 FontMatrix/FontBBox:", d.xref_get_key(12, "FontMatrix"), d.xref_get_key(12, "FontBBox"))


def gone(rect):
    d2 = fitz.open(RES + "type3_font_nomapping.pdf"); p2 = d2[0]
    p2.add_redact_annot(rect); p2.apply_redactions(images=0, graphics=0, text=0)
    return len(spans(p2)) == 0


for name, rf, span_len in (("top", lambda m: fitz.Rect(r.x0 - 5, r.y0 - 30, r.x1 + 5, r.y0 + m), r.height),
                           ("bottom", lambda m: fitz.Rect(r.x0 - 5, r.y1 - m, r.x1 + 5, r.y1 + 30), r.height),
                           ("left", lambda m: fitz.Rect(r.x0 - 30, r.y0 - 5, r.x0 + m, r.y1 + 5), r.width)):
    lo, hi = 0.0, span_len * 2
    if not gone(rf(hi)):
        print(f"   {name}: not even removed at {hi:.2f}pt overlap"); continue
    for _ in range(30):
        m = (lo + hi) / 2
        if gone(rf(m)): hi = m
        else: lo = m
    print(f"   {name}: removed once the band reaches {hi:.3f}pt into the span box ({hi/span_len:.3f} of its {name in ('top','bottom') and 'height' or 'width'} {span_len:.2f})")
# a rect of the span's inner 80% band only (what an N1 clip could hand over)
cy = (r.y0 + r.y1) / 2
for frac in (0.15, 0.3, 0.5, 0.8):
    h = r.height * frac
    print(f"   centred band {frac} of span height: removed = {gone(fitz.Rect(r.x0 - 5, cy - h / 2, r.x1 + 5, cy + h / 2))}")

print("\n== shared Form XObject placed twice on one page, and on two pages")
inner = fitz.open(); ip = inner.new_page(width=300, height=40); ip.insert_text((10, 20), "SHARED text gyp", fontsize=12)
d = fitz.open(); p = d.new_page()
p.show_pdf_page(fitz.Rect(72, 80, 372, 120), inner, 0); p.show_pdf_page(fitz.Rect(72, 300, 372, 340), inner, 0)
xo = p.get_xobjects(); print("   xobjects on page:", [(x[0], x[1]) for x in xo])
ss = spans(p); print("   spans:", [(s["text"], [round(v, 1) for v in s["bbox"]]) for s in ss])
r = fitz.Rect(ss[0]["bbox"])
p.add_redact_annot(r, fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print("   after redacting the FIRST placement: spans left:", [(s["text"], round(s["bbox"][1], 1)) for s in spans(p)], "; ink in 2nd placement:", dark(p, fitz.Rect(72, 300, 372, 340)))
d = fitz.open(); d.new_page(); d.new_page(); p1 = d[0]; p2 = d[1]
p1.show_pdf_page(fitz.Rect(72, 80, 372, 120), inner, 0); p2 = d[1]; p2.show_pdf_page(fitz.Rect(72, 80, 372, 120), inner, 0); p1 = d[0]
print("   two pages: xobject xrefs", [x[0] for x in p1.get_xobjects()], [x[0] for x in p2.get_xobjects()])
r = fitz.Rect(spans(p1)[0]["bbox"]); p1.add_redact_annot(r, fill=(1, 1, 1)); p1.apply_redactions(images=2, graphics=1, text=0)
p2 = d[1]; print("   after redacting on page 1: page 2 spans:", [s["text"] for s in spans(p2)], "; page 2 ink:", dark(p2, fitz.Rect(72, 80, 372, 120)))
# and the real-world variant: the same XObject xref referenced from both pages' resources (insert_pdf/show_pdf_page dedupes?)
d = fitz.open(); d.new_page(); d.new_page(); p1 = d[0]; p2 = d[1]
xref = p1.show_pdf_page(fitz.Rect(72, 80, 372, 120), inner, 0)
p2.show_pdf_page(fitz.Rect(72, 80, 372, 120), inner, 0, oc=0)
print("   show_pdf_page returned xref", xref, "page2 xobjects", [x[0] for x in p2.get_xobjects()])

print("\n== redacting a widget's own appearance text / a label whose rect touches a widget (libreoffice-form.pdf)")
d = fitz.open(FETCH + "libreoffice-form.pdf"); p = d[0]
w = [w for w in p.widgets() if w.field_name == "First Name"][0]
ss = spans(p); alice = [s for s in ss if s["text"] == "Alice"][0]
print("   'Alice' span bbox", [round(v, 1) for v in alice["bbox"]], "widget rect", [round(v, 1) for v in w.rect], "; is 'Alice' in page content stream?", b"Alice" in p.read_contents(), "; in widget AP?", b"Alice" in d.xref_stream(int(d.xref_get_key(w.xref, "AP/N")[1].split()[0])) if d.xref_get_key(w.xref, "AP/N")[0] == "xref" else "n/a")
n = len(list(p.widgets()))
p.add_redact_annot(fitz.Rect(alice["bbox"]), fill=(1, 1, 1)); p.apply_redactions(images=2, graphics=1, text=0)
print("   after redacting 'Alice' bbox: widgets", n, "->", len(list(p.widgets())), "; spans 'Alice' left:", [s["text"] for s in spans(p) if s["text"] == "Alice"], "; widget value:", [x.field_value for x in p.widgets() if x.field_name == "First Name"])
