### Task 4: Background sampling (D2, R3)

**Files:**
- Modify: `engine/operations.py`:
  - the `engine.geometry` import (add `to_display_matrix`)
  - `_sample_background_color` (lines 233–247)
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes: `engine.geometry.to_display_matrix` from Task 1; `build_page`, `block` and `exported` from Task 3.
- Produces:
  - no new engine names. `_sample_background_color` keeps its signature `(page, rect) -> tuple[float, float, float]`.
  - in `tests/test_page_geometry.py`: `_centre_pixel(page, bbox)`, `BAND_BEHIND_LOW`, `SAMPLE_CROPS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
from engine.geometry import to_display_matrix  # noqa: E402
from engine.operations import _sample_background_color  # noqa: E402
from tests.geometry_helpers import BAND, BAND_RGB  # noqa: E402

BAND_BEHIND_LOW = (60, 680, 400, 720)
SAMPLE_CROPS = {"plain": None, "contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _centre_pixel(page, bbox):
    pix = page.get_pixmap()
    c = fitz.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) * to_display_matrix(page)
    return tuple(pix.pixel(int(c.x - pix.x), int(c.y - pix.y))[:3])


@pytest.mark.parametrize("crop", sorted(SAMPLE_CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_background_sample_reads_the_colour_behind_the_block(rotation, crop):
    # D2, tested on the sampler itself (C3). Through an erase, a contained or
    # oversized crop would also move the fill (R11, Task 5), and the old fill
    # landing elsewhere leaves the original band showing at the checked spot
    # -- a false green. Sampling alone is isolated here.
    doc, handle = parse(build_page(rotation=rotation, cropbox=SAMPLE_CROPS[crop], band=BAND_BEHIND_LOW))
    rect = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    rgb = tuple(round(c * 255) for c in _sample_background_color(handle[0], rect))
    assert rgb == BAND_RGB


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_delete_block_erases_to_the_true_background_colour(rotation):
    # End to end on a plain page only: with no CropBox the fill already lands
    # on target (R11 needs a crop), so a wrong colour here is sampling alone.
    doc, handle = parse(build_page(rotation=rotation, band=BAND_BEHIND_LOW))
    b = block(doc, "LOW-MARKER")
    delete_block(handle, 0, b)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    r, g, bl = _centre_pixel(page, b.bbox)
    assert bl > 240 and r < 200, f"erased area is {(r, g, bl)}, expected the band {BAND_RGB}"


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_sampling_is_exact_on_a_fractional_size_page(rotation):
    # R3: a 100.1 x 800.1 page renders 101 x 801 pixels, so inferring scale
    # from raster size (1.008991) lands samples on the wrong pixels; the old
    # sampler also never rotates its points (D2), so every rotation fails.
    # The four sample points of rect (40, 700, 60, 720) are (50, 697),
    # (50, 723), (37, 710) and (63, 710). Each is the centre of a 2x2 band
    # patch, so under the identity render it falls on a pixel INSIDE the
    # patch; a sample that misses by a few pixels reads white.
    doc = fitz.open()
    page = doc.new_page(width=100.1, height=800.1)
    for x, y in ((50, 697), (50, 723), (37, 710), (63, 710)):
        page.draw_rect(fitz.Rect(x - 1, y - 1, x + 1, y + 1), color=None, fill=BAND)
    page.set_rotation(rotation)
    rgb = tuple(round(c * 255) for c in _sample_background_color(page, fitz.Rect(40, 700, 60, 720)))
    assert rgb == BAND_RGB
    doc.close()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured on the engine after Task 3: **16 failed, 52 passed.**
- `test_background_sample_reads_the_colour_behind_the_block`: the 90, 180 and 270 cases fail for all three crops (9). The rotation-0 cases pass.
- `test_delete_block_erases_to_the_true_background_colour[90]`, `[180]` and `[270]` fail; the erased area reads white. `[0]` passes.
- `test_sampling_is_exact_on_a_fractional_size_page` fails at **all four** rotations: rotation 0 on scale (R3), the others on scale and on unrotated points (D2).
- All Task 3 tests still pass.

- [ ] **Step 3: Implement the sampling change**

Add `to_display_matrix` to the `engine.geometry` import in `engine/operations.py` (plan ruling S1: each task imports only the names it uses).

In `_sample_background_color`, replace:

```python
    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width
```

with:

```python
    # Identity render: one pixel per point, in DISPLAY space. Sample points
    # are in UNROTATED space, so each is mapped through the display matrix
    # and the pixmap's own origin is subtracted. Scale is never inferred from
    # raster size -- a 100.1pt page renders 101 pixels wide (spec R3).
    pixmap = page.get_pixmap()
    to_display = to_display_matrix(page)
```

and replace:

```python
        x_px = max(0, min(pixmap.width - 1, int(x_pt * zoom)))
        y_px = max(0, min(pixmap.height - 1, int(y_pt * zoom)))
```

with:

```python
        display = fitz.Point(x_pt, y_pt) * to_display
        x_px = max(0, min(pixmap.width - 1, int(display.x - pixmap.x)))
        y_px = max(0, min(pixmap.height - 1, int(display.y - pixmap.y)))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 68 passed.

- [ ] **Step 5: Confirm rotation 0 is unchanged on integer pages**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: all pass, and none of the 227 pre-Merge-A tests was edited.

Why this must hold: on a 612 × 792 page at rotation 0, the old `zoom` is exactly 1.0 and the new matrix is the identity. Both compute `int(x)`. If an existing sampling test changed result, stop and report it; do not adjust the test.

- [ ] **Step 6: Commit**

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "fix: sample background colour in display space, at true scale

Sample points are in unrotated page space but were fed straight into a
pixmap rendered in rotated display space, so erases on rotated pages filled
with the wrong colour. Scale was also inferred from rounded raster size,
which misses on fractional-size pages at every rotation.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

