"""Point 8: RTL, fill colour, Tc/Tw, the 0.05pt pad vs the gap, V6 timing,
V4 with cropped pages, V1."""
import time
from h import fitz, spans, fmt, raw_page
from engine.parser import parse
from engine.operations import replace_text
from engine.export import export

print("=== colour: does replace_text preserve a non-black fill today? ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Red warning text", fontname="helv", fontsize=12, color=(1, 0, 0))
p.insert_text((72, 130), "Grey note", fontname="helv", fontsize=12, color=(0.5, 0.5, 0.5))
doc, h = parse(d.tobytes())
for b in doc.pages[0].text_blocks:
    replace_text(h, 0, b, b.text + "!")
out = fitz.open("pdf", export(h))
for s in spans(out[0]):
    print("  ", s["text"], "color=", hex(s["color"]))
print("  span dict exposes color:", [hex(s["color"]) for s in spans(d[0])])
print("  TextBlock fields:", [f for f in doc.pages[0].text_blocks[0].__dataclass_fields__])

print()
print("=== RTL: Arabic/Hebrew text as get_text reports it ===")
d = fitz.open(); p = d.new_page()
p.insert_font(fontname="cjk", fontbuffer=fitz.Font("cjk").buffer)
try:
    tw = fitz.TextWriter(p.rect)
    tw.append((300, 100), "שלום עולם", font=fitz.Font("cjk"), fontsize=14, right_to_left=True)
    tw.append((300, 140), "مرحبا بالعالم", font=fitz.Font("cjk"), fontsize=14, right_to_left=True)
    tw.write_text(p)
    for s in spans(p):
        print("  ", fmt(s))
    print("  fitz.Font('cjk').text_length(hebrew):", fitz.Font("cjk").text_length("שלום עולם", 14))
except Exception as e:
    print("  TextWriter RTL failed:", type(e).__name__, e)
# A real RTL PDF stores glyphs in visual order; get_text reports logical text
# and 'dir' (1,0). The widen would grow the LEFT-anchored origin to the right:
# for a right-aligned RTL run the visual right edge moves. Noted as the brief's own limitation.

print()
print("=== Tc/Tw: identity replacement of a tracked span, today's path ===")
d = fitz.open(); p = raw_page(d, "BT /F1 12 Tf 1.5 Tc 72 700 Td (TRACKED HEADING) Tj ET")
doc, h = parse(d.tobytes())
b = doc.pages[0].text_blocks[0]
print("  span", b.text, b.bbox, "text_length at size", fitz.Font("helv").text_length(b.text, b.size))
replace_text(h, 0, b, b.text)
out = fitz.open("pdf", export(h))
for s in spans(out[0]): print("  today:", fmt(s))

print()
print("=== 0.05pt pad vs gap: a same-line neighbour at zero gap ===")
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "WARNING:", fontname="hebo", fontsize=12)
w = fitz.Font("hebo").text_length("WARNING:", 12)
p.insert_text((72 + w, 100), " body text follows here", fontname="helv", fontsize=12)
doc, h = parse(d.tobytes())
for b in doc.pages[0].text_blocks: print("  block", repr(b.text), b.bbox)
label, body = doc.pages[0].text_blocks
gap = body.bbox[0] - label.bbox[2]
print(f"  gap between spans = {gap:.4f}pt; W2 gap for 12pt = {max(1, 0.25*12)}pt -> R = {body.bbox[0] - max(1, 0.25*12):.2f} < target.x1 {label.bbox[2]:.2f} -> 'R never less than own right edge' clause fires")
print("  So for a longer label the brief's exact shrink uses w_avail = own width; erase_rect x1 = bbox.x1 + 0.05 still (unchanged)")

print()
print("=== V6: get_drawings cost on a real busy page ===")
import glob
for f in sorted(glob.glob("/home/user/pdf-ai-engine/tests/fixtures/*.pdf")):
    dd = fitz.open(f)
    pg = dd[0]
    t0 = time.perf_counter(); dr = pg.get_drawings(); t1 = time.perf_counter()
    t2 = time.perf_counter(); pg.get_text("dict"); t3 = time.perf_counter()
    print(f"  {f.split('/')[-1]:40} drawings={len(dr):4} {1000*(t1-t0):7.1f}ms  get_text dict {1000*(t3-t2):6.1f}ms")

print()
print("=== V4 on cropped pages: insert_text at origin on MediaBox-offset / CropBox pages ===")
from tests.geometry_helpers import build_page  # noqa: E402
import inspect
print("  build_page signature:", inspect.signature(build_page))
