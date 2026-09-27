import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai"); sys.path.insert(0, ".")
import pymupdf as fitz
from tests.geometry_helpers import *
from tests.geometry_helpers import drift_probe
import engine.geometry as g
L = "/MediaBox [0 0 612 792]"
rows = {s: standard(f"{L} /CropBox [100 100 {100+s} {100+s}]") for s in (0.5, 0.99, 0.995, 0.999, 1.0, 1.01)}
rows["0.995-unit0.5"] = standard(f"{L} /CropBox [100 100 100.995 100.995] /UserUnit 0.5")
for name, pdf in rows.items():
    p = fitz.open(stream=pdf, filetype="pdf")[0]
    print(name, "rect", tuple(p.rect), "cb", tuple(round(v,3) for v in p.cropbox), "gate:", (g.drawing_refusal(p, 0, g.TEXT_DRAWING) or "None")[:40], "drift", drift_probe(pdf))
print(f"{1.0000001192092896:.10g}")
