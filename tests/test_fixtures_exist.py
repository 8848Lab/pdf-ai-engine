from pathlib import Path

import pymupdf as fitz

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_FILES = [
    "simple_text.pdf",
    "multi_page.pdf",
    "image_only.pdf",
    "mixed.pdf",
    "colored_background.pdf",
    "tight_line_spacing.pdf",
    "two_spans_one_line.pdf",
]


def test_all_fixture_files_exist_and_are_nonempty():
    for name in EXPECTED_FILES:
        path = FIXTURES / name
        assert path.exists(), f"missing fixture: {name}"
        assert path.stat().st_size > 0, f"empty fixture: {name}"


def test_all_fixture_files_are_openable_pdfs():
    for name in EXPECTED_FILES:
        handle = fitz.open(FIXTURES / name)
        assert handle.page_count > 0
        handle.close()


def test_multi_page_fixture_has_three_pages():
    handle = fitz.open(FIXTURES / "multi_page.pdf")
    assert handle.page_count == 3
    handle.close()
