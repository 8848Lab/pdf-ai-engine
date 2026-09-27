# Task 2 — fix round 3 brief (coordinator ruling C16: read MuPDF's real page transform)

Read `task-2-rereview-2.md` in this directory first. Round 2 closed every round-1 item, but the reviewer found two new bypasses in the C15 design, plus Minors.

1. **Important.** `page.transformation_matrix` is derived from MuPDF's transform only at rotation 0. At 90/180/270 it is the constant `(1, 0, 0, -1, 0, cropbox.height)`. So `rotation_is_valid` and the mirror check do nothing on rotated pages. `/UserUnit -1 /Rotate 90|180|270` is allowed for both kinds, and text and redaction fills land in the wrong place.
2. **Important.** MuPDF replaces a box smaller than 1pt with the unit rect. `page.mediabox` mirrors that, but `page.cropbox` does not. `CropBox [100 100 100.5 100.5] /UserUnit 0.5` passes.
3. **Out of scope, ruled in:** coordinates around 1e9pt drift through float32 (`/MediaBox [0 0 1e9 1e9]` misplaces text by 12pt).

**Ruling C16.** Read MuPDF's real page transform through `pdf_page_transform`, and require its linear part to be exactly the rotation PyMuPDF reports, at one positive scale. Refuse a visible side under 1pt. Refuse box coordinates beyond 2^24pt, the float32 exact-integer limit; drift was measured at 1e8–1e9pt and none at 2e7pt or below.

The coordinator verified the code below against the drift probe:
- the 1,024-case matrix at 4 units: 0 mismatches;
- your 39-row Test B table plus the reviewer's 88 new rows (`scratchpad/fable-t2/round3a.py`, `NEW_ROWS`): 0 bypasses.

The only table change is `unit-1`, which is now "invalid rotation". A negative /UserUnit is the same transform as a 180° turn, so the two cannot be told apart and share one message.

The transform is read through PyMuPDF's low-level `mupdf` binding and the private `page._pdf_page()`. PyMuPDF offers no public accessor for the rotated page transform. The call fails closed: if the API is missing, every page is refused, and the plain-page tests go red at once.

## 1. `engine/geometry.py`

Delete `rotation_is_valid` and `user_unit`. Keep `visible_area` and `crop_origin_overhangs` exactly as they are. Add the following, replace `drawing_refusal`'s body, and fix the docstrings: the malformed-rotation docstring is wrong for `/Rotate 135`, which MuPDF snaps to 180 with b = c = 0.

```python
from pymupdf import mupdf

# Linear part (a, b, c, d) of MuPDF's page transform at scale 1, for each
# valid rotation. A page laid out at /UserUnit u has the same pattern times u.
_ROTATION_PATTERNS = {0: (1, 0, 0, -1), 90: (0, 1, 1, 0), 180: (-1, 0, 0, 1), 270: (0, -1, -1, 0)}

# PDF coordinates are float32 inside MuPDF; past 2**24 not every integer is
# representable, and text was measured landing 4-12pt off at 1e8-1e9pt.
_MAX_COORDINATE_PT = 2 ** 24


def page_transform(page: fitz.Page) -> fitz.Matrix | None:
    """MuPDF's own page transform, or None if this PyMuPDF cannot provide it.

    page.transformation_matrix is NOT this: PyMuPDF derives it from MuPDF's
    transform only at rotation 0 and returns a constant at 90/180/270, which
    hides a mirrored or rescaled rotated page. There is no public accessor,
    so this uses the low-level binding; None fails closed.
    """
    try:
        ctm = mupdf.FzMatrix()
        mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)
    except (AttributeError, TypeError):
        return None
    return fitz.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f)


def layout_orientation(page: fitz.Page) -> tuple[int, float] | None:
    """(rotation, scale) that MuPDF actually lays the page out at, or None if
    its transform is not a valid rotation at one positive scale."""
    ctm = page_transform(page)
    if ctm is None:
        return None
    linear = (ctm.a, ctm.b, ctm.c, ctm.d)
    scale = max(abs(value) for value in linear)
    if scale <= 0:
        return None
    for rotation, pattern in _ROTATION_PATTERNS.items():
        if all(abs(value - p * scale) <= 1e-9 * max(1.0, scale) for value, p in zip(linear, pattern)):
            return rotation, scale
    return None
```

`drawing_refusal`, with its rules in this order:

```python
    layout = layout_orientation(page)
    if layout is not None and layout[0] != page.rotation:
        return (
            f"Page {page_index} has an invalid rotation: PyMuPDF lays it out at a "
            f"different orientation than its /Rotate states (a /Rotate that is not a "
            f"multiple of 90, or a negative /UserUnit), so this operation was not "
            f"applied and nothing was changed."
        )
    visible = visible_area(page)
    width, height = visible.width, visible.height
    if page.rotation in (90, 270):
        width, height = height, width
    unit = layout[1] if layout is not None else None
    if (
        unit is None
        or visible.is_empty
        or width < 1 or height < 1  # MuPDF swaps a sub-point box for the unit rect; page.cropbox does not
        or abs(page.rect.width - unit * width) > _LAYOUT_TOLERANCE_PT
        or abs(page.rect.height - unit * height) > _LAYOUT_TOLERANCE_PT
    ):
        return (
            f"Page {page_index} has page boxes that PyMuPDF lays out "
            f"inconsistently (a malformed CropBox, MediaBox or /UserUnit), so the "
            f"editor cannot place anything on it reliably. This operation was not "
            f"applied and nothing was changed."
        )
    if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > _LAYOUT_TOLERANCE_PT:
        return (
            f"Page {page_index} uses PDF /UserUnit scaling ({unit:.7g}), which the "
            f"editor does not support yet, so this operation was not applied and "
            f"nothing was changed. Support is planned."
        )
    if any(abs(v) > _MAX_COORDINATE_PT for box in (page.mediabox, page.cropbox) for v in box):
        return (
            f"Page {page_index} has page boxes larger than {_MAX_COORDINATE_PT} "
            f"points, where PDF coordinates lose precision and content lands in the "
            f"wrong place, so this operation was not applied and nothing was changed."
        )
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return (<the existing overhang message, unchanged>)
    return None
```

Each message keeps the phrase later tasks match on: "invalid rotation", "uses PDF /UserUnit", "Support is planned", "nothing was changed" and "CropBox".

The magnitude rule applies to every operation. Rule order is still rotation first, so M4 holds.

Update `drawing_refusal`'s docstring rule list to these five rules.

## 2. Tests (`tests/test_geometry.py`, `tests/geometry_helpers.py`)

**Test B table changes:**
- Change `unit-1` to `rot`.
- Add a `huge` category, matched by the phrase "larger than".
- Add these rows. Each row's page dict is exactly the one in the reviewer's `scratchpad/fable-t2/round3a.py` `NEW_ROWS`; copy them from there.

| id | expected |
|---|---|
| unit-1-rot90 | rot |
| unit-1-rot180 | rot |
| unit-1-rot270 | rot |
| unit-1-rot180-crop | rot |
| unit-1-indirect-rot90 | rot |
| rot135 | rot |
| rot-inherited-135 | rot |
| crop-tiny | incons |
| crop-tiny-unit0.5 | incons |
| media-huge | huge |
| media-huge-1e7 | - |
| rot315 | - |
| unit-1.0000001-huge | unit (its message must print more than "(1)") |

**Redaction placement (review item 4).** For every Test B row that allows OTHER_DRAWING, also assert where the fill lands:
1. Draw a text span on the page at a known spot.
2. Redact its bbox through `engine.operations._erase_region` with a green fill, which runs at rotation 0 once Task 5 exists. Until then, wrap it in `at_rotation_zero` yourself.
3. Re-open the output. Assert the text is gone and exactly one green fill lies within 0.5pt of the bbox.

`scratchpad/fable-t2/round3b.py` has the reviewer's version.

**Other test changes:**
- **Delete** `test_the_adversarial_table_categories_apply_to_other_drawing_too`: Test B's inline OTHER assertion is strictly stronger. Also delete `raw_object_page` from the helpers; it is dead.
- **Parent-cycle test:** replace `assert "overhangs" in result or "error" in result`, which cannot fail, with the value PyMuPDF actually produces. Measure it, then pin it, for example `result.get("overhangs") is False`, with a comment saying it was measured.
- **Round-2 tests:** update or delete the ones for `rotation_is_valid` / `user_unit` to match the new names. Keep A1, A2, M3 and M4 as agreement tests.
- Add a test that `page_transform` returns a Matrix on a plain page, which pins the low-level API.
- The number of skipped tests in `tests/test_geometry.py` must be 0.

## 3. Red first, then mutations

- **Red.** Run the new rows and the placement assertions against b08c848 before changing the engine. The unit-1-rot* rows and crop-tiny-unit0.5 must fail as bypasses, and media-huge must fail. Record the failures.
- **Mutations.** Run each on a copy, and restore afterwards. Record the failing test ids for each:
  1. `page_transform` → return `page.transformation_matrix`, the round-2 behaviour;
  2. drop the `< 1` check;
  3. drop the magnitude rule;
  4. `layout[0] != page.rotation` → `False`.

## 4. Report

Append a "Fix round 3" section to `task-2-report.md`. Include the red run, the mutations, and the full `tests/` output with its exit status.

Commit on top of HEAD; no amend, reset or rebase. Message: `fix: read MuPDF's own page transform so rotated, mirrored and tiny-box pages are refused`, with the usual attribution lines.
