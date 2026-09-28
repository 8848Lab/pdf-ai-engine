"""N2 with a bleed margin: does stopping BLEED pt short of the rule (instead of 'just short') leave the border unbroken?
Owner's form (14pt) and the bordered table."""
import pymupdf as fitz
from harness import build, erase, render, pix_diff, words
from n1_proto import n1_clip
import n2_form  # reuses its n2_clip (prints its own output first)

for bleed in (0.0, 0.25, 0.5, 0.6, 1.0):
    n2_form.EPS = bleed
    form = [dict(text="Student Name:", pt=(72, 100)), dict(kind="rect", rect=(160, 86, 400, 106), width=0.8), dict(text="Jo Lee", pt=(164, 100), size=14, target=True)]
    d_i, p_i = build(form, omit_target=True); ip = render(p_i)
    d, p = build(form)
    s = [s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"] if s["text"] == "Jo Lee"][0]
    tb = fitz.Rect(s["bbox"]); rect = fitz.Rect(tb.x0, tb.y0, tb.x1 + 0.05, tb.y1)
    rect, k, hits = n2_form.n2_clip(p, rect, tb)
    erase(p, rect)
    lo, dm = pix_diff(render(p), ip)
    print(f"BLEED margin {bleed}: rect y0={rect.y0:.2f} (stroke bottom 86.40): border pixels damaged={dm}, target ink left={lo}, target text left={[x for x in words(p) if x in ('Jo','Lee')]}")
