"""Probe 3: a scan-like page -- full-page image plus OCR-style text, both drawn
under a content-stream `cm` rotation, with /Rotate turning the page upright."""
import sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")

import pymupdf as fitz
from engine.export import export
from engine.geometry import to_display_matrix
from engine.operations import redact_region
from engine.parser import parse

GREY = (200, 200, 200)
FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP

# content-space -> page-space matrices, each keeping a 612x792 page's content inside it
CMS = {
    "cm90ccw": "0 1 -1 0 612 0",      # (x,y) -> (612-y, x): content is 792 wide x 612 tall
    "cm180": "-1 0 0 -1 612 792",     # content 612 x 792, upside down
    "cm270": "0 -1 1 0 0 792",        # (x,y) -> (y, 792-x)
    "none": "1 0 0 1 0 0",
}
CROPS = {"none": None, "contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def scan_page(cm_name, rotate, cropbox):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_font(fontname="helv")
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16), False)
    pix.set_rect(pix.irect, GREY)
    page.insert_image(fitz.Rect(0, 0, 10, 10), stream=pix.tobytes("png"))
    name = page.get_images(full=True)[0][7]
    w, h = (792, 612) if cm_name in ("cm90ccw", "cm270") else (612, 792)
    stream = (
        f"q {CMS[cm_name]} cm "
        f"q {w} 0 0 {h} 0 0 cm /{name} Do Q "
        f"BT /helv 12 Tf 1 0 0 1 100 {h - 200} Tm (LOW-MARKER) Tj ET "
        f"BT /helv 12 Tf 1 0 0 1 100 {h - 300} Tm (KEEP-ME) Tj ET "
        f"Q"
    )
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, stream.encode())
    page.set_contents(xref)
    if cropbox:
        doc.xref_set_key(page.xref, "CropBox", cropbox)
    page = doc.reload_page(page)
    page.set_rotation(rotate)
    data = doc.tobytes()
    doc.close()
    return data


def spans(page):
    t = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=FLAGS)
    return [(s["text"], fitz.Rect(s["bbox"])) for b in t["blocks"] for l in b.get("lines", []) for s in l["spans"]]


def pixel_at(page, point_unrotated):
    pm = page.get_pixmap()
    d = fitz.Point(point_unrotated) * to_display_matrix(page)
    x = max(0, min(pm.width - 1, int(d.x - pm.x)))
    y = max(0, min(pm.height - 1, int(d.y - pm.y)))
    return pm.pixel(x, y)[:3]


fails = 0
for cm_name in CMS:
    for rotate in (0, 90, 180, 270):
        for crop_name, crop in CROPS.items():
            doc, handle = parse(scan_page(cm_name, rotate, crop))
            tb = next(b for b in doc.pages[0].text_blocks if "LOW-MARKER" in b.text)
            keep = next(b for b in doc.pages[0].text_blocks if "KEEP-ME" in b.text)
            target = fitz.Rect(tb.bbox)
            redact_region(handle, 0, tb.bbox)
            out = fitz.open(stream=export(handle), filetype="pdf")
            page = out[0]
            sp = spans(page)
            problems = []
            if any("LOW-MARKER" in t for t, _ in sp):
                problems.append("marker text remains")
            if not any("KEEP-ME" in t for t, _ in sp):
                problems.append("KEEP-ME was removed")
            fills = [fitz.Rect(d["rect"]) for d in page.get_drawings() if d.get("fill") == (0.0, 0.0, 0.0)]
            if len(fills) != 1:
                problems.append(f"{len(fills)} black fills {fills}")
            elif not all(abs(a - b) < 1 for a, b in zip(fills[0], target)):
                problems.append(f"fill {tuple(round(v,1) for v in fills[0])} vs target {tuple(round(v,1) for v in target)}")
            centre = ((target.x0 + target.x1) / 2, (target.y0 + target.y1) / 2)
            px = pixel_at(page, centre)
            if px != (0, 0, 0):
                problems.append(f"rendered pixel at target centre is {px}, not black")
            kc = ((keep.bbox[0] + keep.bbox[2]) / 2, keep.bbox[3] + 8)  # just under KEEP-ME, on the image
            kpx = pixel_at(page, kc)
            if kpx != GREY:
                problems.append(f"image pixel near KEEP-ME is {kpx}, not grey (image damaged elsewhere?)")
            # was the IMAGE itself blanked under the target? inspect the image pixels.
            img = page.get_images(full=True)
            blanked = None
            if img:
                ipm = fitz.Pixmap(out, img[0][0])
                changed = [(x, y) for y in range(ipm.height) for x in range(ipm.width) if ipm.pixel(x, y)[:3] != GREY]
                blanked = f"{len(changed)} of {ipm.width * ipm.height} image px changed"
            if page.rotation != rotate:
                problems.append(f"rotation {page.rotation} != {rotate}")
            status = "ok" if not problems else "FAIL " + "; ".join(problems)
            fails += bool(problems)
            print(f"{cm_name:8s} rot={rotate:3d} crop={crop_name:9s} target={tuple(round(v) for v in target)} {blanked}: {status}")
            out.close(); handle.close()
print(f"\nfailures: {fails}")
