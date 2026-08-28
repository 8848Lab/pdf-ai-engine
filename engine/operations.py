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
    erase step is invisible once new text is drawn over it).

    The apply_redactions modes below are pinned explicitly rather than
    relying on PyMuPDF's own defaults (which happen to currently match
    these values on 1.28.2): a future PyMuPDF release changing its
    defaults must not silently change what "redaction" means in this
    library. images=2 blanks out overlapping image pixels, graphics=1
    removes graphics contained in the rect, text=0 removes overlapping
    text. This matters equally for both callers.
    """
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) // 2
    return ordered[mid]


def _sample_background_color(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """Sample the page's background color in a thin margin just outside
    `rect`'s four edges, returning the median RGB as 0.0-1.0 floats
    suitable for PyMuPDF's `fill=` parameters.

    Samples just outside rect (not inside -- rect tightly bounds the old
    content, so inside pixels are as likely to be glyph strokes as
    background) at each edge's midpoint, offset outward by a few points
    so anti-aliasing at the exact boundary doesn't contaminate the read.
    Median (not mean) per channel is robust against one sample landing on
    a stray mark, e.g. a neighboring character's overshoot or a nearby
    rule line.

    Only correct for a solid-color background -- see the design spec's
    "Background sampling" section for why gradients/patterns/photos are
    explicitly out of scope: sampling a handful of points returns *a*
    color, not the real erased pixels.
    """
    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width

    offset = 3.0  # points, outside each edge -- clears typical anti-aliasing halos
    sample_points_pt = [
        ((rect.x0 + rect.x1) / 2, rect.y0 - offset),  # above the top edge
        ((rect.x0 + rect.x1) / 2, rect.y1 + offset),  # below the bottom edge
        (rect.x0 - offset, (rect.y0 + rect.y1) / 2),  # left of the left edge
        (rect.x1 + offset, (rect.y0 + rect.y1) / 2),  # right of the right edge
    ]

    reds, greens, blues = [], [], []
    for x_pt, y_pt in sample_points_pt:
        x_px = max(0, min(pixmap.width - 1, int(x_pt * zoom)))
        y_px = max(0, min(pixmap.height - 1, int(y_pt * zoom)))
        pixel = pixmap.pixel(x_px, y_px)  # confirm this returns (r, g, b[, a]) 0-255 ints on the installed version
        reds.append(pixel[0])
        greens.append(pixel[1])
        blues.append(pixel[2])

    return (_median(reds) / 255.0, _median(greens) / 255.0, _median(blues) / 255.0)


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
