from pathlib import Path

from engine.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_simple_text_document():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.index == 0
    all_text = " ".join(block.text for block in page.text_blocks)
    assert "REDACT-ME-12345" in all_text
    handle.close()


def test_parses_multi_page_document_preserving_order():
    pdf_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    assert len(doc.pages) == 3
    for i, page in enumerate(doc.pages):
        assert page.index == i
        all_text = " ".join(block.text for block in page.text_blocks)
        assert f"PAGE-MARK-{i + 1}" in all_text
    handle.close()


def test_parses_image_bbox_from_image_only_document():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert len(page.images) == 1
    x0, y0, x1, y1 = page.images[0].bbox
    assert x1 > x0
    assert y1 > y0
    handle.close()


def test_parses_mixed_text_and_image_document():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert len(page.images) == 1
    all_text = " ".join(block.text for block in page.text_blocks)
    assert "PATIENT-0042" in all_text
    handle.close()


def test_page_dimensions_are_populated():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert page.width == 612.0
    assert page.height == 792.0
    handle.close()
