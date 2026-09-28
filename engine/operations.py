"""Mutating operations against a live PyMuPDF document handle.

Supports seven operations: redact_region (real content removal),
replace_text (layout-preserving text replacement), delete_block,
move_block, insert_block, replace_image (swap one image placement's
bitmap), and sanitize_document (metadata/hidden-content scrub), alongside
the read-only get_metadata_summary. All of them mutate the handle in place
rather than the read-oriented Document dataclasses -- see the design specs'
"Data model" and "Operations" sections for why.
"""
import math
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


# C21' (fix round 1, reviewer finding F3): the on-canvas samples are used
# alone only when they agree with each other within this many 0-255 levels
# per channel.
_ON_CANVAS_AGREEMENT_MAX = 26


def _channel_spread(pixels: list[tuple[int, int, int]]) -> int:
    """The largest per-channel (max - min) spread across `pixels`, each a
    0-255 (r, g, b) tuple. Used by C21' to decide whether the on-canvas
    samples agree with each other closely enough to be trusted alone."""
    return max(max(p[i] for p in pixels) - min(p[i] for p in pixels) for i in range(3))


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
        # C21' (fix round 1, reviewer finding F3): math.floor, not int(). A
        # sample just off the canvas on the negative side (e.g. -0.5px) has
        # int(-0.5) == 0 -- truncation toward zero snaps it onto pixel 0,
        # INSIDE the canvas, hiding the very case this function exists to
        # detect. math.floor(-0.5) == -1, correctly off-canvas.
        raw_x = math.floor(display.x - pixmap.x)
        raw_y = math.floor(display.y - pixmap.y)
        on_canvas = 0 <= raw_x < pixmap.width and 0 <= raw_y < pixmap.height
        x_px = max(0, min(pixmap.width - 1, raw_x))
        y_px = max(0, min(pixmap.height - 1, raw_y))
        # Verified on PyMuPDF 1.28.2: page.get_pixmap() defaults to DeviceRGB
        # with alpha=0, and Pixmap.pixel() returns a plain tuple of 0-255 ints
        # -- (r, g, b) here. Indexing the first three entries is therefore
        # correct whether or not a future default adds a trailing alpha.
        pixel = pixmap.pixel(x_px, y_px)
        (on_canvas_pixels if on_canvas else off_canvas_pixels).append(pixel)

    # C21' (plan W7/R14, amended by fix round 1's reviewer finding F3): a
    # sample that falls off the canvas gets clamped onto the page edge
    # above, which can land on printed ink at that edge (a frame, a corner
    # logo, or the target's own overhanging glyph) instead of the true
    # background. The on-canvas samples are used ALONE only when there are
    # at least 2 of them and they agree with each other (their per-channel
    # spread is <= 26/255) -- plain C21 (median of a single on-canvas
    # sample, or of two that disagree, e.g. one landing on a header rule)
    # could make the erased fill WORSE than the old clamped-median behaviour,
    # up to solid black. Otherwise the clamped set is used, exactly as
    # before C21.
    if len(on_canvas_pixels) >= 2 and _channel_spread(on_canvas_pixels) <= _ON_CANVAS_AGREEMENT_MAX:
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
# target, a leader that stops widening (R6', see below), or ignored entirely
# (a rule that passes under a neighbouring word, not this one, and neither
# overlaps the target's x-range nor lies to its right).
_THIN_SEGMENT_MAX_HEIGHT_PT = 1.0

# The underline band a thin horizontal segment must fall in, to overlap the
# target's own x-range in, to bound the limit at its own x1 (R6, amended by
# R6' -- fix round 1, reviewer finding F5): [baseline, max(y1 + 2, baseline +
# 0.75*size)], with >= at the baseline edge. The additive slack below is the
# "+2" term; the 0.75*size term is applied where the band is computed, since
# it needs `size`.
_UNDERLINE_SLACK_PT = 2.0
_UNDERLINE_SLACK_SIZE_RATIO = 0.75


# ---------------------------------------------------------------------------
# The neighbour-aware erase clip (plan 2026-09-28-erase-neighbours; spec
# docs/superpowers/specs/2026-09-28-erase-neighbours-design.md, REVISION
# R1-R12 binding). Applies ONLY at the four TEXT erase sites (R10):
# delete_block, replace_text (both paths) and move_block's source erase --
# never replace_image's own _clean_erase call, and never redact_region.
# ---------------------------------------------------------------------------

_N1_FLOOR = 0.15  # R3
_N1_BBOX_TOL = 0.05  # same tolerance _span_metrics/_right_limit's is_target use
_N2_BLEED_PT = 0.5  # R7 -- the redaction fill's own measured bleed
_N2_INK_CAP_RATIO = 0.75  # R6 fallback cap height, as a fraction of size
_N2_INK_DESCENT_RATIO = 0.25  # R6 fallback descender, as a fraction of size


def _matching_span(
    page: fitz.Page, bbox: tuple[float, float, float, float], text: str | None
) -> dict | None:
    """The live page span matching `bbox` (and `text`, if given), within
    _N1_BBOX_TOL -- the same tolerance _span_metrics and _right_limit's own
    is_target already use for this. None if no span matches.

    R2: "For a hand-built block, [origin and size] come from the page span
    matching its bbox" -- this is that lookup, shared by _n1_clip and
    _n2_clip.
    """
    x0, y0, x1, y1 = bbox
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if text is not None and span["text"] != text:
                    continue
                bx0, by0, bx1, by1 = span["bbox"]
                if (
                    abs(bx0 - x0) < _N1_BBOX_TOL and abs(by0 - y0) < _N1_BBOX_TOL
                    and abs(bx1 - x1) < _N1_BBOX_TOL and abs(by1 - y1) < _N1_BBOX_TOL
                ):
                    return span
    return None


def _n1_clip(page: fitz.Page, rect: fitz.Rect, target: TextBlock) -> fitz.Rect:
    """R1-R5: clip `rect` (today's erase rect for one of the four text erase
    sites) vertically at the edges of every OTHER overlapping text span,
    before any mutation.

    - R2 (same-line exclusion): a span is a same-line neighbour, excluded
      from the clip, iff |span.origin.y - target.origin.y| <= 0.5*target.size
      -- target's own origin/size come from `target` itself, or (a
      hand-built block) from the page span matching its bbox
      (_matching_span). Every other overlapping span is split by its bbox
      centre against the target's own centre: above raises y0 to its y1,
      below lowers y1 to its y0.
    - R3 (the floor): if the clipped rect would keep less than _N1_FLOOR of
      the target's own bbox height, raise RefusedBeforeMutation.
    - R4 (direction): a target whose direction is not near-horizontal is
      refused, before any mutation, if its band overlaps another line's
      span at all -- there is no same-line/above-below concept for it.
    - R5 (Type3): a Type3 target keeps today's full rect unconditionally.

    Never mutates the page.
    """
    target_bbox = fitz.Rect(target.bbox)
    matched = _matching_span(page, target.bbox, target.text)

    # R5: Type3's glyph box does not match the span bbox, so a clipped band
    # may not remove the glyph -- keep today's full rect, unconditionally.
    if matched is not None and matched["font"].startswith("Type3"):
        return fitz.Rect(rect)

    origin = target.origin
    size = target.size
    direction = target.direction
    if origin is None and matched is not None:
        origin = matched["origin"]
        size = matched["size"]
    if direction is None and matched is not None:
        direction = matched.get("dir")
    if origin is None:
        origin = ((target_bbox.x0 + target_bbox.x1) / 2.0, (target_bbox.y0 + target_bbox.y1) / 2.0)
    baseline_y = origin[1]
    cy = (target_bbox.y0 + target_bbox.y1) / 2.0

    # direction=None (no direction recorded, no matching span either -- a
    # fully synthetic hand-built TextBlock) is treated as near-horizontal:
    # there is nothing to refuse against, and no fixture using such a
    # TextBlock has an overlapping neighbour anyway (R11).
    near_horizontal = direction is None or _direction_is_near_horizontal(direction)

    y0, y1 = rect.y0, rect.y1
    other_overlaps = False
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for other in line["spans"]:
                r = fitz.Rect(other["bbox"])
                if max(abs(a - b) for a, b in zip(tuple(r), tuple(target_bbox))) < _N1_BBOX_TOL:
                    continue  # this IS the target's own span
                if not (r.x1 > rect.x0 and r.x0 < rect.x1 and r.y1 > rect.y0 and r.y0 < rect.y1):
                    continue
                other_overlaps = True
                if not near_horizontal:
                    continue  # R4: no same-line/above-below concept here
                other_origin_y = other["origin"][1]
                if abs(other_origin_y - baseline_y) <= 0.5 * size:
                    continue  # R2: same-line neighbour, left to the pad rule
                if (r.y0 + r.y1) / 2.0 < cy:
                    if r.y1 > y0:
                        y0 = r.y1
                else:
                    if r.y0 < y1:
                        y1 = r.y0

    if not near_horizontal:
        if other_overlaps:
            raise RefusedBeforeMutation(
                f"target's direction {direction} is not near-horizontal and its "
                f"band overlaps another line's span -- erasing it would risk "
                f"damaging that line; nothing was changed"
            )
        return fitz.Rect(rect)

    height = target_bbox.height
    kept = (y1 - y0) / height if height else 0.0
    if kept < _N1_FLOOR:
        raise RefusedBeforeMutation(
            f"lines overlap too closely to erase this one without damaging its "
            f"neighbours (clipping would keep {kept:.0%} of its own height, "
            f"below the {_N1_FLOOR:.0%} floor); nothing was changed"
        )
    return fitz.Rect(rect.x0, y0, rect.x1, y1)


def _n2_ink_band(target: TextBlock, baseline_y: float) -> tuple[float, float]:
    """R6: (ink_top_y, ink_bottom_y) for `target` -- the geometric extent of
    its own glyphs above and below the baseline. Uses a Base-14 font's own
    glyph_bbox when target.font names one (an interpretation: the spec asks
    for "the resolved font's glyph bboxes", and a cheap, always-available
    resolution is only trivial for a Base-14 name; a non-Base-14
    target.font falls straight to the fallback), else the 0.75*size cap
    height / 0.25*size descender fallback R6 itself names.
    """
    size = target.size
    cap_ratio, descent_ratio = _N2_INK_CAP_RATIO, _N2_INK_DESCENT_RATIO
    font_key = (target.font or "").lower()
    if font_key in fitz.Base14_fontdict and target.text:
        try:
            font = _base14_font(font_key)
            tops, bottoms = [], []
            for ch in target.text:
                if ch.isspace():
                    continue
                gid = font.has_glyph(ord(ch))
                if not gid:
                    continue
                glyph_rect = font.glyph_bbox(gid)
                tops.append(glyph_rect.y1)
                bottoms.append(glyph_rect.y0)
            if tops:
                cap_ratio = max(0.0, max(tops))
            if bottoms:
                descent_ratio = max(0.0, -min(bottoms))
        except Exception:  # noqa: BLE001 -- fall back to the size-ratio estimate
            pass
    return baseline_y - cap_ratio * size, baseline_y + descent_ratio * size


def _n2_clip(page: fitz.Page, rect: fitz.Rect, target: TextBlock) -> fitz.Rect:
    """R6/R7: clip `rect` further at a drawn horizontal rule (a table/form
    border, a rule under a heading, ...) that belongs to the layout, not the
    target -- one that extends beyond the target on both sides (or starts
    left of it) and whose stroke lies entirely outside the target's own ink
    band (_n2_ink_band), stopping _N2_BLEED_PT short of the stroke (R7,
    re-measured: a 0.25pt margin still damages pixels, 0.5pt does not). A
    rule that crosses the ink zone is left exactly as it is today. Runs
    after _n1_clip; only ever moves y0 up or y1 down, same direction as N1.

    The search is bounded to rules within one rect-height of the current
    clip edges -- not specified by name in the spec (R6 gives no explicit
    distance cap), an interpretation call to keep an unrelated page rule
    (a header or footer line, which routinely "starts left of" a narrow
    target and sits "entirely above/below" its ink band by construction)
    from being treated as this target's own layout.

    Never mutates the page.
    """
    matched = _matching_span(page, target.bbox, target.text)
    if matched is not None and matched["font"].startswith("Type3"):
        return fitz.Rect(rect)  # R5, the same exception

    tx0, ty0, tx1, ty1 = target.bbox
    origin = target.origin
    if origin is None and matched is not None:
        origin = matched["origin"]
    if origin is None:
        origin = ((tx0 + tx1) / 2.0, (ty0 + ty1) / 2.0)
    baseline_y = origin[1]

    ink_top, ink_bottom = _n2_ink_band(target, baseline_y)
    proximity = max(3.0, rect.height)
    y0, y1 = rect.y0, rect.y1

    for item in page.get_drawings():
        width = item.get("width") or 0.0
        for seg in _drawing_edges(item):
            if (seg.y1 - seg.y0) >= _THIN_SEGMENT_MAX_HEIGHT_PT:
                continue  # not a horizontal rule
            layout = (seg.x0 < tx0 and seg.x1 > tx1) or seg.x0 < tx0
            if not layout:
                continue
            stroke_top = seg.y0 - width / 2.0
            stroke_bottom = seg.y1 + width / 2.0
            if stroke_bottom <= ink_top and stroke_bottom >= y0 - proximity:
                candidate = stroke_bottom + _N2_BLEED_PT
                if candidate > y0:
                    y0 = candidate
            elif stroke_top >= ink_bottom and stroke_top <= y1 + proximity:
                candidate = stroke_top - _N2_BLEED_PT
                if candidate < y1:
                    y1 = candidate
            # else: the stroke crosses the ink zone -- left as it is today.

    if y1 <= y0:
        raise RefusedBeforeMutation(
            "a layout rule clips this target's erase rect to zero or negative "
            "height; nothing was changed"
        )
    return fitz.Rect(rect.x0, y0, rect.x1, y1)


def _erase_text_block(page: fitz.Page, rect: fitz.Rect, target: TextBlock) -> None:
    """Erase `rect` -- one of the four text erase sites' own today's erase
    rect -- with the neighbour-aware clip (R1-R8), in place of a bare
    _clean_erase(page, rect) call.

    Order, entirely before the first mutating call:
      1. _n1_clip (R1-R5): clip vertically at overlapping neighbour spans,
         or raise RefusedBeforeMutation.
      2. _n2_clip (R6/R7): clip further at a layout rule crossing the
         (already N1-clipped) rect's edge, or raise.

    Then, mutating:
      3. R8: a first pass over the FULL, UNCLIPPED rect removing only
         contained drawings (text=1, graphics=1, images=0) -- the target's
         own underline/strike-through, which a clip that excludes that
         strip would otherwise orphan. For the common case (clipped ==
         rect, no overlapping neighbour or layout rule) this exactly
         duplicates what the final erase below does anyway via its own
         graphics=1 -- so it changes nothing for the existing suite.
      4. _clean_erase(page, clipped) -- N4: the fill samples around the
         rect actually filled, i.e. the clipped rect here.
    """
    clipped = _n1_clip(page, rect, target)
    clipped = _n2_clip(page, clipped, target)

    # R8's own pass is needed only when the rect was actually narrowed --
    # when it was not (the common case: no overlapping neighbour, no
    # layout rule), the final erase below already covers the exact same
    # full rect with its own graphics=1, making a separate pass here purely
    # redundant. Skipping it then keeps this helper's call pattern
    # identical to the pre-N1/N2 single _clean_erase call for every
    # existing fixture (R11: none has an overlapping neighbour), which
    # test_widen_path_erase_rect_is_pinned_to_bbox_plus_the_pad pins via a
    # count of add_redact_annot calls.
    if clipped.y0 != rect.y0 or clipped.y1 != rect.y1:
        # Measured on PyMuPDF 1.28.2: apply_redactions(graphics=1)'s own
        # "contained in rectangle" test does NOT treat a drawing whose edge
        # exactly touches the redact rect's own edge (e.g. an underline
        # starting at exactly target.bbox.x0, as insert_text's own bbox
        # always does) as contained -- it is silently left behind. A 0.5pt
        # outward pad on this pass's own rect (never on `clipped`, `rect`,
        # or the returned value) reliably clears that boundary, the same
        # margin R7 already uses for the redaction fill's own measured
        # bleed.
        #
        # That pad must NOT reach past a genuine layout rule (R6/R7) --
        # otherwise this pass would remove exactly the rule N2 clipped the
        # real erase away from, on the vertical edge(s) N2 actually moved.
        # _n2_clip is re-applied here to the FULL (unclipped) `rect`
        # directly -- independent of N1's own, possibly smaller, clip --
        # so R8's own pass stops at a real rule's own 0.5pt-short boundary,
        # and only pads the 0.5pt edge-touch margin on a side N2 left
        # untouched.
        try:
            n2_on_full = _n2_clip(page, rect, target)
        except RefusedBeforeMutation:
            n2_on_full = clipped
        pad_top = _N2_BLEED_PT if n2_on_full.y0 <= rect.y0 + 1e-6 else 0.0
        pad_bottom = _N2_BLEED_PT if n2_on_full.y1 >= rect.y1 - 1e-6 else 0.0
        r8_rect = fitz.Rect(
            rect.x0 - _N2_BLEED_PT, n2_on_full.y0 - pad_top,
            rect.x1 + _N2_BLEED_PT, n2_on_full.y1 + pad_bottom,
        )
        with at_rotation_zero(page):
            page.add_redact_annot(r8_rect, fill=False)
            page.apply_redactions(text=1, graphics=1, images=0)

    _clean_erase(page, clipped)


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

    # ---- text spans (R3, W-F1), and the R7'/R8 column-edge neighbours ----
    # Each entry is (rect, origin_y): the origin (not just the bbox) is
    # needed for W-F1's same-line test and R7's baseline window.
    other_spans: list[tuple[fitz.Rect, float]] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                r = fitz.Rect(span["bbox"])
                if is_target(r):
                    continue
                origin_y = span["origin"][1]
                other_spans.append((r, origin_y))
                # A span whose left edge aligns with the target's own
                # (within 2pt) is a same-column neighbour (a paragraph
                # sibling above or below, or a stacked form's own value in
                # another row) -- not a rightward obstacle in the R3 sense,
                # even though normal single-line leading routinely makes its
                # bbox vertically overlap the target's own band. Same-column
                # neighbours are governed separately, by R7' (the column
                # edge) and R8 (right-alignment) below; without this
                # exclusion a real paragraph's own line spacing would make
                # R3 fire against its own siblings and defeat R7' for
                # ordinary single-spaced body text.
                #
                # Ruling W-F1 (fix round 1, reviewer finding F1, CRITICAL):
                # that exclusion applies ONLY when the aligned span is on
                # ANOTHER line -- abs(origin.y - baseline) > 0.5*size. A
                # left-aligned span on the SAME line (a narrow 1.95pt-wide
                # first glyph followed by the rest of the word in another
                # span, a flattened overprint starting 0.5pt right of the
                # target's own x0, overlapping OCR word/line boxes) must
                # still count as an R3 obstacle -- otherwise a widened draw
                # covers it. Measured: this keeps all 48 paragraph fixtures
                # widening while blocking all three attacks.
                other_line = abs(origin_y - baseline) > 0.5 * size
                column_aligned = abs(r.x0 - tx0) <= 2.0 and other_line
                if not column_aligned and r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
                    candidates.append(max(r.x0, tx1) - gap)

    # ---- R8: a right-aligned neighbour marks the target as right-aligned ----
    for r, _origin_y in other_spans:
        if (
            abs(r.y0 - ty0) <= 2 * line_height
            and abs(r.x1 - tx1) <= 1.0
            and abs(r.x0 - tx0) > 2.0
        ):
            candidates.append(tx1)
            break

    # ---- R7': the paragraph column edge (fix round 1, reviewer finding F2)
    # ----
    # Cap at the largest aligned neighbour's x1 only when at least 2 aligned
    # neighbours' x1 values fall within 10% of the COLUMN WIDTH of that
    # largest x1 -- not "all agree with each other", which a real paragraph's
    # own short last line routinely breaks. The window is baselines within
    # 3*size of the target's own baseline (not "2 bbox heights", which
    # misses neighbours at leading >= 1.4).
    aligned = [
        (r, origin_y) for r, origin_y in other_spans
        if abs(r.x0 - tx0) <= 2.0 and abs(origin_y - baseline) <= 3 * size
    ]
    if aligned:
        x1_values = [r.x1 for r, _origin_y in aligned]
        top = max(x1_values)
        column_width = top - tx0
        cluster = [x for x in x1_values if column_width > 0 and top - x <= 0.1 * column_width]
        if column_width > 0 and len(cluster) >= 2:
            candidates.append(max(top, tx1))

    # ---- images (R5): any image in the band forbids widening outright ----
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.x1 > tx1 and _overlaps_band(ty0, ty1, r):
            candidates.append(tx1)
            break

    # ---- drawings (R3/R6'): rectangles split into edges first ----
    # R6' (fix round 1, reviewer finding F5): a thin horizontal segment is
    # either:
    #   - an underline: it overlaps the target's own x-range, and lies in
    #     the underline band -- bounds R at its own x1;
    #   - a leader: it lies entirely to the right of the target (its x0 >=
    #     tx1) and overlaps the target's vertical band -- an ordinary
    #     obstacle, so a dotted/dashed leader now stops widening;
    #   - otherwise ignored (neither overlaps the target's x-range nor
    #     starts at or past its right edge -- a rule under a different
    #     word).
    # The underline band is [baseline, max(y1 + 2, baseline + 0.75*size)],
    # with >= at the baseline edge.
    underline_top = baseline
    underline_bottom = max(ty1 + _UNDERLINE_SLACK_PT, baseline + _UNDERLINE_SLACK_SIZE_RATIO * size)
    for item in page.get_drawings():
        for seg in _drawing_edges(item):
            thin = (seg.y1 - seg.y0) < _THIN_SEGMENT_MAX_HEIGHT_PT
            if thin:
                overlaps_target_x = seg.x1 > tx0 and seg.x0 < tx1
                in_underline_band = seg.y1 >= underline_top and seg.y0 < underline_bottom
                if overlaps_target_x:
                    if in_underline_band:
                        candidates.append(seg.x1)
                    # An underline-shaped segment outside the band bounds
                    # nothing (R6) -- ignored.
                    continue
                if seg.x0 >= tx1 and _overlaps_band(ty0, ty1, seg):
                    # A leader: ordinary R3-style obstacle treatment.
                    candidates.append(max(seg.x0, tx1) - gap)
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
    # F6 (fix round 1, reviewer finding F6, MINOR): the margin candidate is
    # folded directly into the min() call as its `default`, rather than
    # appended to `candidates` as an ordinary entry, so a future change that
    # removes every other append() call can never leave min() looking at an
    # empty list.
    bounds = unrotated_bounds(page)
    all_x0 = [r.x0 for r, _origin_y in other_spans] + [tx0]
    min_x0 = min(all_x0)
    left_margin = max(18.0, min_x0 - bounds.x0)
    margin_limit = bounds.x1 - left_margin

    R = min(candidates, default=margin_limit)
    if margin_limit < R:
        R = margin_limit
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
    color: tuple[float, float, float] = (0, 0, 0),
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

    color is the RGB fill passed straight to insert_textbox, defaulting to
    black (move_block's own behaviour, and this function's original
    behaviour before D3). replace_text's box path passes target's own
    colour (D3), falling back to black when the parsed block carries none.

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
                color=color,
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
    #
    # Final review finding F1 (IMPORTANT, a regression against master): a
    # Base-14 name (e.g. "helvetica") is written into the PDF as a *simple*
    # (single-byte) font -- PyMuPDF's own insert_textbox encodes it that
    # way, mapping every codepoint above 255 (curly quotes, bullets,
    # ligatures like fi, accented Latin Extended-A characters, a thin
    # space, ...) to "?" instead of refusing or falling through. has_glyph()
    # on a Base-14 fitz.Font accepts many of these codepoints (it reports
    # the GLYPH exists in principle), so _missing_glyphs alone says Tier 2
    # covers them -- but the actual PDF write path cannot draw them at all.
    # On the widen path this additionally breaks W3's own contract: "?" is
    # measured at a different (typically much narrower) advance width than
    # the real character, so w_need is computed from characters that will
    # never actually be drawn that width, making the one-line rect too
    # short once the real (wider) "?" glyphs are written -- erasing the
    # target and then failing to draw at all. Restricting Tier 2 to text
    # entirely within Latin-1 (ord(c) < 256 for every character) sends
    # anything else straight to Tier 3's bundled broad-coverage font, which
    # embeds as a real multi-byte font and draws every character correctly.
    # This also fixes the parked P3 finding ("?" drawn for characters above
    # 255) on BOTH the widen and box paths, since _select_font is shared.
    base14_key = target.font.lower()
    if base14_key not in fitz.Base14_fontdict:
        base14_key = _base14_style_match(target.font)
    base14_font = _base14_font(base14_key)
    if not _missing_glyphs(base14_font, new_text) and all(ord(c) < 256 for c in new_text):
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


# ---- replace_text's widen-before-shrink path (plan Task 4, spec W1/W3, ----
# ---- rulings D2/D3, R1, R9, R11, R13) -------------------------------------

# A line break in new_text collapses to a single space (D2, amended by the
# Task 4 Fable review's finding C1): \r\n first, so the pair collapses to
# ONE space rather than two, then any lone separator str.splitlines() itself
# recognises -- \r, \n, \v (0x0b), \f (0x0c), 0x1c-0x1e (the file/group/
# record separators), 0x85 (NEL), U+2028 (LINE SEPARATOR) or U+2029
# (PARAGRAPH SEPARATOR) -- plus \t. The original set (D2's own \r, \n,
# U+2028, U+2029) missed the rest of str.splitlines()'s own separators and
# \t: any of those reaching insert_textbox on the widen path still means
# "start a new line here" or "indent", not "one line of text", exactly like
# a bare \n did -- W1 draws one line by definition, on BOTH paths, and this
# runs before the path is even decided.
_LINE_BREAK_RE = re.compile("\r\n|[\r\n\v\f\x1c\x1d\x1e\x85  \t]")

# R13: dir is compared to (1, 0) with this tolerance on each component. A
# 1-degree OCR skew reports dir (1.0, -0.0175) -- well outside this -- and
# takes today's path, per probe_w5.py.
_DIRECTION_TOLERANCE = 1e-3

# R1's baseline sanity gate: both checks must hold within this many points.
_BASELINE_SANITY_TOLERANCE_PT = 1.0


def _direction_is_near_horizontal(direction: tuple[float, float] | None) -> bool:
    """R13: is `direction` within `_DIRECTION_TOLERANCE` of (1, 0)?

    False for None (no direction recorded -- today's path).
    """
    if direction is None:
        return False
    dx, dy = direction
    return abs(dx - 1.0) <= _DIRECTION_TOLERANCE and abs(dy) <= _DIRECTION_TOLERANCE


def _span_metrics(page: fitz.Page, target: TextBlock) -> tuple[float, float] | None:
    """The (ascender, descender) PyMuPDF itself reports for the span
    matching `target`, re-read from `page.get_text("dict")`.

    R1 requires "the span's own reported metrics", and TextBlock carries no
    ascender/descender field (Task 2 added only origin/direction/color, and
    Task 4's file scope does not touch engine/document.py) -- so this
    re-reads the live page rather than trusting a proxy for those metrics.
    The resolved DRAWING font's own ascender/descender was considered and
    rejected: for Type3/unresolvable fonts, _select_font's Tier-2 fallback
    (e.g. Helvetica) has different metrics than the original span, which
    could make R1's gate pass when it must not.

    Docstring correction (Task 4 Fable review, fix round 2, M-a): the
    original justification here cited probe_w1.py's Type3 fixture, but that
    example does NOT actually prove re-reading matters -- Type3's own d2
    check (the bbox-height comparison) is ~4.5pt even using HELVETICA's
    metrics, so the gate already rejects that fixture via d2 alone, whether
    or not d1 is computed from the right font. The real proof is a genuine,
    non-Type3 embedded font whose ascender/descender differ enough from
    Helvetica's to matter: DejaVu Sans at 12pt, drawn with insert_text, is
    reliable under its OWN metrics (d1 = d2 = 0) but would be wrongly
    REJECTED if Helvetica's metrics were substituted (d1 ~= 1.76pt, d2 ~=
    2.53pt, both over the 1pt tolerance) -- see
    test_r1_gate_uses_the_spans_own_metrics_not_helvetica in
    tests/test_replace_widen.py.

    Matched by bbox (within the same 0.05pt tolerance _right_limit's
    is_target uses) and by text, since this runs before any mutation and the
    target's span is still exactly on the page. Returns None if no matching
    span is found -- callers treat that as the gate failing (today's path).
    """
    tx0, ty0, tx1, ty1 = target.bbox
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"] != target.text:
                    continue
                bx0, by0, bx1, by1 = span["bbox"]
                if (
                    abs(bx0 - tx0) < 0.05 and abs(by0 - ty0) < 0.05
                    and abs(bx1 - tx1) < 0.05 and abs(by1 - ty1) < 0.05
                ):
                    return span["ascender"], span["descender"]
    return None


def _origin_is_reliable(page: fitz.Page, target: TextBlock) -> bool:
    """R1's baseline sanity gate: is `target.origin` trustworthy enough to
    draw the replacement at it directly, rather than falling back to
    today's box-and-shrink path?

    Both must hold, using the span's own reported ascender/descender (see
    _span_metrics):
      - |origin.y - (bbox.y0 + size*asc)| <= 1pt
      - |bbox.height - size*(asc - desc)| <= 1pt

    False whenever target.origin is None, or no matching span can be
    re-read (see _span_metrics). This single check routes y-mirrored text
    (which reports dir (1, 0) but has a materially different bbox-to-origin
    relationship), a scaled Tm or Tz, and Type3 fonts to today's path --
    confirmed against probe_w1.py's cases.

    Note (Task 4 Fable review, fix round 2, M-b): this gate is SIZE
    DEPENDENT for a font whose bbox/origin relationship is not exactly
    linear in size at typical point sizes (rounding in the source PDF's own
    recorded bbox, or in a font's own hinting). ZapfDingbats is measured to
    pass at 12pt (d1 ~= 0.38pt, d2 ~= 0.44pt, both comfortably under the 1pt
    tolerance) but FAIL at 72pt (d1 ~= 2.27pt, d2 ~= 2.66pt -- the same
    relative gap, scaled up by 6x, crosses the tolerance) -- see
    test_r1_gate_zapfdingbats_routes_by_size in tests/test_replace_widen.py.
    This is expected, not a bug: the tolerance is an absolute point value
    (R1), not a fraction of size, so it is deliberately stricter at larger
    sizes; ZapfDingbats is not special-cased for it.
    """
    if target.origin is None:
        return False
    metrics = _span_metrics(page, target)
    if metrics is None:
        return False
    asc, desc = metrics
    x0, y0, x1, y1 = target.bbox
    ox, oy = target.origin
    size = target.size
    d1 = abs(oy - (y0 + size * asc))
    d2 = abs((y1 - y0) - size * (asc - desc))
    return d1 <= _BASELINE_SANITY_TOLERANCE_PT and d2 <= _BASELINE_SANITY_TOLERANCE_PT


def _widen_draw_rect(
    origin: tuple[float, float], size: float, font: fitz.Font, width: float
) -> fitz.Rect:
    """The rect R9 draws the widened/shrunk replacement into: exactly one
    line, its baseline pinned at `origin`.

    Same height rule as _insertion_rect (insert_textbox's own internal
    `lheight - descender*fontsize <= rect.height` acceptance check for one
    line), but anchored at `origin`'s own derived top (`origin.y -
    size*ascender`) rather than at a bbox's top-left -- so the baseline
    lands exactly at `origin.y`, not merely close to it. Verified empirically
    (this task's own probe) to read back as one span whose origin equals
    `origin` to float precision, at every page rotation and for real,
    embedded and Base-14 fonts alike.

    `width` is the exact advance width for the text this will draw, at
    `size`, in `font` -- the caller has already resolved this from
    `font.text_length`. `_WIDTH_PRECISION_PAD_PT` absorbs the same
    measurement/metrics rounding gap _insertion_rect's own pad exists for.
    """
    asc = font.ascender
    desc = font.descender
    line_height_factor = asc - desc
    if line_height_factor <= 1:
        line_height_factor = 1.2
    needed_height = size * (line_height_factor - desc)
    top = origin[1] - size * asc
    return fitz.Rect(
        origin[0], top, origin[0] + width + _WIDTH_PRECISION_PAD_PT, top + needed_height
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
    """Replace target's content with new_text, in the original colour, on
    the original baseline whenever that baseline can be trusted (see below);
    otherwise via PyMuPDF's word-wrap and this function's own font-shrink
    retry loop, all within target's own block. See the design spec's
    "Operation" section, and its REVISION (D1-D3, R1-R15), which is binding.

    Two paths, decided per call (plan Task 4):

    - **The new, widen-before-shrink path** (spec W1-W3), taken when
      target.origin is present, target.direction is within 1e-3 of (1, 0)
      (R13), and R1's baseline sanity gate passes (_origin_is_reliable) --
      this covers y-mirrored text, a scaled Tm or Tz, and Type3 fonts, which
      all report misleading geometry and are routed to the path below
      instead. On this path the free space to target's right is computed
      FIRST (_right_limit, read-only, no mutation) and the text is drawn as
      ONE line at its original size if it fits there, otherwise at the
      exact size that makes it fit (font advance width is linear in size,
      so no retry loop is needed) -- and if even that is below the 50%
      shrink floor, this raises RefusedBeforeMutation BEFORE erasing
      anything (R11): the "erased, then did not fit" failure is retired for
      this path. The draw itself uses insert_textbox with R9's rect, which
      this task's own probe confirmed reads back as exactly one span whose
      origin equals the original to float precision.
    - **Today's box-and-shrink path**, otherwise (including whenever
      target.origin or target.direction is None, e.g. a hand-built
      TextBlock). Unchanged except for D2 and D3 below.

    Two corrections from the critique apply to BOTH paths, before the path
    is even decided:
    - **D2** (amended by the Task 4 Fable review's C1): every separator
      str.splitlines() itself recognises (\\r\\n, \\r, \\n, \\v, \\f, 0x1c-
      0x1e, 0x85, U+2028, U+2029), plus \\t, collapses to a single space --
      W1 draws one line by definition, and any of these reaching
      insert_textbox on the box path still means "start a new line here" or
      "indent", not "the replacement contains two lines of content" -- see
      _LINE_BREAK_RE.
    - **D3:** the replacement is drawn in target's own colour (black when
      target.color is None, e.g. a hand-built TextBlock) -- not always
      black, as before this plan.

    The region *erased* is always target.bbox plus the small precision pad
    (_WIDTH_PRECISION_PAD_PT) on the right, target.bbox's own top and
    bottom -- never the widened area, which is free by construction (R3-R5)
    and has no old ink to remove (W4).

    Callers must **re-parse before reusing a TextBlock after an edit**
    (Task 4 Fable review, fix round 2, M-c): every field on `target` --
    bbox, origin, direction, color -- describes the page as it was at parse
    time. Calling replace_text (or any other mutating operation) changes
    the live page, so a second call must be made against a freshly parsed
    TextBlock for the NEW content, not the stale one from before the first
    edit. This matters doubly here: _span_metrics re-matches `target`
    against the live page by bbox AND text, and a stale TextBlock whose
    bbox happens to fall within the match tolerance of an unrelated span
    (e.g. two near-duplicate words a few points apart) can silently pick up
    the WRONG span's metrics.

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
      its own shrink-retry loop on the box path, as this plan assumes.
    - insert_textbox() is all-or-nothing on failure, NOT partial-draw: a
      call that returns a negative deficit draws nothing at all -- verified
      against a single-line-height bbox (this task's real fixture target),
      a taller multi-line bbox that fits ~2 of ~10 needed lines, and a
      fresh blank page, all producing zero extracted characters from a
      failed attempt. This differs from the brief's assumed "partial draw
      on failure" behavior, so the box path's retry loop erases the region
      ONCE before the loop (not on every iteration): a failed attempt at a
      larger fontsize never leaves anything for the next, smaller attempt
      to stack on top of.

    Every check that can be made without touching the page runs before the
    erase step, so the only way this function can erase content and then
    fail is the one case the design spec deliberately wants to fail loudly
    (see the last Raises entry, box path only). In particular the font is
    resolved up front via _select_font's three-tier cascade (see that
    function's docstring): if no tier's font can render every character
    new_text needs, that failure surfaces as the ValueError this function's
    contract promises before anything is erased -- were it reached only
    after the erase, it would leave the document permanently damaged and
    (absent _select_font's own validation) risk insert_textbox raising a
    bare Exception ("need font file or buffer", verified on 1.28.2) that
    this function's contract never promises.

    Raises:
        ValueError: page_index out of range or target.bbox degenerate/
            off-page (same checks redact_region uses, via
            _validate_target); the page cannot be drawn on correctly
            (malformed /Rotate, /UserUnit, or a CropBox overhang); see
            engine.geometry.drawing_refusal; new_text is empty;
            target.size is not positive; no available font (the block's
            own real font, a Base-14 fallback, or PyMuPDF's bundled
            broad-coverage font) can render every character in new_text --
            see _select_font. RefusedBeforeMutation (a ValueError), before
            any erase: on the new path, new_text does not fit even at the
            widened width, shrunk to 50% of target.size (R11). On the box
            path only, new_text not fitting within target's own region even
            after shrinking to 50% of target.size raises a PLAIN ValueError
            *after* erasing the target -- box-path replace_text does not
            cascade reflow into neighboring content, it fails loudly
            instead, and the region is left cleanly erased, by design,
            rather than silently reflowing into its neighbors. Either path,
            a drawing failure unrelated to fit (insert_textbox raising for
            some other reason) is also a plain ValueError, always after the
            erase.
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

    # ---- D2: a line break in new_text collapses to a single space ----
    new_text = _LINE_BREAK_RE.sub(" ", new_text)

    # ---- font resolution (unchanged) ----
    # Resolves the block's own real font (extracted from the source PDF
    # and re-embedded), falling back through Base-14 and finally PyMuPDF's
    # bundled broad-coverage font -- see _select_font's docstring. Raises
    # ValueError before any mutation if no tier covers new_text.
    resolved_fontname, resolved_font = _select_font(handle, page, target, new_text)

    # D3: draw in the original colour; black when none was recorded (e.g. a
    # hand-built TextBlock, or a caller-supplied replace() before Task 2).
    color = target.color if target.color is not None else (0.0, 0.0, 0.0)

    # ---- decide the path (R1, R13) ----
    use_widen_path = (
        _direction_is_near_horizontal(target.direction)
        and _origin_is_reliable(page, target)
    )

    if use_widen_path:
        origin_x, origin_y = target.origin

        # ---- W2/W3: the limit, then the size, all before any mutation ----
        limit = _right_limit(page, target.bbox, origin_y, target.size)
        w_avail = max(0.0, limit - origin_x)
        w_need = resolved_font.text_length(new_text, target.size)

        if w_need <= w_avail:
            draw_size = target.size
            draw_width = w_need
        else:
            draw_size = target.size * w_avail / w_need
            floor = target.size * _SHRINK_FLOOR_RATIO
            if draw_size < floor:
                raise RefusedBeforeMutation(
                    f"new_text ({len(new_text)} chars) does not fit to the right of "
                    f"target.bbox {tuple(target.bbox)} (available width "
                    f"{w_avail:.2f}pt) even shrunk to the floor ({floor:.2f}pt, 50% "
                    f"of the original {target.size}pt) -- the computed size would be "
                    f"{draw_size:.2f}pt. Nothing has been modified."
                )
            draw_width = resolved_font.text_length(new_text, draw_size)

        # ---- erase: target.bbox plus the precision pad, unchanged (W4) ----
        bounds = unrotated_bounds(page)
        erase_x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, bounds.x1))
        erase_rect = fitz.Rect(rect.x0, rect.y0, erase_x1, rect.y1)
        _erase_text_block(page, erase_rect, target)

        # See _select_font's and _draw_shrink_to_fit's docstrings for why
        # Tier 1/Tier 3 registration is deferred to after the erase.
        if resolved_fontname not in fitz.Base14_fontdict:
            page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)

        # ---- R9: one line, drawn at the original baseline ----
        draw_rect = _widen_draw_rect(target.origin, draw_size, resolved_font, draw_width)
        try:
            remaining_space = page.insert_textbox(
                draw_rect, new_text, fontname=resolved_fontname, fontsize=draw_size, color=color,
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, see the box path below
            raise ValueError(
                f"failed to draw text at origin {target.origin} at {draw_size:.2f}pt: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        # Fable review, finding C1 (CRITICAL): insert_textbox's return value
        # was previously ignored on this path. A negative return means
        # insert_textbox drew NOTHING at all (verified: it is all-or-nothing
        # on failure, same as the box path -- see this function's own
        # investigation notes above) -- so without this check, a case R9's
        # rect sizing did not anticipate (e.g. a measurement gap between
        # text_length and insert_textbox's own internal layout) erased the
        # old text and left the region silently blank. This is a plain
        # ValueError, not RefusedBeforeMutation: the erase has already
        # happened by this point, so "nothing was changed" would be false.
        if remaining_space < 0:
            raise ValueError(
                f"insert_textbox reported a deficit of {-remaining_space:.2f}pt "
                f"drawing {new_text!r} at origin {target.origin} at "
                f"{draw_size:.2f}pt into {tuple(draw_rect)} -- nothing was drawn. "
                f"The target region has already been erased."
            )
        return

    # ---- today's box-and-shrink path, otherwise ----
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
    _erase_text_block(page, erase_rect, target)

    # _select_font deliberately does NOT register a Tier 1/Tier 3 font on
    # `page` itself -- see _select_font's docstring and _draw_shrink_to_fit's
    # own registration-ordering comment for why that registration is
    # deferred to here.
    _draw_shrink_to_fit(
        page, insert_rect, resolved_fontname, resolved_font, new_text,
        target.size, context_bbox=target.bbox, color=color,
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
    _erase_text_block(page, rect, target)


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
    _erase_text_block(source_page, source_rect, target)
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
