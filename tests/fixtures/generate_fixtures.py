"""One-time fixture generator. Run manually:
    ./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py

Produces the PDF files this test suite checks into tests/fixtures/ and reads
as fixed, versioned input. Not run as part of the test suite itself -- the
generated files are checked into git, so tests never depend on this script
existing or on PyMuPDF's page.insert_text/insert_image behavior at test
time, only on the fixed files it already produced.
"""
import pymupdf as fitz
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def _red_square_png(size: int = 64) -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, size, size))
    pixmap.set_rect(pixmap.irect, (200, 30, 30))
    return pixmap.tobytes("png")


def make_simple_text() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 100),
        "This is a simple single-page redaction test document.",
        fontsize=12,
    )
    page.insert_text(
        (72, 130),
        "Confidential note: the secret code is REDACT-ME-12345.",
        fontsize=12,
    )
    doc.save(FIXTURES_DIR / "simple_text.pdf")
    doc.close()


def make_multi_page() -> None:
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"This is page {i + 1} of a 3-page test document.", fontsize=12)
        page.insert_text((72, 130), f"Unique marker for page {i + 1}: PAGE-MARK-{i + 1}.", fontsize=12)
    doc.save(FIXTURES_DIR / "multi_page.pdf")
    doc.close()


def make_image_only() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(fitz.Rect(72, 100, 136, 164), stream=_red_square_png())
    doc.save(FIXTURES_DIR / "image_only.pdf")
    doc.close()


def make_mixed() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Mixed-content document with text and an embedded image below.", fontsize=12)
    page.insert_text((72, 130), "Sensitive figure caption: Subject ID PATIENT-0042.", fontsize=12)
    page.insert_image(fitz.Rect(72, 150, 136, 214), stream=_red_square_png())
    doc.save(FIXTURES_DIR / "mixed.pdf")
    doc.close()


def make_colored_background() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # A solid, non-white rectangle behind the text run, so
    # _sample_background_color (Task 3) has a genuine non-white
    # background to detect. Draw the rect first, then the text on top.
    # Verified on PyMuPDF 1.28.2: draw_rect(rect, color=None, fill=...)
    # paints a solid, unstroked rectangle -- color=None suppresses the
    # border so the fill color is the only thing on the page behind the
    # text, which is what _sample_background_color needs to read back.
    page.draw_rect(fitz.Rect(60, 100, 400, 140), color=None, fill=(0.7, 0.85, 1.0))
    page.insert_text(
        (72, 125),
        "Short text over a light-blue highlight box: REPLACE-ME-SHORT.",
        fontsize=12,
    )
    doc.save(FIXTURES_DIR / "colored_background.pdf")
    doc.close()


def make_tight_line_spacing() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Two lines at 17pt pitch -- ~1.4x leading on 12pt text, an ordinary
    # spacing for real reports and contracts, and deliberately NOT the
    # ~30pt spacing every other fixture in this directory uses. The
    # existing fixtures are far enough apart that an operation on one line
    # cannot physically reach the next, which is exactly why they could not
    # catch replace_text erasing into the following line.
    #
    # Line 2's marker sits early enough on the line to fall within line 1's
    # horizontal extent, so an over-tall erase over line 1 genuinely
    # overlaps it rather than missing it by luck of the layout.
    page.insert_text((72, 100), "First line: REPLACE-THIS-LINE stands alone.", fontsize=12)
    page.insert_text((72, 117), "Second line: KEEP-ME-INTACT must survive untouched.", fontsize=12)
    doc.save(FIXTURES_DIR / "tight_line_spacing.pdf")
    doc.close()


def make_two_spans_one_line() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Two spans abutting on ONE line, with no gap at all between them: a
    # bold label immediately followed by normal body text, the commonest
    # multi-span line in real documents. The second span starts exactly
    # where the first one's advance width ends, so any horizontal slack
    # replace_text adds to its erase region lands directly on the second
    # span's first character.
    #
    # Every other fixture here is single-span-per-line, which is why none
    # of them could catch the width pad clipping a neighbour.
    label = "WARNING: "
    label_width = fitz.Font("hebo").text_length(label, fontsize=12)
    page.insert_text((72, 100), label, fontsize=12, fontname="hebo")
    page.insert_text(
        (72 + label_width, 100),
        "the rest of this line must survive.",
        fontsize=12,
        fontname="helv",
    )
    doc.save(FIXTURES_DIR / "two_spans_one_line.pdf")
    doc.close()


def make_embedded_custom_font() -> None:
    """A block whose font is genuinely embedded under a name that is
    neither a Base-14 name nor (after normalization) matches one -- the
    fixture Task 2's Tier-1-succeeds test needs. Embeds Base-14
    Helvetica's own font data under a fake alias, which both makes it a
    real embedded resource (not a name-only reference, unlike every other
    fixture in this file) and reproduces a real formatting mismatch this
    project found between how page.get_text() and page.get_fonts() report
    the same font (see _normalize_font_name's docstring in operations.py).
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page.insert_font(fontname="CustomCorporateFont", fontbuffer=helv.buffer)
    page.insert_text(
        (72, 100),
        "Embedded custom font target EMBEDDED-FONT-TARGET-555.",
        fontsize=12,
        fontname="CustomCorporateFont",
    )
    doc.save(FIXTURES_DIR / "embedded_custom_font.pdf")
    doc.close()


def make_move_target() -> None:
    """Two pages: page 0 has a block whose font is genuinely embedded under
    an alias that is NOT a Base-14 name; page 1 has no fonts embedded at
    all. move_block's cross-page fixture -- proves a cross-page move
    gracefully falls back to a Base-14 substitute (Tier 2 of _select_font)
    when the destination page does not already have the source's font,
    rather than crashing. Verified empirically: Tier 1 is genuinely tried
    against the destination page and genuinely fails to find a match here,
    exercising the real fallback path rather than assuming it.
    """
    doc = fitz.open()
    page0 = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page0.insert_font(fontname="MoveTargetFont", fontbuffer=helv.buffer)
    page0.insert_text(
        (72, 100),
        "Move target block MOVE-ME-777.",
        fontsize=12,
        fontname="MoveTargetFont",
    )
    doc.new_page(width=612, height=792)  # page 1: intentionally blank
    doc.save(FIXTURES_DIR / "move_target.pdf")
    doc.close()


def make_sanitize_target() -> None:
    """A single fixture carrying every kind of content sanitize_document
    should remove: Info-dict metadata, an XMP stream, invisible
    (render_mode=3) text, and a real embedded JavaScript action -- plus
    ordinary visible text that must survive. One fixture, not several,
    since sanitize_document exercises all of these together.

    The invisible-text and JavaScript constructions were both verified
    directly against the installed PyMuPDF version while writing this
    plan's design spec (docs/superpowers/specs/2026-08-30-document-
    sanitize-design.md's Testing strategy section) -- render_mode=3 text
    is genuinely extractable via get_text() before scrub and genuinely
    gone after; the low-level /Names /JavaScript catalog injection below
    genuinely produces bytes scrub(javascript=True) removes.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Visible text that must survive: KEEP-ME-VISIBLE.", fontsize=12)
    page.insert_text((72, 130), "INVISIBLE-HIDDEN-TEXT-777", fontsize=12, render_mode=3)

    doc.set_metadata(
        {
            "title": "Confidential Report",
            "author": "Jane Doe",
            "subject": "Internal review",
            "keywords": "secret,internal",
            "creator": "Acme Word Processor",
            "producer": "Acme PDF Engine",
            "creationDate": "D:20260101120000",
            "modDate": "D:20260102120000",
        }
    )
    doc.set_xml_metadata(
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:creator><rdf:Seq><rdf:li>Jane Doe</rdf:li></rdf:Seq></dc:creator>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
    )

    js_xref = doc.get_new_xref()
    doc.update_object(js_xref, '<< /S /JavaScript /JS (app.alert("EMBEDDED-JS-PAYLOAD");) >>')
    names_xref = doc.get_new_xref()
    doc.update_object(names_xref, f"<< /Names [ (EmbeddedJS) {js_xref} 0 R ] >>")
    doc.xref_set_key(doc.pdf_catalog(), "Names", f"<< /JavaScript {names_xref} 0 R >>")

    doc.save(FIXTURES_DIR / "sanitize_target.pdf")
    doc.close()


def make_no_metadata() -> None:
    """A fixture with no metadata/XMP set at all -- confirmed empirically
    that a freshly-created, saved PyMuPDF document has every metadata
    field blank and no XMP stream by default, so this needs no special
    construction beyond just not calling set_metadata()/set_xml_metadata().
    sanitize_document must not raise on it and must correctly report
    nothing was found.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Plain document with no metadata to scrub.", fontsize=12)
    doc.save(FIXTURES_DIR / "no_metadata.pdf")
    doc.close()


if __name__ == "__main__":
    make_simple_text()
    make_multi_page()
    make_image_only()
    make_mixed()
    make_colored_background()
    make_tight_line_spacing()
    make_two_spans_one_line()
    make_embedded_custom_font()
    make_move_target()
    make_sanitize_target()
    make_no_metadata()
    print("Fixtures written to", FIXTURES_DIR)
