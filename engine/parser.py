"""PDF bytes -> Document: read-only introspection.

Returns both the read-oriented Document projection (for callers to find
redaction-target coordinates) and the live PyMuPDF handle the same bytes
were opened into, since operations.py/export.py mutate and read from that
handle directly rather than a second write path. See the design spec's
"Data model" section for why.
"""
import pymupdf as fitz

from engine.document import Document, Image, Page, TextBlock


def parse(pdf_bytes: bytes) -> tuple[Document, fitz.Document]:
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
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

        images = [Image(bbox=tuple(info["bbox"])) for info in pdf_page.get_image_info()]

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
