from pathlib import Path

import pytest
import pymupdf as fitz

from engine.operations import redact_region
from engine.operations import _sample_background_color

FIXTURES = Path(__file__).parent / "fixtures"


def test_redact_region_removes_text_from_extraction():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    # Locate the sensitive string's bbox via PyMuPDF's own search, so this
    # test doesn't hardcode coordinates that would silently drift if the
    # fixture's text position ever changes.
    hits = page.search_for("REDACT-ME-12345")
    assert hits, "fixture must contain the sensitive string for this test to mean anything"

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    handle.close()


def test_redact_region_only_affects_the_targeted_page():
    pdf_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page0 = handle[0]
    hits = page0.search_for("PAGE-MARK-1")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    assert "PAGE-MARK-1" not in page0.get_text()
    assert "PAGE-MARK-2" in handle[1].get_text()
    assert "PAGE-MARK-3" in handle[2].get_text()
    handle.close()


def test_redact_region_accumulates_across_multiple_calls_on_same_page():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    caption_hits = page.search_for("PATIENT-0042")
    assert caption_hits
    redact_region(handle, page_index=0, bbox=tuple(caption_hits[0]))

    intro_hits = page.search_for("Mixed-content document")
    assert intro_hits
    redact_region(handle, page_index=0, bbox=tuple(intro_hits[0]))

    remaining_text = page.get_text()
    assert "PATIENT-0042" not in remaining_text
    assert "Mixed-content document" not in remaining_text
    handle.close()


def test_redact_region_leaves_unrelated_text_on_the_same_page_intact():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("PATIENT-0042")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    assert "Mixed-content document with text and an embedded image below." in page.get_text()
    handle.close()


def test_redact_region_removes_image_content_via_explicit_default_modes():
    # Pins finding #2: apply_redactions() is called with images/graphics/text
    # passed explicitly (images=2 blanks out overlapping image pixels). This
    # test would fail if that mode were ever silently dropped or changed to
    # images=0 (ignore images).
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    before = page.get_image_info()
    assert before, "fixture must contain an image for this test to mean anything"
    image_bbox = before[0]["bbox"]

    redact_region(handle, page_index=0, bbox=image_bbox)

    assert page.get_image_info() == []
    handle.close()


def test_redact_region_normalizes_inverted_bbox_and_still_redacts():
    # A bbox with x1<x0 and/or y1<y0 is a simple ordering mistake, not a
    # meaningless rectangle -- fitz.Rect.normalize() recovers the intended
    # rectangle by sorting each axis independently, so redact_region must
    # still correctly redact rather than treat this as invalid geometry.
    # This is what actually fixes the reviewer's original finding: before
    # this fix wave, an inverted bbox produced a silent no-op that looked
    # redacted but wasn't; after it, the geometry is recovered and the
    # redaction genuinely happens.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    x0, y0, x1, y1 = tuple(hits[0])
    inverted_bbox = (x1, y1, x0, y0)  # x1<x0 and y1<y0

    redact_region(handle, page_index=0, bbox=inverted_bbox)

    assert "REDACT-ME-12345" not in page.get_text()
    handle.close()


def test_redact_region_raises_on_zero_area_bbox():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    with pytest.raises(ValueError):
        redact_region(handle, page_index=0, bbox=(100.0, 100.0, 100.0, 200.0))

    handle.close()


def test_redact_region_raises_on_fully_off_page_bbox():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    assert tuple(page.rect) == (0.0, 0.0, 612.0, 792.0)

    with pytest.raises(ValueError):
        redact_region(handle, page_index=0, bbox=(1000.0, 1000.0, 1100.0, 1100.0))

    handle.close()


def test_redact_region_succeeds_on_bbox_that_is_only_partially_off_page():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    x0, y0, x1, y1 = tuple(hits[0])
    # Extend far past the right edge of the (612pt-wide) page -- still
    # overlaps the target text and the page itself, so this must succeed.
    mostly_off_page_bbox = (x0, y0, x1 + 5000.0, y1)

    redact_region(handle, page_index=0, bbox=mostly_off_page_bbox)

    assert "REDACT-ME-12345" not in page.get_text()
    handle.close()


def test_redact_region_raises_on_negative_page_index():
    pdf_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    last_page_text_before = handle[handle.page_count - 1].get_text()

    with pytest.raises(ValueError):
        redact_region(handle, page_index=-1, bbox=(72.0, 100.0, 400.0, 140.0))

    # Must not have silently wrapped around and redacted the last page.
    assert handle[handle.page_count - 1].get_text() == last_page_text_before
    handle.close()


def test_redact_region_raises_on_page_index_out_of_range():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    with pytest.raises(ValueError):
        redact_region(handle, page_index=handle.page_count, bbox=(72.0, 100.0, 400.0, 140.0))

    handle.close()


def test_sample_background_color_reads_white_on_white_fixture():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    rect = fitz.Rect(hits[0])

    color = _sample_background_color(page, rect)

    # Allow a small tolerance for anti-aliasing near the sample points,
    # not an exact (1.0, 1.0, 1.0) match.
    assert all(c > 0.95 for c in color), f"expected near-white, got {color}"
    handle.close()


def test_sample_background_color_reads_the_real_non_white_background():
    pdf_bytes = (FIXTURES / "colored_background.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REPLACE-ME-SHORT")
    assert hits
    rect = fitz.Rect(hits[0])

    color = _sample_background_color(page, rect)

    # The fixture's rectangle was drawn with fill=(0.7, 0.85, 1.0) -- a
    # light blue. Assert the sample lands close to that, not white and
    # not black, with a tolerance loose enough to absorb anti-aliasing
    # and pixel-rounding but tight enough to prove a real color read
    # happened (not a hardcoded white default).
    r, g, b = color
    assert 0.55 <= r <= 0.85, f"red channel {r} not close to expected 0.7"
    assert 0.70 <= g <= 1.0, f"green channel {g} not close to expected 0.85"
    assert 0.85 <= b <= 1.0, f"blue channel {b} not close to expected 1.0"
    handle.close()
