"""W4 / privacy: content the obstacle model can miss: invisible text (Tr 3),
white text, text under an image, clipped text, annotation appearances,
widgets, and shading/pattern fills."""
from h import fitz, spans, fmt, raw_page
from w2proto import right_limit
from engine.parser import parse

print("=== A. Tr 3 (invisible OCR text): does get_text('dict') report it? does parse()? ===")
d = fitz.open()
p = raw_page(d, "BT /F1 12 Tf 3 Tr 300 100 Td (INVISIBLE OCR) Tj ET BT /F1 12 Tf 0 Tr 72 100 Td (Visible) Tj ET")
default = spans(p)
print("   default flags:", [(s["text"], s["bbox"][0]) for s in default])
print("   with TEXT_PRESERVE_... flags=0:", [(s["text"]) for s in spans(p, flags=0)])
try:
    print("   TEXT_..._HIDDEN? attrs:", [a for a in dir(fitz) if "HIDDEN" in a or "INVISIBLE" in a])
except Exception as e:
    print(e)
doc, h = parse(d.tobytes())
print("   parse() blocks:", [(b.text, b.bbox[0]) for b in doc.pages[0].text_blocks])
R, why = right_limit(p, next(s for s in default if s["text"] == "Visible")["bbox"], 12)
print(f"   W2 R for 'Visible' = {R:.1f} by {why}  (invisible text at x=300 {'IS' if R < 300 else 'is NOT'} an obstacle)")
# Render to see whether Tr 3 text is truly invisible
pix = p.get_pixmap(clip=fitz.Rect(300, 88, 400, 104))
print("   pixels in the Tr3 area: any dark?", any(pix.pixel(x, y)[0] < 200 for x in range(pix.width) for y in range(pix.height)))

print()
print("=== B. white-on-white text ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
p.insert_text((300, 100), "WHITE HIDDEN", fontname="helv", fontsize=12, color=(1, 1, 1))
ss = spans(p); print("   spans:", [(s["text"], hex(s["color"])) for s in ss])
R, why = right_limit(p, ss[0]["bbox"], 12); print(f"   R={R:.1f} by {why} -> white text is an obstacle (safe, if over-cautious)")

print()
print("=== C. text under an image (image drawn over it) ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
p.insert_text((300, 100), "UNDER IMAGE", fontname="helv", fontsize=12)
pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0); pm.set_rect(pm.irect, (200, 220, 255))
p.insert_image(fitz.Rect(290, 80, 420, 110), pixmap=pm)
ss = spans(p); print("   spans:", [s["text"] for s in ss], "images:", [tuple(i["bbox"]) for i in p.get_image_info()])
R, why = right_limit(p, ss[0]["bbox"], 12); print(f"   R={R:.1f} by {why}")

print()
print("=== D. text clipped away by a clip path (get_text reports it?) ===")
d = fitz.open()
p = raw_page(d, "q 0 0 200 792 re W n BT /F1 12 Tf 72 100 Td (Visible) Tj ET BT /F1 12 Tf 300 100 Td (CLIPPED OUT) Tj ET Q")
ss = spans(p); print("   default spans:", [s["text"] for s in ss])
print("   flags with TEXT_MEDIABOX_CLIP only:", [s["text"] for s in spans(p, flags=fitz.TEXT_MEDIABOX_CLIP)])
pix = p.get_pixmap(clip=fitz.Rect(300, 88, 400, 104))
print("   rendered ink in clipped area?", any(pix.pixel(x, y)[0] < 200 for x in range(pix.width) for y in range(pix.height)))

print()
print("=== E. annotation appearance text and widget appearance: in get_text? in get_drawings? ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
w = fitz.Widget(); w.field_name = "f"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT; w.rect = fitz.Rect(300, 86, 450, 106); w.field_value = "WIDGET VALUE"
p.add_widget(w)
a = p.add_freetext_annot(fitz.Rect(470, 86, 590, 106), "FREETEXT")
a.update()
p.add_highlight_annot(fitz.Rect(200, 88, 260, 104))
ss = spans(p); print("   get_text spans:", [s["text"] for s in ss])
print("   get_drawings items:", [(it["rect"]) for it in p.get_drawings()])
print("   get_text(dict) of the page through a fresh reopen:", [s["text"] for s in spans(fitz.open('pdf', d.tobytes())[0])])
R, why = right_limit(p, ss[0]["bbox"], 12); print(f"   R={R:.1f} by {why}  -> widget at 300 {'IS' if R < 300 else 'is NOT'} an obstacle; the annot at 470 {'IS' if R < 470 else 'is NOT'}")
pix = p.get_pixmap(clip=fitz.Rect(300, 86, 450, 106))
print("   widget renders ink in get_pixmap?", any(pix.pixel(x, y)[0] < 200 for x in range(pix.width) for y in range(pix.height)))
# what does today's replace_text erase do to a widget in the erase rect? (apply_redactions removes annots)

print()
print("=== F. shading (gradient) fill and inline image to the right ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
try:
    sh = p.draw_rect(fitz.Rect(300, 80, 400, 110), color=None, fill=(0.3, 0.3, 0.3))
    print("   filled rect drawings:", [(it["rect"], it.get("fill")) for it in p.get_drawings()])
except Exception as e:
    print("   ", e)
ss = spans(p); R, why = right_limit(p, ss[0]["bbox"], 12); print(f"   R={R:.1f} by {why}")

print()
print("=== G. Form XObject content (text inside a nested XObject) ===")
d = fitz.open(); src = fitz.open(); sp = src.new_page(); sp.insert_text((10, 20), "IN XOBJECT", fontname="helv", fontsize=12)
p = d.new_page(); p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
p.show_pdf_page(fitz.Rect(300, 80, 500, 110), src, 0, clip=fitz.Rect(0, 0, 200, 30))
ss = spans(p); print("   spans:", [(s["text"], s["bbox"][0]) for s in ss]); R, why = right_limit(p, ss[0]["bbox"], 12); print(f"   R={R:.1f} by {why}")

print()
print("=== H. today's erase vs a widget overlapping the erase rect ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Visible", fontname="helv", fontsize=12)
w = fitz.Widget(); w.field_name = "f"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT; w.rect = fitz.Rect(60, 86, 200, 106); w.field_value = "FIELD"
p.add_widget(w)
from engine.operations import replace_text
doc, h = parse(d.tobytes())
replace_text(h, 0, doc.pages[0].text_blocks[0], "Visible!")
print("   widgets after replace_text:", [(x.field_name, x.field_value) for x in h[0].widgets()])
