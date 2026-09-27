"""Re-review 3, part B: (1) why text at page-space x > 2^24 is unreadable; (2) scale-within-
tolerance times a large box offset, at every rotation; (3) the infinite-MediaBox page count."""
import sys

sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz  # noqa: E402

from engine.geometry import OTHER_DRAWING, TEXT_DRAWING, drawing_refusal  # noqa: E402
from tests.geometry_helpers import standard, with_text  # noqa: E402
from round4 import cat, frac_probe, redaction, INF, L  # noqa: E402

FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP


def spans(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    out = []
    t = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=FLAGS)
    for block in t["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                out.append((span["text"], tuple(round(v, 2) for v in span["bbox"])))
    words = page.get_text("words", clip=fitz.INFINITE_RECT(), flags=FLAGS)
    raw = page.get_text("rawdict", clip=fitz.INFINITE_RECT(), flags=FLAGS)
    chars = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for ch in span["chars"]:
                    chars.append((ch["c"], tuple(round(v, 2) for v in ch["bbox"])))
    doc.close()
    return out, [(w[4], tuple(round(v, 2) for v in w[:4])) for w in words], chars[:8]


print("=== (1) text beyond 2^24 in page space ===")
for cid, extra in [
    ("media-sym-2^24", "/MediaBox [-16777216 0 16777216 792]"),
    ("media-neg-2^24", "/MediaBox [-16777216 0 612 792]"),
    ("media-neg-1.5e7", "/MediaBox [-15000000 0 612 792]"),
    ("media-neg-9e6", "/MediaBox [-9000000 0 612 792]"),
    ("media-neg-2^23", "/MediaBox [-8388608 0 612 792]"),
    ("media-neg-2^24-y", "/MediaBox [0 -16777216 612 792]"),
    ("media-tall-2^24-textattop", "/MediaBox [0 0 612 16777216]"),
]:
    b = with_text(extra)
    d = fitz.open(stream=b, filetype="pdf")
    t, o = cat(drawing_refusal(d[0], 0, TEXT_DRAWING)), cat(drawing_refusal(d[0], 0, OTHER_DRAWING))
    d.close()
    sp, words, chars = spans(b)
    print(f"{cid:26} text={t:6} other={o:6} spans={sp} words={words}")
    print(f"{'':26} chars={chars}")

print()
print("=== (2) scale within tolerance x large offset, per rotation ===")
for x0 in (1000000, 16000000):
    for rot in (0, 90, 180, 270):
        for u in ("1.00001", "0.99999"):
            extra = f"/MediaBox [{x0} {x0} {x0 + 612} {x0 + 792}] /UserUnit {u} /Rotate {rot}"
            b = standard(extra)
            d = fitz.open(stream=b, filetype="pdf")
            t = cat(drawing_refusal(d[0], 0, TEXT_DRAWING))
            o = cat(drawing_refusal(d[0], 0, OTHER_DRAWING))
            d.close()
            drift, origin = frac_probe(b, (100.0, 140.0))
            r = redaction(with_text(extra))
            flag = ""
            if t == "-" and (drift is None or drift > 0.01):
                flag += "  <<< TEXT ALLOWED, DRIFT"
            if o == "-" and (r.get("bbox") is None or not r.get("gone") or r.get("off") is None or r["off"] > 0.01):
                flag += "  <<< OTHER ALLOWED, FILL OFF"
            print(f"x0={x0:8} rot={rot:3} u={u:8} text={t:6} other={o:6} probe drift={drift} origin={origin} "
                  f"redact off={r.get('off')} gone={r.get('gone')} bbox={r.get('bbox')}{flag}")

print()
print("=== (3) infinite MediaBox, no CropBox ===")
for cid, extra in [("media-inf", INF), ("media-inf-crop-inf", f"{INF} /CropBox [-2147483648 -2147483648 2147483520 2147483520]"),
                   ("media-inf-rot90", f"{INF} /Rotate 90")]:
    d = fitz.open(stream=standard(extra), filetype="pdf")
    print(f"{cid:22} page_count={d.page_count} is_pdf={d.is_pdf}", end=" ")
    try:
        p = d[0]
        print("loaded rect=", p.rect)
    except Exception as e:  # noqa: BLE001
        print(f"doc[0] raised {type(e).__name__}: {e}")
    d.close()

print()
print("=== (4) fractional drift for candidate bounds (page-space extent) ===")
for cid, extra, point in [
    ("sym-2^17 (extent 2^18)", "/MediaBox [-131072 0 131072 792]", (262144 - 100.3, 140.7)),
    ("sym-2^18 (extent 2^19)", "/MediaBox [-262144 0 262144 792]", (524288 - 100.3, 140.7)),
    ("offset-2^18", "/MediaBox [262144 0 262756 792]", (100.3, 140.7)),
    ("offset-2^19", "/MediaBox [524288 0 524900 792]", (100.3, 140.7)),
    ("tall-2^18", "/MediaBox [0 0 612 262144]", (100.3, 140.7)),
    ("tall-2^19", "/MediaBox [0 0 612 524288]", (100.3, 140.7)),
    ("14400", "/MediaBox [0 0 14400 14400]", (14400 - 100.3, 140.7)),
    ("14400 x.37", "/MediaBox [0 0 14400 14400]", (14400 - 100.37, 140.73)),
]:
    b = standard(extra)
    d = fitz.open(stream=b, filetype="pdf")
    t = cat(drawing_refusal(d[0], 0, TEXT_DRAWING))
    d.close()
    drift, origin = frac_probe(b, point)
    print(f"{cid:24} text={t:6} point={point} origin={origin} drift={None if drift is None else round(drift, 5)}")
