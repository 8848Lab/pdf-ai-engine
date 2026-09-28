"""PDF bytes -> Document: read-only introspection.

Returns both the read-oriented Document projection (for callers to find
redaction-target coordinates) and the live PyMuPDF handle the same bytes
were opened into, since operations.py/export.py mutate and read from that
handle directly rather than a second write path. See the design spec's
"Data model" section for why.
"""
import pymupdf as fitz

from engine.document import Document, Image, Page, TextBlock


def _image_identity(info: dict) -> bytes:
    """The key placements are counted under: the image's content digest.

    Not the xref. The same picture is routinely stored as a separate image
    object per page -- any merge of separately-built PDFs produces that --
    and counting by xref would report "appears once" on each page while the
    same picture is on all of them. PyMuPDF's own get_image_rects() already
    matches on the digest internally, so this keeps the per-page count
    consistent with it rather than diverging.

    Inline images (xref 0) need no special case: they have no image object,
    but PyMuPDF still hashes their decoded pixels, so they compare by content
    like everything else. Keying them on position instead would collide
    unrelated pictures drawn at the same spot on different pages -- common in
    composited or scanned documents -- and report them as the same image.

    The digest is over decoded pixels, so one picture stored once as PNG and
    once as JPEG counts as one. Two pictures differing by a single pixel
    count as two, which is why a count of 1 is not a guarantee of absence.
    """
    return info["digest"]


def _collect_image_info(handle: fitz.Document) -> list[list[dict]]:
    """Every page's image placements, fetched once.

    A pre-pass is unavoidable -- an image's document-wide counts cannot be
    known while building its own page, since the same picture may appear
    again later -- but re-fetching per page in the main loop would double
    the cost of the single most expensive call in parse(). parse() runs
    after every edit (the session rebuilds its registry from a fresh parse),
    so that cost lands on every operation, including on documents with no
    images at all.
    """
    return [handle[page_index].get_image_info(xrefs=True) for page_index in range(handle.page_count)]


def parse(pdf_bytes: bytes) -> tuple[Document, fitz.Document]:
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    image_info_by_page = _collect_image_info(handle)
    placements_in_document: dict[bytes, int] = {}
    pages_containing: dict[bytes, set[int]] = {}
    for page_index, infos in enumerate(image_info_by_page):
        for info in infos:
            key = _image_identity(info)
            placements_in_document[key] = placements_in_document.get(key, 0) + 1
            pages_containing.setdefault(key, set()).add(page_index)

    pages = []
    for page_index in range(handle.page_count):
        pdf_page = handle[page_index]

        text_blocks = []
        for block in pdf_page.get_text("dict")["blocks"]:
            if block["type"] != 0:  # 0 = text block, 1 = image block
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text_blocks.append(
                        TextBlock(
                            text=span["text"],
                            bbox=tuple(span["bbox"]),
                            font=span["font"],
                            size=span["size"],
                            origin=tuple(span["origin"]),
                            direction=tuple(line["dir"]),
                            color=fitz.sRGB_to_pdf(span["color"]),
                        )
                    )

        page_infos = image_info_by_page[page_index]
        placements_on_page: dict[bytes, int] = {}
        for info in page_infos:
            key = _image_identity(info)
            placements_on_page[key] = placements_on_page.get(key, 0) + 1

        images = []
        for info in page_infos:
            key = _image_identity(info)
            images.append(
                Image(
                    bbox=tuple(info["bbox"]),
                    xref=info["xref"],
                    width=info["width"],
                    height=info["height"],
                    placement_count=placements_on_page[key],
                    document_placement_count=placements_in_document[key],
                    document_page_count=len(pages_containing[key]),
                )
            )

        pages.append(
            Page(
                index=page_index,
                # DISPLAY dimensions: page.rect, which swaps width and height at
                # 90/270. Block bboxes are in UNROTATED space -- use
                # engine.geometry.unrotated_bounds for any coordinate math.
                width=pdf_page.rect.width,
                height=pdf_page.rect.height,
                text_blocks=text_blocks,
                images=images,
            )
        )
    return Document(pages=pages), handle
