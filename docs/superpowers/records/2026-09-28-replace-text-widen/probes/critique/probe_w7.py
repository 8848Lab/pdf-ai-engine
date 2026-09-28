"""W7 (C21): a fixture where the clamped off-canvas sample reads a glyph and the
on-canvas median fixes it."""
from h import fitz, spans, fmt
from engine.operations import _sample_background_color, _median
from engine.geometry import to_display_matrix


def sample_c21(page, rect):
    pixmap = page.get_pixmap()
    to_display = to_display_matrix(page)
    offset = 3.0
    pts = [((rect.x0 + rect.x1) / 2, rect.y0 - offset), ((rect.x0 + rect.x1) / 2, rect.y1 + offset),
           (rect.x0 - offset, (rect.y0 + rect.y1) / 2), (rect.x1 + offset, (rect.y0 + rect.y1) / 2)]
    on, off = [], []
    for x_pt, y_pt in pts:
        d = fitz.Point(x_pt, y_pt) * to_display
        xi, yi = int(d.x - pixmap.x), int(d.y - pixmap.y)
        on_canvas = 0 <= xi < pixmap.width and 0 <= yi < pixmap.height
        xp = max(0, min(pixmap.width - 1, xi)); yp = max(0, min(pixmap.height - 1, yi))
        (on if on_canvas else off).append(pixmap.pixel(xp, yp)[:3])
    use = on if (on and off) else on + off
    return tuple(_median([p[i] for p in use]) / 255 for i in range(3)), on, off


def show(label, page, rect):
    old = _sample_background_color(page, rect)
    new, on, off = sample_c21(page, rect)
    print(f"{label}\n   rect={tuple(rect)} old={tuple(round(v,3) for v in old)} c21={tuple(round(v,3) for v in new)} on={on} off={off}")


# Case 1: span overhanging the top-right corner of the page; big black glyphs
# so the clamped top and right samples land on ink of the target's own text.
d = fitz.open(); p = d.new_page(width=300, height=200)
p.insert_text((250, 6), "MMMMMMM", fontname="helv", fontsize=24)  # baseline at y=6 -> glyphs above y=0 mostly
s = spans(p)[0]; print(fmt(s))
show("case 1: top-right overhang, 24pt M's", p, fitz.Rect(s["bbox"]))

# Case 2: heavy black bar drawn at the corner behind a small overhanging span
d = fitz.open(); p = d.new_page(width=300, height=200)
p.draw_rect(fitz.Rect(280, 0, 300, 20), color=None, fill=(0, 0, 0))  # black logo block at the corner
p.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
s = spans(p)[0]; print(fmt(s))
show("case 2: corner logo, span overhangs right, top sample off canvas", p, fitz.Rect(s["bbox"]))

# Case 3: right overhang only (one sample off): median of 4 with one dark
d = fitz.open(); p = d.new_page(width=300, height=200)
p.draw_rect(fitz.Rect(290, 90, 300, 110), color=None, fill=(0, 0, 0))
p.insert_text((260, 105), "Overhang!!", fontname="helv", fontsize=14)
s = spans(p)[0]; print(fmt(s))
show("case 3: right overhang only, ink at the right edge", p, fitz.Rect(s["bbox"]))

# Case 4: rect in the top-right corner but the page is rotated 90 (display
# space mapping): both clamped samples off canvas
d = fitz.open(); p = d.new_page(width=300, height=200); p.set_rotation(90)
p.draw_rect(fitz.Rect(280, 0, 300, 20), color=None, fill=(0.2, 0.2, 0.2))
p.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
s = spans(p)[0]; print(fmt(s))
show("case 4: as case 2 on a /Rotate 90 page", p, fitz.Rect(s["bbox"]))

# Case 5: an ordinary near-edge target (all on canvas) is unchanged by C21
d = fitz.open(); p = d.new_page(width=300, height=200)
p.insert_text((200, 100), "Edge", fontname="helv", fontsize=12)
s = spans(p)[0]
show("case 5: all on canvas (control)", p, fitz.Rect(s["bbox"]))

# Case 7: page BORDER lines along the top and right edges (a printed frame),
# span overhangs the top-right corner: top+right samples clamp onto the border
# ink, bottom+left are on the white canvas.
d = fitz.open(); p = d.new_page(width=300, height=200)
p.draw_rect(fitz.Rect(0, 0, 300, 1.5), color=None, fill=(0, 0, 0))
p.draw_rect(fitz.Rect(298.5, 0, 300, 200), color=None, fill=(0, 0, 0))
p.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
s = spans(p)[0]; print(fmt(s))
show("case 7: page frame at top/right edges, span overhangs the corner", p, fitz.Rect(s["bbox"]))

# Case 8: same on a light-blue page
d = fitz.open(); p = d.new_page(width=300, height=200)
p.draw_rect(p.rect, color=None, fill=(0.7, 0.85, 1.0))
p.draw_rect(fitz.Rect(0, 0, 300, 1.5), color=None, fill=(0, 0, 0))
p.draw_rect(fitz.Rect(298.5, 0, 300, 200), color=None, fill=(0, 0, 0))
p.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
s = spans(p)[0]
show("case 8: as 7 on a light-blue page", p, fitz.Rect(s["bbox"]))

# Case 9: the target's OWN glyph is what the clamped sample reads: a big
# glyph overhanging the corner (24pt 'M' at the corner) -- top sample clamps to
# y=0 inside the M's stem, right sample clamps to x=299 inside the last M.
d = fitz.open(); p = d.new_page(width=300, height=200)
p.insert_text((270, 14), "MMMM", fontname="hebo", fontsize=28)
s = spans(p)[0]; print(fmt(s))
show("case 9: own bold 28pt glyphs overhang the corner", p, fitz.Rect(s["bbox"]))

# Case 6: coloured page background with the overhang: clamped reads a glyph, on-canvas reads the colour
d = fitz.open(); p = d.new_page(width=300, height=200)
p.draw_rect(p.rect, color=None, fill=(0.7, 0.85, 1.0))
p.draw_rect(fitz.Rect(280, 0, 300, 20), color=None, fill=(0, 0, 0))
p.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
s = spans(p)[0]
show("case 6: light-blue page, corner logo, overhang", p, fitz.Rect(s["bbox"]))
