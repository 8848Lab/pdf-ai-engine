"""Adversarial probes against engine.geometry.drawing_refusal (read-only on the checkout)."""
import sys
import threading
import time
import traceback

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

from engine.geometry import (  # noqa: E402
    OTHER_DRAWING,
    TEXT_DRAWING,
    crop_origin_overhangs,
    drawing_refusal,
    raw_rotation,
    user_unit,
)


def build(objects: list[str]) -> bytes:
    """objects[0] is obj 1. Trailer /Root 1 0 R."""
    body = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref_offset = len(body)
    n = len(objects) + 1
    xref = f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return body + xref + trailer


def standard(page_extra="", pages_extra="", extra_objects=()):
    """Catalog=1, Pages=2, Page=3, extras from 4."""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [3 0 R] /Count 1 {pages_extra} >>",
        f"<< /Type /Page /Parent 2 0 R {page_extra} >>",
        *extra_objects,
    ]
    return build(objs)


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
        return "HANG(>%ss)" % seconds
    if "error" in box:
        return "EXC " + box["error"]
    return box["value"]


def probe_drift(pdf_bytes):
    """Insert PROBE at (100,140), reopen, report origin and whether it drifted."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    page.insert_text((100, 140), "PROBE", fontsize=10)
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    p = reopened[0]
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    d = p.get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    origin = None
    for block in d["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"] == "PROBE":
                    origin = span["origin"]
    reopened.close()
    if origin is None:
        return None, "PROBE-NOT-FOUND"
    drifted = abs(origin[0] - 100) > 0.01 or abs(origin[1] - 140) > 0.01
    return drifted, (round(origin[0], 3), round(origin[1], 3))


def gate(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    out = {}
    out["raw_rotation"] = with_timeout(lambda: raw_rotation(page))
    out["user_unit"] = with_timeout(lambda: user_unit(page))
    out["overhang"] = with_timeout(lambda: crop_origin_overhangs(page))
    out["refuse_text"] = with_timeout(lambda: drawing_refusal(page, 0, TEXT_DRAWING))
    out["refuse_other"] = with_timeout(lambda: drawing_refusal(page, 0, OTHER_DRAWING))
    return out


def pymupdf_view(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    out = {}
    for name in ("rotation", "rect", "mediabox", "cropbox"):
        out[name] = with_timeout(lambda n=name: getattr(page, n))
    return out


def report(title, pdf_bytes):
    print("=" * 78)
    print(title)
    t0 = time.perf_counter()
    g = gate(pdf_bytes)
    t1 = time.perf_counter()
    print(f"  gate ({t1 - t0:.3f}s): raw_rotation={g['raw_rotation']!r} user_unit={g['user_unit']!r} "
          f"overhang={g['overhang']!r}")
    rt = g["refuse_text"]
    ro = g["refuse_other"]
    print(f"  refuse_text = {('REFUSED: ' + rt[:70]) if isinstance(rt, str) and rt.startswith('Page') else rt!r}")
    print(f"  refuse_other= {('REFUSED: ' + ro[:70]) if isinstance(ro, str) and ro.startswith('Page') else ro!r}")
    v = pymupdf_view(pdf_bytes)
    print(f"  pymupdf: rotation={v['rotation']!r} rect={v['rect']!r}")
    print(f"           mediabox={v['mediabox']!r} cropbox={v['cropbox']!r}")
    dr = with_timeout(lambda: probe_drift(pdf_bytes), 10)
    print(f"  drift probe: {dr!r}")
    return g, v, dr


if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]

    def want(tag):
        return "all" in which or tag in which

    LETTER = "/MediaBox [0 0 612 792]"

    if want("chain"):
        # A. Deep reference chain on /UserUnit: 4 -> 5 -> ... -> last = 2
        for depth in (3, 50, 200, 5000):
            chain = [f"{5 + i} 0 R" for i in range(depth - 1)] + ["2"]
            pdf = standard(f"{LETTER} /UserUnit 4 0 R", extra_objects=chain)
            report(f"A. /UserUnit reference chain depth={depth}", pdf)

    if want("parentref"):
        # B. /Parent is an indirect reference to a reference to /Pages (which carries /Rotate 45)
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Rotate 45 >>",
            f"<< /Type /Page /Parent 4 0 R {LETTER} >>",
            "2 0 R",
        ])
        report("B1. /Parent -> obj4 ('2 0 R') -> /Pages with /Rotate 45", pdf)
        # B2. same but the ancestor carries an overhanging CropBox
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",
            f"<< /Type /Page /Parent 4 0 R {LETTER} >>",
            "2 0 R",
        ])
        report("B2. /Parent -> obj4 ('2 0 R') -> /Pages with overhanging CropBox", pdf)
        # B3. /Parent points at a non-dict (an int)
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 4 0 R {LETTER} >>",
            "42",
        ])
        report("B3. /Parent -> int object", pdf)
        # B4. /Parent dangling (object 99 does not exist)
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 99 0 R {LETTER} >>",
        ])
        report("B4. /Parent -> dangling xref 99", pdf)
        # B5. /Parent cycle through an indirect reference object: page -> 4 ('3 0 R')
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 4 0 R {LETTER} >>",
            "3 0 R",
        ])
        report("B5. /Parent -> obj4 ('3 0 R') -> back to the page (cycle via reference object)", pdf)
        # B6. two-node /Parent cycle between /Pages nodes with nothing set
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Parent 4 0 R >>",
            "<< /Type /Page /Parent 2 0 R >>",
            "<< /Type /Pages /Kids [2 0 R] /Count 1 /Parent 2 0 R >>",
        ])
        report("B6. /Pages <-> /Pages cycle, no MediaBox anywhere", pdf)

    if want("dangling"):
        for key, val in (("UserUnit", "99 0 R"), ("Rotate", "99 0 R"), ("MediaBox", "99 0 R"), ("CropBox", "99 0 R")):
            extra = f"{LETTER} /{key} {val}" if key != "MediaBox" else f"/{key} {val}"
            report(f"C. /{key} -> dangling xref 99", standard(extra))
        # xref present in table but object is 'null'
        report("C2. /UserUnit -> explicit null object", standard(f"{LETTER} /UserUnit 4 0 R", extra_objects=["null"]))

    if want("huge"):
        for rot in ("257698037790", "4294967386", "2147483738", "9223372036854775898", "99999999999999999999999",
                    "1e30", "9e1", "90.0", "90.5", "89.99999999999999999", "90.00000001", "-0", "+90"):
            report(f"D. /Rotate {rot}", standard(f"{LETTER} /Rotate {rot}"))

    if want("unit"):
        for uu in ("1.0000001", "1.00000001", "1.0", "1.", "1", "0", "-1", "true", "4294967297", "1e0",
                   "99999999999999999999999", "0.5", "(2)", "[2]", "<< >>"):
            report(f"E. /UserUnit {uu}", standard(f"{LETTER} /UserUnit {uu}"))

    if want("boxes"):
        # G. indirect element inside a box array
        report("G1. CropBox [4 0 R -60 660 820] with obj4 = -40",
               standard(f"{LETTER} /CropBox [4 0 R -60 660 820]", extra_objects=["-40"]))
        report("G2. MediaBox [4 0 R 0 612 792] (obj4=-100) + CropBox [-40 0 612 792]",
               standard("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["-100"]))
        # H. five-entry boxes
        report("H1. CropBox with 5 entries [-40 -60 660 820 0]", standard(f"{LETTER} /CropBox [-40 -60 660 820 0]"))
        report("H2. MediaBox with 5 entries [0 0 612 792 0] + overhanging CropBox",
               standard("/MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820]"))
        # I. malformed MediaBox with an overhanging CropBox
        report("I1. MediaBox [0 0 612] (3 entries) + CropBox [-40 -60 660 820]",
               standard("/MediaBox [0 0 612] /CropBox [-40 -60 660 820]"))
        report("I2. MediaBox [0 0 612 /Foo] + CropBox [-40 -60 660 820]",
               standard("/MediaBox [0 0 612 /Foo] /CropBox [-40 -60 660 820]"))
        report("I3. MediaBox absent entirely + CropBox [-40 -60 660 820]",
               standard("/CropBox [-40 -60 660 820]"))
        report("I4. MediaBox [0 0 612 792] CropBox [-40 -60 660 /Foo]",
               standard(f"{LETTER} /CropBox [-40 -60 660 /Foo]"))
        report("I5. CropBox with 3 entries [-40 -60 660] (MuPDF -> empty rect?)",
               standard(f"{LETTER} /CropBox [-40 -60 660]"))
        report("I6. CropBox [-40 -60 660 820 % comment] via nested array [[-40 -60 660 820]]",
               standard(f"{LETTER} /CropBox [[-40 -60 660 820]]"))

    if want("nullwalk"):
        # J. page-level key is an unresolvable/null indirect; ancestor provides a different box.
        # Chosen so the CropBox drifts against the default letter box but NOT against the inherited one.
        for label, page_media, extras in (
            ("null object", "4 0 R", ["null"]),
            ("cycle 4<->5", "4 0 R", ["5 0 R", "4 0 R"]),
            ("dangling 99", "99 0 R", []),
        ):
            pdf = build([
                "<< /Type /Catalog /Pages 2 0 R >>",
                "<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [-100 -100 512 692] >>",
                f"<< /Type /Page /Parent 2 0 R /MediaBox {page_media} /CropBox [-40 0 612 692] >>",
                *extras,
            ])
            report(f"J. page /MediaBox -> {label}; parent MediaBox [-100 -100 512 692]; CropBox [-40 0 612 692]", pdf)
        # J2: same idea for CropBox -> null with an overhanging parent CropBox (the fix's own test scenario)
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /CropBox [-40 -60 660 820] >>",
            f"<< /Type /Page /Parent 2 0 R {LETTER} /CropBox 4 0 R >>",
            "null",
        ])
        report("J2. page /CropBox -> null object; parent CropBox overhangs (fix test scenario)", pdf)
        # J3: page /Rotate -> null, parent /Rotate 45
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Rotate 45 >>",
            f"<< /Type /Page /Parent 2 0 R {LETTER} /Rotate 4 0 R >>",
            "null",
        ])
        report("J3. page /Rotate -> null object; parent /Rotate 45", pdf)
        # J4: page /Rotate -> cycle, parent /Rotate 45
        pdf = build([
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Rotate 45 >>",
            f"<< /Type /Page /Parent 2 0 R {LETTER} /Rotate 4 0 R >>",
            "5 0 R", "4 0 R",
        ])
        report("J4. page /Rotate -> cycle; parent /Rotate 45", pdf)

    if want("deepparent"):
        # K. a very deep but finite /Parent chain: Rotate 45 at the root
        depth = 3000
        objs = ["<< /Type /Catalog /Pages 4 0 R >>", "placeholder", f"<< /Type /Page /Parent 4 0 R {LETTER} >>"]
        # objects 4..(4+depth-1) are /Pages nodes; node i has /Parent i+1; the last has /Rotate 45
        for i in range(depth):
            num = 4 + i
            if i == depth - 1:
                objs.append(f"<< /Type /Pages /Kids [{num - 1} 0 R] /Count 1 /Rotate 45 >>")
            else:
                kid = 3 if i == 0 else num - 1
                objs.append(f"<< /Type /Pages /Kids [{kid} 0 R] /Count 1 /Parent {num + 1} 0 R >>")
        objs[1] = "null"
        report(f"K. /Parent chain depth={depth}, /Rotate 45 at the root", build(objs))

    if want("mixed"):
        # L. mixed indirect ancestors: page -> Parent 2 (direct); 2 has /Parent 4 0 R where obj 4 = '5 0 R'; obj5 = /Pages with /Rotate 4 0 R? keep simpler:
        pdf = build([
            "<< /Type /Catalog /Pages 5 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Parent 4 0 R >>",
            f"<< /Type /Page /Parent 2 0 R {LETTER} >>",
            "5 0 R",
            "<< /Type /Pages /Kids [2 0 R] /Count 1 /Rotate 6 0 R >>",
            "7 0 R",
            "45",
        ])
        report("L1. grandparent reached via reference object, /Rotate via 2-hop chain = 45", pdf)
        pdf = build([
            "<< /Type /Catalog /Pages 5 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 /Parent 4 0 R >>",
            f"<< /Type /Page /Parent 2 0 R {LETTER} >>",
            "5 0 R",
            "<< /Type /Pages /Kids [2 0 R] /Count 1 /UserUnit 2 /CropBox 6 0 R >>",
            "7 0 R",
            "[-40 -60 660 820]",
        ])
        report("L2. grandparent via reference object; CropBox via 2-hop chain overhangs; UserUnit on ancestor", pdf)
