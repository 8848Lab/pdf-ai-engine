"""Tests for the replace_text widen-before-shrink work (plan
docs/superpowers/plans/2026-09-28-replace-text-widen.md; spec
docs/superpowers/specs/2026-09-28-replace-text-widen-design.md, REVISION
section binding).

Fixtures are built inline from the critic's executed probes
(docs/superpowers/records/2026-09-28-replace-text-widen/probes/critique/
probe_w7.py, probe_w2.py, probe_w4.py, scenarios.py) -- never imported from
that directory.
"""
import pymupdf as fitz
import pytest

from engine.operations import _sample_background_color
from engine.parser import parse
from tests.test_page_geometry import fingerprint


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
