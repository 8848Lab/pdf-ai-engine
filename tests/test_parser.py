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


def test_parses_image_metadata_fields_from_image_only_document():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    image = doc.pages[0].images[0]
    assert image.xref > 0
    assert image.width == 64
    assert image.height == 64
    assert image.placement_count == 1
    handle.close()


def test_parses_two_placements_of_one_xref_as_two_images():
    # The same image stream placed twice shares one xref but must surface as
    # two distinct Images, each with its own bbox -- that is what lets the
    # session registry give each placement its own id, and what replace_image
    # relies on to target exactly one of them.
    pdf_bytes = (FIXTURES / "image_two_placements.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    images = doc.pages[0].images
    assert len(images) == 2
    assert images[0].xref == images[1].xref
    assert images[0].placement_count == 2
    assert images[1].placement_count == 2
    assert images[0].bbox != images[1].bbox
    handle.close()


def test_document_placement_count_spans_pages_while_placement_count_does_not():
    # image_across_pages.pdf places ONE image stream on two pages, so both
    # placements share an xref. Each page's own placement_count is 1 -- true
    # but useless on its own, since replacing either one leaves the original
    # referenced from the other page.
    pdf_bytes = (FIXTURES / "image_across_pages.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    page0_image = doc.pages[0].images[0]
    page1_image = doc.pages[1].images[0]

    assert page0_image.xref == page1_image.xref
    assert page0_image.placement_count == 1
    assert page1_image.placement_count == 1
    assert page0_image.document_placement_count == 2
    assert page1_image.document_placement_count == 2
    handle.close()


def test_document_placement_count_equals_placement_count_within_one_page():
    # The two placements of image_two_placements.pdf are both on page 0, so
    # the document-wide count must not double-count them.
    pdf_bytes = (FIXTURES / "image_two_placements.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    for image in doc.pages[0].images:
        assert image.placement_count == 2
        assert image.document_placement_count == 2
    handle.close()


def test_document_placement_count_is_one_for_a_lone_image():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    image = doc.pages[0].images[0]
    assert image.placement_count == 1
    assert image.document_placement_count == 1
    handle.close()
