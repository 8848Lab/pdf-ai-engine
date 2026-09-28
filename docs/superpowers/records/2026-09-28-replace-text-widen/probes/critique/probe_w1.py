"""W1: is span origin the right thing to preserve, and is the fallback
derivation bbox.y0 + size*ascender sound? Also: insert_text with a Tier-1
re-embedded font vs the original."""
from h import fitz, spans, fmt, raw_page, DEJAVU, DEJAVU_SERIF, FREESANS
from engine.operations import _select_font, _extract_target_font
from engine.parser import parse

print("=== A. fallback derivation bbox.y0 + size*ascender vs true origin ===")
cases = [
    ("helv 12", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET", [("helv", None)]),
    ("tiro 12", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET", [("tiro", None)]),
    ("zadb 12", "BT /F1 12 Tf 72 700 Td (abc) Tj ET", [("zadb", None)]),
    ("DejaVuSans 12", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET", [("dv", DEJAVU)]),
    ("DejaVuSerif 12", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET", [("dvs", DEJAVU_SERIF)]),
    ("FreeSans 12", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET", [("fs", FREESANS)]),
    ("rise Ts=4", "BT /F1 12 Tf 72 700 Td 4 Ts (Hello) Tj ET", [("helv", None)]),
    ("superscript small+rise", "BT /F1 12 Tf 72 700 Td (x) Tj /F1 7 Tf 5 Ts (2) Tj ET", [("helv", None)]),
    ("Tm scale x2", "BT /F1 12 Tf 2 0 0 1 72 700 Tm (Hello) Tj ET", [("helv", None)]),
    ("Tm scale y1.5", "BT /F1 12 Tf 1 0 0 1.5 72 700 Tm (Hello) Tj ET", [("helv", None)]),
    ("Tm skew 0.3", "BT /F1 12 Tf 1 0 0.3 1 72 700 Tm (Hello) Tj ET", [("helv", None)]),
    ("Tm uniform x1.5 size 8", "BT /F1 8 Tf 1.5 0 0 1.5 72 700 Tm (Hello) Tj ET", [("helv", None)]),
    ("Tz 150 (horiz scaling)", "BT /F1 12 Tf 150 Tz 72 700 Td (Hello) Tj ET", [("helv", None)]),
    ("Tc 2 Tw 5", "BT /F1 12 Tf 2 Tc 5 Tw 72 700 Td (Hello World) Tj ET", [("helv", None)]),
    ("cm rotate 90", "q 0 1 -1 0 400 100 cm BT /F1 12 Tf 72 300 Td (Hello) Tj ET Q", [("helv", None)]),
    ("cm mirror x", "q -1 0 0 1 612 0 cm BT /F1 12 Tf 72 700 Td (Hello) Tj ET Q", [("helv", None)]),
    ("Tm upside down", "BT /F1 12 Tf -1 0 0 -1 300 700 Tm (Hello) Tj ET", [("helv", None)]),
]
doc = fitz.open()
for label, content, fonts in cases:
    page = raw_page(doc, content, fonts)
    for s in spans(page):
        derived = s["bbox"][1] + s["size"] * s["asc"]
        f = fitz.Font(fonts[0][0]) if fonts[0][1] is None else fitz.Font(fontfile=fonts[0][1])
        derived_font = s["bbox"][1] + s["size"] * f.ascender
        print(f"{label:26} {fmt(s)}")
        print(f"{'':26}   derived(span asc)={derived:.2f} derived(fitz.Font asc {f.ascender:.4f})={derived_font:.2f} "
              f"true origin.y={s['origin'][1]}  ok={abs(derived - s['origin'][1]) < 0.05}")

print()
print("=== B. Type3 font ===")
# Build a minimal Type3 font by hand: one glyph 'a' = filled box, FontMatrix 0.001.
d3 = fitz.open()
p = d3.new_page()
charproc = d3.get_new_xref()
d3.update_object(charproc, "<<>>")
d3.update_stream(charproc, b"600 0 0 0 600 700 d1 0 0 600 700 re f")
t3 = d3.get_new_xref()
d3.update_object(t3, f"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 600 700] /FontMatrix [0.001 0 0 0.001 0 0] "
                      f"/CharProcs << /square {charproc} 0 R >> /Encoding << /Type /Encoding /Differences [97 /square] >> "
                      f"/FirstChar 97 /LastChar 97 /Widths [600] /Resources << >> >>")
d3.xref_set_key(p.xref, "Resources", f"<< /Font << /T3 {t3} 0 R >> >>")
d3.update_stream(p.get_contents()[0] if p.get_contents() else d3.get_new_xref(), b"BT /T3 12 Tf 72 700 Td (aaa) Tj ET") if p.get_contents() else None
if not p.get_contents():
    c = d3.get_new_xref(); d3.update_object(c, "<<>>"); d3.update_stream(c, b"BT /T3 12 Tf 72 700 Td (aaa) Tj ET")
    d3.xref_set_key(p.xref, "Contents", f"{c} 0 R")
d3 = fitz.open("pdf", d3.tobytes())
p = d3[0]
for s in spans(p):
    print(fmt(s), "derived", round(s["bbox"][1] + s["size"] * s["asc"], 2))
print("get_fonts:", p.get_fonts(full=True))
dd, hh = parse(d3.tobytes())
tb = dd.pages[0].text_blocks
print("parsed blocks:", [(b.text, b.font, b.size) for b in tb])
print("extract_target_font:", _extract_target_font(hh, hh[0], tb[0].font))
try:
    print("select_font:", _select_font(hh, hh[0], tb[0], "bbb"))
except Exception as e:
    print("select_font raised", type(e).__name__, e)

print()
print("=== C. Tier 1 re-embedded font: insert_text at origin vs original ===")
for label, path in (("DejaVuSans", DEJAVU), ("DejaVuSerif", DEJAVU_SERIF), ("FreeSans", FREESANS)):
    d = fitz.open()
    page = raw_page(d, "BT /F1 14 Tf 72 700 Td (Quarterly Report) Tj ET", [(label, path)])
    dd, hh = parse(d.tobytes())
    page = hh[0]
    tb = dd.pages[0].text_blocks[0]
    orig = spans(page)[0]
    name, font = _select_font(hh, page, tb, tb.text)
    page.insert_font(fontname=name, fontbuffer=font.buffer)
    page.insert_text((orig["origin"][0], orig["origin"][1] + 40), tb.text, fontname=name, fontsize=tb.size)
    new = [s for s in spans(page) if s["origin"][1] > orig["origin"][1] + 1][0]
    print(label, "tier", name)
    print("   orig", fmt(orig))
    print("   new ", fmt(new), " dy_origin", round(new["origin"][1] - orig["origin"][1], 2),
          "bbox dy0", round(new["bbox"][1] - orig["bbox"][1], 2), "width diff", round((new["bbox"][2]-new["bbox"][0]) - (orig["bbox"][2]-orig["bbox"][0]), 3))
    print("   fitz.Font(file).ascender", round(fitz.Font(fontfile=path).ascender, 4), "tier1 font.ascender", round(font.ascender, 4))

print()
print("=== D. subset font (real fixture) ===")
import glob
for f in sorted(glob.glob("/home/user/pdf-ai-engine/tests/fixtures/*.pdf")):
    d = fitz.open(f)
    for pno in range(min(2, d.page_count)):
        pg = d[pno]
        fonts = pg.get_fonts(full=True)
        if any("+" in fi[3] for fi in fonts):
            ss = spans(pg)[:3]
            for s in ss:
                derived = s["bbox"][1] + s["size"] * s["asc"]
                print(f.split('/')[-1], pno, fmt(s), "derived", round(derived, 2), "ok", abs(derived - s["origin"][1]) < 0.05)
            break
