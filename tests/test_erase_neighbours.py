"""Tests for plan docs/superpowers/plans/2026-09-28-erase-neighbours.md
(spec docs/superpowers/specs/2026-09-28-erase-neighbours-design.md, REVISION
section R1-R12 binding).

Fixtures and the ideal-page oracle are built inline here, adapted from the
critic's executed probes
(docs/superpowers/records/2026-09-28-erase-neighbours/probes/critique/
harness.py, n1_layouts.py, n1_sameline.py, n2_form.py, n2_bleed.py,
n3_scan.py, extras.py) -- never imported from that directory.
"""
import dataclasses

import pymupdf as fitz
import pytest

from engine.document import TextBlock
from engine.errors import RefusedBeforeMutation
from engine.operations import (
    _erase_text_block,
    _n1_clip,
    _n2_clip,
    delete_block,
    move_block,
    replace_text,
)
from engine.parser import parse
from tests.test_page_geometry import fingerprint


# ---------------------------------------------------------------------------
# The ideal-page oracle (harness.py, adapted): build a page from a list of
# text lines, one erase mutator, and compare the mutated page against the
# same page built WITHOUT the target line, in both exported words and
# pixels.
# ---------------------------------------------------------------------------

ZOOM = 3


def build_paragraph_pdf(lines, pitch, size=12, font="helv", x=72, y0=100, omit_index=None):
    """`lines`: list of strings, one per line, inserted at
    (x, y0 + i*pitch). omit_index skips that line entirely (the ideal
    page)."""
    d = fitz.open()
    p = d.new_page()
    for i, text in enumerate(lines):
        if omit_index is not None and i == omit_index:
            continue
        p.insert_text((x, y0 + i * pitch), text, fontsize=size, fontname=font)
    return d.tobytes()


def words_of(pdf_bytes):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return sorted(w[4] for w in d[0].get_text("words"))
    finally:
        d.close()


def render_clip(pdf_bytes, clip):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return d[0].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=clip)
    finally:
        d.close()


def pix_diff(after, ideal):
    """(leftover, damage): pixels dark in `after` but light in `ideal` (the
    target's own ink left behind), and vice versa (neighbour ink lost or a
    neighbour region painted over)."""
    a, b = after.samples, ideal.samples
    assert len(a) == len(b)
    leftover = sum(1 for x, y in zip(a, b) if x < 128 <= y)
    damage = sum(1 for x, y in zip(a, b) if y < 128 <= x)
    return leftover, damage


def stroke_lines_remaining(page):
    """The page's own drawn lines/strokes (type 's') -- excludes the erase's
    own painted fill rectangle ('fs'), which get_drawings() also reports."""
    return [dr for dr in page.get_drawings() if dr.get("type") == "s"]


def target_block(doc, prefix="TARGET"):
    for b in doc.pages[0].text_blocks:
        if b.text.startswith(prefix):
            return b
    raise AssertionError(f"no text block starting with {prefix!r} on page 0")


# ---------------------------------------------------------------------------
# Task 1 (R1-R5, R8, R10): the pitch/position/operation sweep (R11 fixtures)
# ---------------------------------------------------------------------------

PITCHES = [18, 16.5, 15, 14.4, 13, 12, 11]
POSITIONS = ["first", "middle", "last"]
OPERATIONS = ["delete", "replace_widen", "replace_box", "move"]

_BAND_MARGIN = 30.0  # pt, clip margin around the 3-line band for pixel checks


def _paragraph_lines(position):
    words = "quick brown fox jumps gyp"
    if position == "first":
        return [f"TARGET {words} 0", f"LINE1 {words} 1", f"LINE2 {words} 2"], 0
    if position == "last":
        return [f"LINE0 {words} 0", f"LINE1 {words} 1", f"TARGET {words} 2"], 2
    return [f"LINE0 {words} 0", f"TARGET {words} 1", f"LINE2 {words} 2"], 1


def _apply_operation(handle, op, target):
    if op == "delete":
        delete_block(handle, 0, target)
    elif op == "replace_widen":
        replace_text(handle, 0, target, "X")
    elif op == "replace_box":
        # Force today's box-and-shrink path (R2's hand-built-block branch):
        # stripping origin/direction routes replace_text away from the
        # widen path even though a real, matching span is still on the
        # page for _n1_clip/_n2_clip to find by bbox.
        stripped = dataclasses.replace(target, origin=None, direction=None)
        replace_text(handle, 0, stripped, "X")
    elif op == "move":
        move_block(handle, 0, target, offset=(0, 300))
    else:  # pragma: no cover -- guards a typo in the parametrize table
        raise AssertionError(op)


@pytest.mark.parametrize("op", OPERATIONS)
@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("pitch", PITCHES)
def test_erase_preserves_neighbours_across_pitch_position_and_operation(pitch, position, op):
    lines, idx = _paragraph_lines(position)
    pdf = build_paragraph_pdf(lines, pitch)
    ideal_pdf = build_paragraph_pdf(lines, pitch, omit_index=idx)
    ideal_words = words_of(ideal_pdf)
    clip = fitz.Rect(60, 100 - _BAND_MARGIN, 300, 100 + 2 * pitch + _BAND_MARGIN)
    ideal_pix = render_clip(ideal_pdf, clip)

    doc, handle = parse(pdf)
    target = target_block(doc)

    _apply_operation(handle, op, target)

    page = handle[0]
    after_words = sorted(w[4] for w in page.get_text("words"))
    missing = [w for w in ideal_words if w not in after_words]
    assert not missing, (
        f"neighbour word(s) lost (pitch={pitch} position={position} op={op}): {missing}"
    )

    after_pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=clip)
    leftover, damage = pix_diff(after_pix, ideal_pix)
    assert damage == 0, (
        f"{damage} neighbour pixel(s) damaged (pitch={pitch} position={position} op={op})"
    )
    handle.close()


# ---------------------------------------------------------------------------
# R2: same-line neighbours are excluded from the vertical clip
# ---------------------------------------------------------------------------


def test_n1_clip_leaves_a_same_line_neighbour_alone():
    """A bold label immediately followed by body text on the SAME line, with
    NO lines above or below at all -- so any clip found here can only be
    the (wrongly) mis-detected same-line neighbour, never a genuine
    above/below one. R2's exclusion must leave the rect entirely
    unclipped."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "TARGET:", fontsize=12, fontname="hebo")
    label_width = p.get_text("dict")["blocks"][0]["lines"][-1]["spans"][-1]["bbox"][2]
    p.insert_text((label_width, 100), " do not touch the body", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="TARGET:")
    page = handle[0]
    rect = fitz.Rect(target.bbox)
    clipped = _n1_clip(page, rect, target)

    assert clipped.y0 == rect.y0 and clipped.y1 == rect.y1, (
        f"same-line neighbour should not clip the rect at all, got {clipped}"
    )

    delete_block(handle, 0, target)
    remaining = handle[0].get_text()
    assert "do not touch the body" in remaining
    assert "TARGET" not in remaining
    handle.close()


def test_delete_block_leaves_a_same_line_neighbour_intact_between_tight_lines():
    """The same fixture, now sandwiched between tight-leading lines above
    and below (pitch 13) -- the above/below lines DO clip (they are
    genuine neighbours), but the same-line body text must survive
    end-to-end."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 87), "above line gyp", fontsize=12)
    p.insert_text((72, 100), "TARGET:", fontsize=12, fontname="hebo")
    label_width = p.get_text("dict")["blocks"][-1]["lines"][-1]["spans"][-1]["bbox"][2]
    p.insert_text((label_width, 100), " do not touch the body", fontsize=12)
    p.insert_text((72, 113), "below line gyp", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="TARGET:")
    delete_block(handle, 0, target)
    remaining = handle[0].get_text()
    assert "do not touch the body" in remaining
    assert "above line" in remaining
    assert "below line" in remaining
    assert "TARGET" not in remaining
    handle.close()


# ---------------------------------------------------------------------------
# Superscripts / subscripts
# ---------------------------------------------------------------------------


def test_delete_block_removes_its_own_superscript():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "ABOVE line gyp", fontsize=12)
    p.insert_text((72, 114.4), "TARGET E = mc", fontsize=12)
    p.insert_text((72 + 78, 109.4), "2", fontsize=7)  # the target's own superscript
    p.insert_text((72, 128.8), "BELOW line gyp", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="TARGET")
    delete_block(handle, 0, target)

    remaining = handle[0].get_text()
    assert "ABOVE" in remaining and "BELOW" in remaining
    assert "TARGET" not in remaining
    # The superscript "2" belonged to the target's own line -- it must go
    # with it, not survive as an orphan.
    assert "2" not in remaining
    handle.close()


def test_delete_block_leaves_a_neighbours_subscript_intact():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "ABOVE line H", fontsize=12)
    p.insert_text((72 + 72, 103), "2", fontsize=7)  # subscript of the ABOVE line
    p.insert_text((72 + 76, 100), "O and more", fontsize=12)
    p.insert_text((72, 114.4), "TARGET line gyp", fontsize=12)
    p.insert_text((72, 128.8), "BELOW line gyp", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="TARGET")
    delete_block(handle, 0, target)

    remaining = handle[0].get_text()
    assert "TARGET" not in remaining
    assert "ABOVE" in remaining and "BELOW" in remaining
    assert "2" in remaining  # the neighbour's own subscript survives
    assert "O and more" in remaining
    handle.close()


# ---------------------------------------------------------------------------
# R8: the target's own underline (removed) at tight leading
# ---------------------------------------------------------------------------


def test_delete_block_removes_its_own_underline_at_tight_leading():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 87), "above line gyp", fontsize=12)
    p.insert_text((72, 100), "underlined target", fontsize=12)
    x1 = p.get_text("dict")["blocks"][-1]["lines"][0]["spans"][0]["bbox"][2]
    p.draw_line(fitz.Point(72, 101.5), fitz.Point(x1, 101.5), width=0.6)
    p.insert_text((72, 113), "below line gyp", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="underlined")
    delete_block(handle, 0, target)

    page = handle[0]
    remaining = page.get_text()
    assert "above line" in remaining and "below line" in remaining
    assert "underlined" not in remaining and "target" not in remaining
    # The underline, entirely inside the target's own (unclipped) bbox
    # band, must be gone too -- not orphaned by the clip.
    assert stroke_lines_remaining(page) == []


# ---------------------------------------------------------------------------
# R3: the floor refusal, pinned with fingerprint() and a mutator spy
# ---------------------------------------------------------------------------


def test_delete_block_refuses_before_mutation_when_lines_overlap_past_the_floor():
    d = fitz.open()
    p = d.new_page()
    # pitch 9.2: kept = 11.6% of the target's own height -- positive (not
    # an inverted rect, which _n2_clip's own degenerate-rect guard would
    # also catch, masking a mutation that removes R3's own floor check).
    p.insert_text((72, 100), "LINE0 too close gyp", fontsize=12)
    p.insert_text((72, 109.2), "TARGET too close gyp", fontsize=12)
    p.insert_text((72, 118.4), "LINE2 too close gyp", fontsize=12)

    pdf = d.tobytes()
    doc, handle = parse(pdf)
    page = handle[0]
    target = target_block(doc)

    before = fingerprint(handle)

    mutator_calls = []
    real = fitz.Page.add_redact_annot

    def spy(self, *a, **k):
        mutator_calls.append((a, k))
        return real(self, *a, **k)

    import unittest.mock as mock

    with mock.patch.object(fitz.Page, "add_redact_annot", spy):
        with pytest.raises(RefusedBeforeMutation):
            delete_block(handle, 0, target)

    assert mutator_calls == [], f"mutator was called before the refusal: {mutator_calls}"
    assert fingerprint(handle) == before, "document changed despite the refusal"


# ---------------------------------------------------------------------------
# R4: vertical text refused when its band overlaps another line's span
# ---------------------------------------------------------------------------


def test_delete_block_refuses_rotated_text_whose_band_overlaps_a_neighbour():
    d = fitz.open()
    p = d.new_page()
    for i, prefix in enumerate(("LINE0", "TARGET", "LINE2")):
        p.insert_text((200 + i * 13, 400), f"{prefix} rotated text gyp", fontsize=12, rotate=90)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    assert target.direction is not None
    before = fingerprint(handle)

    with pytest.raises(RefusedBeforeMutation):
        delete_block(handle, 0, target)

    assert fingerprint(handle) == before


def test_delete_block_allows_rotated_text_once_spaced_apart():
    d = fitz.open()
    p = d.new_page()
    for i, prefix in enumerate(("LINE0", "TARGET", "LINE2")):
        p.insert_text((200 + i * 20, 400), f"{prefix} rotated text gyp", fontsize=12, rotate=90)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    delete_block(handle, 0, target)

    remaining = handle[0].get_text()
    assert "LINE0" in remaining and "LINE2" in remaining
    assert "TARGET" not in remaining


# ---------------------------------------------------------------------------
# R5: a Type3 target keeps today's full rect
# ---------------------------------------------------------------------------


def _type3_fixture():
    """One glyph 'square' in a Type3 font, FontMatrix 0.001 -- the same
    construction as tests/test_replace_widen.py's own _type3_fixture (not
    imported from there: this file's fixtures are self-contained, per this
    plan's instructions)."""
    d = fitz.open()
    p = d.new_page()
    charproc = d.get_new_xref()
    d.update_object(charproc, "<<>>")
    d.update_stream(charproc, b"600 0 0 0 600 700 d1 0 0 600 700 re f")
    t3 = d.get_new_xref()
    d.update_object(
        t3,
        "<< /Type /Font /Subtype /Type3 /FontBBox [0 0 600 700] "
        "/FontMatrix [0.001 0 0 0.001 0 0] "
        f"/CharProcs << /square {charproc} 0 R >> "
        "/Encoding << /Type /Encoding /Differences [97 /square] >> "
        "/FirstChar 97 /LastChar 97 /Widths [600] /Resources << >> >>",
    )
    d.xref_set_key(p.xref, "Resources", f"<< /Font << /T3 {t3} 0 R >> >>")
    c = d.get_new_xref()
    d.update_object(c, "<<>>")
    # A real horizontal text line, tight below the Type3 glyph (whose own
    # bbox reaches down to about y=691.6) -- so R5's exception is the ONLY
    # thing stopping a clip here; without it, this neighbour's bbox
    # overlaps the (mis-measured, for Type3) erase band and would be
    # clipped against.
    d.update_stream(
        c,
        b"BT /T3 12 Tf 72 700 Td (aaa) Tj ET "
        b"BT /Helv 12 Tf 72 693 Td (BELOW gyp) Tj ET",
    )
    d.xref_set_key(p.xref, "Contents", f"{c} 0 R")
    d.xref_set_key(
        p.xref, "Resources",
        f"<< /Font << /T3 {t3} 0 R /Helv << /Type /Font /Subtype /Type1 "
        f"/BaseFont /Helvetica >> >> >>",
    )
    return d.tobytes()


def test_type3_target_keeps_the_full_rect_and_still_erases():
    doc, handle = parse(_type3_fixture())
    target = doc.pages[0].text_blocks[0]
    page = handle[0]
    rect = fitz.Rect(target.bbox)

    clipped = _n1_clip(page, rect, target)
    assert clipped == rect, "R5: a Type3 target must keep today's full rect"

    delete_block(handle, 0, target)
    # R5 is a stated limitation (R12): a Type3 target keeps the full,
    # unclipped rect, so it does NOT get neighbour protection the way a
    # real-glyph target would -- the assertion here is only that the
    # Type3 glyph itself is gone, not that "BELOW gyp" survives whole.
    assert "☐" not in handle[0].get_text() and "aaa" not in handle[0].get_text()


# ---------------------------------------------------------------------------
# Task 2 (R6, R7): layout rules and the bleed margin
# ---------------------------------------------------------------------------


def _owners_form(value_size, value_y=100):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "Student Name:", fontsize=12)
    p.draw_rect(fitz.Rect(160, 86, 400, 106), width=0.8)
    p.insert_text((164, value_y), "Jo Lee", fontsize=value_size)
    return d.tobytes()


def _border_pixel_diff(before_pdf, after_page, border_rect):
    """Pixels changed inside `border_rect` between the pre-erase page and
    the live (post-erase) page -- the border-unbroken pixel diff the plan
    asks for."""
    before_doc = fitz.open(stream=before_pdf, filetype="pdf")
    try:
        before_pix = before_doc[0].get_pixmap(
            matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=border_rect
        )
        after_pix = after_page.get_pixmap(
            matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=border_rect
        )
        a, b = before_pix.samples, after_pix.samples
        return sum(1 for x, y in zip(a, b) if x < 128 and y >= 128)
    finally:
        before_doc.close()


@pytest.mark.parametrize("value_size", [14, 18])
def test_delete_block_leaves_the_forms_border_unbroken(value_size):
    pdf = _owners_form(value_size)
    doc, handle = parse(pdf)
    target = target_block(doc, prefix="Jo")
    delete_block(handle, 0, target)

    page = handle[0]
    # The border stroke's own band, top and bottom -- a pixel diff against
    # the pre-erase page over just the border's rows.
    top_border = fitz.Rect(160, 85, 400, 87)
    bottom_border = fitz.Rect(160, 105, 400, 107)
    assert _border_pixel_diff(pdf, page, top_border) == 0, "top border damaged"
    assert _border_pixel_diff(pdf, page, bottom_border) == 0, "bottom border damaged"
    assert "Jo Lee" not in page.get_text()


def test_delete_block_leaves_a_bordered_table_row_unbroken():
    d = fitz.open()
    p = d.new_page()
    for r in range(4):
        y = 100 + r * 13
        for c, x in enumerate((72, 200, 330)):
            label = "TARGET" if (r == 1 and c == 1) else f"r{r}c{c}"
            p.insert_text((x + 3, y), f"{label} cell gyp", fontsize=10)
        p.draw_line(fitz.Point(70, y - 10.5), fitz.Point(460, y - 10.5), width=0.5)
    p.draw_line(fitz.Point(70, 100 + 3 * 13 + 2.5), fitz.Point(460, 100 + 3 * 13 + 2.5), width=0.5)
    for x in (70, 198, 328, 460):
        p.draw_line(fitz.Point(x, 89.5), fitz.Point(x, 141.5), width=0.5)
    pdf = d.tobytes()

    doc, handle = parse(pdf)
    target = target_block(doc)
    delete_block(handle, 0, target)

    page = handle[0]
    # Checked away from the target's own column (x 72-198, the target sits
    # in the middle column, x 200-330): a window there catches genuine
    # border damage without also catching the target's own descenders
    # ('g'/'y'/'p' in "TARGET cell gyp") being correctly removed WHOLE
    # (spec E3) even where their antialiasing reaches into this row.
    row_top = fitz.Rect(70, 102, 198, 103)
    row_bottom = fitz.Rect(70, 115, 198, 116)
    assert _border_pixel_diff(pdf, page, row_top) == 0, "row top rule damaged"
    assert _border_pixel_diff(pdf, page, row_bottom) == 0, "row bottom rule damaged"
    remaining = page.get_text()
    assert "r0c0" in remaining and "r3c2" in remaining
    assert "TARGET" not in remaining


def test_a_rule_crossing_the_ink_zone_keeps_todays_behaviour():
    """A strike-through through the middle of the target's own ink (not
    above its cap or below its descender) must NOT be treated as a layout
    obstacle -- it keeps today's behaviour: removed along with the target,
    the rect is not clipped because of it."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "struck target", fontsize=12)
    x1 = p.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["bbox"][2]
    # baseline - 4: inside the ink band. Starts 1pt right of the target's
    # own bbox.x0 -- exactly AT it is a separate, pre-existing PyMuPDF
    # containment quirk (apply_redactions(graphics=1)'s "contained" test
    # does not count a drawing edge-flush with the redact rect's own edge;
    # see _erase_text_block's R8 comment), not what this test is about.
    p.draw_line(fitz.Point(73, 96), fitz.Point(x1 - 1, 96), width=0.8)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="struck")
    page = handle[0]
    rect = fitz.Rect(target.bbox)
    clipped = _n2_clip(page, rect, target)
    assert clipped == rect, "a rule crossing the ink zone must not clip the rect"

    delete_block(handle, 0, target)
    page = handle[0]
    assert page.get_text().strip() == ""
    assert stroke_lines_remaining(page) == []


# ---------------------------------------------------------------------------
# Task 3 (R9): image-backed (scanned) targets
# ---------------------------------------------------------------------------

_SCAN_LINES = [
    "ABOVE line with gyp descenders",
    "TARGET line with gyp descenders",
    "BELOW line with gyp descenders",
    "FOURTH line gyp",
]


def _make_synthetic_scan(pitch=13):
    src = fitz.open()
    sp = src.new_page(width=300, height=120)
    for i, text in enumerate(_SCAN_LINES):
        sp.insert_text((10, 30 + i * pitch), text, fontsize=12)
    pix = sp.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace="gray")
    d = fitz.open()
    p = d.new_page(width=300, height=120)
    p.insert_image(p.rect, pixmap=pix)
    # invisible OCR layer at the same positions
    for i, text in enumerate(_SCAN_LINES):
        p.insert_text((10, 30 + i * pitch), text, fontsize=12, render_mode=3)
    return d.tobytes()


def test_delete_block_on_a_scan_keeps_every_ocr_word_and_blanks_the_targets_ink():
    pdf = _make_synthetic_scan()
    doc, handle = parse(pdf)
    target = target_block(doc)
    page = handle[0]

    before_words = sorted(w[4] for w in page.get_text("words"))
    other_words = [w for w in before_words if w not in ("TARGET", "line", "with", "gyp", "descenders")]
    # sanity: there really are neighbour-only words to lose
    assert "ABOVE" in before_words and "BELOW" in before_words and "FOURTH" in before_words

    delete_block(handle, 0, target)
    page = handle[0]
    after_words = sorted(w[4] for w in page.get_text("words"))

    missing_neighbours = [w for w in ("ABOVE", "BELOW", "FOURTH") if w not in after_words]
    assert not missing_neighbours, f"neighbour OCR word(s) lost: {missing_neighbours}"
    assert "TARGET" not in after_words

    target_rect = fitz.Rect(target.bbox)
    ink_left = sum(
        1 for v in page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace="gray", clip=target_rect).samples
        if v < 128
    )
    assert ink_left == 0, f"{ink_left} dark pixel(s) of the target's own ink remain"
