"""Re-review 2: attack the interpreted-geometry gate (read-only on the checkout).

Part A: the 39-row table + new adversarial rows, each: gate (text/other),
transformation matrix, rotation, rect, drift probe.
Part B: transformation_matrix b/c/a/d over the 1,024-case matrix.
"""
import sys
import threading

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

from engine.geometry import OTHER_DRAWING, TEXT_DRAWING, drawing_refusal, layout_orientation  # noqa: E402
from tests.geometry_helpers import build, drift_probe, matrix_cases, matrix_page, standard  # noqa: E402

L = "/MediaBox [0 0 612 792]"


def with_timeout(fn, seconds=5):
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = f"{type(exc).__name__}: {exc}"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=seconds)
    if t.is_alive():
        return "HANG"
    if "error" in box:
        return "EXC " + box["error"]
    return box["value"]


def cat(reason):
    if reason is None:
        return "-"
    for k, phrase in (("rot", "invalid rotation"), ("unit", "uses PDF /UserUnit"),
                      ("incons", "lays out inconsistently"), ("over", "CropBox")):
        if phrase in reason:
            return k
    return "?"


def evaluate(pdf_bytes):
    def inner():
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        m = page.transformation_matrix
        info = dict(
            rot=page.rotation,
            rect=tuple(round(v, 3) for v in page.rect),
            media=tuple(round(v, 3) for v in page.mediabox),
            crop=tuple(round(v, 3) for v in page.cropbox),
            tm=tuple(round(v, 4) for v in m),
            unit=layout_orientation(page),
            text=cat(drawing_refusal(page, 0, TEXT_DRAWING)),
            other=cat(drawing_refusal(page, 0, OTHER_DRAWING)),
        )
        doc.close()
        return info
    info = with_timeout(inner)
    probe = with_timeout(lambda: drift_probe(pdf_bytes))
    return info, probe


NEW_ROWS = [
    # mirrored + rotated: transformation_matrix is fixed (1,0,0,-1,0,h) at rotation != 0
    ("unit-1-rot90", lambda: standard(f"{L} /UserUnit -1 /Rotate 90")),
    ("unit-1-rot180", lambda: standard(f"{L} /UserUnit -1 /Rotate 180")),
    ("unit-1-rot270", lambda: standard(f"{L} /UserUnit -1 /Rotate 270")),
    ("unit-1-square-rot90", lambda: standard("/MediaBox [0 0 600 600] /UserUnit -1 /Rotate 90")),
    ("unit-2-rot90", lambda: standard(f"{L} /UserUnit -2 /Rotate 90")),
    ("unit-1-crop-rot90", lambda: standard(f"{L} /CropBox [50 50 500 700] /UserUnit -1 /Rotate 90")),
    ("unit-1-rot180-crop", lambda: standard(f"{L} /CropBox [50 50 500 700] /UserUnit -1 /Rotate 180")),
    ("unit-1-rot-90", lambda: standard(f"{L} /UserUnit -1 /Rotate -90")),
    ("unit-1-rot450", lambda: standard(f"{L} /UserUnit -1 /Rotate 450")),
    ("unit-1-indirect-rot90", lambda: standard(f"{L} /UserUnit 4 0 R /Rotate 90", extra_objects=["-1"])),
    ("unit-1.0000001-rot90", lambda: standard(f"{L} /UserUnit -1.0000001 /Rotate 90")),
    # rotations MuPDF snaps to 180 or 0 while PyMuPDF reports 0
    ("rot135", lambda: standard(f"{L} /Rotate 135")),
    ("rot180+44", lambda: standard(f"{L} /Rotate 224")),
    ("rot225", lambda: standard(f"{L} /Rotate 225")),
    ("rot315", lambda: standard(f"{L} /Rotate 315")),
    ("rot30", lambda: standard(f"{L} /Rotate 30")),
    ("rot-45", lambda: standard(f"{L} /Rotate -45")),
    ("rot-135", lambda: standard(f"{L} /Rotate -135")),
    ("rot135-square", lambda: standard("/MediaBox [0 0 600 600] /Rotate 135")),
    ("rot2.7e9-square", lambda: standard("/MediaBox [0 0 600 600] /Rotate 2700000000.0")),
    ("rot-2^31", lambda: standard(f"{L} /Rotate 2147483648")),
    ("rot-2^31-real", lambda: standard(f"{L} /Rotate 2147483648.0")),
    ("rot-neg2^31", lambda: standard(f"{L} /Rotate -2147483648")),
    ("rot-2^63", lambda: standard(f"{L} /Rotate 9223372036854775808")),
    ("rot-inherited-135", lambda: standard(L, pages_extra="/Rotate 135")),
    ("rot-real-90.4", lambda: standard(f"{L} /Rotate 90.4")),
    ("rot-real-89.6", lambda: standard(f"{L} /Rotate 89.6")),
    ("rot-real-134.9", lambda: standard(f"{L} /Rotate 134.9")),
    # huge / tiny boxes
    ("media-huge", lambda: standard("/MediaBox [0 0 1000000000 1000000000]")),
    ("media-huge-1e7", lambda: standard("/MediaBox [0 0 10000000 10000000]")),
    ("media-huge-offset", lambda: standard("/MediaBox [1000000 1000000 1000612 1000792]")),
    ("media-huge-offset-crop-left", lambda: standard("/MediaBox [1000000 1000000 1000612 1000792] /CropBox [999990 1000000 1000612 1000792]")),
    ("media-14400", lambda: standard("/MediaBox [0 0 14400 14400]")),
    ("media-tiny", lambda: standard("/MediaBox [0 0 0.5 0.5]")),
    ("media-1x1", lambda: standard("/MediaBox [0 0 1 1]")),
    ("crop-tiny", lambda: standard(f"{L} /CropBox [100 100 100.5 100.5]")),
    ("crop-tiny-unit0.5", lambda: standard(f"{L} /CropBox [100 100 100.5 100.5] /UserUnit 0.5")),
    ("crop-tiny-w", lambda: standard(f"{L} /CropBox [100 100 100.5 300]")),
    ("crop-1x1", lambda: standard(f"{L} /CropBox [100 100 101 101]")),
    ("crop-1x1-left", lambda: standard(f"{L} /CropBox [-1 100 0.5 101]")),
    ("media-tiny-crop-over", lambda: standard("/MediaBox [0 0 0.5 0.5] /CropBox [-40 -60 660 820]")),
    # NaN / inf-like tokens and exponent reals
    ("media-nan", lambda: standard("/MediaBox [0 0 nan 792]")),
    ("media-inf", lambda: standard("/MediaBox [0 0 inf 792]")),
    ("crop-nan", lambda: standard(f"{L} /CropBox [nan -60 660 820]")),
    ("crop-exp", lambda: standard(f"{L} /CropBox [-4e1 -60 660 820]")),
    ("crop-huge-neg", lambda: standard(f"{L} /CropBox [-1e38 -60 660 820]")),
    ("crop-huge-neg-plain", lambda: standard(f"{L} /CropBox [-99999999999999999999999999999999999999 -60 660 820]")),
    ("crop-int64-left", lambda: standard(f"{L} /CropBox [-4294967336 -60 660 820]")),
    ("unit-nan", lambda: standard(f"{L} /UserUnit nan")),
    ("unit-1e-30", lambda: standard(f"{L} /UserUnit 0.000000000000000000000000000001")),
    ("unit-tiny-1e-10", lambda: standard(f"{L} /UserUnit 0.0000000001")),
    ("unit-1e10", lambda: standard(f"{L} /UserUnit 10000000000")),
    ("unit-1.00001", lambda: standard(f"{L} /UserUnit 1.00001")),
    ("unit-1.000012", lambda: standard(f"{L} /UserUnit 1.000012")),
    ("unit-0.99999", lambda: standard(f"{L} /UserUnit 0.99999")),
    ("unit-1.0001", lambda: standard(f"{L} /UserUnit 1.0001")),
    ("unit-1.0000001-huge", lambda: standard("/MediaBox [0 0 100000 100000] /UserUnit 1.0000001")),
    ("unit-2-neg-crop", lambda: standard(f"{L} /UserUnit 2 /CropBox [-40 -60 660 820]")),
    # swapped corners + rotation
    ("media-swapped-rot90", lambda: standard("/MediaBox [612 792 0 0] /Rotate 90")),
    ("media-swapped-crop-swapped-rot270", lambda: standard("/MediaBox [612 792 0 0] /CropBox [612 792 -40 -60] /Rotate 270")),
    ("crop-swapped-x-rot90", lambda: standard(f"{L} /CropBox [612 -60 -40 792] /Rotate 90")),
    ("crop-swapped-rot180-top", lambda: standard(f"{L} /CropBox [612 830 0 0] /Rotate 180")),
    ("media-partial-swap", lambda: standard("/MediaBox [612 0 0 792] /CropBox [-40 0 612 792]")),
    # UserUnit + crop coincidence: crop 306x396 (half) at unit 2 -> rect 612x792
    ("unit2-crop-half", lambda: standard(f"{L} /UserUnit 2 /CropBox [0 0 306 396]")),
    ("unit2-crop-half-top", lambda: standard(f"{L} /UserUnit 2 /CropBox [0 396 306 792]")),
    ("unit0.5-crop-double", lambda: standard(f"{L} /UserUnit 0.5 /CropBox [-306 -396 918 1188]")),
    # boxes via inheritance / references in new shapes
    ("crop-ref-to-ref-array", lambda: standard(f"{L} /CropBox 4 0 R", extra_objects=["5 0 R", "[-40 -60 660 820]"])),
    ("media-inherit-crop-ref", lambda: standard("/CropBox 4 0 R", pages_extra=L, extra_objects=["[-40 -60 660 820]"])),
    ("crop-dict", lambda: standard(f"{L} /CropBox << /A 1 >>")),
    ("crop-string", lambda: standard(f"{L} /CropBox (abc)")),
    ("crop-5-entries-first-4-over", lambda: standard(f"{L} /CropBox [-40 -60 660 820 999]")),
    ("crop-ref-elements", lambda: standard(f"{L} /CropBox [4 0 R 5 0 R 660 820]", extra_objects=["-40", "-60"])),
    ("crop-cycle-ref", lambda: standard(f"{L} /CropBox 4 0 R", extra_objects=["5 0 R", "4 0 R"])),
    ("unit-cycle-ref", lambda: standard(f"{L} /UserUnit 4 0 R", extra_objects=["5 0 R", "4 0 R"])),
    ("rot-cycle-ref", lambda: standard(f"{L} /Rotate 4 0 R", extra_objects=["5 0 R", "4 0 R"])),
    ("rot-string", lambda: standard(f"{L} /Rotate (90)")),
    ("rot-name", lambda: standard(f"{L} /Rotate /90")),
    ("rot-bool", lambda: standard(f"{L} /Rotate true")),
    ("rot-array", lambda: standard(f"{L} /Rotate [90]")),
    ("unit-bool", lambda: standard(f"{L} /UserUnit true")),
    ("no-type-page", lambda: build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Parent 2 0 R {L} /CropBox [-40 -60 660 820] >>",
    ])),
    ("kids-loop", lambda: build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 /Parent 2 0 R /CropBox [-40 -60 660 820] >>",
        f"<< /Type /Page /Parent 2 0 R {L} >>",
    ])),
    ("parent-self-crop", lambda: build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 3 0 R {L} /CropBox [-40 -60 660 820] >>",
    ])),
    ("parent-self-nocrop", lambda: build([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",
        f"<< /Type /Page /Parent 3 0 R {L} >>",
    ])),
    ("annots-page", lambda: standard(f"{L} /Annots [] /UserUnit -1 /Rotate 90")),
]

TABLE_ROWS = None  # filled from the test module


def load_table():
    import importlib
    mod = importlib.import_module("tests.test_geometry")
    return [(cid, b, exp) for cid, b, exp in mod._ADVERSARIAL_TABLE]


def show(rows, with_expected=False):
    for row in rows:
        cid, builder = row[0], row[1]
        expected = row[2] if with_expected else ""
        info, probe = evaluate(builder())
        if isinstance(info, str):
            print(f"{cid:34} INFO={info}  probe={probe}")
            continue
        bypass = ""
        if isinstance(probe, tuple) and probe[0] and info["text"] == "-":
            bypass = "  <<< BYPASS"
        if isinstance(probe, str):
            bypass = "  <<< PROBE " + probe[:60]
        flag = ""
        if with_expected and expected != info["text"] and not (expected == "any" and info["text"] != "-"):
            flag = f"  <<< TABLE SAYS {expected}"
        print(f"{cid:34} text={info['text']:6} other={info['other']:6} probe={probe} rot={info['rot']} "
              f"unit={info['unit']} rect={info['rect']} tm={info['tm']} media={info['media']} crop={info['crop']}{bypass}{flag}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("table", "all"):
        print("=== 39-row table, real gate ===")
        show(load_table(), with_expected=True)
    if which in ("new", "all"):
        print("=== new rows ===")
        show(NEW_ROWS)
    if which in ("matrix", "all"):
        print("=== matrix: transformation_matrix terms and gate/probe agreement ===")
        offdiag = []
        wrongsign = []
        fixed_at_rot = 0
        mism = []
        n = 0
        for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
            n += 1
            doc = matrix_page(media, crop, unit, rot)
            b = doc.tobytes()
            doc.close()
            d = fitz.open(stream=b, filetype="pdf")
            p = d[0]
            m = p.transformation_matrix
            if abs(m.b) > 1e-9 or abs(m.c) > 1e-9:
                offdiag.append((name, tuple(m)))
            if not (m.a > 0 and m.d < 0):
                wrongsign.append((name, tuple(m)))
            if rot != 0 and tuple(m) == (1, 0, 0, -1, 0, p.cropbox.height):
                fixed_at_rot += 1
            reason = drawing_refusal(p, 0, TEXT_DRAWING)
            d.close()
            drifted, origin = drift_probe(b)
            if unit == 1:
                if drifted and (reason is None or "CropBox" not in reason):
                    mism.append((name, reason, origin))
                if not drifted and reason is not None:
                    mism.append((name, reason, origin))
            else:
                if reason is None or f"{unit:g}" not in reason:
                    mism.append((name, reason, origin))
        print(f"cases={n} offdiag={len(offdiag)} wrongsign={len(wrongsign)} fixed_matrix_at_rotated={fixed_at_rot} mismatches={len(mism)}")
        for x in (offdiag + wrongsign + mism)[:10]:
            print("  ", x)
