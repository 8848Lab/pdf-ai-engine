import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai"); sys.path.insert(0, ".")
import pymupdf as fitz
from tests.geometry_helpers import matrix_cases, matrix_page
from adversarial import probe_drift, standard, build
from cand import refusal
exec(open("behav2.py").read().split("L = \"/MediaBox")[0].split("bad = 0")[0].split("def geometry_consistent")[0])
bad = 0
for label, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
    doc = matrix_page(media, crop, unit, rot); data = doc.tobytes(); doc.close()
    p = fitz.open(stream=data, filetype="pdf")[0]
    r = refusal(p, "text"); drifted, _ = probe_drift(data)
    exp_unit = None if unit == 1 else f"unit {unit:g}"
    if unit != 1:
        if r != exp_unit: bad += 1; print("MISMATCH", label, r)
    elif (r is not None) != drifted or r not in (None, "overhang"):
        bad += 1; print("MISMATCH", label, r, drifted)
print("matrix mismatches:", bad)
src = open("behav2.py").read(); adv_src = "L = \"/MediaBox" + src.split("L = \"/MediaBox", 1)[1].split("for name, pdf in adv.items")[0]
exec(adv_src)
adv.update({
 "unit0": standard(L + " /UserUnit 0"), "unit-1": standard(L + " /UserUnit -1"), "unit0.5": standard(L + " /UserUnit 0.5"),
 "unit1e30": standard(L + " /UserUnit 1e30"),
 "rot-90": standard(L + " /Rotate -90"), "rot450": standard(L + " /Rotate 450"),
 "crop-empty": standard(L + " /CropBox [100 100 100 100]"),
 "crop-outside": standard(L + " /CropBox [700 800 900 1000]"),
 "media-zero": standard("/MediaBox [0 0 0 0]"),
 "crop-inverted": standard(L + " /CropBox [612 792 -40 -60]"),
 "rot90-left": standard(L + " /Rotate 90 /CropBox [-40 0 612 792]"),
 "rot180-top": standard(L + " /Rotate 180 /CropBox [0 0 612 830]"),
})
for name, pdf in adv.items():
    try:
        p = fitz.open(stream=pdf, filetype="pdf")[0]; r = refusal(p, "text")
    except Exception as e:
        r = f"EXC {type(e).__name__}: {e}"
    dr = probe_drift(pdf)
    v = "BYPASS" if (r is None and dr[0]) else ("false-refusal" if (r is not None and not dr[0]) else "agree")
    print(f"{name:20} gate={r!s:18} drift={dr} -> {v}")
