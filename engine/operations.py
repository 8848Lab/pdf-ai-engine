"""Mutating operations against a live PyMuPDF document handle.

v0.1 supports exactly one operation: redact_region. It mutates the handle
in place rather than the read-oriented Document dataclasses -- see the
design spec's "Data model" and "Operations" sections for why.
"""
import pymupdf as fitz


def redact_region(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> None:
    """Black out and strip content from a rectangular region of one page.

    Note on redaction floor: PyMuPDF removes content by geometric
    intersection with `bbox`, and is generous vertically (a bbox inset
    several points from a text line's true bounds still removes the whole
    line) -- but there is a real floor. A bbox that is technically valid
    (passes the checks below) but too thin/short to meaningfully intersect
    the target glyphs may leave content behind despite still drawing a
    visible black bar over it. Callers should size bboxes to fully cover
    the target content's rendered bounds, not just its nominal coordinates.

    Raises:
        ValueError: if page_index is out of range, or bbox is degenerate
            (empty/zero-area after normalization) or does not intersect
            the target page at all. A bad bbox is a caller bug -- this
            function fails loudly rather than silently no-op'ing or
            producing a document that looks redacted but isn't.
    """
    if page_index < 0 or page_index >= handle.page_count:
        raise ValueError(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )

    page = handle[page_index]

    # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
    # swapping them into min/max order. It does NOT fix a zero-area or
    # off-page rect -- those are caught explicitly below.
    rect = fitz.Rect(bbox)
    rect.normalize()

    if rect.is_empty:
        raise ValueError(
            f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
            f"normalization: {tuple(rect)}) -- redact_region refuses to "
            f"silently no-op on invalid geometry"
        )
    if not rect.intersects(page.rect):
        raise ValueError(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
        )

    page.add_redact_annot(rect, fill=(0, 0, 0))
    # Pin these explicitly rather than relying on PyMuPDF's own defaults
    # (which happen to currently match these values on 1.28.2): a future
    # PyMuPDF release changing its defaults must not silently change what
    # "redaction" means in this library. images=2 blanks out overlapping
    # image pixels, graphics=1 removes graphics contained in the rect,
    # text=0 removes overlapping text.
    page.apply_redactions(images=2, graphics=1, text=0)
