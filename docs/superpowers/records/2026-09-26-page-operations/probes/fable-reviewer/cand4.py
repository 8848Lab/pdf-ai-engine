"""Candidate repair for the magnitude rule: bound 2**18 on page.mediabox, page.cropbox AND
page.rect. Checks: 1,024 matrix; Test B table + round3a NEW_ROWS + round4 NEW4 (only 'huge'
verdicts may change); fractional drift at the far corner of allowed pages near the bound."""
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

import engine.geometry as geo  # noqa: E402
from engine.geometry import OTHER_DRAWING, TEXT_DRAWING  # noqa: E402
from tests.geometry_helpers import drift_probe, matrix_cases, matrix_page, standard, with_text  # noqa: E402
from round4 import NEW4, cat, frac_probe, load_table, redaction  # noqa: E402

BOUND = 2 ** 18


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
    if any(abs(v) > BOUND for box in (page.mediabox, page.cropbox, page.rect) for v in box):
        return "larger than"
    if kind == TEXT_DRAWING and geo.crop_origin_overhangs(page):
        return "CropBox"
    return None


def gate(pdf_bytes, kind=TEXT_DRAWING):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        r = cat(refusal(d[0], 0, kind))
        cur = cat(geo.drawing_refusal(d[0], 0, kind))
    finally:
        d.close()
    return r, cur


if __name__ == "__main__":
    bad = 0
    for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
        doc = matrix_page(media, crop, unit, rot)
        b = doc.tobytes()
        doc.close()
        r, cur = gate(b)
        if r != cur:
            bad += 1
            print("matrix differs", name, r, cur)
    print("matrix: candidate differs from current on", bad, "of 1024")

    from round3a import NEW_ROWS  # noqa: E402  (imports fail: user_unit gone) -- guarded below
    rows = load_table() + [(c, b, "?") for c, b in NEW_ROWS] + [(c, b, "?") for c, b in NEW4]
    changed = []
    bypass = []
    for cid, builder, expected in rows:
        try:
            data = builder()
            r, cur = gate(data)
            ro, curo = gate(data, OTHER_DRAWING)
        except Exception as exc:  # noqa: BLE001
            print(f"{cid:34} EXC {type(exc).__name__}")
            continue
        drifted, origin = drift_probe(data)
        if (r, ro) != (cur, curo):
            changed.append((cid, (cur, curo), (r, ro)))
        if r == "-" and drifted is not False:
            bypass.append((cid, origin))
    print("rows checked:", len(rows), "verdict changes:", len(changed), "bypasses:", len(bypass))
    for c in changed:
        print("  changed", c)
    for b in bypass:
        print("  BYPASS", b)

    print("fractional drift at the far corner, pages around the candidate bound:")
    for cid, extra, point in [
        ("2^18 square", f"/MediaBox [0 0 {BOUND} {BOUND}]", (BOUND - 100.37, BOUND - 140.73)),
        ("2^18 wide", f"/MediaBox [0 0 {BOUND} 792]", (BOUND - 100.37, 140.73)),
        ("sym 2^17 (extent 2^18)", f"/MediaBox [-{BOUND // 2} 0 {BOUND // 2} 792]", (BOUND - 100.37, 140.73)),
        ("offset to 2^18", f"/MediaBox [{BOUND - 612} 0 {BOUND} 792]", (100.37, 140.73)),
        ("2^18+2 (refused?)", f"/MediaBox [0 0 {BOUND + 2} 792]", (BOUND - 100.37, 140.73)),
        ("sym 2^18 (extent 2^19, refused?)", f"/MediaBox [-{BOUND} 0 {BOUND} 792]", (2 * BOUND - 100.37, 140.73)),
        ("crop -2^18 (refused?)", f"/MediaBox [0 0 612 792] /CropBox [-{BOUND} 0 612 792]", (100.37, 140.73)),
    ]:
        b = standard(extra)
        r, cur = gate(b)
        drift, origin = frac_probe(b, point)
        print(f"  {cid:34} candidate={r:6} current={cur:6} drift={None if drift is None else round(drift, 5)}")

    print("redaction rows (engine flow) on two more OTHER-allowed pages:")
    for cid, extra in [("media-0.995-crop-big", "/MediaBox [100 100 100.995 100.995] /CropBox [0 0 612 792]"),
                       ("media-tiny-crop-over", "/MediaBox [0 0 0.5 0.5] /CropBox [-40 -60 660 820]"),
                       ("crop-1.005", "/MediaBox [0 0 612 792] /CropBox [100 100 101.005 101.005]")]:
        print(" ", cid, redaction(with_text(extra)))
