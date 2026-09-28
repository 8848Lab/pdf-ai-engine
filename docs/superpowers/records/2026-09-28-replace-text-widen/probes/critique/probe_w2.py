"""W2: run the prototype right-limit against realistic pages and judge R."""
from h import fitz, spans, fmt
from w2proto import right_limit

W = 612


def report(label, page, target_text, expect, size=None):
    ss = spans(page)
    t = next(s for s in ss if s["text"] == target_text)
    size = size or t["size"]
    R, why, cands = right_limit(page, t["bbox"], size, explain=True)
    verdict = "OK" if expect[0] <= R <= expect[1] else "WRONG"
    print(f"[{verdict}] {label}\n      target {target_text!r} x1={t['bbox'][2]:.1f}  R={R:.1f} by {why}; expected R in [{expect[0]}, {expect[1]}]")
    if verdict == "WRONG":
        for c in cands: print("         cand", round(c[0], 1), c[1])
    return R


# 1. form with an underline rule starting left of the value
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
p.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
p.draw_line(fitz.Point(110, 103), fitz.Point(400, 103), width=0.6)
report("form underline rule under the value (starts left, ends x=400)", p, "Jo Lee", (390, 400))

# 1b. underline rule that starts under the value, NOT left of it, but ends far right
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
p.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
p.draw_line(fitz.Point(140, 103), fitz.Point(400, 103), width=0.6)
report("underline rule starting UNDER the value (x=140..400): a horizontal line, not an obstacle", p, "Jo Lee", (390, 400))

# 1c. dotted leader / dashed underline: many short segments to the right
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
p.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
x = 160
while x < 400:
    p.draw_line(fitz.Point(x, 103), fitz.Point(x + 3, 103), width=0.6); x += 6
report("dotted underline (short dashes to the right, under the baseline band)", p, "Jo Lee", (390, 400))

# 2. table cell with vertical rules
d = fitz.open(); p = d.new_page()
for x in (72, 200, 330, 460):
    p.draw_line(fitz.Point(x, 80), fitz.Point(x, 200), width=0.5)
for y in (80, 110, 140, 170, 200):
    p.draw_line(fitz.Point(72, y), fitz.Point(460, y), width=0.5)
p.insert_text((76, 100), "Widget", fontname="helv", fontsize=10)
p.insert_text((204, 100), "Blue", fontname="helv", fontsize=10)
p.insert_text((334, 100), "12", fontname="helv", fontsize=10)
report("table cell 'Blue' with vertical rule at 330", p, "Blue", (320, 330))
report("table cell 'Widget' with vertical rule at 200", p, "Widget", (190, 200))

# 2b. same table drawn with rectangles per cell (common in Word/LibreOffice exports)
d = fitz.open(); p = d.new_page()
for y in range(80, 200, 30):
    for x0, x1 in ((72, 200), (200, 330), (330, 460)):
        p.draw_rect(fitz.Rect(x0, y, x1, y + 30), width=0.5)
p.insert_text((76, 100), "Widget", fontname="helv", fontsize=10)
p.insert_text((204, 100), "Blue", fontname="helv", fontsize=10)
report("table cell 'Blue' where cells are rectangles", p, "Blue", (320, 330))

# 2c. table drawn with FILLED cell backgrounds (zebra rows) and no borders
d = fitz.open(); p = d.new_page()
p.draw_rect(fitz.Rect(72, 88, 460, 106), color=None, fill=(0.9, 0.9, 0.9))
p.insert_text((76, 100), "Widget", fontname="helv", fontsize=10)
p.insert_text((204, 100), "Blue", fontname="helv", fontsize=10)
p.insert_text((334, 100), "12", fontname="helv", fontsize=10)
report("zebra row: filled rect spanning all columns, text 'Blue' next col '12' at 334", p, "Blue", (320, 334))

# 3. multi-column text
d = fitz.open(); p = d.new_page()
left = ["Column one line alpha here", "Column one line beta text", "Column one line gamma"]
right = ["Column two line alpha here", "Column two line beta text", "Column two line gamma"]
for i, t in enumerate(left): p.insert_text((72, 100 + 14 * i), t, fontname="helv", fontsize=10)
for i, t in enumerate(right): p.insert_text((320, 100 + 14 * i), t, fontname="helv", fontsize=10)
report("two-column text, line 3 of column 1 (col2 starts x=320)", p, "Column one line gamma", (300, 320))
# 3b. same, but the target's row has NO right-column text (right column shorter)
d = fitz.open(); p = d.new_page()
for i, t in enumerate(left): p.insert_text((72, 100 + 14 * i), t, fontname="helv", fontsize=10)
for i, t in enumerate(right[:2]): p.insert_text((320, 100 + 14 * i), t, fontname="helv", fontsize=10)
report("two-column text, target row has no right-column neighbour; column edge rule should hold it (<=~200)", p, "Column one line gamma", (72, 210))

# 4. right-aligned numbers in a table
d = fitz.open(); p = d.new_page()
f = fitz.Font("helv")
rows = [("Rent", "1,200.00"), ("Utilities", "85.50"), ("Total", "1,285.50")]
for i, (k, v) in enumerate(rows):
    p.insert_text((72, 100 + 14 * i), k, fontname="helv", fontsize=10)
    w = f.text_length(v, 10); p.insert_text((300 - w, 100 + 14 * i), v, fontname="helv", fontsize=10)
report("right-aligned '85.50': R should not exceed its own right edge 300 (else the column misaligns)", p, "85.50", (300, 300))

# 5. 'Name: ' followed immediately by a value span on the same line
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Name: ", fontname="hebo", fontsize=12)
w = fitz.Font("hebo").text_length("Name: ", 12)
p.insert_text((72 + w, 100), "Jo Lee", fontname="helv", fontsize=12)
ss = spans(p); print("      spans:", [(s['text'], s['bbox'][0], s['bbox'][2]) for s in ss])
report("bold 'Name: ' followed by the value: R = value.x0 - gap(3) < own x1 -> clamped, no widening", p, "Name: ", (0, 1000))

# 6. label whose value is a separate span to the right, then empty space
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Jo Lee", fontname="helv", fontsize=12)
p.insert_text((250, 100), "Date: 2026-01-01", fontname="helv", fontsize=12)
report("value with another field 180pt to the right", p, "Jo Lee", (240, 247))

# 7. AcroForm widget + annotations to the right
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Signature:", fontname="helv", fontsize=12)
wdg = fitz.Widget(); wdg.field_name = "sig"; wdg.field_type = fitz.PDF_WIDGET_TYPE_TEXT; wdg.rect = fitz.Rect(150, 86, 400, 106); wdg.field_value = "prefilled"
p.add_widget(wdg)
p.add_rect_annot(fitz.Rect(420, 86, 500, 106))
p.add_freetext_annot(fitz.Rect(510, 86, 590, 106), "note")
print("      get_drawings sees:", len(p.get_drawings()), "items; get_text spans:", [s['text'] for s in spans(p)])
print("      widgets:", [(w.field_name, tuple(w.rect)) for w in p.widgets()], "annots:", [(a.type[1], tuple(a.rect)) for a in p.annots()])
report("AcroForm text widget at x=150..400 right of 'Signature:'", p, "Signature:", (140, 147))

# 8. header/footer: page header line above; footer far below; target on the body's first line
d = fitz.open(); p = d.new_page()
p.insert_text((72, 50), "ACME Corp -- Confidential", fontname="helv", fontsize=9)
p.draw_line(fitz.Point(72, 56), fitz.Point(540, 56), width=0.5)
p.insert_text((72, 100), "Dear Jo,", fontname="helv", fontsize=12)
p.insert_text((72, 760), "Page 1 of 3", fontname="helv", fontsize=9)
report("body line with header/footer: page margin rule (612-72=540)", p, "Dear Jo,", (530, 540))

# 9. rotated page: target on a /Rotate 90 page
d = fitz.open(); p = d.new_page(); p.set_rotation(90)
p.insert_text((72, 100), "Rotated value", fontname="helv", fontsize=12)
p.insert_text((300, 100), "Next", fontname="helv", fontsize=12)
report("/Rotate 90 page, neighbour at x=300 (unrotated space)", p, "Rotated value", (290, 297))

# 10. cropped page: CropBox inset, MediaBox offset
d = fitz.open(); p = d.new_page()
p.set_cropbox(fitz.Rect(50, 50, 500, 700))
p.insert_text((72, 100), "Cropped value", fontname="helv", fontsize=12)
ss = spans(p); print("      cropbox", p.cropbox, "rect", p.rect, "span bbox", ss[0]["bbox"])
R = report("cropped page 50..500: margin rule should use the visible bounds (<=~500-? )", p, "Cropped value", (0, 500))

# 11. column-edge heuristic misfires: list, heading + paragraph, single-line paragraph
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Shopping list", fontname="hebo", fontsize=12)
p.insert_text((72, 116), "- milk", fontname="helv", fontsize=12)
p.insert_text((72, 132), "- eggs", fontname="helv", fontsize=12)
p.insert_text((72, 148), "- a very long line about bread and butter", fontname="helv", fontsize=12)
report("list item '- milk' under a heading, with a long sibling: column edge = longest sibling", p, "- milk", (72, 540))
report("heading 'Shopping list' above a list: column edge = longest list item (heading widen capped)", p, "Shopping list", (72, 540))
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "Title", fontname="hebo", fontsize=16)
p.insert_text((72, 122), "Short", fontname="helv", fontsize=11)
report("heading 'Title' followed by a short paragraph line: column edge = 'Short'.x1 -> R = own x1 (no widening at all)", p, "Title", (200, 540))
d = fitz.open(); p = d.new_page()
p.insert_text((72, 100), "A single-line paragraph.", fontname="helv", fontsize=11)
p.insert_text((72, 300), "Far away text", fontname="helv", fontsize=11)
report("single-line paragraph, nothing within 2 line heights: margin rule", p, "A single-line paragraph.", (530, 540))

# 12. symmetric margin assumption: text starting at x=36 but with a 1in right margin? and a right-aligned page number
d = fitz.open(); p = d.new_page()
p.insert_text((36, 100), "Wide left-aligned body", fontname="helv", fontsize=11)
p.insert_text((36, 760), "footer", fontname="helv", fontsize=8)
R = report("text left margin 36 -> assumed right margin 36 -> R=576", p, "Wide left-aligned body", (570, 576))
d = fitz.open(); p = d.new_page()
p.insert_text((150, 100), "Indented value", fontname="helv", fontsize=11)
p.insert_text((20, 400), "x", fontname="helv", fontsize=6)  # a stray mark near the left edge (e.g. crop mark, page-edge note)
R = report("stray 6pt mark at x=20 drags the left margin to 20 -> R=592 (past any real margin)", p, "Indented value", (0, 1000))
