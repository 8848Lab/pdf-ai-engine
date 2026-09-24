# Image Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `replace_image`, an engine operation that swaps the bitmap of one image placement for caller-supplied bytes — aspect-preserved, centered in the existing rectangle, leaving every other placement of the same `xref` untouched — and wire it through the session, API, and manual-controls UI.

**Architecture:** `replace_image` validates everything up front (`_validate_target`, inline-image rejection, byte-length caps, a `fitz.Pixmap` decode gate), then performs exactly two mutations: `_clean_erase(page, rect)` followed by `page.insert_image(rect, stream=..., keep_proportion=True)`. It deliberately does **not** call PyMuPDF's `Page.replace_image`, which is xref-global. The `Image` dataclass grows the fields (`xref`, `width`, `height`, `placement_count`) the parser can now supply via `get_image_info(xrefs=True)`, and `webui/session.py` grows an image registry parallel to the block registry, drawing ids from the same monotonic counter.

**Tech Stack:** Python 3.13, PyMuPDF (`pymupdf`) 1.28.2, FastAPI + Starlette `TestClient`, pytest, vanilla JS frontend (no build step).

**Spec:** `docs/superpowers/specs/2026-09-02-image-replacement-design.md`

## Global Constraints

- **PyMuPDF is pinned at 1.28.2.** Every behavior this plan relies on was verified empirically against that version (see "Verified behaviors" below). Do not upgrade it as part of this work.
- **`_MAX_IMAGE_BYTES = 20 * 1024 * 1024`** (20 MB) — the exact cap from the spec.
- **No AI tool this pass.** `webui/ai/` is not touched at all: not `tools.py`, not `loop.py`, not `SYSTEM_PROMPT`, not any provider. The model cannot produce image bytes.
- **No use of `Page.replace_image`** anywhere — it is xref-global by nature and would change other placements.
- **`_validate_target` and `_clean_erase` are reused unchanged.** No task modifies either helper.
- **`Page.rect.contains()` is NOT used here.** Unlike `move_block`/`insert_block`, `replace_image`'s rectangle is not caller-chosen — it is an existing placement's own bbox read out of the document, which may legitimately overhang a page edge in a real PDF. `_validate_target`'s `intersects` check is correct for this operation; adding a `contains` check would reject valid real-world documents.
- **No orphan-resource cleanup.** When the replaced placement was its xref's only placement, the original image object is left unreferenced in the file, reclaimed later by `export()`'s `garbage=3` / `sanitize_document`.
- **No aspect-ratio distortion and no cropping.** `keep_proportion=True` contain-fit only; the letterbox margin shows the background color laid down by `_clean_erase`.
- **Every `ValueError` message ends with a "Nothing has been modified." clause when that is true**, matching `move_block`/`insert_block`'s existing convention.
- **Run tests with the repo venv:** `./.venv/Scripts/python.exe -m pytest ...` from `D:/Coding/8848 Lab/pdf-ai`.
- **`from tests.image_helpers import solid_png` is the correct import form** — verified working. `tests/` has no `__init__.py`, but `pyproject.toml`'s `pythonpath = ["."]` puts the repo root on `sys.path`, so `tests` resolves as an implicit namespace package. Do not add a `tests/__init__.py`.

## Verified behaviors (spiked against PyMuPDF 1.28.2 — do not re-litigate)

These were confirmed by running real code before this plan was written. Treat them as facts:

1. `page.get_image_info(xrefs=True)` returns one dict **per placement**, with keys including `bbox`, `xref`, `width`, `height`. For a 64×64 PNG placed at `Rect(72,100,136,164)` it returned `xref=5, width=64, height=64, bbox=(72.0, 100.0, 136.0, 164.0)`.
2. Inserting the **same** `stream=` bytes twice on one page reuses one xref: `get_image_info(xrefs=True)` returned two entries both with `xref=5`, and `page.get_image_rects(5)` returned both rects. This is what makes the two-placement fixture work.
3. `add_redact_annot(rect, fill=...)` + `apply_redactions(images=2, graphics=1, text=0)` (i.e. `_clean_erase`) followed by `insert_image(rect, stream=blue, keep_proportion=True)` changed **only the targeted placement**: the target's center pixel read `(30, 30, 220)` (the new blue) while the other placement's center still read `(200, 30, 30)` (the original red).
4. A 200×50 image inserted with `keep_proportion=True` into a 64×64 box letterboxes: center read blue `(30, 30, 220)`, while 8% and 92% down the box both read the background `(255, 255, 255)`.
5. `fitz.Pixmap(b"not an image")` raises `FzErrorFormat` ("code=7: unknown image file format"). It is **not** a `ValueError`, so the decode gate must catch broad `Exception` and re-raise as `ValueError`.

## Spec deviations (rulings — these override the spec where they conflict)

**R1 — Image controls are rows, not positioned overlays.** The spec's frontend section says image overlays are "positioned over its `bbox` using the same page-image-relative coordinate math the block overlays already use." That coordinate math does not exist. `webui/static/app.js`'s `render()` appends `div.block-controls` as plain stacked rows after the page `<img>`, and `session.get_blocks_summary()` does not even return a bbox. Image controls therefore follow the **real** existing pattern: a `div.image-controls` row per image, appended after the block rows, with the bbox shown as caption text. Building absolute-positioned overlays would be a new UI paradigm, not "the same as blocks."

**R2 — Every state-returning endpoint gains `images`, not just `/api/upload` and `/api/state`.** The spec says adding `images` to those two is "the only change to existing endpoints." That ships a visible bug: `render(data)` rebuilds the entire `#pages` DOM from whatever the last response returned, so after a `/api/redact` or `/api/ai-instruct` (which would return no `images` key) every image row would silently disappear until the next full state refresh. All eight handlers that return session state therefore go through one shared `_state_payload()` helper returning `{pages, blocks, images}`. The frontend still defends with `state.images || []`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `tests/fixtures/generate_fixtures.py` | Modify | Add `make_image_two_placements()` producing a one-page PDF with the same image stream placed at two non-overlapping rects. |
| `tests/fixtures/image_two_placements.pdf` | Create (generated) | Checked-in fixture; `placement_count == 2`. |
| `tests/image_helpers.py` | Create | `solid_png(width, height, color)` — shared PNG byte builder for `test_operations.py` and `test_webui.py`. |
| `tests/test_fixtures_exist.py` | Modify | Register the new fixture in `EXPECTED_FILES`. |
| `engine/document.py` | Modify | `Image` gains `xref`, `width`, `height`, `placement_count` (all required, matching `TextBlock`'s all-required style). |
| `engine/parser.py` | Modify | Build `Image`s from `get_image_info(xrefs=True)` + `get_image_rects()`. |
| `tests/test_document.py` | Modify | Fix the two `Image(bbox=...)` constructions that the new required fields break. |
| `tests/test_parser.py` | Modify | Cover the new fields on both the one-placement and two-placement fixtures. |
| `engine/operations.py` | Modify | Add `_MAX_IMAGE_BYTES` and `replace_image`. Nothing else changes. |
| `tests/test_operations.py` | Modify | Engine-level coverage: happy path, placement isolation, contain-fit letterbox, six raise-paths. |
| `webui/session.py` | Modify | Image registry, `_refresh_blocks` → `_refresh_state`, `_build_block_registry` → `_build_registries`, `get_image`, `get_images_summary`, `replace_image` wrapper. |
| `webui/main.py` | Modify | `_state_payload()` helper, `POST /api/replace-image` (multipart). |
| `tests/test_webui.py` | Modify | Route coverage + the `images` key on every state-returning endpoint. |
| `webui/static/app.js` | Modify | Render image rows; wire the multipart Replace button. |
| `webui/static/styles.css` | Modify | `.image-controls` styling, consistent with `.block-controls`. |
| `README.md` | Modify | Document `replace_image` under Operations. |

---

### Task 1: `Image` model, parser fields, and the two-placement fixture

**Files:**
- Modify: `tests/fixtures/generate_fixtures.py`
- Create: `tests/fixtures/image_two_placements.pdf` (by running the generator)
- Modify: `tests/test_fixtures_exist.py:6-14`
- Modify: `engine/document.py:19-21`
- Modify: `engine/parser.py:35`
- Modify: `tests/test_document.py:12-14`, `tests/test_document.py:23-28`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `engine.document.Image(bbox: tuple[float, float, float, float], xref: int, width: int, height: int, placement_count: int)` — all fields required, positional order as listed. `engine.parser.parse()` keeps its existing `(Document, fitz.Document)` return type. Fixture `tests/fixtures/image_two_placements.pdf`, one page 612×792, the same red PNG at `Rect(72, 100, 136, 164)` and `Rect(300, 100, 364, 164)`.

- [ ] **Step 1: Add the fixture generator function**

In `tests/fixtures/generate_fixtures.py`, after `make_image_only()`:

```python
def make_image_two_placements() -> None:
    """The SAME image stream placed at two non-overlapping rectangles on one
    page. Verified on PyMuPDF 1.28.2: inserting identical `stream=` bytes
    twice reuses a single xref, so get_image_info(xrefs=True) reports two
    entries sharing one xref and get_image_rects() returns both rects --
    exactly the placement_count == 2 case replace_image must not disturb.
    Every other image fixture here is single-placement, which is why none of
    them can catch a replace that leaks across placements.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    red = _red_square_png()
    page.insert_image(fitz.Rect(72, 100, 136, 164), stream=red)
    page.insert_image(fitz.Rect(300, 100, 364, 164), stream=red)
    doc.save(FIXTURES_DIR / "image_two_placements.pdf")
    doc.close()
```

And add `make_image_two_placements()` to the `__main__` block, after `make_image_only()`.

- [ ] **Step 2: Generate the fixture and confirm it has the shape we expect**

Run:
```bash
./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py
./.venv/Scripts/python.exe -c "import pymupdf as fitz; p=fitz.open('tests/fixtures/image_two_placements.pdf')[0]; i=p.get_image_info(xrefs=True); print(len(i), [e['xref'] for e in i], len(p.get_image_rects(i[0]['xref'])))"
```
Expected output: `2 [<n>, <n>] 2` — two entries, **the same** xref twice, two rects. If the two xrefs differ, the fixture is wrong; stop and report rather than proceeding.

- [ ] **Step 3: Register the fixture in the existence test**

In `tests/test_fixtures_exist.py`, add `"image_two_placements.pdf",` to `EXPECTED_FILES` after `"image_only.pdf",`.

- [ ] **Step 4: Write the failing parser tests**

Append to `tests/test_parser.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_parser.py -v`
Expected: the two new tests FAIL with `AttributeError: 'Image' object has no attribute 'xref'`.

- [ ] **Step 6: Extend the `Image` dataclass**

In `engine/document.py`, replace the `Image` dataclass:

```python
@dataclass
class Image:
    """One PLACEMENT of an image on a page -- not one image object. The same
    underlying PDF image object (`xref`) drawn twice on a page produces two
    Images here, sharing an xref but carrying different bboxes, so each
    placement can be targeted independently.
    """
    bbox: tuple[float, float, float, float]
    xref: int
    width: int
    height: int
    placement_count: int
```

- [ ] **Step 7: Fix the two constructions the new required fields break**

In `tests/test_document.py`, replace lines 12-14:

```python
def test_image_holds_its_fields():
    image = Image(bbox=(0.0, 0.0, 64.0, 64.0), xref=7, width=64, height=64, placement_count=1)
    assert image.bbox == (0.0, 0.0, 64.0, 64.0)
    assert image.xref == 7
    assert image.width == 64
    assert image.height == 64
    assert image.placement_count == 1
```

and in `test_page_holds_provided_lists`, replace the `image = Image(bbox=(0.0, 0.0, 1.0, 1.0))` line with:

```python
    image = Image(bbox=(0.0, 0.0, 1.0, 1.0), xref=1, width=8, height=8, placement_count=1)
```

- [ ] **Step 8: Populate the new fields in the parser**

In `engine/parser.py`, replace the single `images = [...]` line (line 35) with:

```python
        images = []
        for info in pdf_page.get_image_info(xrefs=True):
            xref = info["xref"]
            # An inline image (xref 0) is embedded directly in the content
            # stream with no image object to query, so get_image_rects() has
            # nothing to count -- it is still listed so the operator can see
            # it, but it is a single unqueryable placement by definition.
            placement_count = 1 if xref == 0 else len(pdf_page.get_image_rects(xref))
            images.append(
                Image(
                    bbox=tuple(info["bbox"]),
                    xref=xref,
                    width=info["width"],
                    height=info["height"],
                    placement_count=placement_count,
                )
            )
```

- [ ] **Step 9: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, all tests. If `tests/test_visual_regression.py` or any other module constructs an `Image`, fix it the same way as Step 7.

- [ ] **Step 10: Commit**

```bash
git add tests/fixtures/generate_fixtures.py tests/fixtures/image_two_placements.pdf tests/test_fixtures_exist.py engine/document.py engine/parser.py tests/test_document.py tests/test_parser.py
git commit -m "feat: surface xref, pixel size, and placement count on parsed images

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `replace_image` engine operation

**Files:**
- Modify: `engine/operations.py` (import `Image`; add `_MAX_IMAGE_BYTES` and `replace_image`)
- Create: `tests/image_helpers.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: `engine.document.Image` with `bbox`/`xref` from Task 1; the existing `_validate_target(handle, page_index, bbox) -> (fitz.Page, fitz.Rect)` and `_clean_erase(page, rect) -> None`.
- Produces: `engine.operations.replace_image(handle: fitz.Document, page_index: int, target: Image, new_image_bytes: bytes) -> None`, raising `ValueError` on every invalid input. `engine.operations._MAX_IMAGE_BYTES: int`. `tests.image_helpers.solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes`.

- [ ] **Step 1: Create the shared PNG helper**

Create `tests/image_helpers.py`:

```python
"""Small PNG byte builders shared by the engine and webui test modules.

Lives here rather than in generate_fixtures.py because these are built at
TEST time (as replacement-image inputs), not baked into a checked-in
fixture file the way the fixture PDFs are.
"""
import pymupdf as fitz


def solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """A solid-color PNG of the given pixel dimensions. `color` is 0-255 RGB."""
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height))
    pixmap.set_rect(pixmap.irect, color)
    return pixmap.tobytes("png")
```

- [ ] **Step 2: Write the failing engine tests**

Append to `tests/test_operations.py`:

```python
def _sample_page_pixel(page, rect, fx=0.5, fy=0.5):
    """Read the rendered pixel at a fractional position inside `rect`."""
    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width
    x = int((rect[0] + (rect[2] - rect[0]) * fx) * zoom)
    y = int((rect[1] + (rect[3] - rect[1]) * fy) * zoom)
    x = max(0, min(pixmap.width - 1, x))
    y = max(0, min(pixmap.height - 1, y))
    return pixmap.pixel(x, y)


def test_replace_image_swaps_the_bitmap_of_the_target_placement():
    # image_only.pdf's sole image is a solid red (200, 30, 30) square; the
    # replacement is solid blue, so a correct swap is a pure pixel-color
    # question with no layout ambiguity.
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].images[0]

    replace_image(handle, page_index=0, target=target, new_image_bytes=solid_png(64, 64, (30, 30, 220)))

    pixel = _sample_page_pixel(handle[0], target.bbox)
    assert pixel[2] > 150 and pixel[0] < 100, (
        f"expected the replacement blue at the target's center, got {pixel}"
    )
    handle.close()


def test_replace_image_leaves_the_other_placement_of_the_same_xref_untouched():
    # The whole reason this operation does not use PyMuPDF's xref-global
    # Page.replace_image: both placements share one xref, and replacing one
    # must not touch the other.
    pdf_bytes = (FIXTURES / "image_two_placements.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    first, second = doc.pages[0].images
    assert first.xref == second.xref

    replace_image(handle, page_index=0, target=first, new_image_bytes=solid_png(64, 64, (30, 30, 220)))

    replaced = _sample_page_pixel(handle[0], first.bbox)
    untouched = _sample_page_pixel(handle[0], second.bbox)
    assert replaced[2] > 150 and replaced[0] < 100, f"target not replaced, got {replaced}"
    assert untouched[0] > 150 and untouched[2] < 100, (
        f"the OTHER placement of the same xref changed too, got {untouched} -- "
        f"expected the original red"
    )
    handle.close()


def test_replace_image_contains_and_letterboxes_rather_than_stretching():
    # A 200x50 image into a 64x64 box: contain-fit centers it and leaves
    # background-colored bands top and bottom. A stretch-to-fill would make
    # every sampled point blue instead.
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].images[0]

    replace_image(handle, page_index=0, target=target, new_image_bytes=solid_png(200, 50, (30, 30, 220)))

    center = _sample_page_pixel(handle[0], target.bbox, 0.5, 0.5)
    top = _sample_page_pixel(handle[0], target.bbox, 0.5, 0.08)
    bottom = _sample_page_pixel(handle[0], target.bbox, 0.5, 0.92)
    assert center[2] > 150 and center[0] < 100, f"expected blue at the center, got {center}"
    assert min(top) > 200, f"expected a background letterbox band at the top, got {top}"
    assert min(bottom) > 200, f"expected a background letterbox band at the bottom, got {bottom}"
    handle.close()


@pytest.mark.parametrize(
    "mutate_target, image_bytes, expected_fragment",
    [
        (lambda img: replace(img, bbox=(100.0, 100.0, 100.0, 200.0)), b"png-bytes-placeholder", "degenerate"),
        (lambda img: replace(img, bbox=(5000.0, 5000.0, 5064.0, 5064.0)), b"png-bytes-placeholder", "off-page"),
        (lambda img: replace(img, xref=0), b"png-bytes-placeholder", "inline"),
        (lambda img: img, b"", "empty"),
        (lambda img: img, b"x" * (20 * 1024 * 1024 + 1), "cap"),
        (lambda img: img, b"not an image", "decode"),
    ],
    ids=["degenerate-bbox", "off-page-bbox", "inline-image", "empty-bytes", "over-cap", "undecodable"],
)
def test_replace_image_raises_and_leaves_the_document_unmodified(
    mutate_target, image_bytes, expected_fragment
):
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    original = doc.pages[0].images[0]
    before = _sample_page_pixel(page, original.bbox)

    payload = solid_png(64, 64, (30, 30, 220)) if image_bytes == b"png-bytes-placeholder" else image_bytes

    with pytest.raises(ValueError) as excinfo:
        replace_image(handle, page_index=0, target=mutate_target(original), new_image_bytes=payload)
    assert expected_fragment in str(excinfo.value).lower()

    # The ORIGINAL placement must be untouched in every failure case -- this
    # operation validates fully before it erases anything.
    assert _sample_page_pixel(page, original.bbox) == before
    handle.close()


def test_replace_image_raises_on_an_out_of_range_page_index():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].images[0]

    with pytest.raises(ValueError, match="out of range"):
        replace_image(handle, page_index=9, target=target, new_image_bytes=solid_png(8, 8, (0, 0, 255)))
    handle.close()
```

Add to the existing import block at the top of `tests/test_operations.py`: `replace_image` into the `from engine.operations import (...)` list (alphabetical, after `redact_region`), and two new imports after the `from engine.document import TextBlock` line:

```python
from engine.document import Image, TextBlock
from tests.image_helpers import solid_png
```

(`replace` from `dataclasses` is already imported at line 1 and works on the `Image` dataclass unchanged.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k replace_image -v`
Expected: collection error / FAIL with `ImportError: cannot import name 'replace_image' from 'engine.operations'`.

- [ ] **Step 4: Implement `replace_image`**

In `engine/operations.py`, change the import on line 12 to:

```python
from engine.document import Image, TextBlock
```

Then add, after `insert_block` (i.e. before `get_metadata_summary`):

```python
# A generous ceiling that still refuses an accidental multi-hundred-MB
# upload before it is decoded. Not a security boundary -- this tool is
# single-operator and local -- just a guard against pathological input.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def replace_image(
    handle: fitz.Document,
    page_index: int,
    target: Image,
    new_image_bytes: bytes,
) -> None:
    """Swap the bitmap of ONE image placement for new_image_bytes, scaled to
    fit inside the placement's existing rectangle with its own aspect ratio
    preserved and centered. The uncovered letterbox margin shows the page's
    sampled background color.

    Deliberately does not use PyMuPDF's Page.replace_image, which replaces
    every placement of an xref document-wide: when the same image object is
    drawn in several spots, this changes only the one the caller targeted.
    "Replace this logo everywhere" is a separate, later operation. See the
    design spec's "Non-goals" section.

    Unlike move_block/insert_block, the rectangle here is not caller-chosen
    -- it is an existing placement's own bbox -- so _validate_target's
    intersects check is the right guard and no full-containment check is
    applied: a real document may legitimately place an image overhanging a
    page edge, and refusing to edit it would be wrong.

    When the targeted placement was its xref's only placement, the original
    image object is left in the file unreferenced; export()'s garbage
    collection reclaims it.

    Raises:
        ValueError: page_index out of range, or target.bbox degenerate or
            fully off-page (see _validate_target); target is an inline
            image (xref 0), which has no image object to reason about;
            new_image_bytes is empty, over _MAX_IMAGE_BYTES, or not a
            raster image PyMuPDF can decode. All validation completes
            before any mutation, so a raise always leaves the document
            unmodified.
    """
    page, rect = _validate_target(handle, page_index, target.bbox)

    if target.xref == 0:
        raise ValueError(
            "target is an inline image (xref 0): it is embedded directly in the "
            "page's content stream with no image object to replace. Nothing has "
            "been modified."
        )

    if not new_image_bytes:
        raise ValueError(
            "new_image_bytes is empty -- there is nothing to draw. Nothing has "
            "been modified."
        )

    if len(new_image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError(
            f"new_image_bytes is {len(new_image_bytes)} bytes, over the "
            f"{_MAX_IMAGE_BYTES}-byte cap. Nothing has been modified."
        )

    # Decode once up front purely as a validity gate, so a bad upload fails
    # BEFORE the erase rather than leaving a hole in the page. The decoded
    # Pixmap is intentionally discarded -- insert_image re-decodes from the
    # stream itself. PyMuPDF raises its own FzError types here (verified:
    # FzErrorFormat on garbage bytes), not ValueError, hence the broad catch.
    try:
        fitz.Pixmap(new_image_bytes)
    except Exception as exc:  # noqa: BLE001 -- normalizing any decode failure
        raise ValueError(
            f"new_image_bytes could not be decoded as a raster image: "
            f"{type(exc).__name__}: {exc}. Nothing has been modified."
        ) from exc

    _clean_erase(page, rect)
    page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k replace_image -v`
Expected: 10 test cases PASS (3 behavior tests + 6 parametrized raise cases + the out-of-range page-index test).

- [ ] **Step 6: Run the full suite to confirm no regression**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS. `_clean_erase` and `_validate_target` gained a caller but were not modified, so every existing test must still pass unchanged. If any existing test fails, stop — something was modified that should not have been.

- [ ] **Step 7: Commit**

```bash
git add engine/operations.py tests/image_helpers.py tests/test_operations.py
git commit -m "feat: add replace_image (single-placement, contain-fit)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Session-layer image registry

**Files:**
- Modify: `webui/session.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `engine.operations.replace_image` from Task 2; `engine.document.Image` from Task 1.
- Produces: `webui.session.get_image(image_id: int) -> dict` (entry shape `{"id": int, "page_index": int, "image": Image}`), `webui.session.get_images_summary() -> list[dict]` (entry shape `{"id", "page_index", "bbox", "width", "height", "placement_count"}`), `webui.session.replace_image(image_id: int, new_image_bytes: bytes) -> None`. Internally `_refresh_blocks` is renamed `_refresh_state` and `_build_block_registry` is renamed `_build_registries(doc) -> tuple[list[dict], list[dict]]` returning `(blocks, images)`.

- [ ] **Step 1: Write the failing session tests**

Append to `tests/test_webui.py`:

```python
def _upload_two_placements():
    with open(FIXTURES / "image_two_placements.pdf", "rb") as f:
        return client.post(
            "/api/upload",
            files={"file": ("image_two_placements.pdf", f, "application/pdf")},
        )


def test_session_image_registry_gives_each_placement_its_own_id():
    _upload_two_placements()

    images = session.get_images_summary()

    assert len(images) == 2
    assert images[0]["id"] != images[1]["id"]
    assert images[0]["placement_count"] == 2
    assert images[0]["width"] == 64
    assert len(images[0]["bbox"]) == 4


def test_session_image_and_block_ids_never_collide():
    # Both registries draw from ONE monotonic counter specifically so a stale
    # id from the frontend can never resolve to a block when it meant an
    # image, or the reverse.
    with open(FIXTURES / "mixed.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("mixed.pdf", f, "application/pdf")})

    block_ids = {b["id"] for b in session.get_blocks_summary()}
    image_ids = {i["id"] for i in session.get_images_summary()}

    assert block_ids and image_ids
    assert block_ids.isdisjoint(image_ids)


def test_session_get_image_rejects_an_unknown_id():
    _upload_two_placements()

    with pytest.raises(LookupError, match="stale"):
        session.get_image(9999)


def test_session_replace_image_refreshes_the_registry():
    _upload_two_placements()
    first_id = session.get_images_summary()[0]["id"]

    session.replace_image(first_id, solid_png(64, 64, (30, 30, 220)))

    refreshed = session.get_images_summary()
    assert len(refreshed) == 2
    # Ids are monotonic and re-derived after every edit, so the stale id is
    # genuinely gone rather than silently pointing at a different placement.
    assert all(entry["id"] != first_id for entry in refreshed)
```

Add `from tests.image_helpers import solid_png  # noqa: E402` to `tests/test_webui.py`'s import block, after the `from webui.main import app` line.

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "image" -v`
Expected: FAIL with `AttributeError: module 'webui.session' has no attribute 'get_images_summary'`.

- [ ] **Step 3: Rewrite the registry internals in `webui/session.py`**

Change the `_state` initializer (line 19) to:

```python
_state: dict = {"handle": None, "blocks": [], "images": [], "next_block_id": 0}
```

Replace `_build_block_registry` entirely with:

```python
def _build_registries(doc: Document) -> tuple[list[dict], list[dict]]:
    # Ids are drawn from a monotonically increasing counter that only resets
    # when the document is fully replaced, NOT from the entry's position in
    # its registry. Positional ids would be silently reassigned on every
    # refresh, so a stale id held by the frontend (e.g. a double-clicked
    # button firing twice) would resolve to a DIFFERENT surviving entry and
    # destroy it. With monotonic ids a stale id simply no longer exists, and
    # get_block()/get_image() raise the LookupError they were always meant to.
    #
    # Blocks and images share ONE counter, so an id is unambiguous across
    # both registries: a stale image id can never resolve to a block, or the
    # reverse.
    blocks, images = [], []
    for page in doc.pages:
        for block in page.text_blocks:
            blocks.append(
                {"id": _state["next_block_id"], "page_index": page.index, "block": block}
            )
            _state["next_block_id"] += 1
        for image in page.images:
            images.append(
                {"id": _state["next_block_id"], "page_index": page.index, "image": image}
            )
            _state["next_block_id"] += 1
    return blocks, images
```

Replace `_refresh_blocks` with:

```python
def _refresh_state() -> None:
    # Re-derive the Document projection from the handle's CURRENT state via
    # its exported bytes, since parse() is the only way to get a fresh
    # TextBlock/Image list -- the handle itself has no "give me a Document"
    # method. The re-parsed handle this produces is a throwaway: the real
    # handle we keep mutating stays _state["handle"], never this one, which
    # is closed immediately so it doesn't leak across many edits in one
    # session.
    handle = get_handle()
    doc, throwaway_handle = parse(export(handle))
    throwaway_handle.close()
    _state["blocks"], _state["images"] = _build_registries(doc)
```

- [ ] **Step 4: Update every caller of the renamed functions**

Replace `_refresh_blocks()` with `_refresh_state()` in the `finally` block of `redact`, `replace`, `delete`, `move`, and `insert` (5 call sites).

In `load_document`, replace `_state["blocks"] = _build_block_registry(doc)` with:

```python
    _state["blocks"], _state["images"] = _build_registries(doc)
```

In `sanitize_document`'s `finally`, replace `_state["blocks"] = _build_block_registry(doc)` with the same two-target assignment.

In `reset()`, add `_state["images"] = []` after the `_state["blocks"] = []` line.

- [ ] **Step 5: Add the image accessors and the operation wrapper**

Add `replace_image as _replace_image` to the engine imports at the top of `webui/session.py`:

```python
from engine.operations import redact_region, replace_text
from engine.operations import replace_image as _replace_image
```

Add after `insert()`:

```python
def replace_image(image_id: int, new_image_bytes: bytes) -> None:
    entry = get_image(image_id)
    try:
        _replace_image(get_handle(), entry["page_index"], entry["image"], new_image_bytes)
    finally:
        _refresh_state()
```

Add after `get_blocks_summary()`:

```python
def get_image(image_id: int) -> dict:
    for entry in _state["images"]:
        if entry["id"] == image_id:
            return entry
    raise LookupError(
        f"no image with id {image_id} in the current document -- it may be stale after an edit"
    )


def get_images_summary() -> list[dict]:
    return [
        {
            "id": entry["id"],
            "page_index": entry["page_index"],
            "bbox": list(entry["image"].bbox),
            "width": entry["image"].width,
            "height": entry["image"].height,
            "placement_count": entry["image"].placement_count,
        }
        for entry in _state["images"]
    ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -v`
Expected: PASS, including every pre-existing webui test — the renames are internal and the external session API only gained functions.

- [ ] **Step 7: Confirm nothing else referenced the old private names**

Run: `grep -rn "_refresh_blocks\|_build_block_registry" --include=*.py . | grep -v ".venv"`
Expected: no output. If there are hits (e.g. in `webui/ai/tools.py`), update them to the new names.

- [ ] **Step 8: Run the full suite and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS.

```bash
git add webui/session.py tests/test_webui.py
git commit -m "feat: add an image registry to the webui session

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `POST /api/replace-image` and `images` on every state response

**Files:**
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `session.replace_image`, `session.get_images_summary` from Task 3.
- Produces: `POST /api/replace-image` accepting `multipart/form-data` with fields `image_id` (int) and `file` (the replacement image), returning `{pages, blocks, images}`. Every other state-returning endpoint now also includes `images`. Internal helper `_state_payload() -> dict`.

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_webui.py`:

```python
def test_replace_image_round_trip_swaps_the_targeted_placement():
    _upload_two_placements()
    first_id = session.get_images_summary()[0]["id"]

    response = client.post(
        "/api/replace-image",
        data={"image_id": str(first_id)},
        files={"file": ("blue.png", solid_png(64, 64, (30, 30, 220)), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["images"]) == 2
    assert {"pages", "blocks", "images"} <= set(body)


def test_replace_image_rejects_an_unknown_image_id():
    _upload_two_placements()

    response = client.post(
        "/api/replace-image",
        data={"image_id": "9999"},
        files={"file": ("blue.png", solid_png(8, 8, (30, 30, 220)), "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_replace_image_rejects_a_file_that_is_not_an_image():
    _upload_two_placements()
    first_id = session.get_images_summary()[0]["id"]

    response = client.post(
        "/api/replace-image",
        data={"image_id": str(first_id)},
        files={"file": ("notes.txt", b"this is not an image", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_replace_image_returns_a_clean_error_with_no_document_loaded():
    response = client.post(
        "/api/replace-image",
        data={"image_id": "0"},
        files={"file": ("blue.png", solid_png(8, 8, (30, 30, 220)), "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_every_state_returning_endpoint_includes_images():
    # render() in app.js rebuilds the whole page DOM from whichever response
    # came back last, so an endpoint that omits `images` would make the image
    # controls silently vanish after an unrelated text edit.
    with open(FIXTURES / "mixed.pdf", "rb") as f:
        upload = client.post("/api/upload", files={"file": ("mixed.pdf", f, "application/pdf")})
    assert "images" in upload.json()

    block_id = session.get_blocks_summary()[0]["id"]

    assert "images" in client.get("/api/state").json()
    assert "images" in client.post("/api/redact", json={"block_id": block_id}).json()
    assert "images" in client.post("/api/sanitize").json()

    block_id = session.get_blocks_summary()[0]["id"]
    assert "images" in client.post("/api/delete", json={"block_id": block_id}).json()
    assert "images" in client.post(
        "/api/insert",
        json={"page_index": 0, "bbox": [72.0, 400.0, 400.0, 420.0], "text": "X", "size": 12.0},
    ).json()

    block_id = session.get_blocks_summary()[0]["id"]
    assert "images" in client.post(
        "/api/replace", json={"block_id": block_id, "new_text": "short"}
    ).json()

    block_id = session.get_blocks_summary()[0]["id"]
    assert "images" in client.post(
        "/api/move", json={"block_id": block_id, "target_position": [72.0, 500.0]}
    ).json()
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "replace_image or every_state" -v`
Expected: FAIL — 404 for `/api/replace-image`, and `KeyError`/assertion failures on the missing `images` key.

- [ ] **Step 3: Add the shared payload helper and use it everywhere**

In `webui/main.py`, add after the exception handlers:

```python
def _state_payload() -> dict:
    """The session state every mutating route returns. One helper, not eight
    inline dicts: the frontend rebuilds its entire view from whichever
    response came back last, so an endpoint that omitted a key would make
    that part of the UI disappear until the next full refresh.
    """
    return {
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
        "images": session.get_images_summary(),
    }
```

Replace the return statement in `upload`, `state`, `redact`, `replace`, `delete`, `move`, and `insert` with `return _state_payload()`.

In `sanitize`, replace the return with:

```python
    return {**result, **_state_payload()}
```

In `ai_instruct`, replace the return with:

```python
    return {"summary": summary, **_state_payload()}
```

- [ ] **Step 4: Add the multipart route**

Add `Form` to the FastAPI import on line 8:

```python
from fastapi import FastAPI, File, Form, Response, UploadFile
```

Add after the `insert` route:

```python
@app.post("/api/replace-image")
async def replace_image(image_id: int = Form(...), file: UploadFile = File(...)) -> dict:
    # multipart/form-data, not JSON, because the payload is binary -- the
    # same shape /api/upload already uses. Every other mutating route takes
    # a JSON body.
    image_bytes = await file.read()
    session.replace_image(image_id, image_bytes)
    return _state_payload()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -v`
Expected: PASS, all tests.

- [ ] **Step 6: Run the full suite and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS.

```bash
git add webui/main.py tests/test_webui.py
git commit -m "feat: add POST /api/replace-image and return images with every state response

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Manual-controls UI and README

**Files:**
- Modify: `webui/static/app.js:35-120` (the `render` function)
- Modify: `webui/static/styles.css`
- Modify: `README.md:38-60`

**Interfaces:**
- Consumes: the `images` array from Task 4's `_state_payload()` — entries `{id, page_index, bbox, width, height, placement_count}` — and `POST /api/replace-image`'s multipart contract.
- Produces: no new programmatic interface. UI only.

- [ ] **Step 1: Render an image row per placement**

In `webui/static/app.js`, inside `render()`'s `for (const page of state.pages)` loop, immediately after the `for (const block of blocksForPage) { ... }` loop closes and before `pagesDiv.appendChild(pageDiv);`, insert:

```javascript
    // Defensive `|| []`: an older cached response, or a future endpoint that
    // forgets the key, should degrade to "no image controls" rather than
    // throwing and leaving the whole page unrendered.
    const imagesForPage = (state.images || []).filter((i) => i.page_index === page.index);
    for (const image of imagesForPage) {
      const imageDiv = document.createElement("div");
      imageDiv.className = "image-controls";

      const caption = document.createElement("span");
      caption.className = "block-text";
      const [x0, y0] = image.bbox;
      caption.textContent =
        `image ${image.width}x${image.height} px at (${Math.round(x0)}, ${Math.round(y0)})` +
        (image.placement_count > 1
          ? ` — appears ${image.placement_count}x on this page; only this one changes`
          : "");
      imageDiv.appendChild(caption);

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/*";
      imageDiv.appendChild(fileInput);

      const replaceImageButton = document.createElement("button");
      replaceImageButton.textContent = "Replace image";
      imageDiv.appendChild(replaceImageButton);

      replaceImageButton.onclick = () => {
        if (!fileInput.files.length) {
          showError("choose a replacement image first");
          return;
        }
        const formData = new FormData();
        formData.append("image_id", image.id);
        formData.append("file", fileInput.files[0]);
        return actGuardedMultipart([replaceImageButton], "/api/replace-image", formData);
      };

      pageDiv.appendChild(imageDiv);
    }
```

- [ ] **Step 2: Add the multipart sibling of `act`/`actGuarded`**

In `webui/static/app.js`, add after `actGuarded`:

```javascript
async function actGuardedMultipart(buttons, url, formData) {
  for (const button of buttons) {
    button.disabled = true;
  }
  try {
    // Deliberately no Content-Type header: the browser must set it itself so
    // it can add the multipart boundary. Setting it by hand breaks the parse.
    const response = await fetch(url, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      // Re-sync before showing the error, same ordering rationale as act():
      // render() clears the error message.
      await refreshState();
      showError(data.error || "request failed");
      return;
    }
    render(data);
  } finally {
    for (const button of buttons) {
      button.disabled = false;
    }
  }
}
```

- [ ] **Step 3: Style the row and keep it behind the manual-controls toggle**

In `webui/static/styles.css`, widen the six existing `.block-controls` selectors (lines 564, 573, 588, 598, 602, 607) to cover `.image-controls` too, so the image rows inherit the block row's layout and — critically — its `display: none` default plus the `body[data-manual-controls="true"]` reveal. Exact edits:

| Line | From | To |
|---|---|---|
| 564 | `.block-controls {` | `.block-controls,\n.image-controls {` |
| 573 | `body[data-manual-controls="true"] .block-controls {` | `body[data-manual-controls="true"] .block-controls,\nbody[data-manual-controls="true"] .image-controls {` |
| 588 | `.block-controls button {` | `.block-controls button,\n.image-controls button {` |
| 598 | `.block-controls button:hover:not(:disabled) {` | `.block-controls button:hover:not(:disabled),\n.image-controls button:hover:not(:disabled) {` |
| 602 | `.block-controls button:disabled {` | `.block-controls button:disabled,\n.image-controls button:disabled {` |
| 607 | `.block-controls input {` | `.block-controls input,\n.image-controls input {` |

Then append after the `.coord-input` rule (line 617):

```css
.image-controls input[type="file"] {
  min-width: 0;
  max-width: 230px;
  padding: 4px 6px;
}
```

(The `min-width: 0` override matters: `.block-controls input`'s `min-width: 140px` plus a file input's native chrome overflows the row otherwise.)

- [ ] **Step 4: Verify in a real browser**

Run the app: `./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8000`

Then, in the browser at `http://localhost:8000`:
1. Upload `tests/fixtures/image_two_placements.pdf`.
2. Click "Show manual editing controls" — two image rows appear, each captioned `image 64x64 px at (…)` and noting it appears 2× on this page.
3. Pick a PNG for the **first** row and click "Replace image".
4. Confirm: the first red square becomes the new image, **the second stays red**, and both image rows are still present afterward.
5. Redact or delete a text block on a mixed-content PDF (`tests/fixtures/mixed.pdf`) and confirm the image row does **not** disappear (this is Ruling R2's regression, verified by hand).
6. Click "Replace image" with no file chosen — confirm the inline error, no request, and the button re-enables.

Record what you actually observed. Do not claim this step passed without running it.

- [ ] **Step 5: Document the operation in the README**

In `README.md`, add to the `## Operations` list after the `replace_text` entry:

```markdown
- `replace_image(handle, page_index, target, new_image_bytes)` -- swap the
  bitmap of one image placement for new bytes, scaled to fit its existing
  rectangle with the aspect ratio preserved and centered (the letterbox
  margin takes the page's sampled background color). Only the targeted
  placement changes: when the same image object is drawn in several places,
  the others are left exactly as they were, which is why this does not use
  PyMuPDF's xref-global `Page.replace_image`. Manual controls only -- there
  is no AI tool for it, since the model cannot produce image bytes. See
  `docs/superpowers/specs/2026-09-02-image-replacement-design.md`.
```

- [ ] **Step 6: Run the full suite and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS.

```bash
git add webui/static/app.js webui/static/styles.css README.md
git commit -m "feat: add image replacement controls to the manual editing UI

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Final whole-branch review (before merge)

After Task 5, run a fresh whole-branch review against `master` — this is where the last two increments each caught a real blocking bug that no per-task test found (the metadata leak in exported bytes; the partially-off-page destination). Specifically re-check:

- **Exported bytes, not just the live handle.** Assert the replacement is present and correct in `export(handle)` re-parsed from scratch, not only in the in-memory page render. The metadata-leak bug was invisible to every accessor-based test.
- **The orphaned original.** Confirm that replacing the sole placement of an xref and then exporting does not corrupt the file, and note whether the orphan actually survives `export()`'s `garbage=3`.
- **Placement isolation across pages**, not just within one page — the spec claims other placements "on this page or any other" are untouched, but no test covers the cross-page case. Add one if the review agrees it is load-bearing.
- **Registry id monotonicity** under repeated image replaces (ids must never be reused).
