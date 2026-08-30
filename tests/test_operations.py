from dataclasses import replace
from pathlib import Path

import pytest
import pymupdf as fitz

from engine.operations import (
    _base14_style_match,
    _bundled_fallback_font,
    _extract_target_font,
    _insertion_rect,
    _missing_glyphs,
    _normalize_font_name,
    _sample_background_color,
    _select_font,
    redact_region,
    replace_text,
)
from engine.document import TextBlock
from engine.export import export
from engine.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_font_name_strips_subset_tag_and_matches_across_formats():
    # Real case, confirmed against an actual IRS Form 1040: the subset tag
    # only appears in page.get_fonts()'s basename, never in the span's own
    # reported font name.
    assert _normalize_font_name("PIMSLO+HelveticaNeueLTStd-Roman") == \
        _normalize_font_name("HelveticaNeueLTStd-Roman")
    # Real case, confirmed by embedding a font via page.insert_font() and
    # reading it back: get_text()'s span reports 'NimbusSans-Regular' (no
    # spaces) while get_fonts()'s basename reports 'Nimbus Sans Regular'
    # (with spaces) for the identical resource.
    assert _normalize_font_name("NimbusSans-Regular") == \
        _normalize_font_name("Nimbus Sans Regular")
    # Genuinely different fonts must not collide.
    assert _normalize_font_name("Arial-Bold") != _normalize_font_name("Arial-Italic")


def test_missing_glyphs_excludes_space_and_reports_real_gaps():
    helv = fitz.Font("helvetica")
    # Ordinary Latin text: nothing missing, including the space itself.
    assert _missing_glyphs(helv, "Hello World 123") == []
    # A Private Use Area codepoint is guaranteed unassigned by any real font.
    pua_char = chr(0xE000)
    assert _missing_glyphs(helv, f"test{pua_char}") == [pua_char]


def test_missing_glyphs_deduplicates_in_first_occurrence_order():
    helv = fitz.Font("helvetica")
    a, b = chr(0xE000), chr(0xE001)  # two distinct, unassigned Private Use Area codepoints

    missing = _missing_glyphs(helv, f"{a}{b}{a}{b}")

    assert missing == [a, b]


def test_base14_style_match_picks_bold_and_italic_variants():
    assert _base14_style_match("HelveticaNeueLTStd-Bold") == "helvetica-bold"
    assert _base14_style_match("SomeFont-Italic") == "helvetica-oblique"
    assert _base14_style_match("SomeFont-BoldOblique") == "helvetica-boldoblique"
    assert _base14_style_match("SomeFont-Regular") == "helvetica"


def test_bundled_fallback_font_covers_latin_cyrillic_greek_cjk_and_symbols():
    # Pins the reliability-spike finding this whole plan is built on: despite
    # the reserved name "cjk", this font is not CJK-only.
    font = _bundled_fallback_font()
    test_strings = {
        "latin": "ABCXYZabcxyz0123456789",
        "punctuation": "@#%&*()[]{}!?.,;:\"'/\\-_+=<>",
        "cyrillic": "абвгдЖЗИК",
        "greek": "αβγδΩΦΨ",
        "cjk": "中文日本語한국어",
        "currency": "$€£¥©®°",
    }
    for label, chars in test_strings.items():
        assert _missing_glyphs(font, chars) == [], f"{label} should be fully covered"


def test_extract_target_font_resolves_a_real_embedded_font():
    # Build a fixture with a genuinely embedded, custom-named font -- the
    # same construction pattern used by Task 2's new fixture (see that
    # task for why this specific pattern was chosen: embedding a Base-14
    # font's own buffer under a fake alias forces a real font-name-format
    # mismatch between get_text()'s span and get_fonts()'s basename,
    # exercising the exact normalization this helper exists for).
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page.insert_font(fontname="CustomCorporateFont", fontbuffer=helv.buffer)
    page.insert_text((72, 100), "target text", fontsize=12, fontname="CustomCorporateFont")
    data = doc.tobytes()
    doc.close()

    handle = fitz.open(stream=data, filetype="pdf")
    page = handle[0]
    span_font_name = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["font"]

    resolved = _extract_target_font(handle, page, span_font_name)

    assert resolved is not None
    xref, buffer = resolved
    assert isinstance(xref, int)
    assert len(buffer) > 0
    # The extracted buffer must actually be usable as a font.
    font = fitz.Font(fontbuffer=buffer)
    assert font.has_glyph(ord("A"))
    handle.close()


def test_extract_target_font_returns_none_for_a_non_embedded_base14_reference():
    # simple_text.pdf's text is drawn via plain insert_text() with no
    # explicit fontname -- PyMuPDF references "Helvetica" by name only,
    # never embeds it (confirmed: page.get_fonts() reports ext='n/a' and
    # extract_font() returns an empty buffer for it). This must fall
    # through cleanly, not crash or return an unusable "font".
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    resolved = _extract_target_font(handle, page, "Helvetica")

    assert resolved is None
    handle.close()


def test_extract_target_font_returns_none_for_a_font_name_with_no_match_at_all():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    resolved = _extract_target_font(handle, page, "SomeFontThatDoesNotExistAnywhere")

    assert resolved is None
    handle.close()


def _exported_text(handle) -> str:
    """Text of `handle` as it survives a save/reopen round trip.

    The neighbour-damage regressions below are about content *deletion*, so
    they assert against the exported file rather than the live handle: that
    is the artifact a caller actually ships, and it is where a redaction
    that swallowed a neighbour is unambiguously visible.
    """
    reopened = fitz.open(stream=export(handle), filetype="pdf")
    text = "\n".join(page.get_text() for page in reopened)
    reopened.close()
    return text


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

    with pytest.raises(ValueError) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text=way_too_long)

    # The old text must still be gone (the erase step already ran before
    # the fit check), but the region must be left cleanly erased -- not a
    # corrupted partial draw from a failed insert_textbox attempt. This
    # erase-then-raise outcome is the design spec's deliberate choice for
    # this one case (fail loudly rather than cascade reflow into
    # neighbouring content) and is unchanged.
    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text

    # The reported size must be one the loop ACTUALLY tried. The x0.9 steps
    # overshoot the 50% floor (12 -> ... -> 6.377 -> below the floor, exit),
    # so a message naming the un-attempted 6.00pt floor as "the size we
    # tried" would be a lie about what the operation did.
    message = str(excinfo.value)
    attempted = []
    size = target.size
    while size >= target.size * 0.5:
        attempted.append(size)
        size *= 0.9
    assert f"{attempted[-1]:.2f}pt" in message, (
        f"error should name the smallest size actually attempted "
        f"({attempted[-1]:.2f}pt), got: {message}"
    )
    handle.close()


def test_replace_text_leaves_the_following_line_intact_at_normal_line_spacing():
    # Regression pin. replace_text draws into a rect inflated downward by
    # one descender (so insert_textbox accepts the line at its full size),
    # but must NOT erase that inflated height: no content of the target's
    # own lives there, while the FOLLOWING line's does at ordinary leading.
    # When the erase used the inflated rect, apply_redactions(text=0) ate
    # the next line's text for any pitch up to ~20pt -- which includes the
    # 1.4-1.5x leading most real documents use.
    #
    # Every other fixture in this repo spaces its lines ~30pt apart, far
    # enough that the two rects cannot physically overlap, which is exactly
    # why this fixture had to be added to catch it.
    pdf_bytes = (FIXTURES / "tight_line_spacing.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    first, second = doc.pages[0].text_blocks[0], doc.pages[0].text_blocks[1]

    # The fixture must actually pose the problem: lines close enough to be
    # in reach of the inflation, but whose own bboxes do not overlap -- so
    # any damage below is replace_text's doing, not two lines genuinely
    # sitting on top of each other.
    pitch = second.bbox[1] - first.bbox[1]
    assert 16.0 < pitch < 20.0, f"fixture line pitch {pitch} is outside the regression window"
    assert second.bbox[1] >= first.bbox[3], "the two lines' own bboxes must not overlap"

    replace_text(
        handle,
        page_index=0,
        target=first,
        new_text="First line: REPLACED-CLEANLY stands alone.",
    )

    text = _exported_text(handle)
    assert "REPLACE-THIS-LINE" not in text
    assert "REPLACED-CLEANLY" in text
    # The specific failure mode: the untouched line lost its leading words.
    assert "Second line: KEEP-ME-INTACT must survive untouched." in text, (
        f"editing line 1 damaged line 2; surviving text was: {text!r}"
    )
    handle.close()


def test_replace_text_leaves_an_adjacent_span_on_the_same_line_intact():
    # Regression pin for _WIDTH_PRECISION_PAD_PT. The pad exists to absorb
    # a ~1e-4pt measurement/metrics mismatch, but it also widens the ERASE
    # region -- and a span on the same line can start at exactly the
    # target's right edge. At 0.5pt the pad reached far enough into the
    # neighbour that apply_redactions(text=0) deleted its whole leading
    # character ("the rest..." came back as "he rest..."). Every other
    # fixture here is one span per line, so none of them could catch it.
    pdf_bytes = (FIXTURES / "two_spans_one_line.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    label, body = doc.pages[0].text_blocks[0], doc.pages[0].text_blocks[1]

    # The fixture must actually pose the problem: the second span has to
    # begin where the first one ends, with no gap to absorb the pad.
    assert body.bbox[0] - label.bbox[2] < 0.01, (
        f"fixture spans are not abutting (gap {body.bbox[0] - label.bbox[2]})"
    )

    replace_text(handle, page_index=0, target=label, new_text="NOTICE: ")

    text = _exported_text(handle)
    assert "WARNING:" not in text
    assert "NOTICE:" in text
    # The specific failure mode: the neighbour lost its first character.
    assert "the rest of this line must survive." in text, (
        f"editing the label damaged the adjacent span; surviving text was: {text!r}"
    )
    handle.close()


def test_insertion_rect_inflates_the_bbox_but_never_past_the_page_edge():
    # The region replace_text erases and draws into is target.bbox inflated
    # (right edge + precision pad, bottom edge down to insert_textbox's real
    # line box). That growth must stop at the page boundary -- otherwise a
    # target sitting on the bottom/right margin would have replace_text
    # erasing and drawing outside the page.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    assert tuple(page.rect) == (0.0, 0.0, 612.0, 792.0)

    helv = fitz.Font("helvetica")
    interior = _insertion_rect(page, fitz.Rect(72.0, 100.0, 300.0, 116.5), helv, 12.0)
    assert (interior.x0, interior.y0) == (72.0, 100.0), "top-left must be held fixed"
    assert interior.x1 > 300.0 and interior.y1 > 116.5, "both grown edges should inflate"

    at_edge = _insertion_rect(page, fitz.Rect(400.0, 780.0, 612.0, 792.0), helv, 12.0)
    assert at_edge.x1 == 612.0
    assert at_edge.y1 == 792.0
    assert at_edge in page.rect

    handle.close()


def test_replace_text_falls_back_to_base14_when_font_is_not_embedded_anywhere():
    # "Calibri" is not embedded anywhere in this fixture (simple_text.pdf's
    # text is drawn via plain insert_text(), never insert_font()) and is
    # not a Base-14 name itself -- Tier 1 correctly finds no match and
    # falls through, Tier 2's style-match ("Calibri" has no bold/italic in
    # its name) resolves to plain "helvetica", which covers ordinary text.
    # This directly replaces the pre-cascade behavior, where any
    # non-Base-14 name failed outright.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    non_base14 = replace(target, font="Calibri")

    replace_text(handle, page_index=0, target=non_base14, new_text="Replaced via fallback.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "Replaced via fallback." in remaining_text
    handle.close()


def test_replace_text_uses_the_blocks_own_real_font_when_embedded():
    # Proves Tier 1 actually activated, not just that the overall call
    # succeeded (Tier 2's style-match fallback would also succeed here,
    # since "CustomCorporateFont" has no bold/italic in its name -- the
    # meaningful assertion is that the DRAWN text's re-parsed font is NOT
    # a Base-14 name, which only happens if Tier 1's real embedded font
    # was actually used).
    pdf_bytes = (FIXTURES / "embedded_custom_font.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "EMBEDDED-FONT-TARGET-555" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="TIER1-CONFIRMED-ACTIVE")

    remaining_text = page.get_text()
    assert "EMBEDDED-FONT-TARGET-555" not in remaining_text
    assert "TIER1-CONFIRMED-ACTIVE" in remaining_text

    new_span_font = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "TIER1-CONFIRMED-ACTIVE" in span["text"]:
                    new_span_font = span["font"]
    assert new_span_font is not None, "could not find the replacement text's span"
    assert new_span_font.lower() not in fitz.Base14_fontdict, (
        f"expected the block's own real font to be used, but the drawn text's "
        f"font is a Base-14 name ({new_span_font!r}) -- Tier 1 did not activate"
    )
    handle.close()


def test_replace_text_cascades_to_the_bundled_fallback_for_a_cjk_character():
    # target.font ("Calibri") is not embedded (same as the fallback test
    # above, so Tier 1 falls through) and Tier 2's Base-14 Helvetica has no
    # CJK coverage -- only Tier 3's bundled broad-coverage font can render
    # this, proving the cascade actually reaches its last tier rather than
    # stopping at Tier 2.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    non_base14 = replace(target, font="Calibri")

    replace_text(handle, page_index=0, target=non_base14, new_text="中文 CJK test")

    remaining_text = page.get_text()
    assert "中文" in remaining_text, (
        f"expected the CJK characters to render via the Tier 3 fallback, got: {remaining_text!r}"
    )
    handle.close()


def test_replace_text_raises_naming_the_missing_character_when_no_tier_covers_it():
    # A Private Use Area codepoint is guaranteed unassigned by any real
    # font, including PyMuPDF's own bundled broad-coverage Tier 3 font
    # (pinned by test_bundled_fallback_font_covers_... in Task 1 -- this
    # test relies on that font genuinely not covering it, not on a mock).
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    pua_char = chr(0xE000)  # Private Use Area -- confirmed unassigned in both
    # fitz.Font("helvetica") and fitz.Font("cjk") via has_glyph(0xE000) == 0.

    with pytest.raises(ValueError) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text=f"test{pua_char}")

    assert pua_char in str(excinfo.value)
    # Nothing was modified -- the original text must still be there.
    assert "REDACT-ME-12345" in page.get_text()
    handle.close()


def test_replace_text_accepts_base14_font_names_case_insensitively():
    # Base14_fontdict is keyed on lowercase names, but parse() reports what
    # the PDF says -- 'Helvetica', 'Times-Roman'. The check lowercases
    # before looking up, so these must all be accepted rather than rejected
    # as "not Base-14".
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    for font_name in ("Helvetica", "helv", "Times-Roman", "COURIER"):
        doc, handle = parse(pdf_bytes)
        page = handle[0]
        target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

        replace_text(
            handle, page_index=0, target=replace(target, font=font_name), new_text="Short."
        )

        assert "Short." in page.get_text(), f"{font_name} should have been accepted"
        handle.close()


def test_replace_text_reports_an_unexpected_drawing_failure_as_a_valueerror(monkeypatch):
    # Defense in depth for the documented `Raises: ValueError` contract.
    # Every failure mode known on PyMuPDF 1.28.2 is now excluded before the
    # erase step, so no real fixture can drive insert_textbox into raising --
    # forcing it is the only way to prove the wrapper actually converts an
    # unanticipated library exception into the documented type instead of
    # letting a bare Exception escape. This is the single place in this
    # suite that substitutes behavior rather than using real PDF input.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    def boom(*args, **kwargs):
        raise Exception("simulated PyMuPDF failure")

    monkeypatch.setattr(fitz.Page, "insert_textbox", boom)

    with pytest.raises(ValueError) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text="Anything.")

    # The original exception's own text must survive into the message, so a
    # caller can still diagnose what actually went wrong.
    assert "simulated PyMuPDF failure" in str(excinfo.value)
    handle.close()


def test_replace_text_raises_on_non_positive_font_size_without_erasing_anything():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    for bad_size in (0.0, -12.0):
        doc, handle = parse(pdf_bytes)
        page = handle[0]
        target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

        with pytest.raises(ValueError) as excinfo:
            replace_text(
                handle, page_index=0, target=replace(target, size=bad_size), new_text="Anything."
            )

        assert "target.size" in str(excinfo.value)
        # Validated before any page mutation -- the original content stands.
        assert "REDACT-ME-12345" in page.get_text()
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
