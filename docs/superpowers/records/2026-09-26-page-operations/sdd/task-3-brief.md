### Task 3: Bound checks (D1, D3, D4, D5)

**Files:**
- Modify: `engine/operations.py`:
  - the import block (after line 12)
  - `_validate_target` (lines 178–182)
  - `_insertion_rect` (lines 355–356)
  - `move_block`'s containment check (lines 761–764)
  - `insert_block`'s containment check (lines 834–837)
- Modify: `tests/geometry_helpers.py` (append `build_page`)
- Create: `tests/test_page_geometry.py`

**Interfaces:**
- Consumes: `engine.geometry.unrotated_bounds` from Task 1; the existing `tests.image_helpers.solid_png(width, height, color) -> bytes`.
- Produces:
  - `tests.geometry_helpers.build_page(...) -> bytes`
  - in `tests/test_page_geometry.py`: `fingerprint(handle)`, `block(doc, marker)`, `exported(handle)`, `text_spans(page)`

**Every test run in this task and later ones:** save the full pytest output and its exit status in your report (`... > <file> 2>&1; echo "exit $?"`), not only the summary line.

- [ ] **Step 1: Add the `build_page` helper**

Append to `tests/geometry_helpers.py`:

```python
def build_page(
    *,
    rotation=0,
    cropbox=None,
    mediabox=None,
    user_unit=None,
    rotate_raw=None,
    width=612,
    height=792,
    band=None,
    texts=((72, 700, "LOW-MARKER"),),
    image_rect=None,
    image_rgb=(200, 200, 200),
    extra_pages=0,
) -> bytes:
    """PDF bytes for operation-level tests (plan ruling P6).

    ALL content is drawn first, on a plain page. Only then are the boxes,
    /UserUnit and rotation applied, and only then are any extra blank pages
    added -- adding a page invalidates earlier Page handles, which is why the
    order is fixed here.
    """
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    if band is not None:
        page.draw_rect(fitz.Rect(band), color=None, fill=BAND)
    for x, y, text in texts:
        page.insert_text((x, y), text, fontsize=12)
    if image_rect is not None:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
        pix.set_rect(pix.irect, image_rgb)
        page.insert_image(fitz.Rect(image_rect), stream=pix.tobytes("png"))
    xref = page.xref
    if mediabox is not None:
        doc.xref_set_key(xref, "MediaBox", mediabox)
    if cropbox is not None:
        doc.xref_set_key(xref, "CropBox", cropbox)
    if user_unit is not None:
        doc.xref_set_key(xref, "UserUnit", str(user_unit))
    if rotate_raw is not None:
        doc.xref_set_key(xref, "Rotate", rotate_raw)
    page = doc.reload_page(page)
    if rotation:
        page.set_rotation(rotation)
    for _ in range(extra_pages):
        doc.new_page(width=612, height=792)
    data = doc.tobytes()
    doc.close()
    return data
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_page_geometry.py`:

```python
"""Operation-level tests for Merge A: every existing operation on rotated,
cropped, fractional and /UserUnit pages.

Assertions are made on EXPORTED bytes re-parsed from scratch wherever the
claim is about the output, because this project's last three shipped bugs
were each invisible on the live handle.
"""
from pathlib import Path

import pymupdf as fitz
import pytest

import engine
import tests.geometry_helpers
from engine.export import export
from engine.operations import (
    delete_block,
    insert_block,
    move_block,
    redact_region,
    replace_image,
    replace_text,
)
from engine.parser import parse
from tests.geometry_helpers import ROTATIONS, build_page
from tests.image_helpers import solid_png

CHECKOUT = Path(__file__).resolve().parents[1]


def block(doc, marker):
    return next(b for b in doc.pages[0].text_blocks if marker in b.text)


def exported(handle):
    return fitz.open(stream=export(handle), filetype="pdf")


def text_spans(page):
    return [
        span
        for entry in page.get_text("dict")["blocks"] if "lines" in entry
        for line in entry["lines"]
        for span in line["spans"]
        if span["text"].strip()
    ]


def fingerprint(handle):
    """Structural identity of a document (plan ruling P5, strengthened by C2).

    Every xref object's text, every raw stream, and the page count. Never
    compare exported bytes to prove nothing changed: PyMuPDF regenerates the
    trailer /ID on every save, so two exports with no operation in between
    already differ.
    """
    parts = [handle.page_count]
    for xref in range(1, handle.xref_length()):
        parts.append((xref, handle.xref_object(xref, compressed=False)))
        if handle.xref_is_stream(xref):
            parts.append((xref, handle.xref_stream_raw(xref)))
    return parts


def test_imports_resolve_inside_this_checkout():
    # C12: an editable install of another checkout would shadow this one,
    # and every result below would then describe the wrong code.
    for module in (engine, tests.geometry_helpers):
        assert Path(module.__file__).resolve().is_relative_to(CHECKOUT), module.__file__


def test_fingerprint_is_stable_when_nothing_changes():
    doc, handle = parse(build_page())
    assert fingerprint(handle) == fingerprint(handle)


def test_fingerprint_detects_an_added_annotation():
    doc, handle = parse(build_page())
    before = fingerprint(handle)
    handle[0].add_redact_annot(fitz.Rect(10, 10, 20, 20))
    assert fingerprint(handle) != before


def test_fingerprint_detects_a_resource_change():
    doc, handle = parse(build_page())
    before = fingerprint(handle)
    handle[0].insert_font(fontname="probefont", fontbuffer=fitz.Font("helv").buffer)
    assert fingerprint(handle) != before


# Where each fixture geometry puts LOW-MARKER, as the parser reports it. Every
# later test targets the marker by its reported bbox, so these pin the
# fixtures themselves: a fixture change that moved the marker would otherwise
# silently stop a test from exercising its defect (C7).
FIXTURE_ORIGINS = {
    "plain": ({}, (72, 700), 12),
    "rotated-90": ({"rotation": 90}, (72, 700), 12),
    "contained-crop": ({"cropbox": "[40 60 580 740]"}, (32, 648), 12),
    "negative-origin-mediabox": ({"mediabox": "[-100 -100 512 692]"}, (172, 600), 12),
    "user-unit-1.5": ({"user_unit": 1.5}, (108, 1050), 18),
    "malformed-rotate-45": ({"rotate_raw": "45"}, (92, 72), 12),
}


@pytest.mark.parametrize("case", sorted(FIXTURE_ORIGINS))
def test_fixture_places_the_marker_where_the_tests_assume(case):
    kwargs, origin, size = FIXTURE_ORIGINS[case]
    doc, handle = parse(build_page(**kwargs))
    spans = [s for s in text_spans(handle[0]) if "LOW-MARKER" in s["text"]]
    assert len(spans) == 1
    assert spans[0]["origin"] == pytest.approx(origin, abs=0.01, rel=0)
    assert spans[0]["size"] == pytest.approx(size, abs=0.01, rel=0)


# LOW-MARKER sits at y~700 on a 792-high page -- below the 612 that a
# rotated page.rect reports as its height, which is what exposed D1.
LOW_OPS = {
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
    "delete_block": lambda h, b: delete_block(h, 0, b),
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, 20)),
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
}


@pytest.mark.parametrize("rotation", ROTATIONS)
@pytest.mark.parametrize("op", sorted(LOW_OPS))
def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
    doc, handle = parse(build_page(rotation=rotation))
    LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_replace_image_accepts_an_image_low_on_the_page(rotation):
    # The sixth operation that validates a target (spec E1). No CropBox here,
    # so insert_image already lands correctly (spec F2); only D1 is in play.
    doc, handle = parse(build_page(rotation=rotation, texts=(), image_rect=(72, 700, 136, 764)))
    replace_image(handle, 0, doc.pages[0].images[0], solid_png(8, 8, (30, 30, 220)))


@pytest.mark.parametrize("rotation", (90, 270))
def test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected(rotation):
    # x=650 is inside a rotated page.rect (792 wide) but beyond the real,
    # unrotated page (612 wide). The old check accepted it.
    doc, handle = parse(build_page(rotation=rotation))
    with pytest.raises(ValueError, match="entirely off-page"):
        redact_region(handle, 0, (650, 100, 700, 120))


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_a_genuinely_off_page_bbox_is_still_rejected(rotation):
    doc, handle = parse(build_page(rotation=rotation))
    with pytest.raises(ValueError, match="entirely off-page"):
        redact_region(handle, 0, (700, 900, 760, 920))


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page(rotation):
    # Review Focus 2: redact_region uses intersects, not contains, so a bbox
    # overhanging the page's right edge (x=612) is still a valid target. At
    # 90/270 the old check compared it with the swapped rect (612 high), where
    # y=690 is already off-page, and rejected it.
    doc, handle = parse(build_page(rotation=rotation))
    redact_region(handle, 0, (580, 690, 640, 710))  # must not raise


def test_identical_replacement_low_on_a_rotated_page_keeps_its_size():
    # D3: the old growth cap used the rotated height (612), losing the
    # headroom a low block needs, so the replacement shrank. Every span of
    # the replacement is checked, not only the first.
    doc, handle = parse(build_page(rotation=90))
    b = block(doc, "LOW-MARKER")
    replace_text(handle, 0, b, b.text)
    spans = text_spans(exported(handle)[0])
    assert "LOW-MARKER" in "".join(s["text"] for s in spans)
    for span in spans:
        assert span["size"] == pytest.approx(b.size, abs=0.01, rel=0), span["text"]


def test_insert_block_fits_a_tight_box_low_on_a_rotated_page():
    # E2: insert_block has no shrink loop, so on the old code lost headroom
    # made it RAISE "does not fit" for text that fits unrotated.
    doc, handle = parse(build_page(rotation=90))
    b = block(doc, "LOW-MARKER")
    insert_block(handle, 0, (300, b.bbox[1], 560, b.bbox[3]), "FITS", b.size)
    assert "FITS" in exported(handle)[0].get_text()


@pytest.mark.parametrize("rotation", (90, 270))
def test_move_block_accepts_a_destination_low_on_a_rotated_page(rotation):
    # D4: masked by D1 on the old code, and would surface as soon as D1 was
    # fixed alone.
    doc, handle = parse(build_page(rotation=rotation, texts=((72, 100, "TOP-MARKER"),)))
    move_block(handle, 0, block(doc, "TOP-MARKER"), target_position=(72, 740))
    assert "TOP-MARKER" in exported(handle)[0].get_text()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured by the coordinator on this exact file: **20 failed, 28 passed.**
- `test_every_block_operation_accepts_a_block_low_on_the_page`: the 90 and 270 cases of all five operations fail (10) with "entirely off-page". So do `test_replace_image_accepts_an_image_low_on_the_page[90]` and `[270]`.
- `test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90]` and `[270]` fail with `DID NOT RAISE`.
- `test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90]` and `[270]` fail with "entirely off-page": at 90/270 the old check compares against the swapped rect, which is 612 high, so y=690 is off-page.
- `test_identical_replacement_...` and `test_insert_block_fits_...` fail with "entirely off-page". D1 trips before D3.
- `test_move_block_accepts_...[90]` and `[270]` fail.
- Already passing (28), and kept as guards: the import-location test, the three fingerprint self-tests, the six fixture-origin cases, every rotation-0 and rotation-180 case, the genuinely-off-page test, and the straddle test at 0 and 180.

If the result differs, stop and report it. Do not change a test to match.

- [ ] **Step 4: Implement the bound changes**

In `engine/operations.py`, extend the import after `from engine.document import Image, TextBlock`:

```python
from engine.geometry import unrotated_bounds
```

Import only this name (plan ruling S1). Tasks 4, 5 and 7 each add the names they use to this import.

**D1** — in `_validate_target`, replace:

```python
    if not rect.intersects(page.rect):
        raise ValueError(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
        )
```

with:

```python
    bounds = unrotated_bounds(page)
    if not rect.intersects(bounds):
        raise ValueError(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page bounds are {tuple(bounds)}) -- it is entirely off-page"
        )
```

**D3** — in `_insertion_rect`, replace:

```python
    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, page.rect.x1))
    y1 = max(rect.y1, min(rect.y0 + needed_height, page.rect.y1))
```

with:

```python
    bounds = unrotated_bounds(page)
    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, bounds.x1))
    y1 = max(rect.y1, min(rect.y0 + needed_height, bounds.y1))
```

**D4** — in `move_block`, replace:

```python
    if not destination_page.rect.contains(destination_rect):
        raise ValueError(
            f"destination {tuple(destination_rect)} is not fully inside page "
            f"{dest_index} (page rect {tuple(destination_page.rect)}) -- move_block "
```

with:

```python
    destination_bounds = unrotated_bounds(destination_page)
    if not destination_bounds.contains(destination_rect):
        raise ValueError(
            f"destination {tuple(destination_rect)} is not fully inside page "
            f"{dest_index} (page bounds {tuple(destination_bounds)}) -- move_block "
```

**D5** — in `insert_block`, replace:

```python
    if not page.rect.contains(rect):
        raise ValueError(
            f"bbox {tuple(bbox)} is not fully inside page {page_index} "
            f"(page rect {tuple(page.rect)}) -- insert_block does not place "
```

with:

```python
    bounds = unrotated_bounds(page)
    if not bounds.contains(rect):
        raise ValueError(
            f"bbox {tuple(bbox)} is not fully inside page {page_index} "
            f"(page bounds {tuple(bounds)}) -- insert_block does not place "
```

Leave each message's remaining lines exactly as they are.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected: 48 passed.

- [ ] **Step 6: Mutation check — D3 is guarded on its own**

Revert **only** the two D3 lines to `page.rect.x1` / `page.rect.y1`, keeping D1.

Expected — measured: exactly **4** failures:
- `test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]` and `[insert_block-270]`;
- `test_identical_replacement_low_on_a_rotated_page_keeps_its_size`, on size;
- `test_insert_block_fits_a_tight_box_low_on_a_rotated_page`, with "does not fit".

Every other test in the file still passes. Restore D3, and paste the four failure messages into your report.

- [ ] **Step 7: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass, and none of the 227 pre-Merge-A tests was edited.

```bash
git add engine/operations.py tests/geometry_helpers.py tests/test_page_geometry.py
git commit -m "fix: bound checks use the unrotated page extent

On a page with /Rotate set, get_text() reports bboxes in unrotated space
while page.rect is the rotated display box. Every operation's bound check
compared the two, rejecting valid blocks low on scanned pages as off-page,
accepting genuinely off-page bboxes in the swapped region, and starving
replace_text and insert_block of the headroom a low block needs.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

