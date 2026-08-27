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


if __name__ == "__main__":
    make_simple_text()
    make_multi_page()
    make_image_only()
    make_mixed()
    print("Fixtures written to", FIXTURES_DIR)
