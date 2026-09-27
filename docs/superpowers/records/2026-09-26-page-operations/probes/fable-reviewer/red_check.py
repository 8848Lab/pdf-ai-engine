"""Confirm the RED claims against the pre-fix geometry.py (1f3500a), loaded from a scratch copy."""
import importlib.util
import sys
import threading

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")
import pymupdf as fitz  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "geometry_prefix",
    "C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t2/geometry_prefix.py",
)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

from tests.geometry_helpers import box_page  # noqa: E402  (HEAD helper, as the report says it was left in place)

# I1: indirect /UserUnit 2
doc, page = box_page(UserUnit="2", indirect=("UserUnit",))
print("I1 pre-fix user_unit(indirect 2) =", g.user_unit(page), "| PyMuPDF rect =", page.rect)
doc.close()
doc, page = box_page(Rotate="45", indirect=("Rotate",))
print("I1 pre-fix raw_rotation(indirect 45) =", g.raw_rotation(page), "| refusal =", g.drawing_refusal(page, 0, g.OTHER_DRAWING))
doc.close()

# I2: /Parent self-cycle
doc, page = box_page()
parent = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
doc.xref_set_key(parent, "Parent", f"{parent} 0 R")
page = doc.reload_page(page)
res = {}
t = threading.Thread(target=lambda: res.__setitem__("v", g.crop_origin_overhangs(page)), daemon=True)
t.start()
t.join(3)
print("I2 pre-fix crop_origin_overhangs on /Parent cycle: alive after 3s =", t.is_alive(), res)

# M2: three-entry CropBox
doc, page = box_page(CropBox="[0 0 612]")
try:
    print("M2 pre-fix crop_origin_overhangs([0 0 612]) =", g.crop_origin_overhangs(page))
except BaseException as exc:  # noqa: BLE001
    print("M2 pre-fix raised:", type(exc).__name__, str(exc)[:80])
