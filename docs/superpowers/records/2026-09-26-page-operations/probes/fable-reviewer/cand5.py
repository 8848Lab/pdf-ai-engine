"""cand5: magnitude rule extended to the transform's e/f and page.rect (at 2**24 and at 2**18).
Also: re-execute fix-round-4 mutation 2 (drop the `< 1` check) on a scratch copy of the module."""
import importlib.util
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

import engine.geometry as geo  # noqa: E402
from engine.geometry import OTHER_DRAWING, TEXT_DRAWING  # noqa: E402
from tests.geometry_helpers import drift_probe, matrix_cases, matrix_page, standard, with_text  # noqa: E402
from round4 import NEW4, cat, load_table  # noqa: E402
from round3a import NEW_ROWS  # noqa: E402

INF = "/MediaBox [-2147483648 -2147483648 2147483520 2147483520]"


def broken_xref(b):
    i = b.rfind(b"startxref\n")
    return b[:i] + b"startxref\n999999\n%%EOF"


def make_refusal(bound):
    def refusal(page, page_index, kind):
        layout = geo.layout_orientation(page)
        if layout is not None and layout[0] != page.rotation:
            return "invalid rotation"
        visible = geo.visible_area(page)
        w, h = visible.width, visible.height
        if page.rotation in (90, 270):
            w, h = h, w
        unit = layout[1] if layout is not None else None
        if (unit is None or visible.is_empty or w < 1 or h < 1
                or abs(page.rect.width - unit * w) > 0.01 or abs(page.rect.height - unit * h) > 0.01):
            return "lays out inconsistently"
        if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > 0.01:
            return "uses PDF /UserUnit"
        ctm = geo.page_transform(page)
        values = [v for box in (page.mediabox, page.cropbox, page.rect) for v in box] + [ctm.e, ctm.f]
        if any(abs(v) > bound for v in values):
            return "larger than"
        if kind == TEXT_DRAWING and geo.crop_origin_overhangs(page):
            return "CropBox"
        return None
    return refusal


def verdicts(fn, pdf_bytes):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return cat(fn(d[0], 0, TEXT_DRAWING)), cat(fn(d[0], 0, OTHER_DRAWING))
    finally:
        d.close()


ATTACK = [
    ("inf+broken-xref", lambda: broken_xref(standard(INF))),
    ("inf+broken-xref+text", lambda: broken_xref(with_text(INF))),
    ("inf+broken-xref+rot90", lambda: broken_xref(standard(f"{INF} /Rotate 90"))),
    ("inf+broken-xref+crop-letter", lambda: broken_xref(standard(f"{INF} /CropBox [0 0 612 792]"))),
    ("inf-inherited+broken-xref", lambda: broken_xref(standard("", pages_extra=INF))),
]

if __name__ == "__main__":
    for bound in (2 ** 24, 2 ** 18):
        fn = make_refusal(bound)
        print(f"=== bound {bound} ===")
        bad = 0
        for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
            doc = matrix_page(media, crop, unit, rot)
            b = doc.tobytes()
            doc.close()
            if verdicts(fn, b) != verdicts(geo.drawing_refusal, b):
                bad += 1
        print("matrix: differs from current on", bad, "of 1024")
        rows = load_table() + [(c, b, "?") for c, b in NEW_ROWS] + [(c, b, "?") for c, b in NEW4]
        changed, bypass = [], []
        for cid, builder, expected in rows:
            try:
                data = builder()
                new, cur = verdicts(fn, data), verdicts(geo.drawing_refusal, data)
            except Exception as exc:  # noqa: BLE001
                continue
            drifted, origin = drift_probe(data)
            if new != cur:
                changed.append((cid, cur, new))
            if new[0] == "-" and drifted is not False:
                bypass.append((cid, origin))
        print("rows:", len(rows), "verdict changes:", [(c, a, b) for c, a, b in changed], "bypasses:", bypass)
        fitz.TOOLS.mupdf_warnings(reset=True)
        for cid, builder in ATTACK:
            data = builder()
            try:
                cur = verdicts(geo.drawing_refusal, data)
            except Exception as exc:  # noqa: BLE001
                cur = f"EXC {type(exc).__name__}"
            try:
                new = verdicts(fn, data)
            except Exception as exc:  # noqa: BLE001
                new = f"EXC {type(exc).__name__}"
            print(f"  {cid:30} current={cur} candidate={new} probe={drift_probe(data)}")

    print("=== mutation 2 re-executed on a scratch copy (drop `width < 1 or height < 1`) ===")
    src = open("D:/Coding/8848 Lab/pdf-ai/engine/geometry.py", encoding="utf-8").read()
    assert "        or width < 1 or height < 1" in src
    mutated = src.replace("        or width < 1 or height < 1  # MuPDF swaps a sub-point box for the unit rect; page.cropbox does not\n", "")
    assert mutated != src
    path = "C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t2/mut/geometry_mut2.py"
    open(path, "w", encoding="utf-8").write(mutated)
    spec = importlib.util.spec_from_file_location("geometry_mut2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for cid, extra in (("crop-0.995", "/MediaBox [0 0 612 792] /CropBox [100 100 100.995 100.995]"),
                       ("crop-tiny", "/MediaBox [0 0 612 792] /CropBox [100 100 100.5 100.5]"),
                       ("crop-tiny-unit0.5", "/MediaBox [0 0 612 792] /CropBox [100 100 100.5 100.5] /UserUnit 0.5")):
        b = standard(extra)
        d = fitz.open(stream=b, filetype="pdf")
        m = cat(mod.drawing_refusal(d[0], 0, TEXT_DRAWING))
        c = cat(geo.drawing_refusal(d[0], 0, TEXT_DRAWING))
        d.close()
        print(f"  {cid:20} fixed={c:7} mutated={m:7} probe={drift_probe(b)}")
