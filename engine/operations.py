"""Mutating operations against a live PyMuPDF document handle.

v0.1 supports exactly one operation: redact_region. It mutates the handle
in place rather than the read-oriented Document dataclasses -- see the
design spec's "Data model" and "Operations" sections for why.
"""
import fitz


def redact_region(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> None:
    page = handle[page_index]
    page.add_redact_annot(bbox, fill=(0, 0, 0))
    page.apply_redactions()
