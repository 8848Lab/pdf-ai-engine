"""PDF bytes -> Document: read-only introspection.

Returns both the read-oriented Document projection (for callers to find
redaction-target coordinates) and the live PyMuPDF handle the same bytes
were opened into, since operations.py/export.py mutate and read from that
handle directly rather than a second write path. See the design spec's
"Data model" section for why.
"""
import pymupdf as fitz

from engine.document import Document, Image, Page, TextBlock


def _document_placement_counts(handle: fitz.Document) -> dict[int, int]:
    """Total placements of each image xref across every page.

    A pre-pass, because an Image's document-wide count cannot be known while
    building that image's own page -- the same xref may be drawn again on a
    later page. Inline images (xref 0) are excluded: they have no image
    object, so there is nothing to count across pages.
    """
    counts: dict[int, int] = {}
    for page_index in range(handle.page_count):
        page = handle[page_index]
        for info in page.get_image_info(xrefs=True):
            xref = info["xref"]
            if xref == 0:
                continue
            counts[xref] = counts.get(xref, 0) + 1
    return counts


def parse(pdf_bytes: bytes) -> tuple[Document, fitz.Document]:
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    document_counts = _document_placement_counts(handle)
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
                        )
                    )

        images = []
        for info in pdf_page.get_image_info(xrefs=True):
            xref = info["xref"]
            # An inline image (xref 0) is embedded directly in the content
            # stream with no image object to query, so get_image_rects() has
            # nothing to count -- it is still listed so the operator can see
            # it, but it is a single unqueryable placement by definition.
            placement_count = 1 if xref == 0 else len(pdf_page.get_image_rects(xref))
            images.append(
                Image(
                    bbox=tuple(info["bbox"]),
                    xref=xref,
                    width=info["width"],
                    height=info["height"],
                    placement_count=placement_count,
                    document_placement_count=document_counts.get(xref, 1),
                )
            )

        pages.append(
            Page(
                index=page_index,
                width=pdf_page.rect.width,
                height=pdf_page.rect.height,
                text_blocks=text_blocks,
                images=images,
            )
        )
    return Document(pages=pages), handle
