### Task 6: Image placement (R4)

**Files:**
- Modify: `engine/operations.py`, `replace_image`'s `insert_image` call (line 972)
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes: `engine.geometry.at_rotation_zero` from Task 1 (already imported by Task 5); `build_page` from Task 3; `_centre_pixel` from Task 4; `CROPS`, `_fills`, `_on` from Task 5.
- Produces: in `tests/test_page_geometry.py`: `BLUE`, `IMAGE_RECT`, `_png(rgb) -> bytes`. Task 7 uses them.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
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
```

Two traps in the erase-stage test, both already handled above:
- **Build the fixture BEFORE patching.** The fixture itself calls `insert_image`, so disabling it first leaves no image and `images[0]` raises `IndexError`.
- **A CropBox shifts page coordinates.** The band is read back from the fixture itself, never compared with the rect it was drawn at.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured on the engine after Task 5: **6 failed, 100 passed.**
- `test_replace_image_lands_exactly_on_the_placement`: the 90, 180 and 270 cases fail with "image landed at", for both crops. The rotation-0 cases pass.
- `test_replace_image_erases_exactly_the_placement` passes at every case. It pins the erase stage, which Task 5 fixed. On the engine after Task 4 it was measured red at contained 90/180/270 and oversized 180/270.
- `test_replace_image_works_on_a_left_overhang_page` passes; it is Task 7's guard against over-refusal.

- [ ] **Step 3: Implement the fix**

In `replace_image`, replace:

```python
        page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)
```

with:

```python
        # At rotation 0 (spec R4): on a rotated page with a CropBox,
        # insert_image lands 40-52pt from the rect it was given. The rect is
        # unchanged; only the page's orientation is, and it is restored.
        with at_rotation_zero(page):
            page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)
```

Keep it inside the existing `try`, so a failure still becomes `ValueError`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 106 passed.

- [ ] **Step 5: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "fix: place replacement images correctly on rotated, cropped pages

Since replace_image shipped, a replacement on a page with both a CropBox and
rotation landed 40-52pt from the requested spot, leaving the placement
blank. The image is now inserted at rotation 0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

