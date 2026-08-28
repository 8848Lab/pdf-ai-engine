"""Mutating operations against a live PyMuPDF document handle.

Supports two operations: redact_region (v0.1, real content removal) and
replace_text (v0.2, layout-preserving text replacement). Both mutate the
handle in place rather than the read-oriented Document dataclasses -- see
the design specs' "Data model" and "Operations" sections for why.
"""
import pymupdf as fitz


def _validate_target(
    handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
) -> tuple[fitz.Page, fitz.Rect]:
    """Shared page_index/bbox validation for every mutating operation.

    Raises:
        ValueError: page_index out of range, or bbox degenerate (empty/
            zero-area after normalization) or does not intersect the
            target page at all. A bad target is a caller bug -- every
            operation using this helper fails loudly rather than
            silently no-op'ing or producing output that looks right but
            isn't.
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
            f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
            f"invalid geometry"
        )
    if not rect.intersects(page.rect):
        raise ValueError(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
        )

    return page, rect


def _erase_region(page: fitz.Page, rect: fitz.Rect, fill: tuple[float, float, float]) -> None:
    """Mark and apply a redaction over `rect`, filled with `fill`.

    Shared by redact_region (fill=black, the visible "this was removed"
    signal) and replace_text (fill=the sampled background color, so the
    erase step is invisible once new text is drawn over it). The pinned
    apply_redactions modes matter equally for both callers -- see
    redact_region's own docstring below for why they're hardcoded rather
    than left to PyMuPDF's own defaults.
    """
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)


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
        ValueError: see _validate_target.
    """
    page, rect = _validate_target(handle, page_index, bbox)
    _erase_region(page, rect, fill=(0, 0, 0))
