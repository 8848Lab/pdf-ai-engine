from pathlib import Path

import pytest
import pymupdf as fitz

from engine.operations import redact_region, replace_text
from engine.operations import _sample_background_color
from engine.document import TextBlock
from engine.parser import parse

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


def test_replace_text_same_length_replacement():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="Confidential note: the code is CHANGED-NOW-99999.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "CHANGED-NOW-99999" in remaining_text
    handle.close()


def test_replace_text_shorter_replacement():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="Gone.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "Gone." in remaining_text
    handle.close()


def test_replace_text_longer_replacement_shrinks_font_to_fit():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    original_size = target.size

    # Meaningfully longer than the original -- long enough to require
    # shrinking within the same single-line-height bbox.
    #
    # NOTE (Step 1 investigation adaptation): the brief's original candidate
    # string here ("Confidential note: the replacement secret access code is
    # now CHANGED-TO-SOMETHING-LONGER-99999-ABCDEF.", ~105 chars) was measured
    # empirically against the real target bbox (which is the whole line's
    # span bbox, ~306x16.5pt -- see task-4-report.md Step 1) and does NOT fit
    # even at the implementation's 50% font-shrink floor (insert_textbox's
    # deficit never crosses zero before fontsize drops below 6.0pt). That
    # would make this "should succeed" test exercise the raise path instead.
    # This replacement string is shorter but still clearly longer than the
    # original span text, and was confirmed to fit only after shrinking (to
    # ~7.87pt, 65% of the original 12pt) -- i.e. it genuinely exercises
    # auto-shrink-to-fit rather than happening to fit at full size.
    longer_text = "Confidential: the new code is CHANGED-TO-SOMETHING-LONGER-99999-ABCDEF."
    replace_text(handle, page_index=0, target=target, new_text=longer_text)

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "CHANGED-TO-SOMETHING-LONGER-99999-ABCDEF" in remaining_text

    # Confirm auto-shrink actually engaged -- not just that the call
    # succeeded. Re-inspect the live handle's own text-dict for the new
    # span's actual font size, per the design spec's fit-quality
    # requirement: a longer-but-fits replacement's re-parsed size must be
    # smaller than the original.
    new_size = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "CHANGED-TO-SOMETHING-LONGER" in span["text"]:
                    new_size = span["size"]
    assert new_size is not None, "could not find the replacement text's span to check its font size"
    assert new_size < original_size, (
        f"expected font-shrink to engage for a longer replacement, but size stayed "
        f"{new_size} (original was {original_size})"
    )
    handle.close()


def test_replace_text_raises_when_text_does_not_fit_even_shrunk():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    # Several sentences of filler -- unambiguously too much text for one
    # ~16pt-tall, ~306pt-wide single-line bbox even after shrinking to the
    # implementation's floor. Confirmed empirically in Step 1's investigation
    # (remains hundreds of points short of fitting at every attempted size
    # down to the 50% floor).
    way_too_long = " ".join(
        [f"This is filler sentence number {i} added to overflow the box." for i in range(15)]
    )

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=target, new_text=way_too_long)

    # The old text must still be gone (the erase step already ran before
    # the fit check), but the region must be left cleanly erased -- not a
    # corrupted partial draw from a failed insert_textbox attempt.
    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    handle.close()


def test_replace_text_raises_on_empty_new_text():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=target, new_text="")

    # An empty-new_text call must reject before mutating anything.
    assert "REDACT-ME-12345" in page.get_text()
    handle.close()


def test_replace_text_reuses_target_validation():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    off_page_target = TextBlock(text="x", bbox=(5000.0, 5000.0, 5100.0, 5100.0), font="helv", size=12.0)

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=off_page_target, new_text="anything")
    handle.close()
