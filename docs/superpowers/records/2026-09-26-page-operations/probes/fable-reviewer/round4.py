"""Re-review 3: attack the C16 gate (layout_orientation + size/tolerance/magnitude).

Sections:
  table   : Test B table + round3a NEW_ROWS through the real gate, with drift probe.
  matrix  : 1,024-case matrix, gate/probe agreement.
  new     : new rows for this round: gate, probe, fractional probe, redaction offset.
  closed  : the low-level API failing -> every page refused.
"""
import sys
import threading

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402
from pymupdf import mupdf  # noqa: E402

import engine.geometry as geo  # noqa: E402
from engine.geometry import (  # noqa: E402
    OTHER_DRAWING, TEXT_DRAWING, at_rotation_zero, drawing_refusal, layout_orientation, page_transform,
)
from engine.operations import _erase_region  # noqa: E402
from tests.geometry_helpers import (  # noqa: E402
    build, drift_probe, find_span_bbox, matrix_cases, matrix_page, standard, with_text,
)

L = "/MediaBox [0 0 612 792]"
INF = "/MediaBox [-2147483648 -2147483648 2147483520 2147483520]"


def with_timeout(fn, seconds=10):
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
        return "EXC " + box["error"][:80]
    return box["value"]


def cat(reason):
    if reason is None:
        return "-"
    for k, phrase in (("rot", "invalid rotation"), ("unit", "uses PDF /UserUnit"),
                      ("incons", "lays out inconsistently"), ("huge", "larger than"), ("over", "CropBox")):
        if phrase in reason:
            return k
    return "?"


def ctm_of(page):
    m = page_transform(page)
    return None if m is None else tuple(round(v, 4) for v in m)


def frac_probe(pdf_bytes, point):
    """insert_text at a fractional point, re-open, return (drift_pt, origin)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc[0].insert_text(point, "PROBE", fontsize=10)
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    text = reopened[0].get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    origin = next(
        (span["origin"] for block in text["blocks"] for line in block.get("lines", [])
         for span in line["spans"] if span["text"] == "PROBE"),
        None,
    )
    reopened.close()
    if origin is None:
        return None, None
    return max(abs(origin[0] - point[0]), abs(origin[1] - point[1])), tuple(round(v, 4) for v in origin)


def redaction(pdf_bytes):
    """Engine flow: bbox at the page's rotation, _erase_region inside at_rotation_zero."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    other = drawing_refusal(page, 0, OTHER_DRAWING)
    bbox = find_span_bbox(page, "VISIBLE")
    if bbox is None:
        doc.close()
        return dict(other=cat(other), bbox=None)
    with at_rotation_zero(page):
        _erase_region(page, bbox, fill=(0, 1, 0))
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    p = reopened[0]
    gone = find_span_bbox(p, "VISIBLE") is None
    fills = [fitz.Rect(d["rect"]) for d in p.get_drawings() if d.get("fill") is not None]
    reopened.close()
    if not fills:
        return dict(other=cat(other), bbox=tuple(round(v, 2) for v in bbox), gone=gone, fill=None, off=None, n=0)
    f = fills[0]
    off = max(abs(f.x0 - bbox.x0), abs(f.y0 - bbox.y0), abs(f.x1 - bbox.x1), abs(f.y1 - bbox.y1))
    return dict(other=cat(other), bbox=tuple(round(v, 2) for v in bbox), gone=gone,
                fill=tuple(round(v, 2) for v in f), off=round(off, 4), n=len(fills))


def evaluate(pdf_bytes):
    def inner():
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        info = dict(
            rot=page.rotation,
            rect=tuple(round(v, 3) for v in page.rect),
            media=tuple(round(v, 3) for v in page.mediabox),
            crop=tuple(round(v, 3) for v in page.cropbox),
            ctm=ctm_of(page),
            layout=layout_orientation(page),
            text=cat(drawing_refusal(page, 0, TEXT_DRAWING)),
            other=cat(drawing_refusal(page, 0, OTHER_DRAWING)),
        )
        doc.close()
        return info
    info = with_timeout(inner)
    probe = with_timeout(lambda: drift_probe(pdf_bytes))
    return info, probe


def show(rows, with_expected=False):
    n_bypass = 0
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
            n_bypass += 1
        if isinstance(probe, str):
            bypass = "  <<< PROBE " + probe[:60]
        flag = ""
        if with_expected and expected != info["text"] and not (expected == "any" and info["text"] != "-"):
            flag = f"  <<< TABLE SAYS {expected}"
        print(f"{cid:34} text={info['text']:6} other={info['other']:6} probe={probe} rot={info['rot']} "
              f"layout={info['layout']} rect={info['rect']} ctm={info['ctm']} crop={info['crop']}{bypass}{flag}")
    print(f"-- bypasses: {n_bypass}")


def load_table():
    import importlib
    mod = importlib.import_module("tests.test_geometry")
    return [(cid, b, exp) for cid, b, exp in mod._ADVERSARIAL_TABLE]


# --- new rows for this round -------------------------------------------------
def crop_sq(w, extra=""):
    return standard(f"{L} /CropBox [100 100 {100 + w} {100 + w}] {extra}")


NEW4 = [
    # mirror + MuPDF rotation snap: the ctm's linear part can match page.rotation again
    ("rot135-unit-1", lambda: standard(f"{L} /Rotate 135 /UserUnit -1")),
    ("rot224-unit-1", lambda: standard(f"{L} /Rotate 224 /UserUnit -1")),
    ("rot135-unit-1-crop", lambda: standard(f"{L} /CropBox [50 50 500 700] /Rotate 135 /UserUnit -1")),
    ("rot135-unit-1-square", lambda: standard("/MediaBox [0 0 600 600] /Rotate 135 /UserUnit -1")),
    ("rot-inh135-unit-1", lambda: standard(f"{L} /UserUnit -1", pages_extra="/Rotate 135")),
    ("rot135-indirect-unit-1", lambda: standard(f"{L} /Rotate 4 0 R /UserUnit -1", extra_objects=["135"])),
    ("rot45-unit-1", lambda: standard(f"{L} /Rotate 45 /UserUnit -1")),
    ("rot225-unit-1", lambda: standard(f"{L} /Rotate 225 /UserUnit -1")),
    ("rot315-unit-1", lambda: standard(f"{L} /Rotate 315 /UserUnit -1")),
    ("rot135-unit-2", lambda: standard(f"{L} /Rotate 135 /UserUnit -2")),
    ("rot135-unit-0.5", lambda: standard(f"{L} /Rotate 135 /UserUnit -0.5")),
    ("rot135-unit-1.0000001", lambda: standard(f"{L} /Rotate 135 /UserUnit -1.0000001")),
    ("rot135-unit-1-over", lambda: standard(f"{L} /CropBox [-40 -60 660 820] /Rotate 135 /UserUnit -1")),
    # tolerance-edge crop boxes (square, at 100,100)
    ("crop-0.99", lambda: crop_sq(0.99)),
    ("crop-0.995", lambda: crop_sq(0.995)),
    ("crop-0.999", lambda: crop_sq(0.999)),
    ("crop-0.9999", lambda: crop_sq(0.9999)),
    ("crop-0.99999", lambda: crop_sq(0.99999)),
    ("crop-0.9999999", lambda: crop_sq(0.9999999)),
    ("crop-1.0", lambda: crop_sq(1.0)),
    ("crop-1.005", lambda: crop_sq(1.005)),
    ("crop-1.01", lambda: crop_sq(1.01)),
    ("crop-0.995-rot90", lambda: crop_sq(0.995, "/Rotate 90")),
    ("crop-0.995-rot180", lambda: crop_sq(0.995, "/Rotate 180")),
    ("crop-0.995-unit0.5", lambda: crop_sq(0.995, "/UserUnit 0.5")),
    ("crop-0.995-unit2", lambda: crop_sq(0.995, "/UserUnit 2")),
    ("crop-0.5-unit2", lambda: crop_sq(0.5, "/UserUnit 2")),
    ("crop-0.995x300", lambda: standard(f"{L} /CropBox [100 100 100.995 400]")),
    ("crop-0.995x300-rot90", lambda: standard(f"{L} /CropBox [100 100 100.995 400] /Rotate 90")),
    ("crop-300x0.995-rot90", lambda: standard(f"{L} /CropBox [100 100 400 100.995] /Rotate 90")),
    ("crop-0.995-offset-media", lambda: standard("/MediaBox [50 50 662 842] /CropBox [100 100 100.995 100.995]")),
    ("crop-0.995-at-origin", lambda: standard(f"{L} /CropBox [0 0 0.995 0.995]")),
    ("crop-0.995-at-top", lambda: standard(f"{L} /CropBox [0 791.005 0.995 792]")),
    ("media-0.995", lambda: standard("/MediaBox [0 0 0.995 0.995]")),
    ("media-0.995-offset", lambda: standard("/MediaBox [100 100 100.995 100.995]")),
    ("media-0.995-crop-same", lambda: standard("/MediaBox [100 100 100.995 100.995] /CropBox [100 100 100.995 100.995]")),
    ("media-0.995-crop-big", lambda: standard("/MediaBox [100 100 100.995 100.995] /CropBox [0 0 612 792]")),
    ("media-tiny-crop-tiny-over", lambda: standard("/MediaBox [0 0 0.5 0.5] /CropBox [-0.3 -0.3 0.6 0.6]")),
    ("crop-float32-edge", lambda: standard(f"{L} /CropBox [0.3 0.3 1.3 1.3]")),
    ("crop-float32-edge2", lambda: standard(f"{L} /CropBox [16000.3 100 16001.3 101]")),
    ("crop-width-1-float32", lambda: standard(f"{L} /CropBox [100.00001 100 101 101]")),
    # scale / tolerance coincidences
    ("unit-1.0000163", lambda: standard(f"{L} /UserUnit 1.0000163")),
    ("unit-1.0000164", lambda: standard(f"{L} /UserUnit 1.0000164")),
    ("unit-1.00001-over", lambda: standard(f"{L} /UserUnit 1.00001 /CropBox [-40 -60 660 820]")),
    ("unit-1.00001-rot90", lambda: standard(f"{L} /UserUnit 1.00001 /Rotate 90")),
    ("unit-0.99999-rot270", lambda: standard(f"{L} /UserUnit 0.99999 /Rotate 270")),
    ("unit-1.00001-huge-offset", lambda: standard("/MediaBox [1000000 1000000 1000612 1000792] /UserUnit 1.00001")),
    ("unit-1-crop-half-rot90", lambda: standard(f"{L} /UserUnit -1 /CropBox [0 0 306 396] /Rotate 90")),
    # near 2^24 and page-space magnitude
    ("media-2^24", lambda: standard("/MediaBox [0 0 16777216 16777216]")),
    ("media-2^24+1", lambda: standard("/MediaBox [0 0 16777217 16777217]")),
    ("media-2^24+2", lambda: standard("/MediaBox [0 0 16777218 16777218]")),
    ("media-2^24-wide", lambda: standard("/MediaBox [0 0 16777216 792]")),
    ("media-2^24-offset", lambda: standard("/MediaBox [16776500 0 16777112 792]")),
    ("media-sym-2^24", lambda: standard("/MediaBox [-16777216 0 16777216 792]")),
    ("media-sym-2^24-tall", lambda: standard("/MediaBox [-16777216 -16777216 16777216 16777216]")),
    ("media-neg-2^24", lambda: standard("/MediaBox [-16777216 0 612 792]")),
    ("media-neg-2^24-y", lambda: standard("/MediaBox [0 -16777216 612 792]")),
    ("media-sym-1e7", lambda: standard("/MediaBox [-10000000 0 10000000 792]")),
    ("media-sym-2^23", lambda: standard("/MediaBox [-8388608 0 8388608 792]")),
    ("crop-neg-2^24", lambda: standard(f"{L} /CropBox [-16777216 0 612 792]")),
    ("crop-neg-2^24-y", lambda: standard(f"{L} /CropBox [0 -16777216 612 792]")),
    ("media-2^23", lambda: standard("/MediaBox [0 0 8388608 792]")),
    ("media-2^22", lambda: standard("/MediaBox [0 0 4194304 792]")),
    ("media-2^20", lambda: standard("/MediaBox [0 0 1048576 792]")),
    ("media-2^18", lambda: standard("/MediaBox [0 0 262144 792]")),
    ("media-2^17", lambda: standard("/MediaBox [0 0 131072 792]")),
    ("media-2^24-rot90", lambda: standard("/MediaBox [0 0 16777216 792] /Rotate 90")),
    ("media-2^24-unit1.0000001", lambda: standard("/MediaBox [0 0 16777216 792] /UserUnit 1.0000001")),
    # MuPDF's infinite rect: JM_mediabox falls back to letter, the transform does not
    ("media-inf", lambda: standard(INF)),
    ("media-inf-crop-letter", lambda: standard(f"{INF} /CropBox [0 0 612 792]")),
    ("media-inf-crop-offset", lambda: standard(f"{INF} /CropBox [100 100 712 892]")),
    ("media-inf-crop-letter-rot90", lambda: standard(f"{INF} /CropBox [0 0 612 792] /Rotate 90")),
    ("media-inf-crop-huge", lambda: standard(f"{INF} /CropBox [0 0 100000000 100000000]")),
    ("media-inf-crop-far", lambda: standard(f"{INF} /CropBox [100000000 100000000 100000612 100000792]")),
    ("crop-inf", lambda: standard(f"{L} /CropBox [-2147483648 -2147483648 2147483520 2147483520]")),
    ("media-inf-crop-inf", lambda: standard(f"{INF} /CropBox [-2147483648 -2147483648 2147483520 2147483520]")),
    ("media-inf-unit2", lambda: standard(f"{INF} /CropBox [0 0 612 792] /UserUnit 2")),
    ("media-inf-unit-1", lambda: standard(f"{INF} /CropBox [0 0 612 792] /UserUnit -1")),
    # misc
    ("annots-unit-1-rot90", lambda: standard(f"{L} /Annots [] /UserUnit -1 /Rotate 90")),
    ("rot90-unit1e-30", lambda: standard(f"{L} /Rotate 90 /UserUnit 1e-30")),
    ("rot90-unit1e30", lambda: standard(f"{L} /Rotate 90 /UserUnit 1e30")),
    ("unit-real-int", lambda: standard(f"{L} /UserUnit -1.0")),
    ("unit-neg-zero", lambda: standard(f"{L} /UserUnit -0.0")),
    ("unit-neg-tiny", lambda: standard(f"{L} /UserUnit -0.0000001")),
    ("rot270-unit-1-indirect-chain", lambda: standard(f"{L} /UserUnit 4 0 R /Rotate 270", extra_objects=["5 0 R", "-1"])),
]

# rows whose fractional placement matters: (id, builder, probe point)
FRAC = [
    ("letter", lambda: standard(L), (100.3, 140.7)),
    ("media-2^17", lambda: standard("/MediaBox [0 0 131072 792]"), (131072 - 100.3, 140.7)),
    ("media-2^18", lambda: standard("/MediaBox [0 0 262144 792]"), (262144 - 100.3, 140.7)),
    ("media-2^19", lambda: standard("/MediaBox [0 0 524288 792]"), (524288 - 100.3, 140.7)),
    ("media-2^20", lambda: standard("/MediaBox [0 0 1048576 792]"), (1048576 - 100.3, 140.7)),
    ("media-2^22", lambda: standard("/MediaBox [0 0 4194304 792]"), (4194304 - 100.3, 140.7)),
    ("media-2^23", lambda: standard("/MediaBox [0 0 8388608 792]"), (8388608 - 100.3, 140.7)),
    ("media-1e7", lambda: standard("/MediaBox [0 0 10000000 792]"), (10000000 - 100.3, 140.7)),
    ("media-2^24", lambda: standard("/MediaBox [0 0 16777216 792]"), (16777216 - 100.3, 140.7)),
    ("media-2^24-tall-y", lambda: standard("/MediaBox [0 0 612 16777216]"), (100.3, 140.7)),
    ("media-sym-2^24", lambda: standard("/MediaBox [-16777216 0 16777216 792]"), (16777216 + 100.3, 140.7)),
    ("media-neg-2^24", lambda: standard("/MediaBox [-16777216 0 612 792]"), (16777216 + 100.3, 140.7)),
    ("media-1e7-offset", lambda: standard("/MediaBox [10000000 0 10000612 792]"), (100.3, 140.7)),
    ("media-2^24-offset", lambda: standard("/MediaBox [16776500 0 16777112 792]"), (100.3, 140.7)),
]

# redaction rows: with_text draws VISIBLE at PDF (100, 600)
RED = [
    ("letter", lambda: with_text(L)),
    ("rot135-unit-1", lambda: with_text(f"{L} /Rotate 135 /UserUnit -1")),
    ("rot135-unit-1-crop", lambda: with_text(f"{L} /CropBox [50 50 500 700] /Rotate 135 /UserUnit -1")),
    ("rot135-unit-1-over", lambda: with_text(f"{L} /CropBox [-40 -60 660 820] /Rotate 135 /UserUnit -1")),
    ("media-inf-crop-letter", lambda: with_text(f"{INF} /CropBox [0 0 612 792]")),
    ("media-inf-crop-letter-rot90", lambda: with_text(f"{INF} /CropBox [0 0 612 792] /Rotate 90")),
    ("media-huge-1e7", lambda: with_text("/MediaBox [0 0 10000000 10000000]")),
    ("media-2^24", lambda: with_text("/MediaBox [0 0 16777216 16777216]")),
    ("media-2^24-wide", lambda: with_text("/MediaBox [0 0 16777216 792]")),
    ("media-sym-2^24", lambda: with_text("/MediaBox [-16777216 0 16777216 792]")),
    ("media-neg-2^24", lambda: with_text("/MediaBox [-16777216 0 612 792]")),
    ("media-neg-2^24-y", lambda: with_text("/MediaBox [0 -16777216 612 792]")),
    ("media-sym-1e7", lambda: with_text("/MediaBox [-10000000 0 10000000 792]")),
    ("media-sym-2^23", lambda: with_text("/MediaBox [-8388608 0 8388608 792]")),
    ("media-1e7-offset", lambda: with_text("/MediaBox [10000000 0 10000612 792]")),
    ("media-2^24-offset", lambda: with_text("/MediaBox [16776500 0 16777112 792]")),
    ("media-2^20-offset", lambda: with_text("/MediaBox [1048576 0 1049188 792]")),
    ("media-2^18-offset", lambda: with_text("/MediaBox [262144 0 262756 792]")),
    ("media-2^17-offset", lambda: with_text("/MediaBox [131072 0 131684 792]")),
    ("media-2^24-rot90", lambda: with_text("/MediaBox [0 0 16777216 792] /Rotate 90")),
    ("crop-neg-2^24", lambda: with_text(f"{L} /CropBox [-16777216 0 612 792]")),
    ("unit-1.0000163", lambda: with_text(f"{L} /UserUnit 1.0000163")),
    ("crop-1.0", lambda: with_text(f"{L} /CropBox [100 100 101 101]")),
]


def run_matrix():
    bad = 0
    n = 0
    for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
        n += 1
        doc = matrix_page(media, crop, unit, rot)
        b = doc.tobytes()
        doc.close()
        d = fitz.open(stream=b, filetype="pdf")
        r = cat(drawing_refusal(d[0], 0, TEXT_DRAWING))
        lay = layout_orientation(d[0])
        d.close()
        drifted, _ = drift_probe(b)
        if lay is None or lay[0] != rot or abs(lay[1] - unit) > 1e-6:
            bad += 1
            print("LAYOUT MISMATCH", name, lay)
        if (unit == 1 and ((drifted and r != "over") or (not drifted and r != "-"))) or (unit != 1 and r != "unit"):
            bad += 1
            print("MISMATCH", name, r, drifted)
    print(f"matrix cases={n} mismatches={bad}")


def run_closed():
    doc = fitz.open(stream=standard(L), filetype="pdf")
    page = doc[0]
    print("plain gate:", drawing_refusal(page, 0, TEXT_DRAWING), drawing_refusal(page, 0, OTHER_DRAWING))
    orig = geo.mupdf.pdf_page_transform
    for exc in (AttributeError, TypeError, RuntimeError):
        def boom(*a, **k):
            raise exc("simulated")
        geo.mupdf.pdf_page_transform = boom
        try:
            for kind in (TEXT_DRAWING, OTHER_DRAWING):
                try:
                    r = drawing_refusal(page, 0, kind)
                    print(f"  {exc.__name__:15} {kind:6} -> {cat(r)} {r and r[:60]!r}")
                except Exception as e:  # noqa: BLE001
                    print(f"  {exc.__name__:15} {kind:6} -> raised {type(e).__name__}: {e}")
        finally:
            geo.mupdf.pdf_page_transform = orig
    # missing private accessor
    saved = fitz.Page._pdf_page
    del fitz.Page._pdf_page
    try:
        for kind in (TEXT_DRAWING, OTHER_DRAWING):
            try:
                r = drawing_refusal(page, 0, kind)
                print(f"  no _pdf_page     {kind:6} -> {cat(r)}")
            except Exception as e:  # noqa: BLE001
                print(f"  no _pdf_page     {kind:6} -> raised {type(e).__name__}: {str(e)[:70]}")
    finally:
        fitz.Page._pdf_page = saved
    # a non-PDF page (image document) -- unreachable for the engine, but note the exception type
    img = fitz.open()
    img.close()
    try:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0)
        pngdoc = fitz.open("png", pix.tobytes("png"))
        p = pngdoc[0]
        try:
            r = drawing_refusal(p, 0, TEXT_DRAWING)
            print("  png page ->", cat(r))
        except Exception as e:  # noqa: BLE001
            print(f"  png page -> raised {type(e).__name__}: {str(e)[:60]}")
        pngdoc.close()
    except Exception as e:  # noqa: BLE001
        print("  png open failed:", type(e).__name__, e)
    doc.close()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("table", "all"):
        print("=== Test B table (real gate) ===")
        show(load_table(), with_expected=True)
        from round3a import NEW_ROWS
        print("=== round3a NEW_ROWS ===")
        show(NEW_ROWS)
    if which in ("new", "all"):
        print("=== round-4 new rows ===")
        show(NEW4)
    if which in ("frac", "all"):
        print("=== fractional-position drift (allowed pages only matter) ===")
        for cid, builder, point in FRAC:
            b = builder()
            d = fitz.open(stream=b, filetype="pdf")
            t = cat(drawing_refusal(d[0], 0, TEXT_DRAWING))
            d.close()
            drift, origin = frac_probe(b, point)
            flag = "  <<< ALLOWED, DRIFT > 0.01" if (t == "-" and (drift is None or drift > 0.01)) else ""
            print(f"{cid:22} text={t:6} point={point} origin={origin} drift={None if drift is None else round(drift, 5)}{flag}")
    if which in ("red", "all"):
        print("=== redaction placement (engine flow) ===")
        for cid, builder in RED:
            r = with_timeout(lambda: redaction(builder()), 20)
            if isinstance(r, str):
                print(f"{cid:28} {r}")
                continue
            flag = ""
            if r.get("bbox") is not None and r["other"] == "-" and (not r["gone"] or r["off"] is None or r["off"] > 0.01):
                flag = "  <<< ALLOWED FOR OTHER, FILL OFF > 0.01"
            print(f"{cid:28} other={r['other']:6} bbox={r.get('bbox')} gone={r.get('gone')} fill={r.get('fill')} off={r.get('off')} n={r.get('n')}{flag}")
    if which in ("matrix", "all"):
        print("=== matrix ===")
        run_matrix()
    if which in ("closed", "all"):
        print("=== fail-closed ===")
        run_closed()
