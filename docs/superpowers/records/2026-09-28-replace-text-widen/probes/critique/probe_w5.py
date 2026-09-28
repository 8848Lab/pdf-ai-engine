"""W5: is line['dir'] the right discriminator? Mirrored, upside-down, vertical,
rotated cm, and skewed matrices; plus what today's path does with each."""
from h import fitz, spans, fmt, raw_page

cases = [
    ("plain", "BT /F1 12 Tf 72 700 Td (Hello) Tj ET"),
    ("cm mirror x (text reads backwards)", "q -1 0 0 1 612 0 cm BT /F1 12 Tf 72 700 Td (Hello) Tj ET Q"),
    ("cm mirror y (upside-down glyphs, LTR advance)", "q 1 0 0 -1 0 792 cm BT /F1 12 Tf 72 92 Td (Hello) Tj ET Q"),
    ("Tm upside down (-1 0 0 -1)", "BT /F1 12 Tf -1 0 0 -1 300 700 Tm (Hello) Tj ET"),
    ("Tm rotate 90", "BT /F1 12 Tf 0 1 -1 0 300 500 Tm (Hello) Tj ET"),
    ("cm rotate 90 (Merge A case)", "q 0 1 -1 0 792 0 cm BT /F1 12 Tf 72 700 Td (Hello) Tj ET Q"),
    ("Tm rotate 180 via cm", "q -1 0 0 -1 612 792 cm BT /F1 12 Tf 72 700 Td (Hello) Tj ET Q"),
    ("skew 0.3", "BT /F1 12 Tf 1 0 0.3 1 72 700 Tm (Hello) Tj ET"),
    ("skew vertical 0.2 (b != 0)", "BT /F1 12 Tf 1 0.2 0 1 72 700 Tm (Hello) Tj ET"),
    ("tiny rotation 1deg", "BT /F1 12 Tf 0.99985 0.01745 -0.01745 0.99985 72 700 Tm (Hello) Tj ET"),
    ("Tm scale x2 (dir still (1,0))", "BT /F1 12 Tf 2 0 0 1 72 700 Tm (Hello) Tj ET"),
]
doc = fitz.open()
for label, content in cases:
    page = raw_page(doc, content)
    for s in spans(page):
        print(f"{label:46} {fmt(s)} flags={s['flags']}")

print()
print("Vertical writing mode font (WMode 1) is not buildable from base14 here; dir for a rotated-cm case above is what Merge A measured.")
