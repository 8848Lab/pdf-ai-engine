import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai"); sys.path.insert(0, ".")
import pymupdf as fitz
from tests.geometry_helpers import matrix_cases, matrix_page
from adversarial import probe_drift, standard, build

def geometry_consistent(page):
    """True iff PyMuPDF lays this page out at unit 1 with a valid rotation."""
    cb, r = page.cropbox, page.rect
    w, h = cb.width, cb.height
    if page.rotation in (90, 270):
        w, h = h, w
    tm = page.transformation_matrix
    return (abs(r.width - w) < 1e-6 and abs(r.height - h) < 1e-6
            and abs(tm.b) < 1e-9 and abs(tm.c) < 1e-9)

def overhang(page):
    return page.cropbox.x0 < page.mediabox.x0 or page.cropbox.y0 < 0

bad = 0
for label, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
    doc = matrix_page(media, crop, unit, rot); data = doc.tobytes(); doc.close()
    p = fitz.open(stream=data, filetype="pdf")[0]
    ok = geometry_consistent(p); drifted, _ = probe_drift(data)
    if ok != (unit == 1) or (unit == 1 and drifted != overhang(p)):
        bad += 1; print("MISMATCH", label, ok, overhang(p), drifted)
print("matrix mismatches:", bad)

L = "/MediaBox [0 0 612 792]"
adv = {
 "rot45": standard(L + " /Rotate 45"), "rot2.7e9": standard(L + " /Rotate 2700000000.0"),
 "rot2^32+45": standard(L + " /Rotate 4294967341"), "rot2^32+90": standard(L + " /Rotate 4294967386"),
 "rot45-square": standard("/MediaBox [0 0 600 600] /Rotate 45"),
 "rot270-square": standard("/MediaBox [0 0 600 600] /Rotate 270"),
 "unit2": standard(L + " /UserUnit 2"), "unit2^32+1": standard(L + " /UserUnit 4294967297"),
 "unit1.0000001": standard(L + " /UserUnit 1.0000001"), "unit-ind-2": standard(L + " /UserUnit 4 0 R", extra_objects=["2"]),
 "unit-chain16": standard(L + " /UserUnit 4 0 R", extra_objects=[f"{5+i} 0 R" for i in range(15)] + ["2"]),
 "unit2-rot90": standard(L + " /UserUnit 2 /Rotate 90"),
 "unit2-square-rot90": standard("/MediaBox [0 0 600 600] /UserUnit 2 /Rotate 90"),
 "G1": standard(L + " /CropBox [4 0 R -60 660 820]", extra_objects=["-40"]),
 "H1": standard(L + " /CropBox [-40 -60 660 820 0]"), "H2": standard("/MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820]"),
 "I1": standard("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]"), "I3": standard("/CropBox [-40 -60 660 820]"),
 "I5": standard(L + " /CropBox [-40 -60 660]"), "N3": standard("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["0"]),
 "Jnull": build(["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [-100 -100 512 692] >>","<< /Type /Page /Parent 2 0 R /MediaBox 4 0 R /CropBox [-40 0 612 692] >>","null"]),
 "J2": build(["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",f"<< /Type /Page /Parent 2 0 R {L} /CropBox 4 0 R >>","null"]),
 "B2": build(["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",f"<< /Type /Page /Parent 4 0 R {L} >>","2 0 R"]),
 "dangling": standard(L + " /CropBox 99 0 R /UserUnit 99 0 R /Rotate 99 0 R"),
 "dangling-parent": build(["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",f"<< /Type /Page /Parent 99 0 R {L} >>"]),
 "negmedia+leftcrop": standard("/MediaBox [-100 -100 512 692] /CropBox [-140 0 512 692]"),
 "negmedia+topcrop": standard("/MediaBox [-100 -100 512 692] /CropBox [-100 -100 512 720]"),
}
for name, pdf in adv.items():
    p = fitz.open(stream=pdf, filetype="pdf")[0]
    ok = geometry_consistent(p); ov = overhang(p); dr = probe_drift(pdf)
    allowed_text = ok and not ov
    verdict = "BYPASS" if (allowed_text and dr[0]) else ("false-refusal" if (not allowed_text and not dr[0]) else "agree")
    print(f"{name:20} consistent={ok!s:5} overhang={ov!s:5} drift={dr}  -> {verdict}")
