"""Tests for the replace_text widen-before-shrink work (plan
docs/superpowers/plans/2026-09-28-replace-text-widen.md; spec
docs/superpowers/specs/2026-09-28-replace-text-widen-design.md, REVISION
section binding).

Fixtures are built inline from the critic's executed probes
(docs/superpowers/records/2026-09-28-replace-text-widen/probes/critique/
probe_w7.py, probe_w2.py, probe_w4.py, scenarios.py) -- never imported from
that directory.
"""
import dataclasses
from unittest.mock import MagicMock, patch

import pymupdf as fitz
import pytest

from engine.document import TextBlock
from engine.errors import RefusedBeforeMutation
from engine.export import export
from engine.operations import (
    _BASELINE_SANITY_TOLERANCE_PT,
    _direction_is_near_horizontal,
    _LINE_BREAK_RE,
    _origin_is_reliable,
    _right_limit,
    _sample_background_color,
    _span_metrics,
    _WIDTH_PRECISION_PAD_PT,
    delete_block,
    replace_text,
)
from engine.parser import parse
from tests.geometry_helpers import ROTATIONS, build_page
from tests.test_page_geometry import fingerprint


def _span_of(page: fitz.Page, text: str) -> dict:
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"] == text:
                    return span
    raise KeyError(f"no span with text {text!r} on this page")


def _limit_for(page: fitz.Page, text: str) -> float:
    span = _span_of(page, text)
    return _right_limit(page, tuple(span["bbox"]), span["origin"][1], span["size"])


# ---------------------------------------------------------------------------
# Task 1: C21, off-canvas background samples (W7, R14)
# ---------------------------------------------------------------------------


def _page_frame_fixture(bg_fill=None):
    """The critic's probe_w7.py case 7/8 fixture: a 300x200 page with a
    printed frame (1.5pt black bar along the top, 1.5pt black bar along the
    right edge) and "Wide value" at (285, 12), 12pt helv. The old sampler's
    clamped top/right samples land on the frame's black ink; the true
    background (white, or bg_fill) is only visible on-canvas at the left and
    bottom samples.
    """
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    if bg_fill is not None:
        page.draw_rect(page.rect, color=None, fill=bg_fill)
    page.draw_rect(fitz.Rect(0, 0, 300, 1.5), color=None, fill=(0, 0, 0))
    page.draw_rect(fitz.Rect(298.5, 0, 300, 200), color=None, fill=(0, 0, 0))
    page.insert_text((285, 12), "Wide value", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    return d, page, fitz.Rect(span["bbox"])


def test_c21_case7_white_page_samples_true_white_not_the_frame():
    """probe_w7.py case 7: printed frame at top/right, span overhangs the
    corner. The old sampler clamps onto the frame and reads grey (0.498);
    C21 must read the true white background.
    """
    _doc, page, rect = _page_frame_fixture()
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((1.0, 1.0, 1.0), abs=0.02)


def test_c21_case8_light_blue_page_samples_true_blue_not_the_frame():
    """probe_w7.py case 8: same frame fixture on a light-blue page. The old
    sampler reads a wrong blended blue; C21 must read the true page colour.
    """
    _doc, page, rect = _page_frame_fixture(bg_fill=(0.7, 0.85, 1.0))
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((0.7, 0.85, 1.0), abs=0.02)


def test_c21_all_on_canvas_target_is_unchanged():
    """Control (probe_w7.py case 5): an ordinary near-edge target where every
    sample lands on-canvas is unaffected by C21.
    """
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    page.insert_text((200, 100), "Edge", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    rect = fitz.Rect(span["bbox"])
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((1.0, 1.0, 1.0), abs=0.02)


def test_c21_all_off_canvas_falls_back_to_the_clamped_set():
    """When every sample is off canvas, C21 keeps using the clamped set
    (there is nothing else to sample). Built from a target hugging a corner
    of a tiny page so all four offset samples fall outside it, over a
    uniform fill so the clamped-set fallback still reads the true colour."""
    d = fitz.open()
    page = d.new_page(width=20, height=20)
    page.draw_rect(page.rect, color=None, fill=(0.2, 0.4, 0.6))
    rect = fitz.Rect(0, 0, 20, 20)
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((0.2, 0.4, 0.6), abs=0.02)


# ---------------------------------------------------------------------------
# Fix round 1 (Tasks 1-3 review, Opus, ledger 2026-09-28): C21' (F3), and
# F4's X27-X29.
# ---------------------------------------------------------------------------


def _page_number_fixture(near_edge):
    """The reviewer's c21e2e.py regression fixture: a "12" near the top-right
    corner, with a header rule 3pt below it. The old sampler's single
    on-canvas sample (the one landing on the rule, or nearby) drove the
    whole median grey/wrong; C21' requires >= 2 on-canvas samples that AGREE
    before trusting them alone."""
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    y = 10 if near_edge else 13.5
    page.insert_text((286, y), "12", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    rect = fitz.Rect(span["bbox"])
    page.draw_rect(fitz.Rect(0, rect.y1 + 2, 300, rect.y1 + 4.5), color=None, fill=(0, 0, 0))
    return d.tobytes()


@pytest.mark.parametrize("rotation", ROTATIONS)
@pytest.mark.parametrize("near_edge", [True, False])
@pytest.mark.parametrize("op", ["replace", "delete"])
def test_c21_page_number_regression_reads_white_not_grey(op, near_edge, rotation):
    """F3 IMPORTANT / ruling C21' (reviewer finding, c21e2e.py): with the
    OLD C21 (a single on-canvas sample wins the median outright), this
    "12" near the top-right corner erases to grey (or worse). Run end to
    end through replace_text and delete_block, at all 4 rotations: the
    erased area must read white."""
    doc, handle = parse(_page_number_fixture(near_edge))
    page = handle[0]
    page.set_rotation(rotation)
    target = next(b for b in doc.pages[0].text_blocks if b.text == "12")

    if op == "replace":
        replace_text(handle, page_index=0, target=target, new_text="13")
    else:
        delete_block(handle, page_index=0, target=target)

    pixmap = page.get_pixmap()
    x = min(int((target.bbox[0] + target.bbox[2]) / 2), pixmap.width - 1)
    y = min(int(max(target.bbox[1], 0) + 1), pixmap.height - 1)
    pixel = pixmap.pixel(x, y)
    assert pixel == pytest.approx((255, 255, 255), abs=20)
    handle.close()


def test_c21_one_on_canvas_sample_on_a_rule_does_not_read_black():
    """F3 IMPORTANT / ruling C21': a target overhanging the page's top-right
    corner, where exactly ONE sample lands on-canvas and that one sample
    happens to land on a black rule. Plain C21 (any on-canvas sample beats
    the clamped set) would make the erase fill BLACK -- the worst case the
    reviewer measured. C21' requires >= 2 AGREEING on-canvas samples, so a
    single on-canvas sample alone is never trusted; the clamped set (which
    still includes the true white background from the other, off-canvas-but-
    clamped-onto-white edges) is used instead."""
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    page.insert_text((295, 4), "9", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    rect = fitz.Rect(span["bbox"])
    # A black rule directly under the glyph, in the one sample that lands
    # on-canvas (below the bottom edge).
    page.draw_rect(fitz.Rect(0, rect.y1 + 1, 300, rect.y1 + 6), color=None, fill=(0, 0, 0))
    color = _sample_background_color(page, rect)
    assert color != pytest.approx((0.0, 0.0, 0.0), abs=0.05)


def test_c21_off_canvas_uses_floor_not_truncation():
    """F3 IMPORTANT / ruling C21': math.floor, not int(), decides on-canvas.
    A sample landing at display coordinate -0.9 (just off the negative
    edge) truncates to 0 (int(-0.9) == 0, ON canvas) but floors to -1 (OFF
    canvas) -- math.floor is the correct one. Built with a target near the
    top-left corner so BOTH its top and left sample points land at -0.9 in
    display space (rect.x0 == rect.y0 == 2.1, offset 3.0): with the correct
    floor, those two are excluded as off-canvas, leaving only the bottom and
    right samples (2, agreeing) to be trusted alone. With int() truncation,
    all 4 count as on-canvas, including the corner's black paint, which the
    agreement check then rejects, falling back to a mixed median that is
    NOT the true background."""
    d = fitz.open()
    page = d.new_page(width=50, height=50)
    page.draw_rect(page.rect, color=None, fill=(0.9, 0.9, 0.9))
    # The top row and left column -- what int() truncation would
    # incorrectly sample as "on canvas" for the two ambiguous corner points.
    page.draw_rect(fitz.Rect(0, 0, 50, 1), color=None, fill=(0, 0, 0))
    page.draw_rect(fitz.Rect(0, 0, 1, 50), color=None, fill=(0, 0, 0))
    rect = fitz.Rect(2.1, 2.1, 20, 20)
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((0.9, 0.9, 0.9), abs=0.05)


def test_c21_requires_at_least_two_on_canvas_samples():
    """F4: C21' requires >= 2 on-canvas samples before trusting them alone
    -- kills the mutation that drops that count requirement (checking only
    the channel-agreement condition)."""
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    page.insert_text((295, 4), "9", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    rect = fitz.Rect(span["bbox"])
    page.draw_rect(fitz.Rect(0, rect.y1 + 1, 300, rect.y1 + 6), color=None, fill=(0, 0, 0))
    color = _sample_background_color(page, rect)
    assert color != pytest.approx((0.0, 0.0, 0.0), abs=0.05)


def test_c21_requires_on_canvas_samples_to_agree():
    """F4: C21' requires the on-canvas samples to agree (channel spread
    <= 26/255) before trusting them alone -- kills the mutation that drops
    the agreement check (using the on-canvas set whenever there are >= 2 of
    them, however much they disagree)."""
    d = fitz.open()
    page = d.new_page(width=300, height=200)
    # Two on-canvas samples that flatly disagree: white above, black rule
    # right below -- and no off-canvas samples for this near-centre target,
    # so a plain ">= 2" rule (no agreement check) would use their median,
    # a mid grey neither edge actually is.
    page.insert_text((150, 100), "Val", fontname="helv", fontsize=12)
    span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    rect = fitz.Rect(span["bbox"])
    page.draw_rect(fitz.Rect(0, rect.y1 + 1, 300, rect.y1 + 6), color=None, fill=(0, 0, 0))
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((1.0, 1.0, 1.0), abs=0.05)


def test_c21_on_canvas_check_uses_strict_less_than():
    """F4 (X27): a sample landing EXACTLY at pixmap.width (or .height) is
    off-canvas -- the check is strict (<), not <=. Built with a target near
    the bottom-right corner so BOTH its bottom and right sample points land
    exactly at pixmap.width/height (rect.x1 == rect.y1 == 47, offset 3.0):
    with the correct strict check those two are excluded as off-canvas,
    leaving only the top and left samples (2, agreeing) to be trusted
    alone. With <=, all 4 count as on-canvas, including the last row/
    column's black paint, which the agreement check then rejects."""
    d = fitz.open()
    page = d.new_page(width=50, height=50)
    page.draw_rect(page.rect, color=None, fill=(0.9, 0.9, 0.9))
    # The last on-canvas row and column -- what an off-by-one clamp (<=,
    # clamped to width-1/height-1 = 49) would incorrectly read for the two
    # boundary-exact points.
    page.draw_rect(fitz.Rect(49, 0, 50, 50), color=None, fill=(0, 0, 0))
    page.draw_rect(fitz.Rect(0, 49, 50, 50), color=None, fill=(0, 0, 0))
    rect = fitz.Rect(20, 20, 47, 47)
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((0.9, 0.9, 0.9), abs=0.05)


def test_c21_on_canvas_check_uses_both_axes():
    """F4 (X28/X29): the on-canvas test requires BOTH x and y to be in
    range -- a sample whose x is on-canvas but whose y is off (or vice
    versa) is off-canvas overall. A target overhanging the top of the page,
    with a stray mark at the clamped y=0 row, must not have that mark
    treated as an on-canvas sample."""
    d = fitz.open()
    page = d.new_page(width=100, height=100)
    page.draw_rect(page.rect, color=None, fill=(0.9, 0.9, 0.9))
    # Top sample point: ((x0+x1)/2, y0 - 3). y0 = -1 puts it at y = -4 (off
    # canvas vertically), while x stays on-canvas (target centred at x=50).
    rect = fitz.Rect(40, -1, 60, 19)
    page.draw_rect(fitz.Rect(0, 0, 100, 1), color=None, fill=(0, 0, 0))
    color = _sample_background_color(page, rect)
    assert color == pytest.approx((0.9, 0.9, 0.9), abs=0.05)


# ---------------------------------------------------------------------------
# Task 2: TextBlock gains origin, direction and color (W1, W5, D3)
# ---------------------------------------------------------------------------


def _skewed_red_text_fixture():
    """Red text at a known origin (72, 100), on a line skewed 5 degrees off
    horizontal (dir != (1, 0)) via a morph rotation, so origin/direction/
    color all take distinct, checkable values."""
    d = fitz.open()
    page = d.new_page()
    morph = (fitz.Point(72, 100), fitz.Matrix(1, 0, 0, 1, 0, 0).prerotate(5))
    page.insert_text((72, 100), "Skewed Red", fontsize=14, color=(1, 0, 0), morph=morph)
    return d.tobytes()


def test_textblock_gets_origin_direction_and_color_from_the_parser():
    pdf_bytes = _skewed_red_text_fixture()
    doc, _handle = parse(pdf_bytes)
    block = doc.pages[0].text_blocks[0]

    assert block.origin is not None
    assert block.origin == pytest.approx((71.996, 100.003), abs=0.01)

    assert block.direction is not None
    assert block.direction == pytest.approx((0.9962, -0.0872), abs=0.001)
    assert block.direction != pytest.approx((1.0, 0.0), abs=1e-3)

    assert block.color is not None
    assert block.color == pytest.approx((1.0, 0.0, 0.0), abs=0.01)


def test_textblock_defaults_stay_none_for_a_caller_built_block():
    """A TextBlock built directly by a caller (not through parse()) keeps
    the new fields at their None default -- every existing constructor call
    stays valid."""
    from engine.document import TextBlock

    block = TextBlock(text="x", bbox=(0, 0, 10, 10), font="helv", size=12)
    assert block.origin is None
    assert block.direction is None
    assert block.color is None


def test_parsing_does_not_change_the_document_fingerprint():
    """parse() is read-only -- adding fields it fills must not touch the
    live handle at all."""
    pdf_bytes = _skewed_red_text_fixture()
    _doc, handle = parse(pdf_bytes)
    before = fingerprint(handle)
    parse(pdf_bytes)
    assert fingerprint(handle) == before


def test_get_blocks_summary_is_unaffected_by_the_new_fields():
    """webui's get_blocks_summary lists explicit keys, so the new
    origin/direction/color fields on TextBlock must not appear in it or
    change any existing key's value."""
    import webui.session as session

    pdf_bytes = _skewed_red_text_fixture()
    session.load_document(pdf_bytes)
    summary = session.get_blocks_summary()
    assert len(summary) == 1
    entry = summary[0]
    assert set(entry.keys()) == {"id", "page_index", "text", "font", "size"}
    assert entry["text"] == "Skewed Red"


# ---------------------------------------------------------------------------
# Task 3: _right_limit (W2, R3-R8) -- fixtures shaped after the critic's
# probe_w2.py, probe_w4.py and scenarios.py, built inline.
# ---------------------------------------------------------------------------


def test_right_limit_stops_at_a_text_neighbour_180pt_away():
    """probe_w2.py case 6: a value with another field far to the right. R3's
    generic obstacle rule stops the widening at the neighbour's own x0, less
    the gap."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.insert_text((250, 100), "Date: 2026-01-01", fontname="helv", fontsize=12)
    assert _limit_for(page, "Jo Lee") == pytest.approx(247.0, abs=0.1)


def test_right_limit_gives_no_widening_when_a_neighbour_overlaps_the_targets_x1():
    """scenarios.py "overlapping": a value span starting 1.5pt LEFT of the
    label's own x1 (kerned across a font change). R3 says any obstacle whose
    x1 > target.x1 counts as an obstacle "wherever it starts" -- so this
    still stops the widening, clamped back to the label's own right edge."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="hebo", fontsize=12)
    label_width = fitz.Font("hebo").text_length("Name:", 12)
    page.insert_text((72 + label_width - 1.5, 100), "Jo Lee", fontname="helv", fontsize=12)
    label_bbox = _span_of(page, "Name:")["bbox"]
    assert _limit_for(page, "Name:") == pytest.approx(label_bbox[2], abs=0.05)


def test_right_limit_stops_at_a_vertical_rule():
    """probe_w2.py case 2: a table cell bounded on the right by a vertical
    rule drawn as a line."""
    d = fitz.open()
    page = d.new_page()
    for x in (72, 200, 330, 460):
        page.draw_line(fitz.Point(x, 80), fitz.Point(x, 200), width=0.5)
    for y in (80, 110, 140, 170, 200):
        page.draw_line(fitz.Point(72, y), fitz.Point(460, y), width=0.5)
    page.insert_text((76, 100), "Widget", fontname="helv", fontsize=10)
    page.insert_text((204, 100), "Blue", fontname="helv", fontsize=10)
    page.insert_text((334, 100), "12", fontname="helv", fontsize=10)
    assert _limit_for(page, "Blue") == pytest.approx(327.5, abs=0.1)


def test_right_limit_stops_at_a_cell_rectangles_right_edge_only():
    """probe_w2.py case 2b: the same table drawn with rectangles per cell.
    R3 says rectangles are split into their four edges first, so the cell's
    top and bottom borders (which start left of the target) are not
    obstacles, only its right edge is -- giving the same limit as the
    vertical-rule version."""
    d = fitz.open()
    page = d.new_page()
    for y in range(80, 200, 30):
        for x0, x1 in ((72, 200), (200, 330), (330, 460)):
            page.draw_rect(fitz.Rect(x0, y, x1, y + 30), width=0.5)
    page.insert_text((76, 100), "Widget", fontname="helv", fontsize=10)
    page.insert_text((204, 100), "Blue", fontname="helv", fontsize=10)
    assert _limit_for(page, "Blue") == pytest.approx(327.5, abs=0.1)


def test_right_limit_bounds_at_an_underline():
    """probe_w2.py case 1: an underline rule under the value, starting left
    of it and ending far right. R6 bounds the limit at the underline's own
    x1 (not offset by the gap), so the widened text stays within it."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.draw_line(fitz.Point(110, 103), fitz.Point(400, 103), width=0.6)
    assert _limit_for(page, "Jo Lee") == pytest.approx(400.0, abs=0.1)


def test_right_limit_dotted_leaders_stop_widening():
    """probe_w2.py case 1c: a dotted/dashed leader made of short segments
    that do not start until past the value's own x1. Ruling R6' (fix round
    1, reviewer finding F5): a thin segment lying entirely to the right of
    the target (its x0 >= target.x1) is an ordinary R3-style obstacle, not
    ignored -- so the dashes now pin "leaders stop widening", the safe
    outcome (today's shrink still applies), at the first dash's own x0 less
    the gap."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    x = 160
    while x < 400:
        page.draw_line(fitz.Point(x, 103), fitz.Point(x + 3, 103), width=0.6)
        x += 6
    assert _limit_for(page, "Jo Lee") == pytest.approx(157.0, abs=0.1)


def test_right_limit_stops_at_an_empty_acroform_widget():
    """probe_w2.py case 7: an AcroForm text widget with no value, which
    neither get_text nor get_drawings reports. R4 says every widget rect
    counts as an obstacle regardless."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Signature:", fontname="helv", fontsize=12)
    widget = fitz.Widget()
    widget.field_name = "sig"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(150, 86, 400, 106)
    widget.field_value = ""
    page.add_widget(widget)
    assert _limit_for(page, "Signature:") == pytest.approx(147.0, abs=0.1)


def test_right_limit_forbids_widening_over_a_full_page_scan_image():
    """scenarios.py's ocr_scan: an invisible-OCR word over a scanned image
    that also covers the space to its right. R5 says an image overlapping
    the band with x1 > target.x1 forbids widening outright, regardless of
    where the image starts -- its printed ink is invisible to the obstacle
    model, which is what keeps widening off scanned pages."""
    d = fitz.open()
    page = d.new_page()
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 40), 0)
    pm.set_rect(pm.irect, (255, 255, 255))
    pm.set_rect(fitz.IRect(120, 0, 200, 40), (0, 0, 0))
    page.insert_image(fitz.Rect(72, 80, 472, 160), pixmap=pm)
    page.insert_text((80, 100), "SCANNED", fontname="helv", fontsize=14, render_mode=3)
    own_x1 = _span_of(page, "SCANNED")["bbox"][2]
    assert _limit_for(page, "SCANNED") == pytest.approx(own_x1, abs=0.05)


def test_right_limit_widens_to_the_stacked_forms_box_edge_not_the_column():
    """scenarios.py's stacked(): three form fields at a 22pt pitch, each
    value's box drawn to x=400. All three values share the same left edge
    (x0=164), so a naive column-edge rule would cap widening at the
    shortest sibling's x1.

    Docstring fixed (fix round 1, per the owner's ruling on R7'): the real
    reason R7' does not fire here is the BASELINE WINDOW, not the values'
    differing lengths. R7''s window is baselines within 3*size of the
    target's own baseline -- 3*14 = 42pt at this 14pt value size. "Jo Lee"'s
    row is only 22pt (one pitch) from its immediate neighbour ("1234567",
    within the window) but 44pt from the row after that ("2008-01-01",
    OUTSIDE the window) -- so only ONE aligned neighbour ever qualifies,
    which is never enough for R7''s "at least 2 aligned neighbours" rule
    regardless of how their x1 values compare. (The values also happen to
    be very different lengths, which would independently keep R7' from
    firing even at 2+ neighbours -- but the window alone already rules it
    out here.) The real limit is the box's own right border, less the
    gap."""
    d = fitz.open()
    page = d.new_page()
    rows = [("Student Name:", "Jo Lee"), ("Student ID:", "1234567"), ("Date of Birth:", "2008-01-01")]
    for i, (label, value) in enumerate(rows):
        y = 100 + 22 * i
        page.insert_text((72, y), label, fontname="helv", fontsize=12)
        page.draw_rect(fitz.Rect(160, y - 14, 400, y + 6), width=0.8)
        page.insert_text((164, y), value, fontname="helv", fontsize=14)
    assert _limit_for(page, "Jo Lee") == pytest.approx(396.5, abs=0.1)


def test_right_limit_heading_over_a_shorter_line_is_not_capped():
    """probe_w2.py case 11 (third variant): a heading followed by one short
    paragraph line. R7 requires at least 2 aligned neighbours -- a single
    one (however short) never caps the heading's own widening. The limit
    falls through to the page margin."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Title", fontname="hebo", fontsize=16)
    page.insert_text((72, 122), "Short", fontname="helv", fontsize=11)
    assert _limit_for(page, "Title") == pytest.approx(523.0, abs=0.1)


def test_right_limit_caps_a_real_paragraph_at_the_column_edge():
    """probe_w2.py case 3-style paragraph: three left-aligned lines at
    ordinary single-line spacing (tight enough that adjacent bboxes overlap
    vertically, as real single-spaced body text does). R7 fires because at
    least 2 aligned neighbours' x1 values agree within 10% of the column
    width, capping the shortest line's widening at the longest sibling's x1
    -- not at the column-aligned siblings' own vertical overlap being
    mistaken for an R3 obstacle, and not at the page margin."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Column one line alpha here", fontname="helv", fontsize=10)
    page.insert_text((72, 112), "Column one line beta text", fontname="helv", fontsize=10)
    page.insert_text((72, 124), "Column one line gamma", fontname="helv", fontsize=10)
    alpha_x1 = _span_of(page, "Column one line alpha here")["bbox"][2]
    assert _limit_for(page, "Column one line gamma") == pytest.approx(alpha_x1, abs=0.05)
    assert _limit_for(page, "Column one line gamma") == pytest.approx(194.28, abs=0.1)


def test_right_limit_right_aligned_amount_does_not_widen():
    """probe_w2.py case 4: right-aligned numbers in a table. R8 marks the
    target as right-aligned (a neighbour within two line heights whose x1
    is within 1pt of the target's, while its x0 differs by more than 2pt)
    and forbids widening."""
    d = fitz.open()
    page = d.new_page()
    font = fitz.Font("helv")
    rows = [("Rent", "1,200.00"), ("Utilities", "85.50"), ("Total", "1,285.50")]
    for i, (label, value) in enumerate(rows):
        page.insert_text((72, 100 + 14 * i), label, fontname="helv", fontsize=10)
        width = font.text_length(value, 10)
        page.insert_text((300 - width, 100 + 14 * i), value, fontname="helv", fontsize=10)
    assert _limit_for(page, "85.50") == pytest.approx(300.0, abs=0.05)


def test_right_limit_margin_derived_from_the_leftmost_text():
    """probe_w2.py case 12: text starting at x=36 assumes a symmetric 36pt
    right margin (W2.3). Page defaults to A4 (595pt wide): margin = 595 -
    36 = 559."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((36, 100), "Wide left-aligned body", fontname="helv", fontsize=11)
    page.insert_text((36, 760), "footer", fontname="helv", fontsize=8)
    assert _limit_for(page, "Wide left-aligned body") == pytest.approx(559.0, abs=0.1)


def test_right_limit_margin_is_floored_at_18pt():
    """W2.3: the page margin is floored at 18pt even when the leftmost text
    on the page sits closer to the edge than that (a stray mark near the
    left edge must not drag the assumed margin, and so the widening limit,
    down with it)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Indented value", fontname="helv", fontsize=11)
    page.insert_text((5, 400), "x", fontname="helv", fontsize=6)
    bounds_x1 = page.rect.width
    assert _limit_for(page, "Indented value") == pytest.approx(bounds_x1 - 18.0, abs=0.1)


def test_right_limit_uses_visible_bounds_on_a_cropped_page():
    """probe_w2.py case 10: a cropped page (CropBox inset). The margin rule
    must use the visible (cropped) bounds, not the full MediaBox."""
    d = fitz.open()
    page = d.new_page()
    page.set_cropbox(fitz.Rect(50, 50, 500, 700))
    page.insert_text((72, 100), "Cropped value", fontname="helv", fontsize=12)
    assert _limit_for(page, "Cropped value") == pytest.approx(378.0, abs=0.1)


def test_right_limit_is_rotation_invariant():
    """probe_w2.py case 9: bboxes are reported in unrotated page space, and
    so is target_bbox -- the limit must come out the same at every
    rotation."""
    limits = {}
    for rotation in (0, 90, 180, 270):
        d = fitz.open()
        page = d.new_page()
        page.set_rotation(rotation)
        page.insert_text((72, 100), "Rotated value", fontname="helv", fontsize=12)
        page.insert_text((300, 100), "Next", fontname="helv", fontsize=12)
        limits[rotation] = _limit_for(page, "Rotated value")
    assert limits[0] == pytest.approx(297.0, abs=0.1)
    assert limits[90] == pytest.approx(limits[0], abs=0.01)
    assert limits[180] == pytest.approx(limits[0], abs=0.01)
    assert limits[270] == pytest.approx(limits[0], abs=0.01)


_MUTATOR_METHOD_NAMES = [
    "insert_text",
    "insert_textbox",
    "insert_font",
    "insert_image",
    "add_redact_annot",
    "apply_redactions",
    "draw_rect",
    "draw_line",
    "add_widget",
    "add_freetext_annot",
    "set_rotation",
    "set_cropbox",
    "set_mediabox",
    "clean_contents",
]


def test_right_limit_is_read_only_and_calls_no_mutator():
    """Task 3's hard requirement: _right_limit calls no mutator. A spy on
    every plausible PyMuPDF mutating method records zero calls."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.insert_text((250, 100), "Date: 2026-01-01", fontname="helv", fontsize=12)
    span = _span_of(page, "Jo Lee")

    spies = {}
    for name in _MUTATOR_METHOD_NAMES:
        spy = MagicMock(side_effect=AssertionError(f"_right_limit must not call page.{name}()"))
        spies[name] = spy
        setattr(page, name, spy)

    _right_limit(page, tuple(span["bbox"]), span["origin"][1], span["size"])

    for name, spy in spies.items():
        assert spy.call_count == 0, f"_right_limit called page.{name}()"


def test_right_limit_leaves_the_fingerprint_unchanged():
    """Same requirement, proven against the live document handle: calling
    _right_limit must not change a single byte of the underlying PDF
    object graph."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.insert_text((250, 100), "Date: 2026-01-01", fontname="helv", fontsize=12)
    pdf_bytes = d.tobytes()

    _doc, handle = parse(pdf_bytes)
    target = next(b for b in _doc.pages[0].text_blocks if b.text == "Jo Lee")
    before = fingerprint(handle)

    live_page = handle[0]
    _right_limit(live_page, target.bbox, target.origin[1], target.size)

    assert fingerprint(handle) == before


# ---------------------------------------------------------------------------
# Fix round 1 (Tasks 1-3 review, Opus, ledger 2026-09-28): W-F1, R7', R6',
# F4's killing tests, and F6.
# ---------------------------------------------------------------------------


def test_right_limit_wf1_narrow_first_glyph_same_line_span_blocks_widening():
    """F1 CRITICAL / ruling W-F1: a narrow (1.95pt-wide) first glyph in one
    span, immediately followed on the SAME line by the rest of the word/line
    in another span at the same x0. Before W-F1, a same-x0 span was excluded
    from R3 outright, so this same-line neighbour was wrongly treated as a
    column sibling and ignored -- widening the narrow glyph's span straight
    over it. W-F1 excludes an aligned span from R3 only when it is on
    ANOTHER line (abs(origin.y - baseline) > 0.5*size); here it is the SAME
    line, so it still counts as an obstacle: R must not exceed the target's
    own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "l", fontname="hebo", fontsize=7)
    glyph_width = fitz.Font("hebo").text_length("l", 7)
    page.insert_text((72 + glyph_width, 100), "ist of items that continues", fontname="helv", fontsize=7)
    own_x1 = _span_of(page, "l")["bbox"][2]
    assert _limit_for(page, "l") <= own_x1 + 0.05


def test_right_limit_wf1_flattened_overprint_blocks_widening():
    """F1 CRITICAL / ruling W-F1: a flattened overprint -- a grey "Name"
    label immediately overprinted 0.5pt to the right by "John Smith Jr" in
    black, both starting at nearly the same x0, same line. The critic
    measured a widened draw covering this neighbour (R = 495-523, past the
    neighbour) before W-F1. R must not exceed the target's own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((100, 100), "Name", fontname="helv", fontsize=12, color=(0.6, 0.6, 0.6))
    page.insert_text((100.5, 100), "John Smith Jr", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Name")["bbox"][2]
    assert _limit_for(page, "Name") <= own_x1 + 0.05


def test_right_limit_wf1_overlapping_ocr_word_and_line_boxes_blocks_widening():
    """F1 CRITICAL / ruling W-F1: OCR-style invisible text (render_mode=3)
    where a word-level box ("Invoice") and a line-level box ("Invoice Number
    12345") overlap almost exactly, both starting near the same x0, same
    line -- a realistic OCR sandwich artifact. R must not exceed the
    target's own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((100, 100), "Invoice", fontname="helv", fontsize=12, render_mode=3)
    page.insert_text((100.8, 100.3), "Invoice Number 12345", fontname="helv", fontsize=12, render_mode=3)
    own_x1 = _span_of(page, "Invoice")["bbox"][2]
    assert _limit_for(page, "Invoice") <= own_x1 + 0.05


def test_right_limit_wf1_does_not_break_ordinary_paragraph_widening():
    """W-F1's exclusion still applies to a genuine paragraph sibling on
    ANOTHER line -- the existing paragraph test
    (test_right_limit_caps_a_real_paragraph_at_the_column_edge) already
    proves the column-aligned siblings there are excluded from R3 and still
    let the shortest line widen (capped at the column edge by R7', not
    blocked outright as an R3 obstacle). This test adds an explicit,
    self-contained check: a 3-line paragraph's middle line must still widen
    past its own x1 (not get stuck at it), confirming W-F1's same-line-only
    exclusion did not regress the ordinary case."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Column one line alpha here", fontname="helv", fontsize=10)
    page.insert_text((72, 112), "Column one line beta text", fontname="helv", fontsize=10)
    page.insert_text((72, 124), "Column one line gamma", fontname="helv", fontsize=10)
    own_x1 = _span_of(page, "Column one line beta text")["bbox"][2]
    assert _limit_for(page, "Column one line beta text") > own_x1 + 0.5


def test_right_limit_r7_short_last_line_still_caps_the_middle_line():
    """F2 IMPORTANT / ruling R7': an 11pt paragraph whose LAST line is much
    shorter than the rest ("Romeo"). Before R7', the column-edge rule
    required ALL aligned neighbours' x1 values to agree within 10% of the
    column width -- the short last line alone broke that agreement, so the
    old rule never capped the middle line at all (falls through to the page
    margin, 523pt). R7' instead caps at the LARGEST aligned x1 when at least
    2 aligned neighbours' x1 values agree within 10% of THAT largest value
    -- the two long lines agree with each other, so the middle line is
    correctly capped at the column edge regardless of the short line."""
    d = fitz.open()
    page = d.new_page()
    lines = [
        "Alpha bravo charlie delta echo foxtrot golf",
        "Hotel india juliet",
        "Kilo lima mike november oscar papa quebec",
        "Romeo",
    ]
    for i, text in enumerate(lines):
        page.insert_text((72, 300 + i * 15), text, fontsize=11)
    column_edge = _span_of(page, lines[2])["bbox"][2]
    assert _limit_for(page, lines[1]) == pytest.approx(column_edge, abs=0.1)
    assert _limit_for(page, lines[1]) == pytest.approx(288.41, abs=0.1)


def test_right_limit_r7_leading_1_4_caps_first_and_last_lines():
    """F2 IMPORTANT / ruling R7': the same short-last-line paragraph, but at
    leading 1.4 (15.4pt pitch at 11pt) -- the old window ("2 bbox heights")
    missed the 3rd-away neighbour at this looser leading, so a naive port of
    the old rule would fail to cap either the first or the last line. R7''s
    window (baselines within 3*size = 33pt) still reaches both of the two
    long middle lines from either the first or the last line, so both are
    capped at the shared column edge."""
    d = fitz.open()
    page = d.new_page()
    size = 11
    pitch = 1.4 * size
    lines = [
        "Foxtrot golf hotel",
        "Lima mike november oscar papa quebec romeo",
        "Sierra tango uniform victor whiskey oscarlyy",
        "Yankee",
    ]
    for i, text in enumerate(lines):
        page.insert_text((72, 300 + i * pitch), text, fontsize=size)
    column_edge = _span_of(page, lines[1])["bbox"][2]
    assert _limit_for(page, lines[0]) == pytest.approx(column_edge, abs=0.1)
    assert _limit_for(page, lines[3]) == pytest.approx(column_edge, abs=0.1)
    assert _limit_for(page, lines[0]) == pytest.approx(304.92, abs=0.1)


def test_right_limit_r7_disagreeing_neighbours_do_not_cap():
    """F4 (X16/X17): two aligned neighbours whose x1 values disagree by
    ~30% of the column width -- well past R7''s 10% rule -- must NOT cap
    the target; it falls through to the page margin. Kills X16 (the 10%
    check removed entirely) and X17 (10% loosened to 50%, which this 30%
    gap would still pass)."""
    d = fitz.open()
    page = d.new_page()
    lines = [
        "Short target line here",
        "A very much longer line of paragraph text abcXYZ",
        "Another quite long paragraph line herexyz",
    ]
    for i, text in enumerate(lines):
        page.insert_text((72, 300 + i * 15), text, fontsize=11)
    assert _limit_for(page, lines[0]) == pytest.approx(523.0, abs=0.5)


def test_right_limit_r7_window_excludes_a_neighbour_just_past_3x_size():
    """F4 (X19): R7''s window is baselines within 3*size of the target's own
    baseline. A neighbour placed just past that boundary (3*size + 1pt) must
    not be treated as aligned at all, so it cannot contribute to the
    column-edge cap -- the limit falls through to the page margin."""
    d = fitz.open()
    page = d.new_page()
    size = 11
    page.insert_text((72, 300), "Target line short", fontsize=size)
    page.insert_text((72, 300 + 3 * size + 1), "Far below aligned but outside window quite long text", fontsize=size)
    assert _limit_for(page, "Target line short") == pytest.approx(523.0, abs=0.5)


def test_right_limit_column_alignment_tolerance_is_tight():
    """F4 (X20): the column-alignment tolerance for W-F1's R3 exclusion is
    2pt. A paragraph "sibling" on another line but indented 5pt further
    right (outside that tolerance) is NOT treated as column-aligned, so it
    is NOT excluded from R3 -- it is a genuine obstacle (its x1 exceeds the
    target's, and single-spaced lines' bboxes ordinarily overlap
    vertically), and the target must not widen past its own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 300), "Target line", fontsize=11)
    page.insert_text((77, 312), "Second line offset by five points is long", fontsize=11)
    own_x1 = _span_of(page, "Target line")["bbox"][2]
    assert _limit_for(page, "Target line") == pytest.approx(own_x1, abs=0.05)


def test_right_limit_r8_x0_tolerance_is_tight():
    """F4 (X14): R8's "differs enough to be a different column" tolerance
    on x0 is 2pt. A neighbour whose x0 differs by only 0.5pt (well within
    the ordinary column-alignment tolerance) and whose x1 is within 1pt,
    within the window, must NOT mark the target as right-aligned -- it is
    effectively the same column, not two right-aligned values."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Val3", fontname="helv", fontsize=10)
    own_x1 = _span_of(page, "Val3")["bbox"][2]
    page.insert_text((72.5, 114), "Val4", fontname="helv", fontsize=10)
    assert _limit_for(page, "Val3") == pytest.approx(523.0, abs=0.5)


def test_right_limit_r7_window_does_not_reach_6x_size():
    """F4 (X19): R7''s window is baselines within 3*size, not 6*size. A
    second, far aligned neighbour at 60pt (between 3*size=33 and 6*size=66
    at this 11pt size) must not be pulled into the aligned set -- only the
    nearer neighbour (at 30pt, within the correct window) qualifies, which
    alone is not enough (R7' needs >= 2), so the limit falls through to the
    page margin."""
    d = fitz.open()
    page = d.new_page()
    size = 11
    page.insert_text((72, 300), "Target short line", fontsize=size)
    page.insert_text((72, 300 + 30), "Neighbour one long line here today", fontsize=size)
    page.insert_text((72, 300 + 60), "Neighbour two long line herex todays", fontsize=size)
    assert _limit_for(page, "Target short line") == pytest.approx(523.0, abs=0.5)


def test_right_limit_excludes_the_targets_own_span_from_its_neighbour_lists():
    """F4 (X24): the target's own span must be excluded from the
    "other spans" pool entirely (is_target's skip), not merely from R3's
    obstacle check -- otherwise it can wrongly join R7''s "aligned"
    neighbour list and, alongside a single genuine neighbour whose x1 is
    close to the target's own, produce a false 2-neighbour cluster that
    caps widening when only one real neighbour exists (R7' needs >= 2 REAL
    aligned neighbours)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Alpha bravo charlie delta ec", fontsize=11)
    page.insert_text((72, 112), "Alpha bravo charlie delta echo", fontsize=11)
    assert _limit_for(page, "Alpha bravo charlie delta ec") == pytest.approx(523.0, abs=0.5)


def test_right_limit_r8_window_excludes_a_far_neighbour():
    """F4 (X13): R8's window is 2 line heights. A neighbour 200pt below,
    whose x1 lands within 1pt of the target's own x1 and whose x0 differs by
    more than 2pt (otherwise a textbook R8 right-aligned shape), is far
    outside that window and must NOT mark the target as right-aligned -- the
    target must still be free to widen well past its own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Val", fontname="helv", fontsize=10)
    own_x1 = _span_of(page, "Val")["bbox"][2]
    font = fitz.Font("helv")
    far_width = font.text_length("Vabcdek", 10)
    page.insert_text((own_x1 - far_width, 100 + 200), "Vabcdek", fontname="helv", fontsize=10)
    assert _limit_for(page, "Val") > own_x1 + 5


def test_right_limit_r8_x1_tolerance_is_tight():
    """F4 (X15): R8's x1 tolerance is 1pt. A neighbour whose x1 lands 3pt
    away from the target's own x1 (otherwise within the 2-line-height
    window, and x0 differing by more than 2pt) is outside that tolerance and
    must NOT mark the target as right-aligned."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Val2", fontname="helv", fontsize=10)
    own_x1 = _span_of(page, "Val2")["bbox"][2]
    font = fitz.Font("helv")
    w = font.text_length("Longer2", 10)
    page.insert_text((own_x1 + 3 - w, 114), "Longer2", fontname="helv", fontsize=10)
    assert _limit_for(page, "Val2") > own_x1 + 5


def test_right_limit_underline_exactly_at_the_baseline_bounds_r():
    """R6' states the underline band is [baseline, ...], with >= at the
    baseline edge. A thin rule drawn exactly AT the baseline (seg.y1 ==
    baseline) must still count as an underline and bound R at its own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.draw_line(fitz.Point(110, 100), fitz.Point(400, 100), width=0.6)
    assert _limit_for(page, "Jo Lee") == pytest.approx(400.0, abs=0.1)


def test_right_limit_8pt_fill_in_rule_bounds_r():
    """R6': the underline band's bottom edge is max(y1 + 2, baseline +
    0.75*size). At an 8pt size, 0.75*size = 6pt, wider than the flat +2pt
    slack alone would allow at this small size -- a fill-in rule 5pt below
    the baseline is within that band and must bound R at its own x1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=8)
    page.insert_text((110, 100), "Jo", fontname="helv", fontsize=8)
    page.draw_line(fitz.Point(100, 105), fitz.Point(400, 105), width=0.6)
    assert _limit_for(page, "Jo") == pytest.approx(400.0, abs=0.1)


def test_right_limit_underline_band_check_excludes_a_far_below_rule():
    """F4 (X9): a thin rule overlapping the target's x-range but far below
    the underline band (well past baseline + 0.75*size and y1 + 2) must be
    ignored, not treated as an underline."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    page.draw_line(fitz.Point(110, 130), fitz.Point(400, 130), width=0.6)
    assert _limit_for(page, "Jo Lee") == pytest.approx(523.0, abs=0.5)


def test_right_limit_underline_band_top_is_the_baseline_not_bbox_top():
    """F4 (X33): a thin rule strictly ABOVE the baseline (through the
    middle of the glyphs, like a strikethrough) must NOT count as an
    underline -- the band's top edge is the baseline, not bbox.y0."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    span = _span_of(page, "Jo Lee")
    mid_y = (span["bbox"][1] + span["origin"][1]) / 2
    page.draw_line(fitz.Point(110, mid_y), fitz.Point(400, mid_y), width=0.6)
    assert _limit_for(page, "Jo Lee") == pytest.approx(523.0, abs=0.5)


def test_right_limit_underline_slack_does_not_reach_20pt_below():
    """F4 (X34): a rule just past the correct band's bottom (baseline +
    0.75*size + 3pt, at a 12pt size) must be ignored -- the slack does not
    stretch all the way to 20pt below the baseline."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    span = _span_of(page, "Jo Lee")
    y = span["origin"][1] + 0.75 * 12 + 3
    page.draw_line(fitz.Point(110, y), fitz.Point(400, y), width=0.6)
    assert _limit_for(page, "Jo Lee") == pytest.approx(523.0, abs=0.5)


def test_right_limit_stops_at_an_annotation_only_obstacle():
    """F4 (X1): a plain rectangle annotation (not a form widget) in the
    band, to the right of the target. Kills the mutation that drops the
    page.annots() loop entirely."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Notes:", fontname="helv", fontsize=12)
    page.add_rect_annot(fitz.Rect(150, 86, 300, 106))
    own_x1 = _span_of(page, "Notes:")["bbox"][2]
    assert _limit_for(page, "Notes:") == pytest.approx(146.0, abs=0.1)
    assert _limit_for(page, "Notes:") < 300


def test_right_limit_image_outside_the_band_does_not_block():
    """F4 (X2): an image entirely outside the target's vertical band must
    not forbid widening -- kills the mutation that drops the band check for
    images (R5 only applies to images IN the band)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Label", fontname="helv", fontsize=12)
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), 0)
    pm.set_rect(pm.irect, (0, 0, 0))
    page.insert_image(fitz.Rect(200, 300, 250, 350), pixmap=pm)
    own_x1 = _span_of(page, "Label")["bbox"][2]
    assert _limit_for(page, "Label") > own_x1 + 5


def test_right_limit_widget_outside_the_band_does_not_block():
    """F4 (X4): a form widget entirely outside the target's vertical band,
    but starting close to the target's own x1, must not block widening --
    kills the mutation that drops the band check for widgets (which would
    otherwise treat it as an obstacle purely on its x1 > target.x1, giving a
    limit near the target's own edge instead of the far-away page margin)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Label2", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Label2")["bbox"][2]
    widget = fitz.Widget()
    widget.field_name = "f2"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(own_x1 + 2, 300, own_x1 + 100, 320)
    widget.field_value = ""
    page.add_widget(widget)
    assert _limit_for(page, "Label2") > own_x1 + 20


def test_right_limit_image_entirely_left_of_target_does_not_block():
    """F4 (X3): an image entirely to the LEFT of the target (its own x1 <=
    target.x1), even though it overlaps the band, must not forbid widening
    -- kills the mutation that drops the "x1 > tx1" check for images."""
    d = fitz.open()
    page = d.new_page()
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), 0)
    pm.set_rect(pm.irect, (0, 0, 0))
    page.insert_image(fitz.Rect(0, 85, 50, 105), pixmap=pm)
    page.insert_text((72, 100), "Label3", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Label3")["bbox"][2]
    assert _limit_for(page, "Label3") > own_x1 + 5


def test_right_limit_a_fat_segment_crossing_tx1_blocks_regardless_of_start():
    """F4 (X7): a "fat" (>=1pt tall) diagonal segment whose x-range straddles
    the target's own x1 -- it STARTS left of target.x1 and ENDS right of
    it -- must still block widening (R3's rule is "x1 > target.x1", not
    "x0 >= target.x1"). Kills the mutation that changes the drawing branch's
    condition from seg.x1 > tx1 to seg.x0 >= tx1."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Value", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Value")["bbox"][2]
    page.draw_line(fitz.Point(own_x1 - 5, 85), fitz.Point(own_x1 + 5, 105), width=0.6)
    assert _limit_for(page, "Value") == pytest.approx(own_x1, abs=0.1)


def test_right_limit_span_to_the_right_on_a_different_line_does_not_block():
    """F4 (X8): a text span whose x1 exceeds the target's, but on a
    different line entirely (far below, out of the target's vertical band),
    must not block widening -- kills the mutation that drops the band check
    for the R3 span rule."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Heading", fontname="helv", fontsize=12)
    page.insert_text((300, 400), "Far away line", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Heading")["bbox"][2]
    assert _limit_for(page, "Heading") > own_x1 + 5


def test_right_limit_curve_is_an_obstacle():
    """F4 (X11): a bezier curve drawn to the right of the target counts as
    an obstacle (its bounding box's left edge, less the gap) -- kills the
    mutation that stops page.get_drawings()'s "c" (curve) items from being
    decomposed into segments at all."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Curved", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Curved")["bbox"][2]
    page.draw_bezier(
        fitz.Point(own_x1 + 10, 80), fitz.Point(own_x1 + 15, 90),
        fitz.Point(own_x1 + 15, 110), fitz.Point(own_x1 + 10, 120), width=1.0,
    )
    assert _limit_for(page, "Curved") == pytest.approx(own_x1 + 10 - 3.0, abs=0.1)


def test_right_limit_quad_is_an_obstacle():
    """F4 (X12): a "qu" (quad) item from page.get_drawings() counts as an
    obstacle. page.draw_quad's own PDF output was verified (on this
    PyMuPDF version) to always emit its border as plain "l" line segments,
    which are already obstacles under R3/R6 on their own regardless of "qu"
    handling -- so a real drawn quad cannot isolate this rule. This
    monkeypatches page.get_drawings() to return a single "qu"-only item
    (as PyMuPDF's own docs describe the op reporting), which is the only
    way to exercise _drawing_edges's "qu" branch in isolation and kill the
    mutation that stops "qu" items from being decomposed at all."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Quaded", fontname="helv", fontsize=12)
    own_x1 = _span_of(page, "Quaded")["bbox"][2]
    quad = fitz.Quad(
        fitz.Point(own_x1 + 10, 90), fitz.Point(own_x1 + 30, 90),
        fitz.Point(own_x1 + 10, 110), fitz.Point(own_x1 + 30, 110),
    )
    page.get_drawings = lambda extended=False: [{"items": [("qu", quad)]}]
    assert _limit_for(page, "Quaded") == pytest.approx(own_x1 + 10 - 3.0, abs=0.1)


def test_right_limit_gap_is_floored_at_1pt():
    """F4 (X21): at a tiny font size (2pt, where 0.25*size = 0.5pt), the gap
    is still floored at 1pt, not 0.5pt. A neighbour 5pt past the target's
    own x1 gives a measurably different limit at the two gap values."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "t", fontname="helv", fontsize=2)
    own_x1 = _span_of(page, "t")["bbox"][2]
    page.insert_text((own_x1 + 5, 100), "next", fontname="helv", fontsize=2)
    neighbour_x0 = _span_of(page, "next")["bbox"][0]
    assert _limit_for(page, "t") == pytest.approx(neighbour_x0 - 1.0, abs=0.05)


def test_right_limit_margin_uses_unrotated_bounds_on_a_90_degree_page():
    """F4 (X25): on a page rotated 90 degrees, the margin must use
    unrotated_bounds (the true unrotated extent, matching the space
    target_bbox is given in), not page.rect directly -- page.rect's width
    and height are SWAPPED at 90/270, so using it raw would compute the
    wrong margin. A 612x792 portrait page rotated 90 has page.rect
    792x612; the correct margin uses the unrotated width (612)."""
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    page.set_rotation(90)
    page.insert_text((72, 100), "Rotated margin value", fontname="helv", fontsize=11)
    assert _limit_for(page, "Rotated margin value") == pytest.approx(612.0 - 72.0, abs=0.1)


def test_right_limit_candidates_fold_the_margin_default_safely():
    """F6 MINOR: on a page with nothing else at all (no obstacles, no
    aligned neighbours), the internal `candidates` list collecting R3-R8's
    obstacle-based bounds is genuinely empty, and the margin is folded in
    via min()'s own `default=` argument rather than an ordinary append --
    so min() of an empty list is structurally impossible, not merely
    avoided by always appending one more entry. The result is exactly the
    margin-derived limit."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Alone", fontname="helv", fontsize=11)
    bounds_x1 = page.rect.width
    assert _limit_for(page, "Alone") == pytest.approx(bounds_x1 - 72.0, abs=0.1)


# ---------------------------------------------------------------------------
# Task 4: the new replace_text path (W1, W3, R1, R2/D2, R9, R11, R13, D3)
# ---------------------------------------------------------------------------


def _exported_page(handle, page_index=0):
    return fitz.open(stream=export(handle), filetype="pdf")[page_index]


def _one_span_at(page, text, origin, *, size=None, color=None, abs_pt=0.01):
    """R9's check: exactly one span reading `text`, whose origin equals
    `origin` to within abs_pt (float precision, not "close enough" for a
    human eye)."""
    matches = [
        s
        for b in page.get_text("dict")["blocks"]
        for l in b.get("lines", [])
        for s in l["spans"]
        if s["text"] == text
    ]
    assert len(matches) == 1, f"expected exactly one span reading {text!r}, got {len(matches)}"
    span = matches[0]
    assert span["origin"] == pytest.approx(origin, abs=abs_pt)
    if size is not None:
        assert span["size"] == pytest.approx(size, abs=0.01)
    if color is not None:
        assert fitz.sRGB_to_pdf(span["color"]) == pytest.approx(color, abs=0.02)
    return span


def _owner_form_fixture():
    """The owner's live-test fixture (spec V2, probe1.py): a label, a box
    drawn to x=400, and a 14pt value inside it with ~194pt of empty box to
    its right."""
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    page.insert_text((72, 100), "Student Name:", fontsize=12, fontname="helv")
    page.draw_rect(fitz.Rect(160, 86, 400, 106), color=(0, 0, 0), width=0.8)
    page.insert_text((164, 100), "Jo Lee", fontsize=14, fontname="helv")
    page.insert_text((72, 140), "Date: 2026-01-01", fontsize=12)
    return d.tobytes()


def test_replace_text_widens_the_owners_form_value_to_one_span_at_original_size():
    """Spec V2/W1: "Jonathan Lee" fits inside the box's free space at its
    original 14pt, on the original baseline (100.0), as one span -- not
    wrapped and shrunk to two ~7.44pt spans as today's box path would."""
    doc, handle = parse(_owner_form_fixture())
    target = next(b for b in doc.pages[0].text_blocks if b.text == "Jo Lee")

    replace_text(handle, page_index=0, target=target, new_text="Jonathan Lee")

    page = _exported_page(handle)
    assert "Jo Lee" not in page.get_text()
    _one_span_at(page, "Jonathan Lee", (164.0, 100.0), size=14.0)
    handle.close()


def test_replace_text_refuses_a_value_that_does_not_fit_even_widened():
    """R11: a replacement too long to fit even widened to the box's own
    right edge (400, less the gap) and shrunk to the 50% floor is refused
    BEFORE any erase -- fingerprint unchanged, old value still present."""
    doc, handle = parse(_owner_form_fixture())
    target = next(b for b in doc.pages[0].text_blocks if b.text == "Jo Lee")
    before = fingerprint(handle)

    way_too_long = "Alexandra Montgomery-Smith-The-Third, Esquire, of Upper Wimbledon-on-Thames"
    with pytest.raises(RefusedBeforeMutation) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text=way_too_long)

    assert "Nothing has been modified." in str(excinfo.value)
    assert fingerprint(handle) == before
    assert "Jo Lee" in handle[0].get_text()
    handle.close()


def _paragraph_fixture():
    """probe1.py's paragraph: three left-aligned, ordinarily-spaced lines
    (15pt pitch at 11pt), the middle one the target."""
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    lines = [
        "The quick brown fox jumps over the lazy dog near",
        "the river bank while the farmer watches from the",
        "old wooden porch of the house on the hill today.",
    ]
    for i, text in enumerate(lines):
        page.insert_text((72, 300 + i * 15), text, fontsize=11)
    return d.tobytes()


def test_replace_text_paragraph_line_keeps_its_baseline():
    """Spec's corrected claim: the paragraph line, capped at the column edge
    (R7) rather than the page margin, widens as far as it can and then
    shrinks EXACTLY (9.91pt, not today's 8.91pt-after-two-0.9-steps) -- but
    its baseline (315.0) never moves, unlike today's box path (which lands
    it at 312.75, see spec V2)."""
    doc, handle = parse(_paragraph_fixture())
    target = next(b for b in doc.pages[0].text_blocks if b.text.startswith("the river"))
    new_text = "the river bank while the farmer quietly watches from the"

    replace_text(handle, page_index=0, target=target, new_text=new_text)

    page = _exported_page(handle)
    span = _one_span_at(page, new_text, (72.0, 315.0), size=9.91)
    assert span["size"] < target.size
    handle.close()


def test_replace_text_collapses_a_newline_to_a_single_space():
    """D2: a newline in new_text collapses to a space rather than starting
    a second line -- W1 draws one line by definition."""
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    page.insert_text((72, 100), "Original value", fontsize=12, fontname="helv")
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]

    replace_text(handle, page_index=0, target=target, new_text="First\nLine two")

    page = _exported_page(handle)
    _one_span_at(page, "First Line two", (72.0, 100.0), size=12.0)
    handle.close()


def test_line_break_regex_covers_every_separator_d2_lists():
    """Direct unit coverage of D2's stated separator set: \\r\\n as a pair
    (not two spaces), plus lone \\r, \\n, U+2028 and U+2029."""
    assert _LINE_BREAK_RE.sub(" ", "a\r\nb") == "a b"
    assert _LINE_BREAK_RE.sub(" ", "a\nb") == "a b"
    assert _LINE_BREAK_RE.sub(" ", "a\rb") == "a b"
    assert _LINE_BREAK_RE.sub(" ", "a b") == "a b"
    assert _LINE_BREAK_RE.sub(" ", "a b") == "a b"


def test_replace_text_keeps_the_original_colour():
    """D3: red text stays red -- today's replace_text always drew black."""
    d = fitz.open()
    page = d.new_page(width=612, height=792)
    page.insert_text((72, 100), "Red warning", fontname="helv", fontsize=12, color=(1, 0, 0))
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    assert target.color == pytest.approx((1.0, 0.0, 0.0), abs=0.01)

    replace_text(handle, page_index=0, target=target, new_text="Red warning!")

    page = _exported_page(handle)
    _one_span_at(page, "Red warning!", (72.0, 100.0), size=12.0, color=(1.0, 0.0, 0.0))
    handle.close()


def _raw_page(doc, content, fonts=(("helv", None),), width=612, height=792):
    """A fresh page whose content stream is exactly `content`, with font
    resources named /F1, /F2, ... from `fonts`: (base14-name, None) or
    (alias, ttf-path). Lets a fixture set an arbitrary Tm/Tz/cm the
    high-level drawing calls cannot express."""
    page = doc.new_page(width=width, height=height)
    for i, (name, path) in enumerate(fonts, 1):
        if path:
            page.insert_font(fontname=f"F{i}", fontfile=path, set_simple=True)
        else:
            page.insert_font(fontname=name)
            content = content.replace(f"/F{i} ", f"/{name} ")
    xrefs = page.get_contents()
    if xrefs:
        doc.update_stream(xrefs[0], content.encode("latin-1"))
    else:
        xref = doc.get_new_xref()
        doc.update_object(xref, "<<>>")
        doc.update_stream(xref, content.encode("latin-1"))
        doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    return doc[page.number]


def _uses_widen_path(page, target):
    """The exact routing decision replace_text makes (R1, R13), called
    directly so these tests pin ROUTING, independent of what the two
    possible drawing paths each happen to produce."""
    return _direction_is_near_horizontal(target.direction) and _origin_is_reliable(page, target)


# probe_w1.py / probe_w5.py: cases whose geometry must route to today's box
# path rather than the new widen path, despite `direction` sometimes
# reporting (1, 0).
_MISLEADING_GEOMETRY_CASES = {
    "y-mirrored (cm mirror y)": "q 1 0 0 -1 0 792 cm BT /F1 12 Tf 72 92 Td (Hello) Tj ET",
    "Tm upside down": "BT /F1 12 Tf -1 0 0 -1 300 700 Tm (Hello) Tj ET",
    "Tm scale x2": "BT /F1 12 Tf 2 0 0 1 72 700 Tm (Hello) Tj ET",
    "Tm scale y1.5": "BT /F1 12 Tf 1 0 0 1.5 72 700 Tm (Hello) Tj ET",
    "Tz 150 (horizontal scaling)": "BT /F1 12 Tf 150 Tz 72 700 Td (Hello) Tj ET",
}


def _drawn_baseline_y(page, text):
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if text in s["text"]:
                    return s["origin"][1]
    raise KeyError(f"no span containing {text!r} on this page")


@pytest.mark.parametrize("case", sorted(_MISLEADING_GEOMETRY_CASES))
def test_replace_text_routes_misleading_geometry_to_todays_path(case):
    content = _MISLEADING_GEOMETRY_CASES[case]
    d = fitz.open()
    page = _raw_page(d, content)
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    live_page = handle[0]

    assert not _uses_widen_path(live_page, target), (
        f"{case} must take today's box path (R1/R13), but the widen path was selected"
    )

    replace_text(handle, page_index=0, target=target, new_text="Hello there")
    page = _exported_page(handle)
    assert "Hello there" in page.get_text().replace("\n", " ")

    # The discriminating, mutation-resistant check: today's box path pins
    # the TOP of its drawing rect at target.bbox's own top, not at
    # target.origin (see _insertion_rect) -- so its baseline lands
    # measurably away from the recorded origin. R9's widen path, by
    # contrast, always reproduces target.origin to within 0.01pt (proven by
    # every other test in this section). A drawn baseline within 0.01pt of
    # target.origin here would mean the widen path was actually used
    # despite the routing predicate saying otherwise -- catching a mutation
    # that only breaks replace_text's own use of that predicate, not the
    # predicate itself.
    drawn_y = _drawn_baseline_y(page, "Hello")
    assert abs(drawn_y - target.origin[1]) > 0.3, (
        f"{case}: drawn baseline {drawn_y} is suspiciously close to target.origin "
        f"{target.origin[1]} -- the widen path may have been used"
    )
    handle.close()


def test_replace_text_routes_a_one_degree_skew_to_todays_path():
    """probe_w5.py: a near-horizontal 1-degree OCR skew reports dir
    (0.9998, -0.0175) -- outside R13's 1e-3 tolerance on the y component,
    even though it easily passes R1's own baseline sanity gate on its own."""
    content = "BT /F1 12 Tf 0.99985 0.01745 -0.01745 0.99985 72 700 Tm (Hello) Tj ET"
    d = fitz.open()
    page = _raw_page(d, content)
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    live_page = handle[0]

    assert not _direction_is_near_horizontal(target.direction)
    assert not _uses_widen_path(live_page, target)

    replace_text(handle, page_index=0, target=target, new_text="Hello there")
    page = _exported_page(handle)
    assert "Hello there" in page.get_text().replace("\n", " ")

    # Same discriminating check as the misleading-geometry cases above --
    # see that test's comment.
    drawn_y = _drawn_baseline_y(page, "Hello")
    assert abs(drawn_y - target.origin[1]) > 0.3, (
        f"drawn baseline {drawn_y} is suspiciously close to target.origin "
        f"{target.origin[1]} -- the widen path may have been used"
    )
    handle.close()


def _type3_fixture():
    """probe_w1.py's Type3 fixture: one glyph 'square', FontMatrix 0.001, so
    the font's own reported ascender (0.7) differs sharply from any Base-14
    fallback's -- R1's gate must use the SPAN's own metrics, not a
    fallback-resolved font's, or this case would wrongly pass."""
    d = fitz.open()
    p = d.new_page()
    charproc = d.get_new_xref()
    d.update_object(charproc, "<<>>")
    d.update_stream(charproc, b"600 0 0 0 600 700 d1 0 0 600 700 re f")
    t3 = d.get_new_xref()
    d.update_object(
        t3,
        f"<< /Type /Font /Subtype /Type3 /FontBBox [0 0 600 700] "
        f"/FontMatrix [0.001 0 0 0.001 0 0] "
        f"/CharProcs << /square {charproc} 0 R >> "
        f"/Encoding << /Type /Encoding /Differences [97 /square] >> "
        f"/FirstChar 97 /LastChar 97 /Widths [600] /Resources << >> >>",
    )
    d.xref_set_key(p.xref, "Resources", f"<< /Font << /T3 {t3} 0 R >> >>")
    c = d.get_new_xref()
    d.update_object(c, "<<>>")
    d.update_stream(c, b"BT /T3 12 Tf 72 700 Td (aaa) Tj ET")
    d.xref_set_key(p.xref, "Contents", f"{c} 0 R")
    return d.tobytes()


def test_replace_text_routes_a_type3_font_to_todays_path():
    pdf_bytes = _type3_fixture()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].text_blocks[0]
    live_page = handle[0]

    assert not _origin_is_reliable(live_page, target)
    assert not _uses_widen_path(live_page, target)

    # And the end-to-end call must still succeed (falling through to a
    # Base-14 substitute, per _select_font's cascade), not raise.
    replace_text(handle, page_index=0, target=target, new_text="bbb")
    page = handle[0]

    # Same discriminating check as the misleading-geometry cases above:
    # today's box path pins its drawing rect at target.bbox's own top
    # (130.0), landing Helvetica's baseline at 130 + 12*1.075 = 142.9 --
    # measurably away from Type3's own recorded origin.y (142.0).
    drawn_y = _drawn_baseline_y(page, "bbb")
    assert abs(drawn_y - target.origin[1]) > 0.3, (
        f"drawn baseline {drawn_y} is suspiciously close to target.origin "
        f"{target.origin[1]} -- the widen path may have been used"
    )
    handle.close()


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_text_lands_at_the_original_origin_at_every_rotation(rotation):
    doc, handle = parse(build_page(rotation=rotation))
    target = next(b for b in doc.pages[0].text_blocks if "LOW-MARKER" in b.text)
    original_origin = target.origin

    replace_text(handle, page_index=0, target=target, new_text="LOW-MARKER-EXTENDED")

    page = _exported_page(handle)
    _one_span_at(page, "LOW-MARKER-EXTENDED", original_origin, size=target.size)
    handle.close()


def test_replace_text_lands_at_the_original_origin_on_a_contained_crop():
    """Merge A's "contained-crop" geometry (test_page_geometry.py's
    FIXTURE_ORIGINS): a CropBox strictly inside the MediaBox."""
    doc, handle = parse(build_page(cropbox="[40 60 580 740]"))
    target = next(b for b in doc.pages[0].text_blocks if "LOW-MARKER" in b.text)
    original_origin = target.origin

    replace_text(handle, page_index=0, target=target, new_text="LOW-MARKER-EXTENDED")

    page = _exported_page(handle)
    _one_span_at(page, "LOW-MARKER-EXTENDED", original_origin, size=target.size)
    handle.close()


# ---------------------------------------------------------------------------
# Fix round 2 (Task 4 Fable review, ledger 2026-09-28, commit 71b7334):
# C1, I1, I2, M-a, M-b, M-c. Rebuilt inline from the reviewer's probes
# (scratchpad rev-widen-t4/p3_r9.py, p4_geom.py, mut.py,
# extra_tests/test_widen_silent_nodraw.py) -- never imported from there.
# ---------------------------------------------------------------------------


def _quarterly_fixture(text="Quarterly"):
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 400), text, fontsize=12, fontname="helv")
    return d.tobytes()


# C1 CRITICAL: str.splitlines()'s own separator set, plus \t. D2 originally
# only covered \r, \n, U+2028, U+2029.
_C1_SEPARATORS = ["\t", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85"]


@pytest.mark.parametrize("sep", _C1_SEPARATORS)
def test_widen_path_draws_one_space_joined_span_for_every_separator(sep):
    """C1 CRITICAL: before this fix, a tab or a str.splitlines() separator
    D2 did not cover (\\x0b, \\x0c, \\x1c-\\x1e, \\x85) reached
    insert_textbox on the widen path un-collapsed, making its one-line rect
    too short (or forcing a second line) -- insert_textbox is all-or-
    nothing, so it drew NOTHING, and since the erase happens first on this
    path, the old text was silently erased with no replacement drawn at
    all. Every one of these separators must now collapse to a single space
    before measuring, on a target that genuinely takes the widen path (a
    plain insert_text span with reliable origin/direction), and draw
    successfully as ONE space-joined span."""
    doc, handle = parse(_quarterly_fixture())
    target = doc.pages[0].text_blocks[0]
    assert _uses_widen_path(handle[0], target), "fixture must take the widen path"

    new_text = "Quarterly" + sep + "Report"
    replace_text(handle, page_index=0, target=target, new_text=new_text)

    page = _exported_page(handle)
    assert "Quarterly" not in [
        s["text"] for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
    ], "old text must be gone"
    _one_span_at(page, "Quarterly Report", target.origin, size=target.size)
    handle.close()


def test_widen_path_raises_a_plain_valueerror_when_insert_textbox_reports_a_deficit(monkeypatch):
    """C1 CRITICAL: the widen path previously ignored insert_textbox's
    return value entirely. A negative return means insert_textbox drew
    NOTHING (it is all-or-nothing on failure -- see this task's own
    investigation notes in replace_text's docstring). The erase has
    already happened by the time this is discovered, so the failure must
    be a PLAIN ValueError (not RefusedBeforeMutation, which promises
    nothing changed -- that promise would be false here)."""
    doc, handle = parse(_quarterly_fixture())
    target = doc.pages[0].text_blocks[0]
    assert _uses_widen_path(handle[0], target)
    monkeypatch.setattr(fitz.Page, "insert_textbox", lambda *a, **k: -5.0)

    with pytest.raises(ValueError) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text="Quarterly Report")

    assert not isinstance(excinfo.value, RefusedBeforeMutation)
    handle.close()


def test_widen_path_erase_rect_is_pinned_to_bbox_plus_the_pad():
    """I1: the widen-path erase rect must be exactly target.bbox with the
    0.05pt precision pad added to x1 ONLY -- never widened to the draw
    rect's own width. Spies fitz.Page.add_redact_annot."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 400), "Target line", fontsize=12, fontname="helv")
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    assert _uses_widen_path(handle[0], target)

    calls = []
    orig_add = fitz.Page.add_redact_annot

    def spy(self, quad, *a, **k):
        calls.append(fitz.Rect(quad))
        return orig_add(self, quad, *a, **k)

    with patch.object(fitz.Page, "add_redact_annot", spy):
        replace_text(handle, page_index=0, target=target, new_text="Target line widened out to here and more words")

    assert len(calls) == 1
    expected = fitz.Rect(
        target.bbox[0], target.bbox[1], target.bbox[2] + _WIDTH_PRECISION_PAD_PT, target.bbox[3],
    )
    assert tuple(calls[0]) == pytest.approx(tuple(expected), abs=1e-6)
    handle.close()


@pytest.mark.parametrize("force_box_path", [False, True])
def test_replace_text_keeps_the_original_colour_on_both_paths(force_box_path):
    """I2: D3 (colour preserved) is exercised on BOTH paths -- the box path
    is forced via dataclasses.replace(target, direction=None), which routes
    around R1/R13 entirely. Kills the mutation that drops the colour
    parameter from the box path's _draw_shrink_to_fit call only (which the
    widen-path-only version of this test cannot see)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Red warning", fontname="helv", fontsize=12, color=(1, 0, 0))
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    if force_box_path:
        target = dataclasses.replace(target, direction=None)
        assert not _uses_widen_path(handle[0], target)
    else:
        assert _uses_widen_path(handle[0], target)

    replace_text(handle, page_index=0, target=target, new_text="Red warning!")

    page = _exported_page(handle)
    found = [
        s for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
        if s["text"] == "Red warning!"
    ]
    assert len(found) == 1
    assert fitz.sRGB_to_pdf(found[0]["color"]) == pytest.approx((1.0, 0.0, 0.0), abs=0.02)
    handle.close()


@pytest.mark.parametrize("force_box_path", [False, True])
def test_replace_text_collapses_a_newline_on_both_paths(force_box_path):
    """I2: D2 (newline collapse) is exercised on BOTH paths. Kills the
    mutation that only applies the collapse when the widen path will be
    taken (which the widen-path-only version of this test cannot see)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Original value here", fontsize=12, fontname="helv")
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    if force_box_path:
        target = dataclasses.replace(target, direction=None)
        assert not _uses_widen_path(handle[0], target)
    else:
        assert _uses_widen_path(handle[0], target)

    replace_text(handle, page_index=0, target=target, new_text="First\r\nLine two")

    page = handle[0]
    texts = [s["text"] for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    assert texts == ["First Line two"], texts
    handle.close()


def test_r1_gate_uses_the_spans_own_metrics_not_helvetica():
    """M-a: pins the re-read _span_metrics does (rather than trusting the
    resolved drawing font's metrics) with a case where ONLY the span's own
    metrics decide -- DejaVu Sans at 12pt. Its ascender/descender differ
    from Helvetica's enough that substituting Helvetica's numbers would
    WRONGLY reject a genuinely reliable origin (own metrics: d1 = d2 = 0;
    Helvetica's: d1 ~= 1.76pt, d2 ~= 2.53pt, both over the 1pt tolerance).
    The Type3 fixture used elsewhere in this file does NOT prove this (its
    own d2 already exceeds 1pt even under Helvetica's metrics -- see the
    corrected _span_metrics docstring)."""
    d = fitz.open()
    page = d.new_page()
    page.insert_font(fontname="dv", fontfile="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    page.insert_text((72, 400), "Quarterly", fontsize=12, fontname="dv")
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    live = handle[0]

    assert _origin_is_reliable(live, target)


def test_r1_gate_d2_check_fires_independently_of_d1(monkeypatch):
    """M-b: a case where d1 is exactly 0 (origin matches perfectly) but d2
    (the bbox-height check) alone exceeds the 1pt tolerance -- the gate
    must still reject. Kills the mutation that drops the d2 check
    entirely, keeping only d1."""
    asc, desc, size, y0 = 1.0, -0.3, 12.0, 100.0
    origin_y = y0 + size * asc  # d1 = 0 exactly
    bbox_height = size * (asc - desc) + 2.0  # d2 = 2.0, over tolerance
    target = TextBlock(
        text="x", bbox=(0, y0, 10, y0 + bbox_height), font="helv", size=size,
        origin=(0, origin_y), direction=(1.0, 0.0), color=None,
    )
    monkeypatch.setattr("engine.operations._span_metrics", lambda page, t: (asc, desc))

    assert not _origin_is_reliable(None, target)


def test_r1_gate_tolerance_is_1pt_not_3pt(monkeypatch):
    """M-b: a case where d1 is 1.5pt -- over the correct 1pt tolerance, but
    under a loosened 3pt one. The gate must reject. Kills the mutation
    that widens _BASELINE_SANITY_TOLERANCE_PT from 1pt to 3pt."""
    asc, desc, size, y0 = 1.0, -0.3, 12.0, 100.0
    origin_y = y0 + size * asc + 1.5  # d1 = 1.5pt
    bbox_height = size * (asc - desc)  # d2 = 0
    target = TextBlock(
        text="x", bbox=(0, y0, 10, y0 + bbox_height), font="helv", size=size,
        origin=(0, origin_y), direction=(1.0, 0.0), color=None,
    )
    monkeypatch.setattr("engine.operations._span_metrics", lambda page, t: (asc, desc))

    assert _BASELINE_SANITY_TOLERANCE_PT == pytest.approx(1.0)
    assert not _origin_is_reliable(None, target)


@pytest.mark.parametrize("size,expected_reliable", [(12, True), (72, False)])
def test_r1_gate_zapfdingbats_routes_by_size(size, expected_reliable):
    """M-b: documents the size dependence noted in the ledger and in
    _origin_is_reliable's own docstring -- ZapfDingbats passes R1's 1pt
    tolerance at 12pt (d1 ~= 0.38pt, d2 ~= 0.44pt) but fails at 72pt (the
    same relative gap scaled 6x over: d1 ~= 2.27pt, d2 ~= 2.66pt). This is
    expected (the tolerance is an absolute point value, not a fraction of
    size), not a bug -- ZapfDingbats is not special-cased for it."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 400), "a", fontsize=size, fontname="zadb")
    doc, handle = parse(d.tobytes())
    target = doc.pages[0].text_blocks[0]
    live = handle[0]

    assert _origin_is_reliable(live, target) == expected_reliable


def test_span_metrics_matching_tolerance_is_tight_not_5pt():
    """M-c: a near-duplicate fixture -- two spans reading "Dup", positioned
    close together (helv at baseline 400, cour at baseline 401 -- their
    bboxes differ by ~3pt, well under a loosened 5pt tolerance but well
    over the correct 0.05pt one). _span_metrics must match the SECOND
    span (cour) to its OWN metrics, not silently pick up the first
    (helv)'s -- kills the mutation that loosens the bbox-matching
    tolerance from 0.05pt to 5pt, which would let the first, unrelated
    span's bbox satisfy the match and return the WRONG metrics.

    (The task's "about 0.03pt apart" phrasing describes how tight a
    genuine re-read match is in practice -- real floating-point
    round-tripping noise, not a deliberately-built separation. A 0.03pt
    gap between two real, distinctly-drawn spans cannot be reproduced
    reliably across renders, so this fixture uses a 1pt drawn offset,
    which resolves to an actual ~3pt bbox gap once ascent/descent differ
    between the two fonts -- comfortably demonstrating the same tolerance
    bug the 0.03pt figure was getting at.)"""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 400), "Dup", fontsize=14, fontname="helv")
    page.insert_text((72, 401), "Dup", fontsize=14, fontname="cour")
    all_spans = [
        s for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
    ]
    assert len(all_spans) == 2
    second = all_spans[1]
    target = TextBlock(
        text="Dup", bbox=tuple(second["bbox"]), font="Courier", size=14.0,
        origin=tuple(second["origin"]), direction=(1.0, 0.0), color=None,
    )

    metrics = _span_metrics(page, target)

    assert metrics == pytest.approx((second["ascender"], second["descender"]), abs=1e-4)
