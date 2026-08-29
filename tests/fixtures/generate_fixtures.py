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


if __name__ == "__main__":
    make_simple_text()
    make_multi_page()
    make_image_only()
    make_mixed()
    make_colored_background()
    make_tight_line_spacing()
    make_two_spans_one_line()
    print("Fixtures written to", FIXTURES_DIR)
