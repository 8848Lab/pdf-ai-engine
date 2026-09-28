"""W3/V5: text_length vs what insert_text renders vs the bbox get_text reads
back; kerning, ligatures, Tc/Tw; and the exact-shrink formula."""
from h import fitz, spans, fmt, raw_page, DEJAVU, DEJAVU_SERIF
import inspect

texts = ["AVAWAY To Ye", "office fluffy waffle", "Jonathan Lee", "WAVE To AV. LT Ty"]
fonts = [("helv", None), ("tiro", None), ("dv", DEJAVU), ("dvs", DEJAVU_SERIF)]
print("=== A. text_length vs insert_text rendered bbox width vs textbox ===")
for fname, path in fonts:
    font = fitz.Font(fname) if path is None else fitz.Font(fontfile=path)
    for t in texts:
        d = fitz.open(); p = d.new_page()
        if path:
            p.insert_font(fontname="X", fontfile=path); alias = "X"
        else:
            alias = fname
        p.insert_text((72, 100), t, fontname=alias, fontsize=12)
        s = spans(p)[0]
        w_bbox = s["bbox"][2] - s["bbox"][0]
        tl = font.text_length(t, 12)
        # what does get_text_length say (page-level helper)?
        gtl = fitz.get_text_length(t, fontname=fname, fontsize=12) if path is None else None
        print(f"{fname:5} {t!r:24} text_length={tl:8.3f} rendered bbox w={w_bbox:8.3f} diff={w_bbox-tl:+.4f} get_text_length={gtl}")

print()
print("=== B. existing text with Tc / Tw / Tz: bbox vs text_length at span size ===")
for label, content in [
    ("plain", "BT /F1 12 Tf 72 700 Td (Hello World again) Tj ET"),
    ("Tc 1", "BT /F1 12 Tf 1 Tc 72 700 Td (Hello World again) Tj ET"),
    ("Tw 6", "BT /F1 12 Tf 6 Tw 72 700 Td (Hello World again) Tj ET"),
    ("Tz 120", "BT /F1 12 Tf 120 Tz 72 700 Td (Hello World again) Tj ET"),
    ("TJ kerned", "BT /F1 12 Tf 72 700 Td [(Hello W) -200 (orld again)] TJ ET"),
]:
    d = fitz.open(); p = raw_page(d, content)
    s = spans(p)[0]
    w = s["bbox"][2] - s["bbox"][0]
    tl = fitz.Font("helv").text_length(s["text"], s["size"])
    print(f"{label:10} span size={s['size']} bbox w={w:.2f} text_length={tl:.2f} -> identity replacement would be {'SHRUNK' if tl > w + 0.05 else 'ok'} (ratio {w/tl:.3f})")

print()
print("=== C. exact shrink: linearity of advance in size; insert_text at size s*w_avail/w_need ===")
font = fitz.Font("helv")
t = "Alexandra Montgomery-Smith"
for size in (14, 10.5, 7.44, 7.0):
    print(size, round(font.text_length(t, size), 4), "linear?", round(font.text_length(t, size) / size, 6))
w_avail = 236 - 164
size = 14 * w_avail / font.text_length(t, 14)
d = fitz.open(); p = d.new_page()
p.insert_text((164, 100), t, fontname="helv", fontsize=size)
s = spans(p)[0]
print("exact size", round(size, 4), "rendered", fmt(s), "right edge", s["bbox"][2], "limit", 236)

print()
print("=== D. V3: insert_textbox baseline = rect.y0 + fontsize*ascender ===")
src = inspect.getsource(fitz.utils.insert_textbox) if hasattr(fitz.utils, "insert_textbox") else ""
print("insert_textbox source has 'ascender':", "ascender" in src)
src2 = inspect.getsource(fitz.TextWriter) if False else ""
import pymupdf.utils as U
s3 = inspect.getsource(U)
i = s3.find("def insert_textbox")
print(s3[i:i+200].replace("\n", " ")[:200])
# empirical
for fs in (14, 12.6, 11.34, 7.44):
    d = fitz.open(); p = d.new_page()
    r = fitz.Rect(72, 86, 400, 110)
    p.insert_textbox(r, "Jo Lee", fontname="helv", fontsize=fs)
    s = spans(p)[0]
    print(f"  fs={fs} baseline={s['origin'][1]} rect.y0+fs*asc={86 + fs*font.ascender:.2f}")

print()
print("=== E. newline in new_text: text_length and insert_text ===")
t = "Line one\nLine two"
print("text_length with newline:", font.text_length(t, 12), "vs", font.text_length("Line one", 12), font.text_length("Line one Line two", 12))
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), t, fontname="helv", fontsize=12)
for s in spans(p): print("  insert_text drew:", fmt(s))
