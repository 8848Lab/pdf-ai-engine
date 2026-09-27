import sys
sys.path.insert(0, ".")
from adversarial import build, standard, probe_drift
import pymupdf as fitz
L = "/MediaBox [0 0 612 792]"
cases = {
 "plain": standard(L),
 "all4": standard(L + " /CropBox [-40 -60 660 820]"),
 "left": standard(L + " /CropBox [-40 0 612 792]"),
 "top": standard(L + " /CropBox [0 0 612 830]"),
 "bottom": standard(L + " /CropBox [0 -60 612 792]"),
 "right": standard(L + " /CropBox [0 0 660 792]"),
 "contained": standard(L + " /CropBox [40 60 580 740]"),
 "negmedia": standard("/MediaBox [-100 -100 512 692]"),
 "negmedia+crop": standard("/MediaBox [-100 -100 512 692] /CropBox [-40 0 612 692]"),
 "unit2": standard(L + " /UserUnit 2"),
 "unit2^32+1": standard(L + " /UserUnit 4294967297"),
 "rot45": standard(L + " /Rotate 45"),
 "rot2.7e9": standard(L + " /Rotate 2700000000.0"),
 "rot90": standard(L + " /Rotate 90"),
 "rot90+all4": standard(L + " /Rotate 90 /CropBox [-40 -60 660 820]"),
 "G1": standard(L + " /CropBox [4 0 R -60 660 820]", extra_objects=["-40"]),
 "H1": standard(L + " /CropBox [-40 -60 660 820 0]"),
 "H2": standard("/MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820]"),
 "I1": standard("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]"),
 "I3": standard("/CropBox [-40 -60 660 820]"),
 "I5": standard(L + " /CropBox [-40 -60 660]"),
 "N3": standard("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["0"]),
 "Jnull": build(["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [-100 -100 512 692] >>","<< /Type /Page /Parent 2 0 R /MediaBox 4 0 R /CropBox [-40 0 612 692] >>","null"]),
 "dangling-crop": standard(L + " /CropBox 99 0 R"),
}
for name, pdf in cases.items():
    d = fitz.open(stream=pdf, filetype="pdf"); p = d[0]
    try:
        info = f"rot={p.rotation} rect={tuple(round(v,1) for v in p.rect)} mb={tuple(round(v,1) for v in p.mediabox)} cb={tuple(round(v,1) for v in p.cropbox)} cbpos={tuple(p.cropbox_position)} tm={tuple(round(v,2) for v in p.transformation_matrix)}"
    except Exception as e:
        info = f"EXC {e}"
    dr = probe_drift(pdf)
    print(f"{name:14} drift={dr}  {info}")
