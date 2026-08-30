"""Mutating operations against a live PyMuPDF document handle.

Supports two operations: redact_region (v0.1, real content removal) and
replace_text (v0.2, layout-preserving text replacement). Both mutate the
handle in place rather than the read-oriented Document dataclasses -- see
the design specs' "Data model" and "Operations" sections for why.
"""
import re

import pymupdf as fitz

from engine.document import TextBlock


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
        # Verified on PyMuPDF 1.28.2: page.get_pixmap() defaults to DeviceRGB
        # with alpha=0, and Pixmap.pixel() returns a plain tuple of 0-255 ints
        # -- (r, g, b) here. Indexing the first three entries is therefore
        # correct whether or not a future default adds a trailing alpha.
        pixel = pixmap.pixel(x_px, y_px)
        reds.append(pixel[0])
        greens.append(pixel[1])
        blues.append(pixel[2])

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

    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, page.rect.x1))
    y1 = max(rect.y1, min(rect.y0 + needed_height, page.rect.y1))
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
            _validate_target); new_text is empty; target.size is not
            positive; no available font (the block's own real font, a
            Base-14 fallback, or PyMuPDF's bundled broad-coverage font) can
            render every character in new_text -- see _select_font; or
            new_text does not fit within the target block's region even
            after shrinking to 50% of target.size -- replace_text does not
            cascade reflow into neighboring content, it fails loudly
            instead. This last case is the sole one that raises *after*
            erasing the target: the region is left cleanly erased, by
            design, rather than silently reflowing into its neighbors.
    """
    # ---- validation: everything checkable without mutating the page ----
    if not new_text:
        raise ValueError(
            "new_text must be non-empty -- use redact_region to delete without replacing"
        )

    page, rect = _validate_target(handle, page_index, target.bbox)

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
        ValueError: see _validate_target.
    """
    page, rect = _validate_target(handle, page_index, target.bbox)
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
            fully off-page (see _validate_target); no available font can
            render target.text at the destination (see _select_font); or
            target.text does not fit the destination even after shrinking
            to 50% of target.size -- move_block does not cascade reflow,
            same as replace_text. This last case is the sole one that
            raises AFTER erasing the source: the source is left cleanly
            erased, by design, mirroring replace_text's own contract for
            its equivalent failure case.
    """
    if (target_position is None) == (offset is None):
        raise ValueError(
            "exactly one of target_position or offset must be given "
            f"(target_position={target_position!r}, offset={offset!r}). "
            "Nothing has been modified."
        )

    source_page, source_rect = _validate_target(handle, page_index, target.bbox)

    dest_index = destination_page_index if destination_page_index is not None else page_index
    if dest_index < 0 or dest_index >= handle.page_count:
        raise ValueError(
            f"destination_page_index {dest_index} is out of range for a document "
            f"with {handle.page_count} page(s); must be 0 <= destination_page_index "
            f"< {handle.page_count}. Nothing has been modified."
        )
    destination_page = handle[dest_index]

    width = source_rect.x1 - source_rect.x0
    height = source_rect.y1 - source_rect.y0
    if target_position is not None:
        new_x0, new_y0 = target_position
    else:
        new_x0, new_y0 = source_rect.x0 + offset[0], source_rect.y0 + offset[1]
    destination_bbox = (new_x0, new_y0, new_x0 + width, new_y0 + height)
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)

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
            degenerate or fully off-page (see _validate_target); no
            available font (a Base-14 name/style match, or the bundled
            broad-coverage font) can render every character of text; or
            text does not fit bbox at size -- named explicitly, since no
            shrink is attempted. Nothing is ever drawn before this
            function's validation completes, so a raise always leaves the
            document completely unmodified.
    """
    if not text:
        raise ValueError("text must be non-empty -- nothing to insert")

    page, rect = _validate_target(handle, page_index, bbox)

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
