"""Re-review 4: verify fix round 5 (d545d86) and attack the 2**18 real-extent rule.

Sections (arg): nb1, nb2, attack, matrix, table, all.
"""
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

from engine.geometry import (  # noqa: E402
    OTHER_DRAWING, TEXT_DRAWING, at_rotation_zero, drawing_refusal, layout_orientation, page_transform,
)
from engine.operations import _erase_region  # noqa: E402
from tests.geometry_helpers import (  # noqa: E402
    broken_xref, drift_probe, find_span_bbox, matrix_cases, matrix_page, standard, with_text,
)
from round4 import cat, frac_probe, with_timeout  # noqa: E402

L = "/MediaBox [0 0 612 792]"
INF = "/MediaBox [-2147483648 -2147483648 2147483520 2147483520]"
B = 2 ** 18


def info(pdf_bytes):
    def inner():
        d = fitz.open(stream=pdf_bytes, filetype="pdf")
        p = d[0]
        m = page_transform(p)
        out = dict(
            rot=p.rotation,
            rect=tuple(round(v, 4) for v in p.rect),
            media=tuple(round(v, 4) for v in p.mediabox),
            crop=tuple(round(v, 4) for v in p.cropbox),
            ctm=None if m is None else tuple(round(v, 4) for v in m),
            layout=layout_orientation(p),
            text=cat(drawing_refusal(p, 0, TEXT_DRAWING)),
            other=cat(drawing_refusal(p, 0, OTHER_DRAWING)),
        )
        d.close()
        return out
    return with_timeout(inner)


def redaction(pdf_bytes):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    p = d[0]
    other = cat(drawing_refusal(p, 0, OTHER_DRAWING))
    bbox = find_span_bbox(p, "VISIBLE")
    if bbox is None:
        d.close()
        return dict(other=other, bbox=None)
    with at_rotation_zero(p):
        _erase_region(p, bbox, fill=(0, 1, 0))
    re = fitz.open(stream=d.tobytes(), filetype="pdf")
    d.close()
    p2 = re[0]
    gone = find_span_bbox(p2, "VISIBLE") is None
    fills = [fitz.Rect(x["rect"]) for x in p2.get_drawings() if x.get("fill") == (0, 1, 0)]
    re.close()
    if not fills:
        return dict(other=other, gone=gone, n=0)
    f = fills[0]
    off = max(abs(f.x0 - bbox.x0), abs(f.y0 - bbox.y0), abs(f.x1 - bbox.x1), abs(f.y1 - bbox.y1))
    return dict(other=other, gone=gone, n=len(fills), off=round(off, 4))


def line(cid, b, point=None, red=None):
    i = info(b)
    probe = with_timeout(lambda: drift_probe(b))
    fr = ""
    if point is not None and not isinstance(i, str):
        drift, origin = with_timeout(lambda: frac_probe(b, point))
        fr = f" frac@{point}={drift if drift is None else round(drift, 4)}"
    rd = ""
    if red is not None:
        r = with_timeout(lambda: redaction(red))
        rd = f" redact={r}"
    if isinstance(i, str):
        print(f"{cid:36} {i} probe={probe}{fr}{rd}")
        return
    print(f"{cid:36} gate={i['text']}/{i['other']} rot={i['rot']} lay={i['layout']} ctm={i['ctm']}\n"
          f"{'':36} rect={i['rect']} media={i['media']} crop={i['crop']} probe={probe}{fr}{rd}")


def nb1():
    print("=== NB1: infinite MediaBox with a repaired xref ===")
    rows = [
        ("inf-repaired", broken_xref(standard(INF)), broken_xref(with_text(INF))),
        ("inf-repaired-rot90", broken_xref(standard(f"{INF} /Rotate 90")), broken_xref(with_text(f"{INF} /Rotate 90"))),
        ("inf-repaired-rot180", broken_xref(standard(f"{INF} /Rotate 180")), None),
        ("inf-repaired-rot270", broken_xref(standard(f"{INF} /Rotate 270")), None),
        ("inf-inherited-repaired", broken_xref(standard("", pages_extra=INF)), None),
        ("inf-repaired-crop-letter", broken_xref(standard(f"{INF} /CropBox [0 0 612 792]")),
         broken_xref(with_text(f"{INF} /CropBox [0 0 612 792]"))),
        ("inf-repaired-crop-letter-rot90", broken_xref(standard(f"{INF} /CropBox [0 0 612 792] /Rotate 90")),
         broken_xref(with_text(f"{INF} /CropBox [0 0 612 792] /Rotate 90"))),
        ("inf-repaired-crop-offset", broken_xref(standard(f"{INF} /CropBox [200000 0 200612 792]")), None),
        ("inf-repaired-crop-huge", broken_xref(standard(f"{INF} /CropBox [0 0 300000 792]")), None),
        ("inf-repaired-unit2", broken_xref(standard(f"{INF} /UserUnit 2")), None),
        ("inf-repaired-unit-1", broken_xref(standard(f"{INF} /UserUnit -1")), None),
        # other ways MuPDF might fall back: huge but finite boxes
        ("media-2^31", standard("/MediaBox [0 0 2147483648 792]"), None),
        ("media-2^31-sym", standard("/MediaBox [-2147483648 -2147483648 2147483647 2147483647]"), None),
        ("media-1e12", standard("/MediaBox [0 0 1e12 792]"), None),
        ("media-1e12-sym", standard("/MediaBox [-1e12 -1e12 1e12 1e12]"), None),
        ("media-1e38", standard("/MediaBox [0 0 1e38 792]"), None),
        ("media-1e39", standard("/MediaBox [0 0 1e39 792]"), None),  # overflows float32
        ("media-1e39-repaired", broken_xref(standard("/MediaBox [0 0 1e39 792]")), None),
        ("media-neg1e39-repaired", broken_xref(standard("/MediaBox [-1e39 0 612 792]")), None),
        ("crop-1e39-repaired", broken_xref(standard(f"{L} /CropBox [0 0 1e39 792]")), None),
        ("media-inf-rot90-repaired-text", broken_xref(with_text(f"{INF} /Rotate 90")), None),
    ]
    fitz.TOOLS.mupdf_warnings(reset=True)
    for cid, b, red in rows:
        line(cid, b, red=red)


def nb2():
    print("=== NB2: threshold 2**18, fractional probes near the bound ===")
    # (id, mediabox, page-space fractional point near the far edge)
    rows = []
    for x1 in (262112, 262143, 262143.99, 262144, 262144.01, 262144.02, 262144.5, 262145, 262200, 524288):
        rows.append((f"media-0-{x1}", f"/MediaBox [0 0 {x1} 792]", (x1 - 100.3, 140.7)))
    for x0 in (261500, 261531, 261532, 261532.5, 261533, 262000):
        rows.append((f"offset-{x0}", f"/MediaBox [{x0} 0 {x0 + 612} 792]", (511.7, 140.7)))
    for y in (261352, 261353, 261000):
        rows.append((f"yoffset-{y}", f"/MediaBox [0 {y} 612 {y + 792}]", (511.7, 140.7)))
        rows.append((f"yoffset-{y}-topfrac", f"/MediaBox [0 {y} 612 {y + 792}]", (511.7, 0.7)))
    rows.append(("neg-offset", "/MediaBox [-262112 0 -261500 792]", (100.3, 140.7)))
    rows.append(("neg-offset-2^18", "/MediaBox [-262144 0 -261532 792]", (0.3, 140.7)))
    rows.append(("sym-2^17", "/MediaBox [-131072 0 131072 792]", (262043.7, 140.7)))
    rows.append(("sym-2^17+1", "/MediaBox [-131073 0 131072 792]", (262043.7, 140.7)))
    rows.append(("tall-2^18", "/MediaBox [0 0 612 262144]", (511.7, 262043.7)))
    rows.append(("tall-2^18-top", "/MediaBox [0 0 612 262144]", (511.7, 0.7)))
    rows.append(("tall-2^18+1", "/MediaBox [0 0 612 262145]", (511.7, 262043.7)))
    for cid, media, pt in rows:
        b = standard(media)
        line(cid, b, point=pt)
    # the test's own numbers
    for off in (261500, 2 ** 20):
        b = standard(f"/MediaBox [{off} 0 {off + 612} 792]")
        drift, origin = frac_probe(b, (511.7, 140.7))
        print(f"test-numbers offset={off}: drift={drift:.4f} origin={origin}")
    # worst case: sweep fractional x over the top grid range just under 2^18
    worst = 0.0
    b = standard("/MediaBox [261532 0 262144 792]")
    for k in range(0, 40):
        x = 611.0 + k * 0.023  # PDF x from 262143.0 to ~262143.9
        drift, _ = frac_probe(b, (x, 140.7 + k * 0.017))
        worst = max(worst, drift or 0)
    print(f"sweep just under 2^18 (40 fractional points): worst drift={worst:.5f}")


def attack():
    print("=== e/f vs boxes ===")
    rows = [
        # boxes small, e/f large: only through fallback; try CropBox beyond MediaBox
        ("crop-beyond-neg2^24", f"{L} /CropBox [-16777216 0 612 792]", None, with_text(f"{L} /CropBox [-16777216 0 612 792]")),
        ("crop-beyond-neg2^18+1", f"{L} /CropBox [-262145 0 612 792]", None, None),
        ("crop-beyond-2^18+1", f"{L} /CropBox [0 0 262145 792]", None, None),
        ("crop-beyond-1e9", f"{L} /CropBox [-1e9 -1e9 1e9 1e9]", None, None),
        # boxes large, e/f small
        ("media-2^18+1", "/MediaBox [0 0 262145 792]", None, None),
        ("media-crop-small", "/MediaBox [0 0 262145 792] /CropBox [0 0 612 792]", (511.7, 140.7), with_text("/MediaBox [0 0 262145 792] /CropBox [0 0 612 792]")),
        ("media-2^20-crop-letter", "/MediaBox [0 0 1048576 792] /CropBox [0 0 612 792]", (511.7, 140.7), None),
        ("media-neg-crop-far", "/MediaBox [-262144 0 262144 792] /CropBox [261532 0 262144 792]", (511.7, 140.7), None),
        ("media-2^18-crop-far", "/MediaBox [0 0 262144 792] /CropBox [261532 0 262144 792]", (511.7, 140.7), with_text("/MediaBox [0 0 262144 792] /CropBox [261532 0 262144 792]")),
        ("media-2^18-crop-far-over", "/MediaBox [0 0 262144 792] /CropBox [261532 -10 262144 792]", (511.7, 140.7), with_text("/MediaBox [0 0 262144 792] /CropBox [261532 -10 262144 792]")),
    ]
    for cid, extra, pt, red in rows:
        line(cid, standard(extra), point=pt, red=red)

    print("=== rotation + far offset ===")
    for media, pt in (("[261500 0 262112 792]", (511.7, 140.7)), ("[0 261352 612 262144]", (511.7, 140.7)),
                      ("[-262112 0 -261500 792]", (511.7, 140.7)), ("[261532 261352 262144 262144]", (0.3, 0.7)),
                      ("[262000 0 262612 792]", (511.7, 140.7)), ("[0 262000 612 262792]", (511.7, 140.7))):
        for rot in (0, 90, 180, 270):
            extra = f"/MediaBox {media} /Rotate {rot}"
            # for rotated pages the far-corner point in page space: page rect is rotated
            p = pt if rot in (0, 180) else (pt[1], pt[0])
            line(f"{media}/R{rot}", standard(extra), point=p, red=with_text(extra))

    print("=== /UserUnit + offset ===")
    rows = [
        "/MediaBox [261500 0 262112 792] /UserUnit 1.00001",
        "/MediaBox [261500 0 262112 792] /UserUnit 0.99999",
        "/MediaBox [261500 0 262112 792] /UserUnit 1.00001 /Rotate 90",
        "/MediaBox [261500 0 262112 792] /UserUnit 1.00001 /Rotate 270",
        "/MediaBox [-262144 0 -261532 792] /UserUnit 1.00001",
        "/MediaBox [-262144 0 -261532 792] /UserUnit 1.00001 /Rotate 180",
        "/MediaBox [-262144 0 -261532 792] /UserUnit 1.0000001",
        "/MediaBox [0 0 262144 792] /UserUnit 1.00000001",
        "/MediaBox [0 0 262144 792] /UserUnit 1.00000005",
        "/MediaBox [0 0 262144 792] /UserUnit 1.00000006",
        "/MediaBox [0 0 262144 792] /UserUnit 1.0000001",
        "/MediaBox [0 0 262144 792] /UserUnit 0.9999999",
        "/MediaBox [0 0 262143 792] /UserUnit 1.0000001",
        "/MediaBox [0 0 262100 792] /UserUnit 1.0000001",
        "/MediaBox [0 0 131072 792] /UserUnit 2",
        "/MediaBox [0 0 131072 792] /UserUnit 2.0000001",
        "/MediaBox [0 0 262144 792] /UserUnit 1.00001",
        "/MediaBox [0 0 262144 792] /UserUnit 0.99999",
        "/MediaBox [0 0 262144 792] /UserUnit 1.00001 /Rotate 90",
        "/MediaBox [0 0 1000 792] /UserUnit 300",
        "/MediaBox [0 0 1000 792] /UserUnit 1e-5",
    ]
    for extra in rows:
        line(extra.replace("/MediaBox ", ""), standard(extra), point=(511.7, 140.7))


def matrix():
    print("=== 1,024 matrix: gate vs drift probe, plus fractional probe ===")
    bad = n = 0
    worst = 0.0
    for name, media, crop, unit, rot in matrix_cases(units=(0.5, 1, 1.5, 2)):
        n += 1
        doc = matrix_page(media, crop, unit, rot)
        b = doc.tobytes()
        doc.close()
        d = fitz.open(stream=b, filetype="pdf")
        r = cat(drawing_refusal(d[0], 0, TEXT_DRAWING))
        ro = cat(drawing_refusal(d[0], 0, OTHER_DRAWING))
        lay = layout_orientation(d[0])
        d.close()
        drifted, _ = drift_probe(b)
        if lay is None or lay[0] != rot or abs(lay[1] - unit) > 1e-6:
            bad += 1
            print("LAYOUT MISMATCH", name, lay)
        if (unit == 1 and ((drifted and r != "over") or (not drifted and r != "-"))) or (unit != 1 and r != "unit"):
            bad += 1
            print("MISMATCH", name, r, drifted)
        if unit == 1 and ro != "-":
            bad += 1
            print("OTHER MISMATCH", name, ro)
        if r == "-":
            drift, _ = frac_probe(b, (100.3, 140.7))
            if drift is None or drift > 0.01:
                bad += 1
                print("FRAC MISMATCH", name, drift)
            else:
                worst = max(worst, drift)
    print(f"matrix cases={n} mismatches={bad} worst fractional drift on allowed={worst:.5f}")


def table():
    print("=== Test B table through the real gate (spec.standard), plus redaction on -/over ===")
    import importlib
    mod = importlib.import_module("tests.test_geometry")
    bad = 0
    for cid, spec, exp in mod._ADVERSARIAL_TABLE:
        b = spec.standard()
        i = info(b)
        probe = with_timeout(lambda: drift_probe(b))
        got = (i["text"], i["other"]) if not isinstance(i, str) else i
        ok = True
        if exp == "-":
            ok = got == ("-", "-") and probe[0] is False
        elif exp == "over":
            ok = got == ("over", "-")
        elif exp == "any":
            ok = got[0] != "-" and probe[0] is None
        else:
            ok = got == (exp, exp)
        if probe[0] and got[0] == "-":
            ok = False
        red = ""
        if exp in ("-", "over"):
            r = redaction(spec.with_text())
            red = f" redact={r}"
            if r.get("n") != 1 or not r.get("gone") or r.get("off", 1) > 0.01:
                ok = False
        if not ok:
            bad += 1
        print(f"{'OK ' if ok else 'BAD'} {cid:32} exp={exp:6} got={got} probe={probe}{red}")
    print("rows:", len(mod._ADVERSARIAL_TABLE), "bad:", bad)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("nb1", nb1), ("nb2", nb2), ("attack", attack), ("matrix", matrix), ("table", table)):
        if which in (name, "all"):
            fn()
