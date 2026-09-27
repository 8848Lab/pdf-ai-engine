"""Does a gate built only from PyMuPDF's own interpreted geometry agree with drawing?"""
import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai"); sys.path.insert(0, ".")
import pymupdf as fitz
from tests.geometry_helpers import matrix_cases, matrix_page, _pdf_box
from adversarial import probe_drift

def behav(page):
    tm = page.transformation_matrix
    scale_ok = abs(tm.a - 1) < 1e-9 and abs(tm.b) < 1e-9 and abs(tm.c) < 1e-9 and abs(tm.d + 1) < 1e-9
    cb, mb = page.cropbox, page.mediabox
    overhang = cb.x0 < mb.x0 or cb.y0 < 0
    return scale_ok, overhang

bad = 0; n = 0; stats = {}
for label, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
    doc = matrix_page(media, crop, unit, rot)
    data = doc.tobytes(); doc.close()
    d = fitz.open(stream=data, filetype="pdf"); p = d[0]
    scale_ok, overhang = behav(p)
    drifted, _ = probe_drift(data)
    n += 1
    expect_scale_ok = unit == 1
    # at unit 1, drift must equal overhang; at other units scale must be flagged
    if scale_ok != expect_scale_ok or (unit == 1 and drifted != overhang):
        bad += 1
        if bad <= 10: print("MISMATCH", label, "scale_ok", scale_ok, "overhang", overhang, "drift", drifted, tuple(p.cropbox), tuple(p.mediabox))
    stats[(unit == 1, overhang, drifted)] = stats.get((unit == 1, overhang, drifted), 0) + 1
print("matrix cases", n, "mismatches", bad, stats)
