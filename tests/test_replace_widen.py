"""Tests for the replace_text widen-before-shrink work (plan
docs/superpowers/plans/2026-09-28-replace-text-widen.md; spec
docs/superpowers/specs/2026-09-28-replace-text-widen-design.md, REVISION
section binding).

Fixtures are built inline from the critic's executed probes
(docs/superpowers/records/2026-09-28-replace-text-widen/probes/critique/
probe_w7.py, probe_w2.py, probe_w4.py, scenarios.py) -- never imported from
that directory.
"""
from unittest.mock import MagicMock

import pymupdf as fitz
import pytest

from engine.operations import _right_limit, _sample_background_color
from engine.parser import parse
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


def test_right_limit_dotted_leaders_do_not_stop_widening():
    """probe_w2.py case 1c: a dotted/dashed leader made of short segments
    that do not start until past the value's own x1. R6 says a segment
    under 1pt tall is never an obstacle on its own, and these dashes do not
    overlap the value's x-range either, so they are not an underline. This
    is a pinned, known limitation (spec R6): the widening is NOT stopped by
    the dashes, and falls through to the page margin."""
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 100), "Name:", fontname="helv", fontsize=12)
    page.insert_text((120, 100), "Jo Lee", fontname="helv", fontsize=12)
    x = 160
    while x < 400:
        page.draw_line(fitz.Point(x, 103), fitz.Point(x + 3, 103), width=0.6)
        x += 6
    assert _limit_for(page, "Jo Lee") == pytest.approx(523.0, abs=0.1)


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
    shortest sibling's x1 -- R7 requires at least 2 aligned neighbours
    whose x1 values agree within 10% of the column width, and these three
    values are very different lengths ("Jo Lee" vs "1234567" vs
    "2008-01-01"), so R7 does not fire. The real limit is the box's own
    right border, less the gap."""
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
