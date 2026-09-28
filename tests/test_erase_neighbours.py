"""Tests for plan docs/superpowers/plans/2026-09-28-erase-neighbours.md
(spec docs/superpowers/specs/2026-09-28-erase-neighbours-design.md, REVISION
section R1-R12 binding), plus fix round 1 findings F1-F9.

Fixtures and the ideal-page oracle are built inline here, adapted from the
critic's executed probes
(docs/superpowers/records/2026-09-28-erase-neighbours/probes/critique/
harness.py, n1_layouts.py, n1_sameline.py, n2_form.py, n2_bleed.py,
n3_scan.py, extras.py) and the fix-round-1 reviewer's own probes
(revh.py, p1_layouts.py-p6_more.py) -- never imported from either
directory.

F4: every output assertion checks the EXPORTED bytes (export(handle) or
handle.tobytes(), re-opened as a fresh fitz.Document), never the live
in-memory handle -- export() runs its own garbage collection and full
rewrite, and is what every real caller actually reads back.
"""
import dataclasses
import unittest.mock as mock

import pymupdf as fitz
import pytest

from engine.document import TextBlock
from engine.errors import RefusedBeforeMutation
from engine.export import export
from engine.operations import (
    _erase_text_block,
    _n1_clip,
    _n2_clip,
    _n2_ink_band,
    delete_block,
    move_block,
    replace_text,
)
from engine.parser import parse
from tests.test_page_geometry import fingerprint

ZOOM = 3


# ---------------------------------------------------------------------------
# F4: export-and-reopen helpers. Every test below reads the EXPORTED bytes,
# never handle[0]/handle.tobytes() directly against the live handle.
# ---------------------------------------------------------------------------


def exported_page(handle, page=0):
    """export(handle), re-opened as a fresh fitz.Document -- the page
    every real caller would actually read back."""
    data = export(handle)
    doc = fitz.open(stream=data, filetype="pdf")
    return doc, doc[page]


def exported_text(handle, page=0):
    doc, p = exported_page(handle, page)
    try:
        return p.get_text()
    finally:
        doc.close()


def exported_words(handle, page=0):
    doc, p = exported_page(handle, page)
    try:
        return sorted(w[4] for w in p.get_text("words"))
    finally:
        doc.close()


def exported_drawings(handle, page=0):
    doc, p = exported_page(handle, page)
    try:
        return p.get_drawings()
    finally:
        doc.close()


def exported_pixmap(handle, clip=None, page=0, zoom=ZOOM):
    doc, p = exported_page(handle, page)
    try:
        return p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace="gray", clip=clip)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# The ideal-page oracle (harness.py, adapted): build a page from a list of
# text lines, one erase mutator, and compare the mutated page against the
# same page built WITHOUT the target line, in both exported words and
# pixels.
# ---------------------------------------------------------------------------


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


def render_clip(pdf_bytes, clip, zoom=ZOOM):
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return d[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace="gray", clip=clip)
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


def stroke_lines_remaining(drawings):
    """The page's own drawn lines/strokes (type 's') -- excludes the
    erase's own painted fill rectangle ('fs'), which get_drawings() also
    reports."""
    return [dr for dr in drawings if dr.get("type") == "s"]


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

    after_words = exported_words(handle)
    missing = [w for w in ideal_words if w not in after_words]
    assert not missing, (
        f"neighbour word(s) lost (pitch={pitch} position={position} op={op}): {missing}"
    )

    after_pix = exported_pixmap(handle, clip=clip)
    leftover, damage = pix_diff(after_pix, ideal_pix)
    assert damage == 0, (
        f"{damage} neighbour pixel(s) damaged (pitch={pitch} position={position} op={op})"
    )
    # F4: leftover==0 (none of the TARGET's own ink remains) for delete and
    # move, whose ideal page has no replacement ink at the target's old
    # position at all. replace_widen/replace_box draw "X" there instead,
    # so a leftover check for those would only be checking "X" was drawn,
    # not this plan's own contract -- skipped for those two, on purpose.
    if op in ("delete", "move"):
        assert leftover == 0, (
            f"{leftover} of the target's own pixel(s) left behind "
            f"(pitch={pitch} position={position} op={op})"
        )
    handle.close()


# ---------------------------------------------------------------------------
# F1 (fix round 1): R4 must not be bypassed on a hand-built block (the box
# path strips origin/direction) -- _matching_span must recover direction
# from the matched span's own enclosing LINE (a span dict has no "dir" key
# on PyMuPDF 1.28.2; only the line dict does).
# ---------------------------------------------------------------------------


def _rotated_overlap_fixture():
    d = fitz.open()
    p = d.new_page()
    for i, prefix in enumerate(("LINE0", "TARGET", "LINE2")):
        p.insert_text((200 + i * 13, 400), f"{prefix} rotated text gyp", fontsize=12, rotate=90)
    return d.tobytes()


@pytest.mark.parametrize("op", OPERATIONS)
def test_r4_is_not_bypassed_on_a_hand_built_block_at_any_site(op):
    pdf = _rotated_overlap_fixture()
    doc, handle = parse(pdf)
    target = target_block(doc)
    # The box path (and a fully hand-built caller) strips origin/direction
    # -- R4 must still be recovered via the matching page span's own line.
    stripped = dataclasses.replace(target, origin=None, direction=None)
    before = fingerprint(handle)

    with pytest.raises(RefusedBeforeMutation):
        _apply_operation(handle, op, stripped)

    assert fingerprint(handle) == before, f"document changed despite the refusal ({op})"
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
    remaining = exported_text(handle)
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
    remaining = exported_text(handle)
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

    remaining = exported_text(handle)
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

    remaining = exported_text(handle)
    assert "TARGET" not in remaining
    assert "ABOVE" in remaining and "BELOW" in remaining
    assert "2" in remaining  # the neighbour's own subscript survives
    assert "O and more" in remaining
    handle.close()


# ---------------------------------------------------------------------------
# R8: the target's own underline (removed) at tight leading; F3 (fix round
# 1): a NEIGHBOUR's own underline near the target's rect edge must survive.
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

    remaining = exported_text(handle)
    assert "above line" in remaining and "below line" in remaining
    assert "underlined" not in remaining and "target" not in remaining
    # The underline, entirely inside the target's own ink band, must be
    # gone too -- not orphaned by the clip.
    assert stroke_lines_remaining(exported_drawings(handle)) == []
    handle.close()


@pytest.mark.parametrize("pitch", [14.4, 14.6])
def test_r8_does_not_reach_a_neighbours_underline_at_normal_leading(pitch):
    """F3 (fix round 1): the reviewer measured the earlier round's R8 pass
    -- which searched the FULL, unclipped rect, not bounded to the
    target's own ink band -- removing the line ABOVE's own underline at
    ordinary leading (1.2-1.22), well outside anything N1 itself judged
    close enough to even narrow the rect for. R8 must be bounded to the
    target's own ink band, never the neighbour's."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "above underlined gyp", fontsize=12)
    p.draw_line(fitz.Point(72, 101.5), fitz.Point(140, 101.5), width=0.6)
    p.insert_text((72, 100 + pitch), "TARGET line of text gyp", fontsize=12)
    p.insert_text((72, 100 + 2 * pitch), "below line gyp", fontsize=12)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    delete_block(handle, 0, target)

    left = stroke_lines_remaining(exported_drawings(handle))
    assert left, f"the neighbour-above's underline was removed at pitch {pitch}"
    remaining = exported_text(handle)
    assert "above" in remaining and "underlined" in remaining
    assert "TARGET" not in remaining
    handle.close()


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
    target = target_block(doc)

    before = fingerprint(handle)

    mutator_calls = []
    real = fitz.Page.add_redact_annot

    def spy(self, *a, **k):
        mutator_calls.append((a, k))
        return real(self, *a, **k)

    with mock.patch.object(fitz.Page, "add_redact_annot", spy):
        with pytest.raises(RefusedBeforeMutation):
            delete_block(handle, 0, target)

    assert mutator_calls == [], f"mutator was called before the refusal: {mutator_calls}"
    assert fingerprint(handle) == before, "document changed despite the refusal"


# ---------------------------------------------------------------------------
# R4: vertical text refused when its band overlaps another line's span
# ---------------------------------------------------------------------------


def test_delete_block_refuses_rotated_text_whose_band_overlaps_a_neighbour():
    pdf = _rotated_overlap_fixture()
    doc, handle = parse(pdf)
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

    remaining = exported_text(handle)
    assert "LINE0" in remaining and "LINE2" in remaining
    assert "TARGET" not in remaining
    handle.close()


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
    remaining = exported_text(handle)
    assert "☐" not in remaining and "aaa" not in remaining
    handle.close()


# ---------------------------------------------------------------------------
# Task 2 (R6, R7): layout rules and the bleed margin. F7 (fix round 1): the
# margin is re-measured and pinned at ZOOM 4 (not 3).
# ---------------------------------------------------------------------------

Z4 = 4


def _owners_form(value_size, value_y=100):
    # F7 (fix round 1): "TARGET Lee", matching the reviewer's own probe
    # text exactly -- the pinned 0/0 (14pt) and 14/0 (18pt) pixel counts
    # are specific to this glyph shape/extent, not "Jo Lee"'s.
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "Student Name:", fontsize=12)
    p.draw_rect(fitz.Rect(160, 86, 400, 106), width=0.8)
    p.insert_text((164, value_y), "TARGET Lee", fontsize=value_size)
    return d.tobytes()


def _border_pixel_diff(before_pdf, handle, border_rect, zoom=Z4):
    """Pixels changed inside `border_rect` between the pre-erase page and
    the EXPORTED, re-opened post-erase page -- the border-unbroken pixel
    diff the plan asks for, pinned at zoom 4 (F7): a 0.5pt margin alone
    reads as 0px damaged at zoom 3 but hundreds of px at zoom 4."""
    before_doc = fitz.open(stream=before_pdf, filetype="pdf")
    after_doc, after_page = exported_page(handle)
    try:
        before_pix = before_doc[0].get_pixmap(
            matrix=fitz.Matrix(zoom, zoom), colorspace="gray", clip=border_rect
        )
        after_pix = after_page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom), colorspace="gray", clip=border_rect
        )
        a, b = before_pix.samples, after_pix.samples
        return sum(1 for x, y in zip(a, b) if x < 128 and y >= 128)
    finally:
        before_doc.close()
        after_doc.close()


@pytest.mark.parametrize(
    "value_size, expect_top, expect_bottom",
    [(14, 0, 0), (18, 14, 0)],
)
def test_delete_block_leaves_the_forms_border_unbroken_at_zoom4(value_size, expect_top, expect_bottom):
    """F7: pinned at the reviewer's own measured values with the 1.0pt
    margin -- 0/0 at 14pt, 14/0 at 18pt (the residual 14px at 18pt is a
    known, accepted rounding remainder at zoom 4, not chased further)."""
    pdf = _owners_form(value_size)
    doc, handle = parse(pdf)
    target = target_block(doc, prefix="TARGET")
    delete_block(handle, 0, target)

    top_border = fitz.Rect(160, 85, 400, 87)
    bottom_border = fitz.Rect(160, 105, 400, 107)
    top_damage = _border_pixel_diff(pdf, handle, top_border)
    bottom_damage = _border_pixel_diff(pdf, handle, bottom_border)
    assert top_damage == expect_top, f"top border damaged: {top_damage}"
    assert bottom_damage == expect_bottom, f"bottom border damaged: {bottom_damage}"
    assert "TARGET" not in exported_text(handle)
    handle.close()


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

    # Checked away from the target's own column (x 72-198, the target sits
    # in the middle column, x 200-330): a window there catches genuine
    # border damage without also catching the target's own descenders
    # ('g'/'y'/'p' in "TARGET cell gyp") being correctly removed WHOLE
    # (spec E3) even where their antialiasing reaches into this row.
    row_top = fitz.Rect(70, 102, 198, 103)
    row_bottom = fitz.Rect(70, 115, 198, 116)
    assert _border_pixel_diff(pdf, handle, row_top, zoom=ZOOM) == 0, "row top rule damaged"
    assert _border_pixel_diff(pdf, handle, row_bottom, zoom=ZOOM) == 0, "row bottom rule damaged"
    remaining = exported_text(handle)
    assert "r0c0" in remaining and "r3c2" in remaining
    assert "TARGET" not in remaining
    handle.close()


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
    # own bbox.x0 and stops 1pt short of its x1: a stroke's own half-width
    # (F8, fix round 1) can reach a whisker past its nominal path
    # coordinate, and this test is about the ink-zone rule, not that.
    p.draw_line(fitz.Point(73, 96), fitz.Point(x1 - 1, 96), width=0.8)

    doc, handle = parse(d.tobytes())
    target = target_block(doc, prefix="struck")
    page = handle[0]
    rect = fitz.Rect(target.bbox)
    clipped = _n2_clip(page, rect, target)
    assert clipped == rect, "a rule crossing the ink zone must not clip the rect"

    delete_block(handle, 0, target)
    assert exported_text(handle).strip() == ""
    assert stroke_lines_remaining(exported_drawings(handle)) == []
    handle.close()


# ---------------------------------------------------------------------------
# F9 (fix round 1): N2's "starts left of the target" test must also
# require the rule to actually REACH the target, and its obstacle search
# must use a fixed, meaningful proximity bound.
# ---------------------------------------------------------------------------


def _isolated_target(x=300, y=100, text="TARGET text", size=12):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((x, y), text, fontsize=size)
    return d, p


def test_n2_ignores_a_rule_ending_well_left_of_the_target():
    d, p = _isolated_target()
    tb = fitz.Rect(p.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["bbox"])
    p.draw_line(fitz.Point(72, tb.y0 + 0.2), fitz.Point(tb.x0 - 100, tb.y0 + 0.2), width=0.5)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    page = handle[0]
    clipped = _n2_clip(page, fitz.Rect(target.bbox), target)
    assert clipped == fitz.Rect(target.bbox), (
        f"a rule ending 100pt left of the target (never reaching it) must not clip, got {clipped}"
    )


def test_n2_ignores_a_rule_3pt_beyond_the_proximity_bound():
    d, p = _isolated_target()
    tb = fitz.Rect(p.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["bbox"])
    # 3pt above the bbox top -- AT the fixed proximity bound, so it must
    # not count (the bound is exclusive).
    p.draw_line(fitz.Point(72, tb.y0 - 3), fitz.Point(500, tb.y0 - 3), width=0.4)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    page = handle[0]
    clipped = _n2_clip(page, fitz.Rect(target.bbox), target)
    assert clipped == fitz.Rect(target.bbox), (
        f"a rule exactly at the 3pt proximity bound must not clip, got {clipped}"
    )


def test_n2_still_clips_a_rule_within_the_proximity_bound():
    """Demonstrates the bound is not dead (M3): a rule whose stroke's own
    near edge sits 0.8pt above the bbox top DOES clip (its own stopping
    point, stroke edge + margin, still reaches past the bbox's own edge)
    with the real 3pt bound, but does NOT with a 0.5pt bound --
    distinguishing the two, unlike a rule right at the far edge of either
    bound (see the two tests above), which never actually moves y0
    regardless of the bound's value, because its own margin-adjusted
    stopping point never reaches back past the bbox's own edge."""
    d, p = _isolated_target()
    tb = fitz.Rect(p.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["bbox"])
    # nominal offset 1.0pt, half the 0.4pt stroke width (0.2pt) closer --
    # the stroke's own near edge sits 0.8pt above tb.y0.
    p.draw_line(fitz.Point(72, tb.y0 - 1.0), fitz.Point(500, tb.y0 - 1.0), width=0.4)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    page = handle[0]
    clipped = _n2_clip(page, fitz.Rect(target.bbox), target)
    assert clipped != fitz.Rect(target.bbox), "a rule 0.8pt above the bbox top must clip"

    with mock.patch("engine.operations._N2_PROXIMITY_PT", 0.5):
        doc2, handle2 = parse(d.tobytes())
        target2 = target_block(doc2)
        page2 = handle2[0]
        unmoved = _n2_clip(page2, fitz.Rect(target2.bbox), target2)
    assert unmoved == fitz.Rect(target2.bbox), (
        "with a 0.5pt bound the same rule (0.8pt away) must NOT clip -- "
        "the bound is meaningful, not dead"
    )


# ---------------------------------------------------------------------------
# F2 (fix round 1): _n2_ink_band's glyph_bbox call takes a codepoint, not a
# glyph id -- pin the resulting band shape.
# ---------------------------------------------------------------------------


def test_ink_band_has_no_descender_for_text_without_descenders():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "TEA SET", fontsize=12)
    doc, _ = parse(d.tobytes())
    t = doc.pages[0].text_blocks[0]
    _, ink_bottom = _n2_ink_band(t, 100)
    # No lowercase descenders ('g', 'j', 'p', 'q', 'y') anywhere in the
    # text -- the band's own bottom must sit at or very near the baseline,
    # not the 0.25*size fallback (3pt at this size).
    assert ink_bottom - 100 < 1.0, f"ink bottom {ink_bottom} implies a descender that is not there"


def test_ink_band_descender_for_g_reaches_below_the_baseline():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "sag", fontsize=12)
    doc, _ = parse(d.tobytes())
    t = doc.pages[0].text_blocks[0]
    _, ink_bottom = _n2_ink_band(t, 100)
    # 'g' has a real descender -- measured (fix round 1, F2's own probe)
    # at ~0.22*size below the baseline for Helvetica, comfortably over 1pt
    # at 12pt; the gid-indexed bug reported 0.0 (no descender at all).
    assert ink_bottom - 100 > 1.5, f"ink bottom {ink_bottom} does not reach 'g's real descender"


def test_ink_band_cap_height_for_e_acute_reaches_above_plain_cap_height():
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "École", fontsize=12)
    doc, _ = parse(d.tobytes())
    t_accented = doc.pages[0].text_blocks[0]
    ink_top_accented, _ = _n2_ink_band(t_accented, 100)

    d2 = fitz.open()
    p2 = d2.new_page()
    p2.insert_text((72, 100), "Ecole", fontsize=12)
    doc2, _ = parse(d2.tobytes())
    t_plain = doc2.pages[0].text_blocks[0]
    ink_top_plain, _ = _n2_ink_band(t_plain, 100)

    # "cap above" is baseline - ink_top: 'É' (with its acute accent) must
    # reach further above the baseline than plain 'E'.
    assert (100 - ink_top_accented) > (100 - ink_top_plain), (
        f"'École' cap-above {100 - ink_top_accented} does not exceed plain 'Ecole' {100 - ink_top_plain}"
    )


# ---------------------------------------------------------------------------
# F5 (fix round 1): at tight leading with REAL embedded fonts, N1's edges
# must be inset by the redaction fill's own bleed, or a neighbour's
# descender/cap antialiasing is shaved.
# ---------------------------------------------------------------------------

_LIBERATION_SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_DEJAVU_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _real_font_paragraph_pdf(fontfile, fontname, pitch, omit_index=None):
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname=fontname, fontfile=fontfile)
    for i in range(5):
        if omit_index is not None and i == omit_index:
            continue
        text = ("TARGET" if i == 2 else f"LINE{i}") + " quick gyp " + str(i)
        p.insert_text((72, 100 + i * pitch), text, fontsize=12, fontname=fontname)
    return d.tobytes()


@pytest.mark.parametrize(
    "fontfile, fontname, expect_damage",
    [
        pytest.param(_LIBERATION_SANS, "lib", 0, id="liberation-1.0"),
        pytest.param(_DEJAVU_SANS, "dej", 0, id="dejavu-1.0"),
    ],
)
@pytest.mark.skipif(
    not __import__("os").path.exists(_LIBERATION_SANS) or not __import__("os").path.exists(_DEJAVU_SANS),
    reason="LiberationSans/DejaVu TTFs not present on this system "
           "(Debian/Ubuntu fonts-liberation and fonts-dejavu-core packages)",
)
def test_delete_block_real_font_leading_1_0_no_neighbour_damage(fontfile, fontname, expect_damage):
    pitch = 12 * 1.0
    pdf = _real_font_paragraph_pdf(fontfile, fontname, pitch)
    ideal = _real_font_paragraph_pdf(fontfile, fontname, pitch, omit_index=2)
    doc, handle = parse(pdf)
    target = target_block(doc)
    delete_block(handle, 0, target)

    clip = fitz.Rect(0, 100 - 20, 612, 100 + 4 * pitch + 20)
    after = exported_pixmap(handle, clip=clip, zoom=4)
    ideal_pix = render_clip(ideal, clip, zoom=4)
    _leftover, damage = pix_diff(after, ideal_pix)
    assert damage == expect_damage, f"{damage} neighbour pixel(s) damaged ({fontname}, leading 1.0)"
    handle.close()


@pytest.mark.parametrize(
    "fontfile, fontname, expect_damage",
    [
        # F5 fix measured: LiberationSans leaves exactly one borderline
        # (128-vs-120 grey level, i.e. AT the pix_diff threshold) pixel at
        # leading 1.15 even after the bleed inset -- pinned explicitly
        # rather than chased further, the same way F7 pins 18pt's own
        # residual 14px rather than asserting a blanket 0.
        pytest.param(_LIBERATION_SANS, "lib", 1, id="liberation-1.15"),
        pytest.param(_DEJAVU_SANS, "dej", 0, id="dejavu-1.15"),
    ],
)
@pytest.mark.skipif(
    not __import__("os").path.exists(_LIBERATION_SANS) or not __import__("os").path.exists(_DEJAVU_SANS),
    reason="LiberationSans/DejaVu TTFs not present on this system "
           "(Debian/Ubuntu fonts-liberation and fonts-dejavu-core packages)",
)
def test_delete_block_real_font_leading_1_15_no_neighbour_damage(fontfile, fontname, expect_damage):
    pitch = 12 * 1.15
    pdf = _real_font_paragraph_pdf(fontfile, fontname, pitch)
    ideal = _real_font_paragraph_pdf(fontfile, fontname, pitch, omit_index=2)
    doc, handle = parse(pdf)
    target = target_block(doc)
    delete_block(handle, 0, target)

    clip = fitz.Rect(0, 100 - 20, 612, 100 + 4 * pitch + 20)
    after = exported_pixmap(handle, clip=clip, zoom=4)
    ideal_pix = render_clip(ideal, clip, zoom=4)
    _leftover, damage = pix_diff(after, ideal_pix)
    assert damage == expect_damage, f"{damage} neighbour pixel(s) damaged ({fontname}, leading 1.15)"
    handle.close()


# ---------------------------------------------------------------------------
# Task 3 (R9): image-backed (scanned) targets. F6 (fix round 1): the
# target's own drawing (an underline) must actually be REMOVED, not merely
# painted over, even with no tight neighbour.
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
    # sanity: there really are neighbour-only words to lose
    assert "ABOVE" in before_words and "BELOW" in before_words and "FOURTH" in before_words

    delete_block(handle, 0, target)
    after_words = exported_words(handle)

    missing_neighbours = [w for w in ("ABOVE", "BELOW", "FOURTH") if w not in after_words]
    assert not missing_neighbours, f"neighbour OCR word(s) lost: {missing_neighbours}"
    assert "TARGET" not in after_words

    target_rect = fitz.Rect(target.bbox)
    ink_left = sum(1 for v in exported_pixmap(handle, clip=target_rect).samples if v < 128)
    assert ink_left == 0, f"{ink_left} dark pixel(s) of the target's own ink remain"
    handle.close()


def test_delete_block_on_image_backed_page_removes_its_own_underline():
    """F6: an image-backed target with its OWN underline (a drawing) and
    NO tight neighbour -- N3's pass 2 must set graphics=1, or the
    underline is left physically in the file, merely painted over."""
    d = fitz.open()
    p = d.new_page(width=300, height=120)
    src = fitz.open()
    sp = src.new_page(width=300, height=120)
    sp.insert_text((10, 60), "TARGET scanned word", fontsize=12)
    pix = sp.get_pixmap(matrix=fitz.Matrix(4, 4), colorspace="gray")
    p.insert_image(p.rect, pixmap=pix)
    p.insert_text((10, 60), "TARGET scanned word", fontsize=12, render_mode=3)
    bb = [s["bbox"] for b in p.get_text("dict")["blocks"] if b.get("type") == 0
          for l in b["lines"] for s in l["spans"]][0]
    p.draw_line(fitz.Point(bb[0] + 0.5, 61.5), fitz.Point(bb[2] - 0.5, 61.5), width=0.6)

    doc, handle = parse(d.tobytes())
    target = target_block(doc)
    delete_block(handle, 0, target)

    drawings = exported_drawings(handle)
    assert stroke_lines_remaining(drawings) == [], (
        f"the target's own underline is still in the file: {drawings}"
    )
    assert "TARGET" not in exported_words(handle)
    handle.close()
