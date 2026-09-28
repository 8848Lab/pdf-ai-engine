"""Shared helpers for the critique probes."""
import sys
sys.path.insert(0, "/home/user/pdf-ai-engine")
import pymupdf as fitz  # noqa: E402

DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FREESANS = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"


def spans(page, flags=None, clip=None):
    out = []
    kw = {}
    if flags is not None:
        kw["flags"] = flags
    if clip is not None:
        kw["clip"] = clip
    for b in page.get_text("dict", **kw)["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                out.append({
                    "text": s["text"], "size": round(s["size"], 3),
                    "bbox": tuple(round(v, 2) for v in s["bbox"]),
                    "origin": tuple(round(v, 2) for v in s["origin"]),
                    "dir": tuple(round(v, 3) for v in l["dir"]),
                    "font": s["font"], "asc": round(s["ascender"], 4),
                    "desc": round(s["descender"], 4), "color": s["color"],
                    "flags": s["flags"],
                })
    return out


def fmt(s):
    return (f"{s['text']!r:26} size={s['size']:<7} origin={s['origin']} bbox={s['bbox']} "
            f"dir={s['dir']} font={s['font']} asc={s['asc']} desc={s['desc']}")


def raw_page(doc, content, fonts=(("helv", None),), width=612, height=792):
    """New page whose content stream is `content`, with font resources named
    /F1, /F2, ... from `fonts`: (base14 name, None) or (alias, ttf path)."""
    page = doc.new_page(width=width, height=height)
    for i, (name, path) in enumerate(fonts, 1):
        if path:
            page.insert_font(fontname=f"F{i}", fontfile=path, set_simple=True)
        else:
            page.insert_font(fontname=name)  # Base-14 simple font, resource /<name>
            content = content.replace(f"/F{i} ", f"/{name} ")
    # insert_font on a fresh page creates an (empty) contents stream
    xrefs = page.get_contents()
    if xrefs:
        doc.update_stream(xrefs[0], content.encode("latin-1"))
    else:
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, content.encode("latin-1"))
        doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    page = doc[page.number]
    return page
