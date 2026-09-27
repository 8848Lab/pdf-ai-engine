

from engine import operations  # noqa: E402

BLUE = (30, 30, 220)
BAND_BEHIND_IMAGE = (40, 380, 180, 480)
IMAGE_RECT = (72, 400, 136, 464)


def _png(rgb):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pix.set_rect(pix.irect, rgb)
    return pix.tobytes("png")


@pytest.mark.parametrize("crop", sorted(CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_image_erases_exactly_the_placement(rotation, crop, monkeypatch):
    # R14, the erase stage on its own (C8). A spy records the rect
    # replace_image hands to _clean_erase, and insert_image is disabled so
    # the exported page shows the erase alone: no image, one band-coloured
    # fill exactly on the placement, and the surroundings untouched.
    # Build the fixture BEFORE patching: the fixture itself uses insert_image.
    data = build_page(
        rotation=rotation, cropbox=CROPS[crop], band=BAND_BEHIND_IMAGE,
        image_rect=IMAGE_RECT, texts=((300, 200, "KEEP-ME"),),
    )
    # The band as the page itself reports it: a CropBox shifts page
    # coordinates, so BAND_BEHIND_IMAGE is not where the band is read back.
    original_band = _fills(fitz.open(stream=data, filetype="pdf")[0], BAND)
    assert len(original_band) == 1
    doc, handle = parse(data)
    target = doc.pages[0].images[0]
    erased = []
    real_erase = operations._clean_erase

    def spy_erase(page, rect):
        erased.append(fitz.Rect(rect))
        return real_erase(page, rect)

    monkeypatch.setattr(operations, "_clean_erase", spy_erase)
    monkeypatch.setattr(fitz.Page, "insert_image", lambda self, *args, **kwargs: None)
    replace_image(handle, 0, target, _png(BLUE))
    assert len(erased) == 1 and _on(erased[0], target.bbox), f"erased {erased}"
    page = exported(handle)[0]
    assert not page.get_images()
    assert "KEEP-ME" in page.get_text()
    band_fills = _fills(page, BAND)
    assert any(_on(r, original_band[0]) for r in band_fills), f"band gone: {band_fills}"
    assert [r for r in band_fills if _on(r, target.bbox)], (
        f"no band-coloured erase fill on the placement {target.bbox}: {band_fills}"
    )


@pytest.mark.parametrize("crop", sorted(CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_image_lands_exactly_on_the_placement(rotation, crop):
    # R4, the insert stage (R14 keeps the two stages in separate tests):
    # exactly one image remains, at the placement's own bbox, showing the
    # new colour.
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS[crop], image_rect=IMAGE_RECT))
    target = doc.pages[0].images[0]
    replace_image(handle, 0, target, _png(BLUE))
    page = exported(handle)[0]
    placements = [r for img in page.get_images() for r in page.get_image_rects(img[0])]
    assert len(placements) == 1, f"expected one image, got {placements}"
    assert _on(placements[0], target.bbox), (
        f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
    )
    r, g, b = _centre_pixel(page, target.bbox)
    assert b > 200 and r < 80, f"placement shows {(r, g, b)}, expected the new blue"


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_image_works_on_a_left_overhang_page(rotation):
    # replace_image draws no text, so a CropBox overhang is supported and
    # must stay supported once the refusal gate exists (Task 7).
    doc, handle = parse(build_page(rotation=rotation, cropbox="[-40 0 612 792]", image_rect=IMAGE_RECT))
    target = doc.pages[0].images[0]
    replace_image(handle, 0, target, _png(BLUE))
    page = exported(handle)[0]
    placements = [r for img in page.get_images() for r in page.get_image_rects(img[0])]
    assert len(placements) == 1 and _on(placements[0], target.bbox), placements
