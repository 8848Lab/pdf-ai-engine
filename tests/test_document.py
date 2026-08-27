from engine.document import Document, Image, Page, TextBlock


def test_text_block_holds_its_fields():
    block = TextBlock(text="hello", bbox=(0.0, 0.0, 10.0, 5.0), font="Helvetica", size=12.0)
    assert block.text == "hello"
    assert block.bbox == (0.0, 0.0, 10.0, 5.0)
    assert block.font == "Helvetica"
    assert block.size == 12.0


def test_image_holds_its_bbox():
    image = Image(bbox=(0.0, 0.0, 64.0, 64.0))
    assert image.bbox == (0.0, 0.0, 64.0, 64.0)


def test_page_defaults_to_empty_lists():
    page = Page(index=0, width=612.0, height=792.0)
    assert page.text_blocks == []
    assert page.images == []


def test_page_holds_provided_lists():
    block = TextBlock(text="x", bbox=(0.0, 0.0, 1.0, 1.0), font="Helvetica", size=10.0)
    image = Image(bbox=(0.0, 0.0, 1.0, 1.0))
    page = Page(index=0, width=612.0, height=792.0, text_blocks=[block], images=[image])
    assert page.text_blocks == [block]
    assert page.images == [image]


def test_document_holds_pages_in_order():
    page0 = Page(index=0, width=612.0, height=792.0)
    page1 = Page(index=1, width=612.0, height=792.0)
    doc = Document(pages=[page0, page1])
    assert doc.pages == [page0, page1]
    assert doc.pages[1].index == 1


def test_document_defaults_to_empty_pages():
    doc = Document()
    assert doc.pages == []
