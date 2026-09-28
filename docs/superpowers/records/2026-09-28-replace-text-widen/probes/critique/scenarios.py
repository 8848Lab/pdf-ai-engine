"""End-to-end scenarios against the worktree's W1+W2+W3 prototype."""
import os, sys
WT = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/critique-widen/wt"
sys.path.insert(0, WT)
os.environ["WIDEN_PROTO"] = "widen"
import pymupdf as fitz  # noqa: E402
from engine.parser import parse  # noqa: E402
from engine.operations import replace_text  # noqa: E402
from engine.export import export  # noqa: E402
from engine.errors import RefusedBeforeMutation  # noqa: E402
import engine.operations as ops  # noqa: E402
assert ops.__file__.startswith(WT), ops.__file__


def spans(page):
    return [(s["text"], round(s["size"], 2), tuple(round(v, 1) for v in s["bbox"]), round(s["origin"][1], 2))
            for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]


def run(label, build, target_text, new_text, mode="widen"):
    os.environ["WIDEN_PROTO"] = mode
    d = fitz.open(); p = d.new_page(width=612, height=792); build(p)
    doc, h = parse(d.tobytes())
    t = next(b for b in doc.pages[0].text_blocks if b.text == target_text)
    fp_before = export(h)
    print(f"--- {label} [{mode}]  target {target_text!r} bbox={tuple(round(v,1) for v in t.bbox)} size={t.size}")
    try:
        replace_text(h, 0, t, new_text)
    except Exception as e:
        print(f"    RAISED {type(e).__name__}: {str(e)[:110]}")
        print(f"    fingerprint unchanged: {export(h) == fp_before}")
        return None
    out = fitz.open("pdf", export(h))
    for s in spans(out[0]): print("   ", s)
    return out


def owner_form(p):
    p.insert_text((72, 100), "Student Name:", fontsize=12, fontname="helv")
    p.draw_rect(fitz.Rect(160, 86, 400, 106), color=(0, 0, 0), width=0.8)
    p.insert_text((164, 100), "Jo Lee", fontsize=14, fontname="helv")
    p.insert_text((72, 140), "Date: 2026-01-01", fontsize=12)


run("owner's form (probe1)", owner_form, "Jo Lee", "Jonathan Lee")
run("owner's form, very long", owner_form, "Jo Lee", "Alexandra Montgomery-Smith")
run("owner's form, very long, TODAY", owner_form, "Jo Lee", "Alexandra Montgomery-Smith", mode="")


def stacked(p):
    for i, (k, v) in enumerate([("Student Name:", "Jo Lee"), ("Student ID:", "1234567"), ("Date of Birth:", "2008-01-01")]):
        y = 100 + 22 * i
        p.insert_text((72, y), k, fontname="helv", fontsize=12)
        p.draw_rect(fitz.Rect(160, y - 14, 400, y + 6), width=0.8)
        p.insert_text((164, y), v, fontname="helv", fontsize=14)


run("stacked form fields, 22pt pitch", stacked, "Jo Lee", "Jonathan Lee")


def adjacent(p):
    p.insert_text((72, 100), "Name: ", fontname="hebo", fontsize=12)
    p.insert_text((72 + fitz.Font("hebo").text_length("Name: ", 12), 100), "Jo Lee", fontname="helv", fontsize=12)


run("label directly followed by value: widen label", adjacent, "Name: ", "Full name: ")


def overlapping(p):
    # value starts 1.5pt LEFT of the label's x1 (kerned across a font change)
    p.insert_text((72, 100), "Name:", fontname="hebo", fontsize=12)
    p.insert_text((72 + fitz.Font("hebo").text_length("Name:", 12) - 1.5, 100), "Jo Lee", fontname="helv", fontsize=12)


o = run("value overlapping the label's x1 by 1.5pt: widen label", overlapping, "Name:", "Full legal name:")
if o:
    pix = o[0].get_pixmap(clip=fitz.Rect(105, 88, 150, 104))
    print("    ink in the value's area after the draw (expected: the widened label now covers 'Jo Lee'):",
          sum(1 for x in range(pix.width) for y in range(pix.height) if pix.pixel(x, y)[0] < 128), "dark px")


def newline_case(p):
    p.insert_text((72, 100), "First line here", fontname="helv", fontsize=12)
    p.insert_text((72, 116), "SECOND LINE MUST SURVIVE", fontname="helv", fontsize=12)


run("newline in new_text over a following line", newline_case, "First line here", "First\nline")


def ocr_scan(p):
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 40), 0); pm.set_rect(pm.irect, (255, 255, 255))
    pm.set_rect(fitz.IRect(120, 0, 200, 40), (0, 0, 0))  # printed black box on the scan, right of the OCR'd word
    p.insert_image(fitz.Rect(72, 80, 472, 160), pixmap=pm)
    # invisible OCR text over the scan for the word only
    c = p.get_contents()
    p.insert_text((80, 100), "SCANNED", fontname="helv", fontsize=14, render_mode=3)


o = run("invisible OCR word on a scan with printed ink to its right (not OCR'd)", ocr_scan, "SCANNED", "SCANNED DOCUMENT COPY")
if o:
    pix = o[0].get_pixmap(clip=fitz.Rect(300, 85, 330, 105))
    print("    the widened draw lands on the scan's black box region:", "text drawn at", [s for s in spans(o[0])])


def right_aligned(p):
    f = fitz.Font("helv")
    for i, (k, v) in enumerate([("Rent", "1,200.00"), ("Utilities", "85.50"), ("Total", "1,285.50")]):
        p.insert_text((72, 100 + 14 * i), k, fontname="helv", fontsize=10)
        p.insert_text((300 - f.text_length(v, 10), 100 + 14 * i), v, fontname="helv", fontsize=10)


run("right-aligned amount", right_aligned, "85.50", "1,085.50")


def heading(p):
    p.insert_text((72, 100), "Title", fontname="hebo", fontsize=16)
    p.insert_text((72, 122), "Short", fontname="helv", fontsize=11)


run("heading above a short line", heading, "Title", "Title of the Report")


def tracked(p):
    pass


def colour(p):
    p.insert_text((72, 100), "Red warning", fontname="helv", fontsize=12, color=(1, 0, 0))


o = run("red text", colour, "Red warning", "Red warning!")
if o:
    print("    colour after:", [hex(s["color"]) for b in o[0].get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]])


def cropped(p):
    p.set_cropbox(fitz.Rect(50, 50, 500, 700))
    p.insert_text((72, 100), "Cropped value", fontname="helv", fontsize=12)


run("cropped page", cropped, "Cropped value", "Cropped value widened")
os.environ["WIDEN_PROTO"] = "widen"
for rot in (90, 180, 270):
    def rotated(p, rot=rot):
        p.set_rotation(rot); p.insert_text((72, 100), "Rotated value", fontname="helv", fontsize=12)
    run(f"/Rotate {rot}", rotated, "Rotated value", "Rotated value widened")

print()
print("=== B1: is the pre-erase refusal raised before any mutation, incl. the font registration? ===")
d = fitz.open(); p = d.new_page(); owner_form(p)
doc, h = parse(d.tobytes()); t = next(b for b in doc.pages[0].text_blocks if b.text == "Jo Lee")
before = export(h)
try:
    replace_text(h, 0, t, "x" * 300)
except RefusedBeforeMutation as e:
    print("RefusedBeforeMutation; export identical:", export(h) == before)
