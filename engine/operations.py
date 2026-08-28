"""Mutating operations against a live PyMuPDF document handle.

Supports two operations: redact_region (v0.1, real content removal) and
replace_text (v0.2, layout-preserving text replacement). Both mutate the
handle in place rather than the read-oriented Document dataclasses -- see
the design specs' "Data model" and "Operations" sections for why.
"""
import pymupdf as fitz

from engine.document import TextBlock


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


# Shrink-retry loop tuning for replace_text. The step/floor pair is a
# pragmatic choice (see the design spec's "Operation" section): 10% per
# step is small enough that the accepted size is close to the largest that
# fits, and a 50% floor is the point past which the replacement is no
# longer plausibly "the same text at a slightly smaller size".
_SHRINK_STEP = 0.9
_SHRINK_FLOOR_RATIO = 0.5

# Horizontal slack added to the target's bbox before handing it to
# insert_textbox. TextBlock.bbox comes from span["bbox"], i.e. a
# *measurement* of already-rendered text read back at PDF coordinate
# precision, while insert_textbox re-derives the same text's width from
# full-precision font metrics. Measured across every span in every fixture
# in this repo, the bbox comes out short of the re-derived width by at most
# 9.1e-5pt -- pure round-tripping noise, but enough to push the last word
# onto a second line and make an identity replacement "not fit". 0.5pt is
# ~5000x that worst case while staying below the ~1pt stroke halo
# apply_redactions already paints, so it introduces no new visual risk.
_WIDTH_PRECISION_PAD_PT = 0.5


def _base14_font(font_name: str) -> fitz.Font:
    """Build a fitz.Font from a name already known to be Base-14.

    The dict's own canonical spelling is used rather than `font_name`
    verbatim. Verified on PyMuPDF 1.28.2: insert_textbox accepts any
    capitalisation of a built-in name, while fitz.Font() is strictly
    case-sensitive and rejects e.g. 'COURIER' or 'Times-roman' even though
    insert_textbox would have drawn them fine. Every value in
    Base14_fontdict is accepted by fitz.Font(), so this lookup normalises
    the difference away.
    """
    return fitz.Font(fitz.Base14_fontdict[font_name.lower()])


def _insertion_rect(
    page: fitz.Page, rect: fitz.Rect, font_name: str, size: float
) -> fitz.Rect:
    """Inflate `rect` to the box insert_textbox actually needs to place one
    line of `size`pt text in `font_name`, clamped to the page.

    Why this is needed (verified against PyMuPDF 1.28.2's own
    Page.insert_textbox source): insert_textbox accepts a line only when
    `lheight * lines - descender * fontsize <= rect.height`, where
    `lheight = fontsize * (ascender - descender)` (or `fontsize * 1.2` when
    `ascender - descender <= 1`, which is true of ZapfDingbats). A span's
    reported bbox height, meanwhile, is just `fontsize * (ascender -
    descender)` -- exactly one descender short of what insert_textbox
    demands. Feeding a span's own bbox straight back in therefore always
    fails at the original size and drops into the shrink loop, measured at
    ~19% shrink on this repo's fixtures. Inflating the bottom edge by the
    missing descender makes an identity replacement fit at its original
    size, which is the whole point of a layout-preserving replace.

    Only the right and bottom edges move: insert_textbox places line 1's
    baseline at `rect.y0 + fontsize * ascender` and starts it at `rect.x0`,
    so holding the top-left corner fixed keeps the redrawn text on exactly
    the original baseline and left margin.

    Growth is capped at the page's own edges, so a target hugging the
    bottom or right margin inflates only as far as the page allows (it then
    falls back to the shrink loop rather than erasing or drawing off-page).
    The cap never pulls an edge back inside `rect` itself: a partially
    off-page target stays exactly as valid here as it is for redact_region.
    """
    font = _base14_font(font_name)
    line_height_factor = font.ascender - font.descender
    if line_height_factor <= 1:
        line_height_factor = 1.2
    needed_height = size * (line_height_factor - font.descender)

    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, page.rect.x1))
    y1 = max(rect.y1, min(rect.y0 + needed_height, page.rect.y1))
    return fitz.Rect(rect.x0, rect.y0, x1, y1)


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


def replace_text(
    handle: fitz.Document,
    page_index: int,
    target: TextBlock,
    new_text: str,
) -> None:
    """Replace target's content with new_text, absorbing any length
    difference via PyMuPDF's word-wrap and this function's own font-shrink
    retry loop, all within target's own block. See the design spec's
    "Operation" section.

    The region actually erased and drawn into is target.bbox inflated by
    _insertion_rect (and clamped to the page) -- not target.bbox itself.
    Without that inflation even an identity replacement fails to fit at its
    original size and comes back visibly shrunk; see _insertion_rect for
    the exact PyMuPDF geometry rule this compensates for.

    Investigation findings on the installed PyMuPDF version (1.28.2; see
    task-4-report.md's Step 1 for the full script/output) that this
    implementation is adapted to:

    - insert_textbox() returns a float: the unused vertical space (>= 0)
      if buffer fit inside rect at the given fontsize, or a negative
      number (the vertical shortfall) if it did not. Confirmed empirically,
      matching the brief's primary hypothesis.
    - insert_textbox() does NOT auto-shrink fontsize itself -- fontsize=0
      does not trigger a working "auto" mode (it produced a garbled
      one-character-per-line layout with the span size unchanged at the
      original 12pt, not a real shrink-to-fit). The caller must implement
      its own shrink-retry loop, as this plan assumes.
    - insert_textbox() is all-or-nothing on failure, NOT partial-draw: a
      call that returns a negative deficit draws nothing at all -- verified
      against a single-line-height bbox (this task's real fixture target),
      a taller multi-line bbox that fits ~2 of ~10 needed lines, and a
      fresh blank page, all producing zero extracted characters from a
      failed attempt. This differs from the brief's assumed "partial draw
      on failure" behavior, so the retry loop below erases the region
      ONCE before the loop (not on every iteration): a failed attempt at a
      larger fontsize never leaves anything for the next, smaller attempt
      to stack on top of.

    Every check that can be made without touching the page runs before the
    erase step, so the only way this function can erase content and then
    fail is the one case the design spec deliberately wants to fail loudly
    (see the last Raises entry). In particular the font is validated as a
    PyMuPDF built-in Base-14 name up front: insert_textbox rejects anything
    else with a bare Exception ("need font file or buffer", verified on
    1.28.2), which -- were it reached after the erase -- would leave the
    document permanently damaged and raise a type this function's contract
    never promises.

    Raises:
        ValueError: page_index out of range or target.bbox degenerate/
            off-page (same checks redact_region uses, via
            _validate_target); new_text is empty; target.size is not
            positive; target.font is not one of PyMuPDF's built-in Base-14
            fonts (replace_text draws with built-in fonts only -- it has no
            way to load an embedded or system font file); or new_text does
            not fit within the target block's region even after shrinking
            to 50% of target.size -- replace_text does not cascade reflow
            into neighboring content, it fails loudly instead. This last
            case is the sole one that raises *after* erasing the target:
            the region is left cleanly erased, by design, rather than
            silently reflowing into its neighbors.
    """
    # ---- validation: everything checkable without mutating the page ----
    if not new_text:
        raise ValueError(
            "new_text must be non-empty -- use redact_region to delete without replacing"
        )

    page, rect = _validate_target(handle, page_index, target.bbox)

    base14_key = target.font.lower()
    if base14_key not in fitz.Base14_fontdict:
        raise ValueError(
            f"target.font {target.font!r} is not one of PyMuPDF's built-in "
            f"Base-14 fonts ({', '.join(sorted(fitz.Base14_fontdict))}). "
            f"replace_text draws replacement text with a built-in font only; "
            f"it cannot load the embedded or system font this block actually "
            f"uses. Nothing has been modified."
        )
    if target.size <= 0:
        raise ValueError(
            f"target.size must be positive, got {target.size} -- there is no "
            f"meaningful font size to draw or shrink from. Nothing has been modified."
        )

    # ---- geometry ----
    # Font metrics are safe to look up now that the name is known Base-14.
    insert_rect = _insertion_rect(page, rect, target.font, target.size)

    fill = _sample_background_color(page, insert_rect)

    # Erased once, up front, over the SAME rect insert_textbox will draw
    # into (not the tighter target.bbox) -- otherwise old content could
    # survive in the inflated margin. A failed insert_textbox attempt below
    # draws nothing at all (see the docstring's Step 1 findings), so there
    # is never partial content from a larger-fontsize attempt for a smaller
    # retry to stack on top of: one erase is enough to keep every attempt
    # starting from a clean, background-colored rect.
    _erase_region(page, insert_rect, fill=fill)

    fontsize = target.size
    floor = target.size * _SHRINK_FLOOR_RATIO
    smallest_attempted = fontsize
    remaining_space = -1.0
    while fontsize >= floor:
        smallest_attempted = fontsize
        try:
            remaining_space = page.insert_textbox(
                insert_rect,
                new_text,
                fontname=target.font,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            # Defense in depth. Every failure mode known on PyMuPDF 1.28.2
            # is already excluded by the validation above, and a "doesn't
            # fit" outcome is a negative return value rather than an
            # exception. Anything that still escapes here is unanticipated
            # -- re-raise it as the ValueError this function's contract
            # promises so callers never see a bare Exception.
            raise ValueError(
                f"failed to draw new_text into the target block's region "
                f"{tuple(insert_rect)} at {fontsize:.2f}pt: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if remaining_space >= 0:
            break
        fontsize *= _SHRINK_STEP

    if remaining_space < 0:
        # insert_rect is still cleanly erased -- confirmed above that a
        # failed insert_textbox call never draws partial content, so there
        # is nothing left to clean up before raising.
        raise ValueError(
            f"new_text ({len(new_text)} chars) does not fit within the target "
            f"block's region {tuple(insert_rect)} at any attempted size down to "
            f"{smallest_attempted:.2f}pt (the shrink floor is "
            f"{floor:.2f}pt, 50% of the original {target.size}pt) -- "
            f"replace_text does not cascade reflow into neighboring content; "
            f"shorten the text or use a different operation"
        )
