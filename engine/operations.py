"""Mutating operations against a live PyMuPDF document handle.

Supports seven operations: redact_region (real content removal),
replace_text (layout-preserving text replacement), delete_block,
move_block, insert_block, replace_image (swap one image placement's
bitmap), and sanitize_document (metadata/hidden-content scrub), alongside
the read-only get_metadata_summary. All of them mutate the handle in place
rather than the read-oriented Document dataclasses -- see the design specs'
"Data model" and "Operations" sections for why.
"""
import re

import pymupdf as fitz

from engine.document import Image, TextBlock
from engine.errors import RefusedBeforeMutation
from engine.geometry import (
    OTHER_DRAWING,
    TEXT_DRAWING,
    at_rotation_zero,
    drawing_refusal,
    to_display_matrix,
    unrotated_bounds,
)


_SUBSET_TAG_RE = re.compile(r"^[A-Z]{6}\+")


def _normalize_font_name(name: str) -> str:
    """Normalize a font name for matching a TextBlock.font string (from
    page.get_text()'s span dict) against a page.get_fonts() basename for
    the SAME underlying font resource.

    The two APIs do not always agree on formatting for identical fonts --
    verified empirically: a font embedded via page.insert_font() and later
    read back reports 'NimbusSans-Regular' via get_text()'s span but
    'Nimbus Sans Regular' (with spaces) via get_fonts()'s basename. Real
    third-party-authored PDFs add their own wrinkle: a subset tag (exactly
    6 uppercase letters + '+', e.g. 'PIMSLO+HelveticaNeueLTStd-Roman' --
    confirmed against a real IRS tax form) that only appears in
    get_fonts()'s basename, never in the span's own font name.

    Stripping the subset tag, removing whitespace/hyphens/underscores, and
    lowercasing collapses both wrinkles: 'HelveticaNeueLTStd-Roman' and
    'PIMSLO+HelveticaNeueLTStd-Roman' both normalize to
    'helveticaneueltstdroman'; 'NimbusSans-Regular' and 'Nimbus Sans
    Regular' both normalize to 'nimbussansregular'.
    """
    name = _SUBSET_TAG_RE.sub("", name)
    return re.sub(r"[\s\-_]", "", name).lower()


def _extract_target_font(
    handle: fitz.Document, page: fitz.Page, target_font: str
) -> tuple[int, bytes] | None:
    """Best-effort: find target_font's real embedded font resource on
    `page` (matched via _normalize_font_name against page.get_fonts()'s
    basenames) and return its (xref, raw bytes), or None if no matching
    resource exists, no MATCHING resource is actually embedded (a Base-14
    font referenced by name only reports an empty buffer here -- confirmed:
    page.get_fonts() shows ext='n/a' for it and extract_font() returns
    b''), or anything else about extraction fails.

    A normalized-name match with an empty/unusable buffer does NOT stop
    the search -- it keeps scanning for a LATER resource with the same
    normalized name instead. This matters for a realistic scenario: a PDF
    can contain both a name-only 'Helvetica' reference (empty buffer,
    never embedded) and a genuinely embedded 'ABCDEF+Helvetica' subset
    font, both normalizing to the same name. page.get_fonts() lists
    resources in the order PyMuPDF encounters them, which is not
    guaranteed to put the usable one first -- returning None on the first
    (unusable) match would abandon Tier 1 even though a usable match
    exists later in the same list.

    Never raises: this is Tier 1 of a fallback cascade (see _select_font),
    and any failure here must fall through to Tier 2, not abort the whole
    operation.
    """
    try:
        normalized_target = _normalize_font_name(target_font)
        for font_info in page.get_fonts(full=True):
            if _normalize_font_name(font_info[3]) == normalized_target:
                xref = font_info[0]
                result = handle.extract_font(xref)
                buffer = result[3] if len(result) > 3 else None
                if buffer:
                    return xref, buffer
                # Empty/unusable buffer -- keep scanning, a later resource
                # with the same normalized name may still be usable.
                continue
        return None
    except Exception:
        return None


def _missing_glyphs(font: fitz.Font, text: str) -> list[str]:
    """Characters in `text` (excluding whitespace) that `font` has no
    glyph for, in first-occurrence order with duplicates removed.

    Whitespace is excluded deliberately: real PDF fonts routinely omit an
    actual drawable glyph for it -- not just the space character, but also
    newline, tab, and carriage return -- because these are all handled by
    positioning and line-breaking rather than a drawn glyph, even though
    insert_textbox renders them correctly regardless (a newline starts a
    new line via its own word-wrap logic; it does not need `font` to
    contain a glyph for U+000A). Verified empirically against every font
    tested in this project, including PyMuPDF's own Base-14 set:
    has_glyph() returns 0 for space, '\\n', '\\t', and '\\r' alike.
    Including any of them here would report a false "missing" character
    for essentially every real font. `str.isspace()` covers all of these
    (plus other Unicode whitespace) in one check.
    """
    seen: list[str] = []
    for ch in text:
        if ch.isspace() or ch in seen:
            continue
        if not font.has_glyph(ord(ch)):
            seen.append(ch)
    return seen


def _base14_style_match(font_name: str) -> str:
    """Pick a reasonable generic Base-14 substitute for font_name, using a
    simple bold/italic heuristic on the name itself so a styled font at
    least keeps its styling rather than always falling back to plain
    Helvetica.

    Only used when font_name is NOT already a Base-14 name (callers check
    that first) and Tier 1's real embedded font could not be resolved or
    could not cover the needed text -- see _select_font.
    """
    lowered = font_name.lower()
    is_bold = "bold" in lowered
    is_italic = "italic" in lowered or "oblique" in lowered
    if is_bold and is_italic:
        return "helvetica-boldoblique"
    if is_bold:
        return "helvetica-bold"
    if is_italic:
        return "helvetica-oblique"
    return "helvetica"


def _bundled_fallback_font() -> fitz.Font:
    """PyMuPDF's own bundled broad-coverage font (reserved name 'cjk') --
    the final fallback tier. Despite the name, verified in this project's
    own testing to cover Latin, Cyrillic, Greek, CJK, and common
    currency/punctuation symbols with zero gaps -- not CJK-only.
    """
    return fitz.Font("cjk")


def _validate_target(
    handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
) -> tuple[fitz.Page, fitz.Rect]:
    """Shared page_index/bbox validation for every mutating operation.

    Raises:
        RefusedBeforeMutation (a ValueError): page_index out of range, or
            bbox degenerate (empty/zero-area after normalization) or does
            not intersect the target page at all. A bad target is a
            caller bug -- every operation using this helper fails loudly
            rather than silently no-op'ing or producing output that looks
            right but isn't. Also raised, wrapping the original exception,
            if PyMuPDF itself cannot load the page (ruling C17) -- for
            example a page tree that loops raises before the geometry
            gate ever runs.
    """
    # The range check stays outside the try, so an out-of-range index keeps
    # its own message rather than being reported as "cannot be loaded".
    if page_index < 0 or page_index >= handle.page_count:
        raise RefusedBeforeMutation(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )

    try:
        page = handle[page_index]
        page.rect  # noqa: B018 -- PyMuPDF's Page.bound() can raise IndexError on an infinite page (C17)
    except Exception as exc:  # noqa: BLE001 -- PyMuPDF's own errors on an unloadable page (ruling C17)
        raise RefusedBeforeMutation(
            f"Page {page_index} cannot be loaded by PyMuPDF ({type(exc).__name__}: {exc}), "
            f"so this operation was not applied and nothing was changed."
        ) from exc

    # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
    # swapping them into min/max order. It does NOT fix a zero-area or
    # off-page rect -- those are caught explicitly below.
    rect = fitz.Rect(bbox)
    rect.normalize()

    if rect.is_empty:
        raise RefusedBeforeMutation(
            f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
            f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
            f"invalid geometry"
        )
    bounds = unrotated_bounds(page)
    if not rect.intersects(bounds):
        raise RefusedBeforeMutation(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page bounds are {tuple(bounds)}) -- it is entirely off-page"
        )

    return page, rect


def _refuse_unsupported_drawing(page: fitz.Page, page_index: int, kind: str) -> None:
    """Raise before any mutation if this page cannot be drawn on correctly.

    See engine.geometry.drawing_refusal for the rules and the evidence. Every
    targeted operation calls this right after validating its target.

    Raises:
        RefusedBeforeMutation (a ValueError): the gate refuses the
            operation, or (ruling C17) PyMuPDF itself raised while
            computing the gate. This is defence in depth -- the real
            exception sources measured for the final review (a bare
            infinite-MediaBox page's ``page.rect``, and a looping page
            tree's own load) are both caught earlier, by
            ``_validate_target``'s load wrap below, before this function
            is ever called; no real file has been found that reaches an
            exception here. Either way this is raised before any mutation.
    """
    try:
        reason = drawing_refusal(page, page_index, kind)
    except Exception as exc:  # noqa: BLE001 -- PyMuPDF's own errors on an unrenderable page (ruling C17)
        raise RefusedBeforeMutation(
            f"Page {page_index} cannot be laid out by PyMuPDF ({type(exc).__name__}: {exc}), "
            f"so this operation was not applied and nothing was changed."
        ) from exc
    if reason is not None:
        raise RefusedBeforeMutation(reason)


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

    Both calls run at rotation 0 (spec R11): see at_rotation_zero.
    """
    # Both calls at rotation 0 (spec R11): on a rotated page whose CropBox or
    # MediaBox origin is not (0, 0), PyMuPDF removes the right text but paints
    # the fill elsewhere -- ~88pt away on the test pages, possibly over
    # content that was NOT removed.
    # The rect stays in unrotated coordinates; only the page's orientation
    # changes, and at_rotation_zero restores it even if a call raises.
    with at_rotation_zero(page):
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
    # Identity render: one pixel per point, in DISPLAY space. Sample points
    # are in UNROTATED space, so each is mapped through the display matrix
    # and the pixmap's own origin is subtracted. Scale is never inferred from
    # raster size -- a 100.1pt page renders 101 pixels wide (spec R3).
    pixmap = page.get_pixmap()
    to_display = to_display_matrix(page)

    offset = 3.0  # points, outside each edge -- clears typical anti-aliasing halos
    sample_points_pt = [
        ((rect.x0 + rect.x1) / 2, rect.y0 - offset),  # above the top edge
        ((rect.x0 + rect.x1) / 2, rect.y1 + offset),  # below the bottom edge
        (rect.x0 - offset, (rect.y0 + rect.y1) / 2),  # left of the left edge
        (rect.x1 + offset, (rect.y0 + rect.y1) / 2),  # right of the right edge
    ]

    on_canvas_pixels, off_canvas_pixels = [], []
    for x_pt, y_pt in sample_points_pt:
        display = fitz.Point(x_pt, y_pt) * to_display
        raw_x = int(display.x - pixmap.x)
        raw_y = int(display.y - pixmap.y)
        on_canvas = 0 <= raw_x < pixmap.width and 0 <= raw_y < pixmap.height
        x_px = max(0, min(pixmap.width - 1, raw_x))
        y_px = max(0, min(pixmap.height - 1, raw_y))
        # Verified on PyMuPDF 1.28.2: page.get_pixmap() defaults to DeviceRGB
        # with alpha=0, and Pixmap.pixel() returns a plain tuple of 0-255 ints
        # -- (r, g, b) here. Indexing the first three entries is therefore
        # correct whether or not a future default adds a trailing alpha.
        pixel = pixmap.pixel(x_px, y_px)
        (on_canvas_pixels if on_canvas else off_canvas_pixels).append(pixel)

    # C21 (plan W7/R14): a sample that falls off the canvas gets clamped onto
    # the page edge above, which can land on printed ink at that edge (a
    # frame, a corner logo, or the target's own overhanging glyph) instead of
    # the true background. When at least one sample is on-canvas and at
    # least one is off, the off-canvas (clamped) samples are unreliable and
    # are dropped -- the median is taken over the on-canvas samples only.
    # When every sample is off-canvas there is nothing else to go on, so the
    # clamped set is used exactly as before.
    if on_canvas_pixels and off_canvas_pixels:
        pixels = on_canvas_pixels
    else:
        pixels = on_canvas_pixels + off_canvas_pixels

    reds = [p[0] for p in pixels]
    greens = [p[1] for p in pixels]
    blues = [p[2] for p in pixels]

    return (_median(reds) / 255.0, _median(greens) / 255.0, _median(blues) / 255.0)


def _clean_erase(page: fitz.Page, rect: fitz.Rect) -> None:
    """Erase rect and fill it with the page's own sampled background color,
    leaving no visible trace. Shared by replace_text's erase step,
    delete_block, and move_block's erase-the-source step. See
    _sample_background_color for the sampling method and its solid-color-
    background limitation.
    """
    fill = _sample_background_color(page, rect)
    _erase_region(page, rect, fill=fill)


def _overlaps_band(y0: float, y1: float, other: fitz.Rect) -> bool:
    return other.y1 > y0 and other.y0 < y1


def _drawing_edges(item: dict) -> list[fitz.Rect]:
    """Decompose one page.get_drawings() item into its constituent segments,
    as rects (R3: "rectangles are decomposed into their four edges first, so
    a box's top and bottom borders ... are not obstacles, while its right
    border is").

    A rectangle ("re") becomes its four edges, each a degenerate (zero-width
    or zero-height) rect. A line ("l") becomes its own bounding rect. A
    curve ("c") is taken as the bounding box of its control points -- coarse,
    but a curve is not a rule line in practice. A quad ("qu") is taken as
    its bounding rect.
    """
    segments: list[fitz.Rect] = []
    for it in item.get("items", []):
        kind = it[0]
        if kind == "re":
            r = it[1]
            segments += [
                fitz.Rect(r.x0, r.y0, r.x1, r.y0),
                fitz.Rect(r.x0, r.y1, r.x1, r.y1),
                fitz.Rect(r.x0, r.y0, r.x0, r.y1),
                fitz.Rect(r.x1, r.y0, r.x1, r.y1),
            ]
        elif kind == "l":
            p, q = it[1], it[2]
            segments.append(fitz.Rect(min(p.x, q.x), min(p.y, q.y), max(p.x, q.x), max(p.y, q.y)))
        elif kind == "c":
            pts = it[1:5]
            segments.append(
                fitz.Rect(
                    min(pt.x for pt in pts), min(pt.y for pt in pts),
                    max(pt.x for pt in pts), max(pt.y for pt in pts),
                )
            )
        elif kind == "qu":
            segments.append(it[1].rect)
    return segments


# A horizontal rule segment shorter than this (in points) tall is never an
# obstacle on its own (R6) -- it is either an underline directly under the
# target (see below) or ignored entirely (e.g. a dotted/dashed leader that
# does not overlap the target's own x-range, or a rule that passes under a
# neighbouring word, not this one).
_THIN_SEGMENT_MAX_HEIGHT_PT = 1.0

# The underline band a thin horizontal segment must fall in, and overlap the
# target's own x-range in, to bound the limit at its own x1 (R6).
_UNDERLINE_SLACK_PT = 2.0


def _right_limit(
    page: fitz.Page,
    target_bbox: tuple[float, float, float, float],
    baseline: float,
    size: float,
) -> float:
    """The rightmost x a replacement for `target_bbox` may widen into,
    before any mutation (plan Task 3, spec W2, rulings R3-R8).

    Read-only: calls no mutator. Collects obstacles from page.get_text
    ("dict") spans, page.get_image_info(), page.get_drawings() (rects split
    into their edges), page.widgets() and page.annots(), all in the same
    unrotated page space target_bbox is given in.

    Returns the minimum of:
      - the nearest obstacle to the right within the target's vertical band
        [bbox.y0, bbox.y1], less a gap of max(1pt, 0.25 * size) -- R3/R4;
      - target.x1 outright, if an image obstacle is in the band (R5), or if
        the target is judged right-aligned (R8);
      - an underline's own x1, if a thin horizontal rule bounds the target
        (R6);
      - the paragraph column edge, only when at least 2 aligned neighbours'
        x1 values agree within 10% of the column width (R7);
      - the page's right margin, floored at 18pt (W2.3).

    Never less than target_bbox's own x1.
    """
    tx0, ty0, tx1, ty1 = target_bbox
    gap = max(1.0, 0.25 * size)
    line_height = ty1 - ty0

    def is_target(r: fitz.Rect) -> bool:
        return max(abs(a - b) for a, b in zip(tuple(r), target_bbox)) < 0.05

    candidates: list[float] = []

    # ---- text spans (R3), and the R7 column-edge neighbours ----
    other_spans: list[fitz.Rect] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                r = fitz.Rect(span["bbox"])
                if is_target(r):
                    continue
                other_spans.append(r)
                # A span whose left edge aligns with the target's own
                # (within 2pt) is a same-column neighbour (a paragraph
                # sibling above or below, or a stacked form's own value in
                # another row) -- not a rightward obstacle in the R3 sense,
                # even though normal single-line leading routinely makes its
                # bbox vertically overlap the target's own band. Same-column
                # neighbours are governed separately, by R7 (the column
                # edge) and R8 (right-alignment) below; without this
                # exclusion a real paragraph's own line spacing would make
                # R3 fire against its own siblings and defeat R7 for
                # ordinary single-spaced body text.
                column_aligned = abs(r.x0 - tx0) <= 2.0
                if not column_aligned and r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
                    candidates.append(max(r.x0, tx1) - gap)

    # ---- R8: a right-aligned neighbour marks the target as right-aligned ----
    for r in other_spans:
        if (
            abs(r.y0 - ty0) <= 2 * line_height
            and abs(r.x1 - tx1) <= 1.0
            and abs(r.x0 - tx0) > 2.0
        ):
            candidates.append(tx1)
            break

    # ---- R7: the paragraph column edge ----
    aligned = [
        r for r in other_spans
        if abs(r.x0 - tx0) <= 2.0 and abs(r.y0 - ty0) <= 2 * line_height
    ]
    if len(aligned) >= 2:
        column_width = max(r.x1 for r in aligned) - tx0
        x1_values = [r.x1 for r in aligned]
        if column_width > 0 and (max(x1_values) - min(x1_values)) <= 0.1 * column_width:
            candidates.append(max(max(x1_values), tx1))

    # ---- images (R5): any image in the band forbids widening outright ----
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
            candidates.append(tx1)
            break

    # ---- drawings (R3/R6): rectangles split into edges first ----
    underline_top = baseline
    underline_bottom = ty1 + _UNDERLINE_SLACK_PT
    for item in page.get_drawings():
        for seg in _drawing_edges(item):
            thin = (seg.y1 - seg.y0) < _THIN_SEGMENT_MAX_HEIGHT_PT
            if thin:
                overlaps_target_x = seg.x1 > tx0 and seg.x0 < tx1
                in_underline_band = seg.y1 > underline_top and seg.y0 < underline_bottom
                if overlaps_target_x and in_underline_band:
                    candidates.append(seg.x1)
                # A thin segment that is not an underline of the target is
                # not an obstacle at all (R6) -- ignored either way.
                continue
            if seg.x1 > tx1 and _overlaps_band(ty0, ty1, seg):
                candidates.append(max(seg.x0, tx1) - gap)

    # ---- widgets and annotations (R4) ----
    for widget in page.widgets():
        r = fitz.Rect(widget.rect)
        if r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
            candidates.append(max(r.x0, tx1) - gap)
    for annot in page.annots():
        r = fitz.Rect(annot.rect)
        if r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
            candidates.append(max(r.x0, tx1) - gap)

    # ---- the page's right margin, floored at 18pt (W2.3) ----
    bounds = unrotated_bounds(page)
    all_x0 = [r.x0 for r in other_spans] + [tx0]
    min_x0 = min(all_x0)
    left_margin = max(18.0, min_x0 - bounds.x0)
    candidates.append(bounds.x1 - left_margin)

    R = min(candidates)
    if R < tx1:
        R = tx1
    return R


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
# onto a second line and make an identity replacement "not fit".
#
# 0.05pt is ~550x that measured worst case, so it comfortably absorbs the
# precision gap, and it is deliberately small: this pad widens the *erase*
# region too, and a span on the same line can begin immediately where the
# target's bbox ends (a bold "WARNING:" label directly followed by body
# text, with a zero-point gap between the two spans). At 0.5pt the pad
# reached far enough into such a neighbour that apply_redactions(text=0)
# deleted its whole leading character; at 0.05pt it does not. See
# test_replace_text_leaves_an_adjacent_span_on_the_same_line_intact.
_WIDTH_PRECISION_PAD_PT = 0.05


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
    page: fitz.Page, rect: fitz.Rect, font: fitz.Font, size: float
) -> fitz.Rect:
    """Inflate `rect` to the box insert_textbox actually needs to place one
    line of `size`pt text in `font`, clamped to the page.

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
    falls back to the shrink loop rather than drawing off-page). The cap
    never pulls an edge back inside `rect` itself: a partially off-page
    target stays exactly as valid here as it is for redact_region.

    This is the DRAWING box only. The vertical inflation compensates for
    insert_textbox's internal height check -- there is never any real
    content in the extra bottom margin, since the target's own bbox already
    bounds the rendered ink -- so replace_text deliberately does NOT erase
    this rect's full height. Erasing it would reach into the *following*
    line at ordinary leading and delete its text; see replace_text.
    """
    line_height_factor = font.ascender - font.descender
    if line_height_factor <= 1:
        line_height_factor = 1.2
    needed_height = size * (line_height_factor - font.descender)

    bounds = unrotated_bounds(page)
    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, bounds.x1))
    y1 = max(rect.y1, min(rect.y0 + needed_height, bounds.y1))
    return fitz.Rect(rect.x0, rect.y0, x1, y1)


def _draw_shrink_to_fit(
    page: fitz.Page,
    insert_rect: fitz.Rect,
    resolved_fontname: str,
    resolved_font: fitz.Font,
    text: str,
    starting_size: float,
    context_bbox: fitz.Rect,
) -> None:
    """Register resolved_font on page if it is not a Base-14 name, then draw
    text into insert_rect starting at starting_size, retrying at
    _SHRINK_STEP-smaller sizes down to _SHRINK_FLOOR_RATIO * starting_size
    until it fits. Shared by replace_text and move_block's destination draw
    step -- this is replace_text's original inline shrink-retry loop,
    extracted with no behavior change.

    Registration happens here, not earlier, for the same reason
    replace_text's original inline code registered it here:
    apply_redactions (already run by the caller before this is called)
    garbage-collects a page-registered font resource not yet referenced by
    any content stream, so registering any earlier would risk losing it.

    context_bbox is the caller's own pre-inflation target region, used only
    in the ValueError message on failure (naming the region the caller
    actually asked about, not this function's inflated drawing box) --
    replace_text passes target.bbox, move_block passes the destination bbox
    before _insertion_rect's inflation.

    Raises:
        ValueError: text does not fit insert_rect at any attempted size
            down to the shrink floor. Names context_bbox, the smallest size
            actually attempted, and the floor.
    """
    if resolved_fontname not in fitz.Base14_fontdict:
        page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)

    fontsize = starting_size
    floor = starting_size * _SHRINK_FLOOR_RATIO
    smallest_attempted = fontsize
    remaining_space = -1.0
    while fontsize >= floor:
        smallest_attempted = fontsize
        try:
            remaining_space = page.insert_textbox(
                insert_rect,
                text,
                fontname=resolved_fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            raise ValueError(
                f"failed to draw text into region {tuple(insert_rect)} at "
                f"{fontsize:.2f}pt: {type(exc).__name__}: {exc}"
            ) from exc
        if remaining_space >= 0:
            return
        fontsize *= _SHRINK_STEP

    raise ValueError(
        f"text ({len(text)} chars) does not fit within the target region "
        f"{tuple(context_bbox)} at any attempted size down to "
        f"{smallest_attempted:.2f}pt (the shrink floor is {floor:.2f}pt, "
        f"50% of the original {starting_size}pt)"
    )


_FALLBACK_FONT_ALIAS = "repl-fallback-broad"


def _select_font(
    handle: fitz.Document, page: fitz.Page, target: TextBlock, new_text: str
) -> tuple[str, fitz.Font]:
    """Resolve the best-available font to draw new_text into target's
    region with, trying three tiers in order and returning the first
    whose glyph set covers every character new_text needs (whitespace
    excluded -- see _missing_glyphs):

    1. target's own real font, extracted from the source document -- the
       closest visual match to the original document, and what makes this
       succeed on the vast majority of real-world text. See the design
       spec's reliability spike: both a real IRS Form 1040 and a real
       arXiv paper use exclusively embedded, non-Base-14 fonts (100% and
       99% of blocks respectively), and this tier resolves and draws both
       correctly.
    2. A Base-14 fallback: target.font itself if it already IS a Base-14
       name, otherwise a bold/italic-matched generic substitute (see
       _base14_style_match).
    3. PyMuPDF's bundled 'cjk' font -- not just for CJK despite the name;
       verified in this project's own testing to cover Latin, Cyrillic,
       Greek, CJK, and common symbols/currency/punctuation with zero gaps.
       The true last resort: reached only when neither tier above covers
       every character new_text needs.

    Returns (fontname, font) where `fontname` is ready to pass directly to
    page.insert_textbox(fontname=...) once actually registered on `page`,
    and `font` is the matching fitz.Font, for _insertion_rect's metrics
    lookup. This function does NOT register anything on `page` itself for
    Tier 1/Tier 3 (Tier 2 is a Base-14 name, needing no page resource at
    all) -- it only resolves and returns which font won and its bytes;
    replace_text's own post-erase re-embed step is what actually registers
    the resource, since apply_redactions would garbage-collect an
    unreferenced one registered here before the draw ever happens. See
    replace_text's docstring for why the registration is deferred there.

    Raises:
        ValueError: no tier's font covers every character new_text needs.
        Names the specific unrenderable character(s). Called before any
        page mutation, same as every other check in replace_text -- this
        can never fire after the target has been erased.
    """
    # Tier 1: the block's own real font.
    resolved = _extract_target_font(handle, page, target.font)
    if resolved is not None:
        xref, embedded_bytes = resolved
        try:
            embedded_font = fitz.Font(fontbuffer=embedded_bytes)
        except Exception:
            embedded_font = None
        if embedded_font is not None and not _missing_glyphs(embedded_font, new_text):
            alias = f"repl-embedded-{xref}"
            return alias, embedded_font

    # Tier 2: Base-14, either target.font itself or a style-matched generic.
    base14_key = target.font.lower()
    if base14_key not in fitz.Base14_fontdict:
        base14_key = _base14_style_match(target.font)
    base14_font = _base14_font(base14_key)
    if not _missing_glyphs(base14_font, new_text):
        return base14_key, base14_font

    # Tier 3: PyMuPDF's own bundled broad-coverage font, the last resort.
    fallback_font = _bundled_fallback_font()
    missing = _missing_glyphs(fallback_font, new_text)
    if not missing:
        return _FALLBACK_FONT_ALIAS, fallback_font

    # Plain `{c}` interpolation (not `{c!r}`) is deliberate: repr() escapes
    # any non-printable codepoint -- which most genuinely-missing characters
    # are (Private Use Area, unassigned code points, combining marks) -- so
    # a repr'd list would never actually contain the raw character, only its
    # escaped spelling. The codepoint annotation keeps the message readable
    # even when the raw character itself renders as invisible.
    missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
    raise ValueError(
        f"new_text contains character(s) that no available font can render: "
        f"{missing_display} -- tried the block's own font ({target.font!r}), "
        f"a Base-14 fallback, and PyMuPDF's bundled broad-coverage font. "
        f"Nothing has been modified."
    )


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
        ValueError: see _validate_target; or the page cannot be drawn on
            correctly (malformed /Rotate or /UserUnit); see
            engine.geometry.drawing_refusal.
    """
    page, rect = _validate_target(handle, page_index, bbox)
    _refuse_unsupported_drawing(page, page_index, OTHER_DRAWING)
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

    The region drawn into is target.bbox inflated by _insertion_rect (and
    clamped to the page) -- not target.bbox itself. Without that inflation
    even an identity replacement fails to fit at its original size and
    comes back visibly shrunk; see _insertion_rect for the exact PyMuPDF
    geometry rule this compensates for. The region *erased* is narrower:
    the inflated width, but target.bbox's own top and bottom, since the
    vertical inflation covers no content of the target's and erasing it
    would delete the following line's text at ordinary line spacing.

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
    (see the last Raises entry). In particular the font is resolved up
    front via _select_font's three-tier cascade (see that function's
    docstring): if no tier's font can render every character new_text
    needs, that failure surfaces as the ValueError this function's contract
    promises before anything is erased -- were it reached only after the
    erase, it would leave the document permanently damaged and (absent
    _select_font's own validation) risk insert_textbox raising a bare
    Exception ("need font file or buffer", verified on 1.28.2) that this
    function's contract never promises.

    Raises:
        ValueError: page_index out of range or target.bbox degenerate/
            off-page (same checks redact_region uses, via
            _validate_target); the page cannot be drawn on correctly
            (malformed /Rotate, /UserUnit, or a CropBox overhang); see
            engine.geometry.drawing_refusal; new_text is empty;
            target.size is not positive; no available font (the block's
            own real font, a Base-14 fallback, or PyMuPDF's bundled
            broad-coverage font) can render every character in new_text --
            see _select_font; or new_text does not fit within the target
            block's region even after shrinking to 50% of target.size --
            replace_text does not cascade reflow into neighboring content,
            it fails loudly instead. This last case is the sole one that
            raises *after* erasing the target: the region is left cleanly
            erased, by design, rather than silently reflowing into its
            neighbors.
    """
    # ---- validation: everything checkable without mutating the page ----
    if not new_text:
        raise ValueError(
            "new_text must be non-empty -- use redact_region to delete without replacing"
        )

    page, rect = _validate_target(handle, page_index, target.bbox)
    _refuse_unsupported_drawing(page, page_index, TEXT_DRAWING)

    if target.size <= 0:
        raise ValueError(
            f"target.size must be positive, got {target.size} -- there is no "
            f"meaningful font size to draw or shrink from. Nothing has been modified."
        )

    # ---- font resolution ----
    # Resolves the block's own real font (extracted from the source PDF
    # and re-embedded), falling back through Base-14 and finally PyMuPDF's
    # bundled broad-coverage font -- see _select_font's docstring. Raises
    # ValueError before any mutation if no tier covers new_text.
    resolved_fontname, resolved_font = _select_font(handle, page, target, new_text)

    # ---- geometry ----
    try:
        insert_rect = _insertion_rect(page, rect, resolved_font, target.size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad
        # Same defense in depth as the insert_textbox call below, and for
        # the same reason: this runs before any page mutation, so the only
        # thing an unanticipated font-metrics failure may do is raise the
        # ValueError this function's contract promises -- never a bare
        # Exception, and never after erasing anything.
        raise ValueError(
            f"failed to compute the insertion box for target.bbox "
            f"{tuple(target.bbox)} in {target.font!r} at {target.size}pt: "
            f"{type(exc).__name__}: {exc}. Nothing has been modified."
        ) from exc

    # The erase and the draw use DIFFERENT rects, on purpose:
    #
    #   draw  -> insert_rect            (inflated height, so insert_textbox
    #                                    accepts the line at its full size)
    #   erase -> erase_rect             (insert_rect's width, but the
    #                                    ORIGINAL bbox's top and bottom)
    #
    # insert_rect's extra bottom margin exists solely to satisfy
    # insert_textbox's internal `lheight * lines - descender * fontsize <=
    # rect.height` check; no content of the target's own ever occupies it,
    # because a TextBlock's bbox already bounds its rendered ink. Erasing
    # that margin therefore removes nothing of the target -- but it does
    # reach into the FOLLOWING line's territory at ordinary leading (a 12pt
    # Helvetica line at 1.4-1.5x spacing sits well inside it), and
    # apply_redactions(text=0) deletes any text it touches. Keeping the
    # erase at the original height is what stops replace_text from
    # destroying the next line while editing this one. The inflated *width*
    # is kept, since the precision pad is small (see
    # _WIDTH_PRECISION_PAD_PT) and the drawn text really can extend that
    # far right, so old ink there must go.
    erase_rect = fitz.Rect(rect.x0, rect.y0, insert_rect.x1, rect.y1)

    # Sample around what is actually erased, not around the drawing box:
    # _sample_background_color reads a thin margin just *outside* the rect
    # it is given, so passing the taller insert_rect would probe points
    # that are neither erased nor representative of the erased region's
    # own surroundings.
    _clean_erase(page, erase_rect)

    # _select_font deliberately does NOT register a Tier 1/Tier 3 font on
    # `page` itself -- see _select_font's docstring and _draw_shrink_to_fit's
    # own registration-ordering comment for why that registration is
    # deferred to here.
    _draw_shrink_to_fit(
        page, insert_rect, resolved_fontname, resolved_font, new_text,
        target.size, context_bbox=target.bbox,
    )


def delete_block(handle: fitz.Document, page_index: int, target: TextBlock) -> None:
    """Cleanly remove target's content from the page, filling the erased
    region with the page's own sampled background color -- no visible
    trace, unlike redact_region's deliberate black bar. See the design
    spec's "Architecture" section for why this is a distinct operation
    rather than a block-id-based wrapper around redact_region.

    Raises:
        ValueError: see _validate_target; or the page cannot be drawn on
            correctly (malformed /Rotate or /UserUnit); see
            engine.geometry.drawing_refusal.
    """
    page, rect = _validate_target(handle, page_index, target.bbox)
    _refuse_unsupported_drawing(page, page_index, OTHER_DRAWING)
    _clean_erase(page, rect)


def move_block(
    handle: fitz.Document,
    page_index: int,
    target: TextBlock,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    """Relocate target's own text, at its own font and size, to a new
    position -- same page by default, or a different page via
    destination_page_index. Exactly one of target_position (the new
    top-left corner) or offset (a (dx, dy) shift from the current
    position) must be given; width/height are preserved from target.bbox
    unchanged, only the position moves.

    Font resolution for the destination draw reuses _select_font exactly
    as replace_text does, called against the DESTINATION page: Tier 1
    (the block's own embedded font) succeeds whenever that font resource
    is genuinely present on the destination page -- always true for a
    same-page move, and true for a cross-page move only if the
    destination happens to already share the resource -- and gracefully
    falls through to Tier 2/3 otherwise, exactly like replace_text's own
    fallback. See the design spec's "Architecture" section.

    Raises:
        ValueError: exactly one of target_position/offset was not given;
            page_index or destination_page_index out of range;
            target.bbox or the computed destination bbox is degenerate or
            fully off-page (see _validate_target); the source page cannot
            be drawn on correctly (malformed /Rotate or /UserUnit), or the
            destination page cannot be drawn on correctly (malformed
            /Rotate, /UserUnit, or a CropBox overhang) -- see
            engine.geometry.drawing_refusal; the computed destination is
            only partially on-page (not fully contained in the destination
            page's unrotated bounds, see engine.geometry.unrotated_bounds);
            no available font can render target.text at the destination
            (see _select_font); or target.text does not fit the
            destination even after shrinking to 50% of target.size --
            move_block does not cascade reflow, same as replace_text. This
            last case is the sole one that raises AFTER erasing the
            source: the source is left cleanly erased, by design,
            mirroring replace_text's own contract for its equivalent
            failure case.
    """
    if (target_position is None) == (offset is None):
        raise ValueError(
            "exactly one of target_position or offset must be given "
            f"(target_position={target_position!r}, offset={offset!r}). "
            "Nothing has been modified."
        )

    source_page, source_rect = _validate_target(handle, page_index, target.bbox)
    _refuse_unsupported_drawing(source_page, page_index, OTHER_DRAWING)

    dest_index = destination_page_index if destination_page_index is not None else page_index
    if dest_index < 0 or dest_index >= handle.page_count:
        raise ValueError(
            f"destination_page_index {dest_index} is out of range for a document "
            f"with {handle.page_count} page(s); must be 0 <= destination_page_index "
            f"< {handle.page_count}. Nothing has been modified."
        )

    width = source_rect.x1 - source_rect.x0
    height = source_rect.y1 - source_rect.y0
    if target_position is not None:
        new_x0, new_y0 = target_position
    else:
        new_x0, new_y0 = source_rect.x0 + offset[0], source_rect.y0 + offset[1]
    destination_bbox = (new_x0, new_y0, new_x0 + width, new_y0 + height)
    destination_page, destination_rect = _validate_target(handle, dest_index, destination_bbox)
    _refuse_unsupported_drawing(destination_page, dest_index, TEXT_DRAWING)

    destination_bounds = unrotated_bounds(destination_page)
    if not destination_bounds.contains(destination_rect):
        raise ValueError(
            f"destination {tuple(destination_rect)} is not fully inside page "
            f"{dest_index} (page bounds {tuple(destination_bounds)}) -- move_block "
            f"does not place content off-page. Nothing has been modified."
        )

    # ---- font resolution, before any mutation ----
    resolved_fontname, resolved_font = _select_font(handle, destination_page, target, target.text)

    try:
        insert_rect = _insertion_rect(destination_page, destination_rect, resolved_font, target.size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
        raise ValueError(
            f"failed to compute the insertion box for destination "
            f"{tuple(destination_rect)} in {target.font!r} at {target.size}pt: "
            f"{type(exc).__name__}: {exc}. Nothing has been modified."
        ) from exc

    # ---- mutation: erase source, then draw at the destination ----
    _clean_erase(source_page, source_rect)
    _draw_shrink_to_fit(
        destination_page, insert_rect, resolved_fontname, resolved_font,
        target.text, target.size, context_bbox=destination_rect,
    )


def insert_block(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
    """Draw brand-new text into an empty region of a page -- for adding
    content that has no existing block to replace. Unlike replace_text/
    move_block, there is no shrink-retry: size is an explicit, deliberate
    choice, and a poor fit is a caller error to fix (a smaller size or a
    larger bbox), not something this function silently overrides.

    Font resolution: font defaults to "helvetica" when omitted. Only
    Tiers 2/3 of _select_font's cascade apply -- there is no source block
    to extract an embedded font from (Tier 1). A font value that is
    already a Base-14 name is used as-is; one that is not gets the same
    bold/italic-matched Base-14 substitute _base14_style_match already
    computes for replace_text's non-Base-14 target.font case (e.g. a
    caller-supplied "Arial-Bold" resolves to "helvetica-bold", not a
    failed lookup for an embedded resource of that name, since none
    exists to find). If even the style-matched Base-14 font can't render
    every character of text, the bundled broad-coverage font (Tier 3) is
    tried before raising.

    Raises:
        ValueError: text is empty; size is not positive; bbox is
            degenerate or fully off-page (see _validate_target); bbox is
            only partially on-page (not fully contained in the page's
            unrotated bounds); no available font (a Base-14 name/style match, or the
            bundled broad-coverage font) can render every character of
            text; or text does not fit bbox at size -- named explicitly,
            since no shrink is attempted. Nothing is ever drawn before this
            function's validation completes, so a raise always leaves the document's
            visible content unmodified -- though if font resolution reached the
            Tier-3 bundled fallback font, that font resource may remain registered
            on the page even if the later draw-fit check fails (a small, one-time,
            non-cumulative cost; PyMuPDF's own resource garbage collection cannot
            reclaim a resource still referenced from the page, even an unused one);
            or the page cannot be drawn on correctly (malformed /Rotate,
            /UserUnit, or -- for text -- a CropBox overhang); see
            engine.geometry.drawing_refusal.
    """
    if not text:
        raise ValueError("text must be non-empty -- nothing to insert")

    page, rect = _validate_target(handle, page_index, bbox)
    _refuse_unsupported_drawing(page, page_index, TEXT_DRAWING)

    bounds = unrotated_bounds(page)
    if not bounds.contains(rect):
        raise ValueError(
            f"bbox {tuple(bbox)} is not fully inside page {page_index} "
            f"(page bounds {tuple(bounds)}) -- insert_block does not place "
            f"content off-page. Nothing has been modified."
        )

    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")

    # ---- font resolution: Tier 2/3 only, no source block for Tier 1 ----
    font_key = (font or "helvetica").lower()
    if font_key not in fitz.Base14_fontdict:
        font_key = _base14_style_match(font_key)
    base14_font = _base14_font(font_key)
    if not _missing_glyphs(base14_font, text):
        resolved_fontname, resolved_font = font_key, base14_font
    else:
        fallback_font = _bundled_fallback_font()
        missing = _missing_glyphs(fallback_font, text)
        if missing:
            missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
            raise ValueError(
                f"text contains character(s) that no available font can render: "
                f"{missing_display} -- tried {font_key!r} and PyMuPDF's bundled "
                f"broad-coverage font. Nothing has been modified."
            )
        resolved_fontname, resolved_font = _FALLBACK_FONT_ALIAS, fallback_font

    try:
        insert_rect = _insertion_rect(page, rect, resolved_font, size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
        raise ValueError(
            f"failed to compute the insertion box for bbox {tuple(bbox)} in "
            f"{font_key!r} at {size}pt: {type(exc).__name__}: {exc}. "
            f"Nothing has been modified."
        ) from exc

    # ---- single attempt, no shrink-retry -- size was an explicit choice ----
    if resolved_fontname not in fitz.Base14_fontdict:
        page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
    remaining_space = page.insert_textbox(
        insert_rect, text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0),
    )
    if remaining_space < 0:
        raise ValueError(
            f"text ({len(text)} chars) does not fit within bbox {tuple(bbox)} "
            f"at {size}pt -- insert_block does not shrink to fit; choose a "
            f"smaller size or a larger bbox"
        )


# A generous ceiling that still refuses an accidental multi-hundred-MB
# upload before it is decoded. Not a security boundary -- this tool is
# single-operator and local -- just a guard against pathological input.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def replace_image(
    handle: fitz.Document,
    page_index: int,
    target: Image,
    new_image_bytes: bytes,
) -> None:
    """Swap the bitmap of ONE image placement for new_image_bytes, scaled to
    fit inside the placement's existing rectangle with its own aspect ratio
    preserved and centered. The uncovered letterbox margin shows the page's
    sampled background color.

    Deliberately does not use PyMuPDF's Page.replace_image, which replaces
    every placement of an xref document-wide: when the same image object is
    drawn in several spots, this changes only the one the caller targeted.
    "Replace this logo everywhere" is a separate, later operation. See the
    design spec's "Non-goals" section.

    Unlike move_block/insert_block, the rectangle here is not caller-chosen
    -- it is an existing placement's own bbox -- so _validate_target's
    intersects check is the right guard and no full-containment check is
    applied: a real document may legitimately place an image overhanging a
    page edge, and refusing to edit it would be wrong.

    When the targeted placement was its xref's only placement, the original
    image object is left in the file unreferenced; export()'s garbage
    collection reclaims it.

    Raises:
        ValueError: page_index out of range, or target.bbox degenerate or
            fully off-page (see _validate_target); the page cannot be
            drawn on correctly (malformed /Rotate or /UserUnit); see
            engine.geometry.drawing_refusal; target is an inline image
            (xref 0), which has no image object to reason about;
            new_image_bytes is empty, over _MAX_IMAGE_BYTES, or not a
            raster image PyMuPDF can decode; or the draw itself failed
            after the placement had been erased. Every check that can be
            made without touching the page -- including a full trial decode
            of new_image_bytes -- runs before the erase, so every case above
            leaves the document unmodified. The last does not: the
            placement is left cleanly erased with nothing drawn over it,
            mirroring replace_text's and move_block's own contract for
            their equivalent "erased, then could not draw" case. It is
            reported as a ValueError like every other failure here rather
            than the bare PyMuPDF exception, so a caller's error handling
            does not have to distinguish the two.
    """
    page, rect = _validate_target(handle, page_index, target.bbox)
    _refuse_unsupported_drawing(page, page_index, OTHER_DRAWING)

    if target.xref == 0:
        raise ValueError(
            "target is an inline image (xref 0): it is embedded directly in the "
            "page's content stream with no image object to replace. Nothing has "
            "been modified."
        )

    if not new_image_bytes:
        raise ValueError(
            "new_image_bytes is empty -- there is nothing to draw. Nothing has "
            "been modified."
        )

    if len(new_image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError(
            f"new_image_bytes is {len(new_image_bytes)} bytes, over the "
            f"{_MAX_IMAGE_BYTES}-byte cap. Nothing has been modified."
        )

    # Decode once up front purely as a validity gate, so a bad upload fails
    # BEFORE the erase rather than leaving a hole in the page. The decoded
    # Pixmap is intentionally discarded -- insert_image re-decodes from the
    # stream itself. PyMuPDF raises its own FzError types here (verified:
    # FzErrorFormat on garbage bytes), not ValueError, hence the broad catch.
    try:
        fitz.Pixmap(new_image_bytes)
    except Exception as exc:  # noqa: BLE001 -- normalizing any decode failure
        raise ValueError(
            f"new_image_bytes could not be decoded as a raster image: "
            f"{type(exc).__name__}: {exc}. Nothing has been modified."
        ) from exc

    _clean_erase(page, rect)
    try:
        # At rotation 0 (spec R4): on a rotated page with a CropBox,
        # insert_image lands 40-52pt from the rect it was given. The rect is
        # unchanged; only the page's orientation is, and it is restored.
        with at_rotation_zero(page):
            page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
        # insert_image can fail with exception types this function's
        # contract never promises -- verified on PyMuPDF 1.28.2: a
        # ZeroDivisionError out of its own calc_image_matrix, and an
        # FzErrorSyntax out of MuPDF's image loader. Neither is a
        # ValueError, so without this they bypassed webui/main.py's 400
        # handlers entirely and the operator got a bare non-JSON 500.
        # Unlike the decode gate above, this one genuinely does fire after
        # _clean_erase -- the erase cannot be un-done here, so the honest
        # thing is to say so rather than to swallow it.
        raise ValueError(
            f"failed to draw the replacement image into {tuple(rect)}: "
            f"{type(exc).__name__}: {exc}. The placement has been erased and "
            f"nothing was drawn over it."
        ) from exc


def get_metadata_summary(handle: fitz.Document) -> dict:
    """The document's current Info-dictionary fields (non-empty only) and
    whether a separate XMP metadata stream is present. Read-only -- makes
    no change to the document. See sanitize_document for removing what
    this reports.

    'format', 'encryption', and 'trapped' are excluded from `fields`: they
    are not user-set identifying data (format is always populated, e.g.
    "PDF 1.7"; encryption/trapped are structural/empty in practice) --
    verified on a freshly-created PyMuPDF document that every OTHER field
    is blank by default, so this exclusion list is exactly the three keys
    that would otherwise always appear regardless of what the document
    author actually set.
    """
    fields = {
        k: v for k, v in handle.metadata.items() if v and k not in ("format", "encryption", "trapped")
    }
    return {
        "fields": fields,
        "xmp_present": handle.xref_xml_metadata() != 0,
    }


def sanitize_document(handle: fitz.Document) -> dict:
    """Remove identifying metadata (Info dictionary + XMP stream), hidden/
    invisible text, embedded JavaScript, and stale page thumbnails from the
    whole document, via PyMuPDF's own Document.scrub(). See the design
    spec's "Architecture" section for why these five flags specifically,
    not scrub()'s full flag set (embedded_files/attached_files/
    remove_links/reset_fields/reset_responses are left off -- each has a
    legitimate reason a document owner might want to keep it).

    Returns a summary of what was concretely found and removed: which
    Info-dictionary fields were non-empty before the call, and whether an
    XMP stream existed. Hidden text/JavaScript/thumbnails are always
    covered by the fixed flags below but not individually counted here --
    a live preview of those would require essentially running scrub twice
    (once to detect, once to apply), which this operation deliberately
    does not attempt.
    """
    before = get_metadata_summary(handle)
    handle.scrub(
        attached_files=False,
        clean_pages=True,
        embedded_files=False,
        hidden_text=True,
        javascript=True,
        metadata=True,
        redactions=True,
        redact_images=0,
        remove_links=False,
        reset_fields=False,
        reset_responses=False,
        thumbnails=True,
        xml_metadata=True,
    )
    return {
        "metadata_fields_removed": sorted(before["fields"]),
        "xmp_removed": before["xmp_present"],
    }
