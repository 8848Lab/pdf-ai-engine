# Page Geometry Correctness (Merge A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every existing engine operation correct on pages that carry rotation, a CropBox, fractional dimensions or `/UserUnit`, and refuse — before mutating anything — the configurations the engine cannot yet draw on correctly.

**Architecture:** A new module, `engine/geometry.py`, becomes the single place that knows how PyMuPDF's two coordinate spaces relate: the unrotated space `get_text()` reports bboxes in and drawing calls accept, and the display space of `page.rect` and every pixmap. `engine/operations.py` switches its bound checks, pixel sampling, redaction and image insertion onto those helpers, and gains one refusal gate called right after target validation. No operation's signature changes.

**Tech Stack:** Python 3.13, PyMuPDF 1.28.2 (declared `pymupdf>=1.24,<2`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-page-operations-design.md` — read the original brief, then **REVISION 1 and REVISION 2 at the bottom, which are binding over it.** This plan implements Merge A only. Merge B (the page operations themselves) is planned separately after this lands.

## Global Constraints

- PyMuPDF is **installed at 1.28.2** and **declared `pymupdf>=1.24,<2`**. It is not pinned. Do not change the declaration.
- **The existing 227 tests must pass unedited.** If one fails, the change is wrong, not the test.
- No operation's public signature changes: `redact_region`, `replace_text`, `delete_block`, `move_block`, `insert_block`, `replace_image`, `sanitize_document`, `get_metadata_summary`.
- **Drawing calls keep receiving unrotated coordinates.** Never transform a rect passed to `insert_textbox`, `insert_image` or `add_redact_annot`. What changes is *how* two of those calls are made (at rotation 0), not the coordinates given to them.
- `engine/export.py` is not touched. `export()` keeps `garbage=3`; the session keeps refreshing via `snapshot()`.
- **Every refusal raises `ValueError` before any mutation**, with a message that names the cause and says nothing was changed. For `/UserUnit`, the message also says support is planned. That wording is the owner's instruction.
- **Redaction is refused only for `/UserUnit` ≠ 1 and a malformed `/Rotate`.** Never for a CropBox overhang.
- Every test command is prefixed `timeout 600`.
- Tests touch no network, database or model.
- Run everything from the repo root: `D:/Coding/8848 Lab/pdf-ai`, with `./.venv/Scripts/python.exe`.
- `tests/` has no `__init__.py` and must not gain one. `pyproject.toml`'s `pythonpath = ["."]` makes `from tests.x import y` work.
- Do not run `tests/fixtures/generate_fixtures.py`. It re-serialises every checked-in fixture.
- Commit attribution, exactly:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka
  ```

## Plan-level rulings

These rulings were made while writing this plan and are binding. Each one closes a gap the spec left open.

**P1 — The helpers live in a new `engine/geometry.py`, under public names.**
- The spec names `_unrotated_bounds` and `_to_display_matrix`. Here they are `unrotated_bounds` and `to_display_matrix`: the same functions, but the module's API, so not underscored.
- Why a separate module: coordinate-space correctness is one concern, the 1,024-case matrix tests it in isolation, and `operations.py` is already 1,049 lines.

**P2 — The geometry-matrix tests build documents in memory from raw PDF content streams.**
- They do not use checked-in fixture files. 1,024 fixture files would be impractical.
- The raw streams keep the fixture convention's actual intent: setup never uses the drawing calls under test.

**P3 — A malformed `/Rotate` refuses every drawing operation.**
- "Malformed" means a value that is not a multiple of 90. The spec does not mention this case; the coordinator found it while planning.
- With `/Rotate 45`, PyMuPDF reports `page.rotation == 0` but a swapped `page.rect`. A redaction on that page then removes the text but paints its fill elsewhere.
- Values that are well-formed but un-normalised (`-90`, `450`, `-270`, `360`, `720`) are fine. PyMuPDF normalises them to 270, 90, 90, 0 and 0.

**P4 — `move_block` gates both of its pages.**
- The source page is gated as `OTHER_DRAWING`, because the source is erased. The destination page is gated as `TEXT_DRAWING`.
- The spec named only the destination, but its `/UserUnit` rule covers every drawing, and the source erase paints a fill.

**P5 — "Nothing was modified" is asserted on a structural fingerprint, never on exported bytes.**
- PyMuPDF regenerates the trailer `/ID` on every save, so two `export()` calls with no operation in between already differ: the trailer `/ID` is regenerated.
- The fingerprint is the `fingerprint()` helper in Task 3.

**P6 — In operation tests, setup content is drawn on a plain page first.**
- Only after the content is drawn are the boxes, `/UserUnit` and rotation applied.
- Drawing after those are set is exactly the broken path, so the fixture would be testing itself.

**P7 — R9's stale-id verification is deferred to Merge B.**
- Merge A changes no ids, no registry and no page count, so it has no stale-id behaviour to verify.
- The success, failure and no-op cases R9 names all belong to the page operations.

## Verified by the coordinator before this plan was written

Every claim below was run, not reasoned about, on the Windows target with PyMuPDF 1.28.2.

- The complete engine change in this plan was applied in a scratch worktree, and **all 227 existing tests passed unedited**. The coordinator asserted under pytest itself that the scratch copy was the engine being tested, because an editable install could have shadowed it.
- **14 end-to-end checks passed through the public operations**, covering D1, D2, D3, D5, R4, R5, R11, R12 and P4.
- The planned tests in Tasks 3 and 4 are **red on the current engine and green on the patched one.** Reverting *only* D3 turns E2 and D3 red by their own mechanisms ("does not fit", and a shrunken size), while D1 and R3 stay green. So they are independent.
- The critic's probes reproduce exactly:
  - `recheck_geometry.py`: 1,024 cases, **zero** bound, visible, off-page or sample failures.
  - `recheck_drawing.py` at unit 1: all seven counts match the critic's.
- The redaction fill is misplaced **without** the fix in these cases (the Task 5 table).
- PyMuPDF behaviours the gates depend on:
  - `/UserUnit` is **not** inherited by PyMuPDF.
  - `/Rotate`, `/MediaBox` and `/CropBox` **are** inherited.
  - A box can be an indirect reference (`('xref', '5 0 R')`).
- The geometry matrix runs in about **4 seconds** on the coordinator's machine; timings are not requirements.

## Review Focus

These are the five inputs the spec implies but no spec-listed test exercises, most likely first. Each one has its test added to the task that owns the code.

1. **A multi-page document with different geometry per page.** The gate must use the target page's settings, not page 0's. A plain page must stay editable when another page uses `/UserUnit`. → Task 7, `test_gate_uses_the_target_pages_own_geometry`.
2. **A bbox straddling the page edge on a rotated page.** A bbox that intersects the page without being contained must still be accepted by `redact_region` (its `intersects` semantics are preserved). → Task 3, `test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page`.
3. **Rotation inherited from `/Pages`.** Redaction must land on target, and the effective rotation must survive the rotation-0 workaround. → Task 5, `test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation`.
4. **A malformed `/Rotate`, including when inherited.** It must be refused, and must not produce a misplaced fill. → Tasks 2 and 7.
5. **A drawing call raising inside `at_rotation_zero`.** The page's rotation must be restored, not left at 0. → Task 1, `test_at_rotation_zero_restores_rotation_when_the_body_raises`.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `engine/geometry.py` | **Create** | Coordinate-space helpers, box/unit/rotation readers, the refusal rules |
| `engine/operations.py` | Modify | Use the helpers at D1–D5; R3 sampling; R4 and R11 at rotation 0; one gate per operation |
| `engine/parser.py` | Modify (docstring only) | Document `Page.width/height` as display dimensions |
| `tests/geometry_helpers.py` | **Create** | The matrix case generator, `matrix_page`, `box_page` and `build_page` builders |
| `tests/test_geometry.py` | **Create** | Unit tests for `engine/geometry.py`, including the 1,024-case matrix |
| `tests/test_page_geometry.py` | **Create** | Operation-level tests: bounds, sampling, redaction fill, image placement, gates |
| `docs/superpowers/records/2026-09-26-page-operations/audit.md` | **Create** | The R9 audit report |
| `README.md` | Modify | One paragraph on supported page geometry |

---

### Task 1: Geometry helpers — bounds, display matrix, rotation-0 context

**Files:**
- Create: `engine/geometry.py`
- Create: `tests/geometry_helpers.py`
- Create: `tests/test_geometry.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `engine.geometry.unrotated_bounds(page: fitz.Page) -> fitz.Rect`
  - `engine.geometry.to_display_matrix(page: fitz.Page) -> fitz.Matrix`
  - `engine.geometry.at_rotation_zero(page: fitz.Page)`, a context manager
  - `tests.geometry_helpers.matrix_cases(units=(1,))`, which yields `(name, media: Rect, crop: Rect, unit: float, rot: int)`
  - `tests.geometry_helpers.matrix_page(media, crop, unit, rot) -> fitz.Document`
  - `tests.geometry_helpers.reopen(doc) -> fitz.Document`
  - the constants `ROTATIONS`, `BAND` and `BAND_RGB`

- [ ] **Step 1: Create the test helpers**

Create `tests/geometry_helpers.py`:

```python
"""Builders for pages with rotation, CropBox, MediaBox and /UserUnit set.

Two jobs, two kinds of builder:

- ``matrix_cases`` / ``matrix_page``: the Codex critic's 1,024-configuration
  generator, ported with fixed parameters from
  docs/superpowers/records/2026-09-26-page-operations/probes/recheck_common.py.
  Page content is written as a RAW content stream, so it never depends on the
  PyMuPDF drawing calls whose behaviour on these pages is under test.
- ``build_page`` (added in Task 3): one page for operation-level tests. Its
  content is drawn on a plain page FIRST, and only then are the boxes,
  /UserUnit and rotation applied. Do not reorder that: drawing after they are
  set is exactly the broken path, and the fixture would be testing itself.
"""
from itertools import product

import pymupdf as fitz

ROTATIONS = (0, 90, 180, 270)
BAND = (0.7, 0.85, 1.0)
BAND_RGB = (178, 216, 255)

_ORIGINS = ((0, 0), (100, 200), (-100, -200), (13.125, -27.375))


def matrix_cases(units=(1,)):
    """Four MediaBox origins x 16 CropBox overhang masks x units x 4 rotations.

    Mask bits: 1 = extends left, 2 = extends bottom, 4 = extends right,
    8 = extends top. With units=(0.5, 1, 1.5, 2) this is 1,024 cases.
    """
    for (ox, oy), mask, unit, rot in product(_ORIGINS, range(16), units, ROTATIONS):
        media = fitz.Rect(ox, oy, ox + 300, oy + 400)
        crop = fitz.Rect(
            ox + (-17.5 if mask & 1 else 20.25),
            oy + (-23.75 if mask & 2 else 20.25),
            ox + 300 + (31.25 if mask & 4 else -20.25),
            oy + 400 + (11.125 if mask & 8 else -20.25),
        )
        yield f"origin=({ox},{oy}) mask={mask} unit={unit} rot={rot}", media, crop, unit, rot


def _pdf_box(rect) -> str:
    return "[" + " ".join(str(v) for v in rect) + "]"


def matrix_page(media, crop, unit, rot) -> fitz.Document:
    """A page with a blue band, text VISIBLE on the band, and text OFFPAGE
    beyond the visible area's right edge. Positions are chosen so that, in
    PyMuPDF page coordinates, the band covers (35..135, 58..88) at any unit.
    """
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_font(fontname="helv")
    doc.xref_set_key(page.xref, "MediaBox", _pdf_box(media))
    doc.xref_set_key(page.xref, "CropBox", _pdf_box(crop))
    doc.xref_set_key(page.xref, "UserUnit", str(unit))
    page = doc.reload_page(page)
    page.set_rotation(rot)
    visible = media & crop
    x, y = visible.x0 + 40 / unit, visible.y1 - 80 / unit
    stream = (
        f"q {BAND[0]} {BAND[1]} {BAND[2]} rg {x - 5 / unit} {y - 8 / unit} "
        f"{100 / unit} {30 / unit} re f Q "
        f"BT /helv {10 / unit} Tf 1 0 0 1 {x} {y} Tm (VISIBLE) Tj ET\n"
        f"BT /helv {10 / unit} Tf 1 0 0 1 {visible.x1 + 40 / unit} {y} Tm (OFFPAGE) Tj ET"
    )
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, stream.encode())
    page.set_contents(xref)
    return doc


def reopen(doc: fitz.Document) -> fitz.Document:
    """Round-trip through bytes so assertions see what a recipient would."""
    reopened = fitz.open(stream=doc.tobytes(garbage=3), filetype="pdf")
    doc.close()
    return reopened
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_geometry.py`:

```python
"""Unit tests for engine/geometry.py.

The two matrix tests are the critic's 1,024-configuration attack on R2. They
collect every failure and assert on the list, so one run reports all of them
rather than stopping at the first.
"""
import pymupdf as fitz
import pytest

from engine.geometry import at_rotation_zero, to_display_matrix, unrotated_bounds
from tests.geometry_helpers import BAND_RGB, ROTATIONS, matrix_cases, matrix_page, reopen

ALL_UNITS = (0.5, 1, 1.5, 2)


def _spans(page):
    # Include text outside the visible area, so OFFPAGE is reported at all.
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    blocks = page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)["blocks"]
    return {
        span["text"]: fitz.Rect(span["bbox"])
        for block in blocks if "lines" in block
        for line in block["lines"] for span in line["spans"]
    }


def _pixel(page, point, matrix):
    pix = page.get_pixmap()
    q = fitz.Point(point) * matrix
    x = max(0, min(pix.width - 1, int(q.x - pix.x)))
    y = max(0, min(pix.height - 1, int(q.y - pix.y)))
    return tuple(pix.pixel(x, y)[:3])


def _near(a, b, tol=0.003):
    return max(abs(x - y) for x, y in zip(a, b)) < tol


def test_unrotated_bounds_hold_across_the_1024_case_matrix():
    failures = []
    for name, media, crop, unit, rot in matrix_cases(units=ALL_UNITS):
        doc = reopen(matrix_page(media, crop, unit, rot))
        page = doc[0]
        visible = media & crop
        bounds = unrotated_bounds(page)
        spans = _spans(page)
        if not _near(bounds, (0, 0, visible.width * unit, visible.height * unit)):
            failures.append(f"{name}: extent {tuple(bounds)}")
        if not bounds.contains(spans["VISIBLE"]):
            failures.append(f"{name}: visible text falls outside the bounds")
        if bounds.intersects(spans["OFFPAGE"]):
            failures.append(f"{name}: off-page text falls inside the bounds")
        doc.close()
    assert not failures, f"{len(failures)} failures, first five: {failures[:5]}"


def test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix():
    failures = []
    for name, media, crop, unit, rot in matrix_cases(units=ALL_UNITS):
        doc = reopen(matrix_page(media, crop, unit, rot))
        page = doc[0]
        got = _pixel(page, (80, 85), to_display_matrix(page))
        if got != BAND_RGB:
            failures.append(f"{name}: sampled {got}")
        doc.close()
    assert not failures, f"{len(failures)} failures, first five: {failures[:5]}"


def test_to_display_matrix_equals_the_library_matrix_on_an_ordinary_page():
    # Pins that the new matrix is a strict correction: where PyMuPDF's own
    # matrix is right, ours must be identical to it.
    for rot in ROTATIONS:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.set_rotation(rot)
        assert _near(tuple(to_display_matrix(page)), tuple(page.rotation_matrix)), rot
        doc.close()


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_at_rotation_zero_draws_unrotated_and_restores(rotation):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(rotation)
    with at_rotation_zero(page):
        assert page.rotation == 0
    assert page.rotation == rotation
    doc.close()


def test_at_rotation_zero_restores_rotation_when_the_body_raises():
    # Review Focus 5: a failed draw must never leave the page re-oriented.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(90)
    with pytest.raises(RuntimeError, match="boom"):
        with at_rotation_zero(page):
            raise RuntimeError("boom")
    assert page.rotation == 90
    doc.close()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'engine.geometry'`.

- [ ] **Step 4: Implement the helpers**

Create `engine/geometry.py`:

```python
"""Coordinate-space correctness for PyMuPDF pages.

PyMuPDF exposes two coordinate spaces that disagree whenever a page carries
rotation, a CropBox, fractional dimensions or /UserUnit:

- the UNROTATED page space that ``get_text()`` reports bboxes in, and that
  the drawing calls (``insert_textbox``, ``insert_image``,
  ``add_redact_annot``) accept;
- the DISPLAY space of ``page.rect`` and of every rendered pixmap.

Every bound check and every pixel lookup in engine/operations.py must pick
the right one. This module is the single place that knows how. See
docs/superpowers/specs/2026-09-26-page-operations-design.md, rulings R2,
R3, R4, R5, R11, R12 and R16, for the evidence behind each function.
"""
import contextlib

import pymupdf as fitz


def unrotated_bounds(page: fitz.Page) -> fitz.Rect:
    """The page's extent in the unrotated space bboxes are reported in.

    ``page.rect`` is the display box, whose width and height swap at 90
    and 270. Un-swapping them gives the true unrotated extent. Verified on
    1,024 configurations (shifted, fractional and negative MediaBox origins,
    every CropBox overhang, /UserUnit 0.5-2, all four rotations).

    Deliberately NOT ``page.rect * page.derotation_matrix``: that returns
    ``(0,88,612,880)`` at rotation 90 on a CropBox extending past the
    MediaBox, and rejects visible text.
    """
    width, height = page.rect.width, page.rect.height
    if page.rotation in (90, 270):
        width, height = height, width
    return fitz.Rect(0, 0, width, height)


def to_display_matrix(page: fitz.Page) -> fitz.Matrix:
    """Maps a point from unrotated page space into display space.

    A rotation by ``page.rotation``, then the translation that brings the
    rotated extent back to the origin. Identical to ``page.rotation_matrix``
    on ordinary pages; it differs exactly where the library matrix is wrong
    (an oversized CropBox, and /UserUnit), which is where it matters.
    """
    matrix = fitz.Matrix(page.rotation)
    rotated = unrotated_bounds(page) * matrix
    return matrix * fitz.Matrix(1, 0, 0, 1, -rotated.x0, -rotated.y0)


@contextlib.contextmanager
def at_rotation_zero(page: fitz.Page):
    """Temporarily draw with the page unrotated, restoring rotation after.

    PyMuPDF's ``insert_image`` and its redaction fill both misplace their
    output on a rotated page that also has a CropBox: images land 40-52pt
    off, and a redaction's black fill paints ~88pt away from the text it
    removed (the text itself is still removed). Drawing at rotation 0 lands
    both exactly, at every rotation and on both offset and oversized
    CropBoxes. Rotation is restored in a ``finally`` so a failed draw never
    leaves the page with a changed orientation.
    """
    original = page.rotation
    if original == 0:
        yield
        return
    page.set_rotation(0)
    try:
        yield
    finally:
        page.set_rotation(original)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v`
Expected: 8 passed. The two matrix tests take about 4 seconds between them.

- [ ] **Step 6: Mutation check — prove the matrix tests bite**

Mutate `to_display_matrix` temporarily so it returns `page.rotation_matrix`, then run the second matrix test.
Expected: it fails, reporting **640** failures.
Restore the function and confirm that `git diff engine/geometry.py` shows only your intended new file. Paste the failure count into your report.

- [ ] **Step 7: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 235 passed (227 + 8).

```bash
git add engine/geometry.py tests/geometry_helpers.py tests/test_geometry.py
git commit -m "feat: add page geometry helpers for rotated, cropped and scaled pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

### Task 2: Box, unit and rotation readers, and the refusal rules

**Files:**
- Modify: `engine/geometry.py` (append)
- Modify: `tests/geometry_helpers.py` (append `box_page`)
- Modify: `tests/test_geometry.py` (append)

**Interfaces:**
- Consumes: `engine/geometry.py` from Task 1.
- Produces:
  - `engine.geometry.raw_rotation(page) -> float`
  - `engine.geometry.user_unit(page) -> float`
  - `engine.geometry.crop_origin_overhangs(page) -> bool`
  - `engine.geometry.drawing_refusal(page, page_index: int, kind: str) -> str | None`
  - the constants `engine.geometry.TEXT_DRAWING` and `engine.geometry.OTHER_DRAWING`
  - `tests.geometry_helpers.box_page(**keys) -> tuple[fitz.Document, fitz.Page]`

- [ ] **Step 1: Add the `box_page` helper**

Append to `tests/geometry_helpers.py`:

```python
def box_page(*, where="page", indirect=(), **keys):
    """A plain 612x792 page with raw keys written onto it or onto /Pages.

    ``where="parent"`` writes the keys on the parent /Pages node instead, to
    exercise inheritance. That also removes the page's own /Rotate, which
    ``new_page`` writes explicitly as 0 and which would otherwise override
    an inherited value. ``indirect`` names keys to store as ``N 0 R``
    references rather than inline.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    target = page.xref
    if where == "parent":
        target = int(doc.xref_get_key(page.xref, "Parent")[1].split()[0])
        if "Rotate" in keys:
            doc.xref_set_key(page.xref, "Rotate", "null")
    for key, value in keys.items():
        if key in indirect:
            ref = doc.get_new_xref()
            doc.update_object(ref, value)
            value = f"{ref} 0 R"
        doc.xref_set_key(target, key, value)
    return doc, doc.reload_page(page)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_geometry.py`:

```python
from engine.geometry import (  # noqa: E402
    OTHER_DRAWING,
    TEXT_DRAWING,
    crop_origin_overhangs,
    drawing_refusal,
    raw_rotation,
    user_unit,
)
from tests.geometry_helpers import box_page  # noqa: E402


@pytest.mark.parametrize(
    "keys, expected",
    [
        (dict(CropBox="[-40 0 612 792]"), True),       # left only
        (dict(CropBox="[0 0 612 830]"), True),         # top only
        (dict(CropBox="[-40 -60 660 820]"), True),     # all four
        (dict(CropBox="[0 -60 612 792]"), False),      # bottom only
        (dict(CropBox="[0 0 660 792]"), False),        # right only
        (dict(CropBox="[40 60 580 740]"), False),      # contained
        (dict(), False),                               # no CropBox at all
        # The false-positive trap for mediabox.contains(cropbox): it draws fine.
        (dict(MediaBox="[-100 -100 512 692]"), False),
    ],
    ids=["left", "top", "all-four", "bottom", "right", "contained", "none",
         "negative-origin-mediabox"],
)
def test_crop_origin_overhangs_matches_where_text_actually_drifts(keys, expected):
    doc, page = box_page(**keys)
    assert crop_origin_overhangs(page) is expected
    doc.close()


def test_crop_origin_overhangs_resolves_an_inherited_cropbox():
    doc, page = box_page(where="parent", CropBox="[-40 -60 660 820]")
    assert doc.xref_get_key(page.xref, "CropBox") == ("null", "null")
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_crop_origin_overhangs_resolves_an_indirect_cropbox():
    doc, page = box_page(CropBox="[-40 -60 660 820]", indirect=("CropBox",))
    assert doc.xref_get_key(page.xref, "CropBox")[0] == "xref"
    assert crop_origin_overhangs(page) is True
    doc.close()


def test_crop_origin_overhangs_resolves_an_inherited_mediabox():
    doc, page = box_page(where="parent", MediaBox="[0 0 612 792]")
    assert crop_origin_overhangs(page) is False
    doc.close()


def test_the_predicate_matches_observed_text_drift_on_all_256_unit_one_cases():
    # The predicate is only worth having if it agrees with what PyMuPDF
    # actually does. Draw a probe string on each configuration and compare.
    mismatches = []
    for name, media, crop, unit, rot in matrix_cases(units=(1,)):
        doc = matrix_page(media, crop, unit, rot)
        page = doc[0]
        predicted = crop_origin_overhangs(page)
        page.insert_text((100, 140), "PROBE", fontsize=10)
        drawn = reopen(doc)[0]
        origin = next(
            span["origin"] for block in drawn.get_text("dict")["blocks"] if "lines" in block
            for line in block["lines"] for span in line["spans"] if span["text"] == "PROBE"
        )
        drifted = abs(origin[0] - 100) > 0.01 or abs(origin[1] - 140) > 0.01
        if predicted != drifted:
            mismatches.append(f"{name}: predicted={predicted} drifted={drifted}")
    assert not mismatches, f"{len(mismatches)} mismatches: {mismatches[:5]}"


@pytest.mark.parametrize(
    "keys, where, expected",
    [
        (dict(), "page", 1.0),
        (dict(UserUnit="1.5"), "page", 1.5),
        (dict(UserUnit="2"), "page", 2.0),
        # PyMuPDF ignores /UserUnit on /Pages, so the gate must too.
        (dict(UserUnit="1.5"), "parent", 1.0),
    ],
)
def test_user_unit_reads_the_page_level_value_only(keys, where, expected):
    doc, page = box_page(where=where, **keys)
    assert user_unit(page) == expected
    doc.close()


@pytest.mark.parametrize(
    "raw, where, expected",
    [("90", "page", 90.0), ("-90", "page", -90.0), ("45", "page", 45.0),
     ("90", "parent", 90.0), ("45", "parent", 45.0)],
)
def test_raw_rotation_reports_the_value_as_written(raw, where, expected):
    doc, page = box_page(where=where, Rotate=raw)
    assert raw_rotation(page) == expected
    doc.close()


def test_a_plain_page_is_never_refused():
    doc, page = box_page()
    assert drawing_refusal(page, 0, TEXT_DRAWING) is None
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


@pytest.mark.parametrize("kind", [TEXT_DRAWING, OTHER_DRAWING])
def test_user_unit_refuses_every_kind_with_the_owners_warning(kind):
    doc, page = box_page(UserUnit="1.5")
    reason = drawing_refusal(page, 3, kind)
    assert reason is not None
    assert "Page 3" in reason
    assert "/UserUnit" in reason and "1.5" in reason
    assert "nothing was changed" in reason
    assert "Support is planned" in reason
    doc.close()


def test_an_overhang_refuses_text_drawing_only():
    doc, page = box_page(CropBox="[-40 -60 660 820]")
    reason = drawing_refusal(page, 0, TEXT_DRAWING)
    assert reason is not None and "CropBox" in reason and "nothing was changed" in reason
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()


@pytest.mark.parametrize("where", ["page", "parent"])
@pytest.mark.parametrize("kind", [TEXT_DRAWING, OTHER_DRAWING])
def test_a_malformed_rotation_refuses_every_kind(kind, where):
    # Review Focus 4 / plan ruling P3.
    doc, page = box_page(where=where, Rotate="45")
    reason = drawing_refusal(page, 0, kind)
    assert reason is not None and "invalid rotation" in reason and "nothing was changed" in reason
    doc.close()


@pytest.mark.parametrize("raw", ["-90", "450", "-270", "360", "720"])
def test_un_normalised_but_valid_rotations_are_not_refused(raw):
    doc, page = box_page(Rotate=raw)
    assert drawing_refusal(page, 0, OTHER_DRAWING) is None
    doc.close()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v`
Expected: collection error, `ImportError: cannot import name 'OTHER_DRAWING' from 'engine.geometry'`.

- [ ] **Step 4: Implement the readers and the rules**

Append to `engine/geometry.py`:

```python
def _resolve(doc: fitz.Document, kind: str, value: str) -> tuple[str, str]:
    """Follow one level of indirection: a key may hold ``N 0 R``."""
    if kind != "xref":
        return kind, value
    obj = doc.xref_object(int(value.split()[0])).strip()
    return ("array" if obj.startswith("[") else "other"), obj


def _inherited(page: fitz.Page, key: str) -> tuple[str, str] | None:
    """A page attribute as written in the PDF, resolving page-tree inheritance.

    /MediaBox, /CropBox and /Rotate are INHERITABLE: set only on an ancestor
    /Pages node, they read as null at page level. This walks the /Parent
    chain, resolving indirect references, and returns ``(kind, value)`` from
    the nearest node that sets the key, or None if none does.
    """
    doc = page.parent
    xref = page.xref
    while xref:
        kind, value = _resolve(doc, *doc.xref_get_key(xref, key))
        if kind != "null":
            return kind, value
        kind, parent = doc.xref_get_key(xref, "Parent")
        if kind != "xref":
            return None
        xref = int(parent.split()[0])
    return None


def _raw_box(page: fitz.Page, key: str) -> fitz.Rect | None:
    """A box as written in the PDF, in raw PDF user space (y up).

    Read raw, with inheritance resolved, because PyMuPDF's own
    ``page.mediabox``/``page.cropbox`` are converted into two frames that
    disagree on a negative-origin MediaBox, so they cannot be compared
    against each other.
    """
    found = _inherited(page, key)
    if found is None or found[0] != "array":
        return None
    box = fitz.Rect([float(v) for v in found[1].strip("[] \n").split()])
    box.normalize()
    return box


def raw_rotation(page: fitz.Page) -> float:
    """The /Rotate value as written, inheritance resolved, defaulting to 0.

    Needed because ``page.rotation`` hides malformed values: for /Rotate 45
    it reports 0 while ``page.rect`` is swapped as if rotated, and an erase
    on such a page removes the text but paints its fill somewhere else.
    """
    found = _inherited(page, "Rotate")
    if found is None or found[0] not in ("int", "float"):
        return 0.0
    return float(found[1])


def user_unit(page: fitz.Page) -> float:
    """The page's /UserUnit, defaulting to 1.

    Read at page level ONLY. PyMuPDF does not inherit /UserUnit (verified:
    set on /Pages alone, it leaves ``page.rect`` unscaled), and it is
    PyMuPDF that draws -- so the gate must agree with PyMuPDF, not with a
    stricter reading of the spec.
    """
    doc = page.parent
    kind, value = _resolve(doc, *doc.xref_get_key(page.xref, "UserUnit"))
    if kind in ("int", "float"):
        return float(value)
    return 1.0


def crop_origin_overhangs(page: fitz.Page) -> bool:
    """True when the CropBox's top-left corner lies outside the MediaBox.

    In that configuration ``insert_text`` and ``insert_textbox`` draw shifted
    by the out-of-bounds offset at every rotation, including 0, while
    ``get_text()`` reads unshifted. Verified exact on 256 unit-1
    configurations: drift occurs iff ``crop.x0 < media.x0`` or
    ``crop.y1 > media.y1`` in raw PDF coordinates.

    Deliberately NOT ``mediabox.contains(cropbox)``: that flags a right-only
    overhang and a negative-origin MediaBox, both of which draw correctly.
    """
    media = _raw_box(page, "MediaBox")
    if media is None:
        return False
    crop = _raw_box(page, "CropBox") or media
    return crop.x0 < media.x0 or crop.y1 > media.y1


# Operations are grouped by what they paint, because the refusal rules
# apply to different sets. See spec R5 and R12.
TEXT_DRAWING = "text"  # replace_text, move_block (destination), insert_block
OTHER_DRAWING = "other"  # redact_region, delete_block, replace_image, move_block (source)


def drawing_refusal(page: fitz.Page, page_index: int, kind: str) -> str | None:
    """Why an operation must not draw on this page, or None if it may.

    Checked in order, before any mutation:

    1. A /Rotate that is not a multiple of 90 refuses EVERY drawing
       operation. The file is malformed, PyMuPDF reports it inconsistently
       (rotation 0 with a swapped rect), and an erase on such a page removes
       the text but paints its fill elsewhere.
    2. /UserUnit != 1 refuses EVERY drawing operation, including redaction
       (R12, the owner's ruling): text and fills are drawn at the wrong
       scale, and it is untested whether a scaled redaction removes only
       the intended text.
    3. A CropBox top-left overhang refuses TEXT drawing only (R5). Redaction,
       erasing and image insertion are verified correct on such pages.

    The message is written as a warning to the operator, per the owner's
    instruction: it names the cause, says nothing changed, and -- for
    /UserUnit -- that support is planned.

    Callers run this after ``_validate_target``, so on a malformed-rotation
    page whose swapped bounds reject the bbox first, the operator sees an
    off-page error instead of this one. Either way nothing is modified.
    """
    rotate = raw_rotation(page)
    if rotate % 90 != 0:
        return (
            f"Page {page_index} has an invalid rotation (/Rotate {rotate:g}; the PDF "
            f"format requires a multiple of 90), so this operation was not applied "
            f"and nothing was changed."
        )
    unit = user_unit(page)
    if unit != 1:
        return (
            f"Page {page_index} uses PDF /UserUnit scaling ({unit:g}), which the "
            f"editor does not support yet, so this operation was not applied and "
            f"nothing was changed. Support is planned."
        )
    if kind == TEXT_DRAWING and crop_origin_overhangs(page):
        return (
            f"Page {page_index} has a CropBox that extends past the top-left of its "
            f"MediaBox. Text drawn on such a page lands in the wrong place, so this "
            f"operation was not applied and nothing was changed. Redaction and "
            f"deleting content still work on this page."
        )
    return None
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v`
Expected: all pass.

- [ ] **Step 6: Mutation check — the false-positive trap**

Replace the body of `crop_origin_overhangs` temporarily with `return not page.mediabox.contains(page.cropbox)`.
Expected: `test_crop_origin_overhangs_matches_where_text_actually_drifts` fails on the `right` and `negative-origin-mediabox` cases.
Restore the function and paste the failing case ids into your report.

- [ ] **Step 7: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass. No existing test changes.

```bash
git add engine/geometry.py tests/geometry_helpers.py tests/test_geometry.py
git commit -m "feat: read page boxes, units and rotation, and decide when drawing is unsafe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

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

### Task 5: Redaction fill placement (R11)

**Files:**
- Modify: `engine/operations.py`:
  - the `engine.geometry` import (add `at_rotation_zero`)
  - `_erase_region` (lines 202–203)
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes: `engine.geometry.at_rotation_zero` from Task 1; `build_page`, `block` and `exported` from Task 3.
- Produces:
  - no new engine names. `_erase_region` keeps its signature `(page, rect, fill) -> None`.
  - in `tests/test_page_geometry.py`: `CROPS`, `BLACK`, `_same_colour(actual, expected, tolerance=0.01)`, `_fills(page, colour)`, `_on(rect, target)`, `_inherited_rotation_page(rotate, cropbox=None) -> bytes`. Tasks 6 and 7 use them.

**Red/green reference, measured by the coordinator on the engine after Task 4.** "Fill on target" means the exported fill rectangle equals the target rect. The text is removed in every case, with or without the fix.

| CropBox | 0° | 90° | 180° | 270° |
|---|---|---|---|---|
| contained `[40 60 580 740]` | on target | **off** | **off** | **off** |
| oversized `[-40 -60 660 820]` | on target | on target | **off** | **off** |

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
from engine.operations import _erase_region  # noqa: E402

GREEN = (0.0, 1.0, 0.0)
BLACK = (0.0, 0.0, 0.0)
CROPS = {"contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _same_colour(actual, expected, tolerance=0.01):
    # Drawing colours come back as floats that have been through a content
    # stream, and a sampled fill is a 0-255 value divided by 255 (C11).
    return (
        actual is not None
        and len(actual) == len(expected)
        and all(abs(a - e) <= tolerance for a, e in zip(actual, expected))
    )


def _fills(page, colour):
    return [fitz.Rect(d["rect"]) for d in page.get_drawings() if _same_colour(d.get("fill"), colour)]


def _on(rect, target):
    return all(abs(a - b) < 1 for a, b in zip(rect, target))


@pytest.mark.parametrize("crop", sorted(CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_erase_region_paints_exactly_one_fill_on_the_target(rotation, crop):
    # R11. Every _clean_erase caller and redact_region go through
    # _erase_region, so this pins all of them. Three separate properties,
    # all checked on the exported bytes: the text is gone, there is exactly
    # one fill, and that fill is on the target -- checking only the first
    # is how this defect was missed.
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS[crop]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    _erase_region(handle[0], target, fill=GREEN)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    fills = _fills(page, GREEN)
    assert len(fills) == 1, f"expected one fill, got {fills}"
    assert _on(fills[0], target), f"fill painted at {tuple(fills[0])}, target was {tuple(target)}"
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_redact_region_black_box_lands_on_the_target(rotation):
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["oversized"]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    page = exported(handle)[0]
    fills = _fills(page, BLACK)
    assert "LOW-MARKER" not in page.get_text()
    assert len(fills) == 1 and _on(fills[0], target)


def _inherited_rotation_page(rotate, cropbox=None):
    """A page whose /Rotate is set only on its /Pages parent."""
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 700), "LOW-MARKER", fontsize=12)
    if cropbox is not None:
        source.xref_set_key(page.xref, "CropBox", cropbox)
    parent = int(source.xref_get_key(page.xref, "Parent")[1].split()[0])
    source.xref_set_key(page.xref, "Rotate", "null")
    source.xref_set_key(parent, "Rotate", rotate)
    data = source.tobytes()
    source.close()
    return data


def test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation():
    # Review Focus 3, with a contained CropBox so the fill-placement defect
    # is actually exercised (C4: without a crop this test was already green).
    # at_rotation_zero writes a page-level /Rotate while drawing and restores
    # it, so the page may end with an explicit value where it had an
    # inherited one -- the effective rotation must be unchanged.
    doc, handle = parse(_inherited_rotation_page("90", cropbox=CROPS["contained"]))
    assert handle[0].rotation == 90
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    out = exported(handle)[0]
    fills = _fills(out, BLACK)
    assert out.rotation == 90
    assert len(fills) == 1 and _on(fills[0], target), f"fills {fills}, target {tuple(target)}"


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_both_redaction_calls_run_at_rotation_zero(rotation, monkeypatch):
    # R11 wraps BOTH calls. Only apply_redactions is known to need it, so
    # only a spy on each call can tell the wrapper was kept around both (C4).
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["contained"]))
    seen = {}
    real_add, real_apply = fitz.Page.add_redact_annot, fitz.Page.apply_redactions

    def spy_add(self, *args, **kwargs):
        seen["add_redact_annot"] = self.rotation
        return real_add(self, *args, **kwargs)

    def spy_apply(self, *args, **kwargs):
        seen["apply_redactions"] = self.rotation
        return real_apply(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "add_redact_annot", spy_add)
    monkeypatch.setattr(fitz.Page, "apply_redactions", spy_apply)
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert seen == {"add_redact_annot": 0, "apply_redactions": 0}
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("failing", ["add_redact_annot", "apply_redactions"])
def test_rotation_is_restored_when_a_redaction_call_raises(failing, monkeypatch):
    # A guard, green before and after the fix: it fails only if the restore
    # is not in a finally.
    doc, handle = parse(build_page(rotation=90, cropbox=CROPS["contained"]))

    def boom(self, *args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(fitz.Page, failing, boom)
    with pytest.raises(RuntimeError, match="injected"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert handle[0].rotation == 90
```

- [ ] **Step 2: Run the tests and confirm they fail as the table predicts**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured: **11 failed, 75 passed.**
- `test_erase_region_paints_exactly_one_fill_on_the_target`: exactly the five cells marked **off** in the table fail, with the "fill painted at" message.
- `test_redact_region_black_box_lands_on_the_target[180]` and `[270]` fail (the oversized row).
- `test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation` fails on fill placement.
- `test_both_redaction_calls_run_at_rotation_zero[90]`, `[180]` and `[270]` fail: the spies see the page's own rotation.
- Already passing, and kept as guards: the on-target cells, black box at 0 and 90, and both `test_rotation_is_restored_when_a_redaction_call_raises` cases. The last pair fails only if the restore is not in a `finally`.

If a cell's result differs from the table, stop and report it. Do not delete the test.

- [ ] **Step 3: Implement the fix**

Add `at_rotation_zero` to the `engine.geometry` import in `engine/operations.py`.

In `_erase_region`, replace:

```python
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)
```

with:

```python
    # Both calls at rotation 0 (spec R11): on a rotated page with a CropBox,
    # PyMuPDF removes the right text but paints the fill elsewhere -- ~88pt
    # away on the test pages, possibly over content that was NOT removed.
    # The rect stays in unrotated coordinates; only the page's orientation
    # changes, and at_rotation_zero restores it even if a call raises.
    with at_rotation_zero(page):
        page.add_redact_annot(rect, fill=fill)
        page.apply_redactions(images=2, graphics=1, text=0)
```

Keep the existing docstring. Add one line to it saying the pair runs at rotation 0 per R11.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 86 passed.

- [ ] **Step 5: Mutation check — the wrapper covers both calls**

Temporarily move `page.add_redact_annot(...)` out of the `with` block, above it. Expected: the three `test_both_redaction_calls_run_at_rotation_zero` cases fail on `add_redact_annot`. Restore it, and paste the failure line into your report.

- [ ] **Step 6: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "fix: paint redaction and erase fills where the content was removed

On a rotated page with a CropBox, PyMuPDF removed the correct text but
painted the fill elsewhere -- 88pt away on the test pages, possibly over
content that was never removed. The privacy guarantee held; the visible
result did not. Both redaction calls now run at rotation 0, which lands the
fill on target at every rotation.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

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

### Task 7: The refusal gate (R5, R12, P3, P4)

**Files:**
- Modify: `engine/operations.py`:
  - the `engine.geometry` import (add `OTHER_DRAWING`, `TEXT_DRAWING`, `drawing_refusal`)
  - a new `_refuse_unsupported_drawing` helper, placed before `_erase_region`
  - one gate call in each of the six targeted operations; two in `move_block`
  - `move_block`'s destination binding
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes:
  - `engine.geometry.drawing_refusal`, `TEXT_DRAWING` and `OTHER_DRAWING` from Task 2
  - `build_page`, `block`, `exported` and `fingerprint` from Task 3; `_inherited_rotation_page` from Task 5; `BLUE`, `IMAGE_RECT` and `_png` from Task 6
- Produces: `engine.operations._refuse_unsupported_drawing(page, page_index, kind) -> None`

**Gate placement, one call right after each operation's validation, before anything else:**

| Operation | After line | Gate |
|---|---|---|
| `redact_region` | `page, rect = _validate_target(handle, page_index, bbox)` | `page, page_index, OTHER_DRAWING` |
| `replace_text` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, TEXT_DRAWING` |
| `delete_block` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, OTHER_DRAWING` |
| `move_block` | `source_page, source_rect = _validate_target(...)` | `source_page, page_index, OTHER_DRAWING` (P4: the source is erased) |
| `move_block` | `destination_page, destination_rect = _validate_target(...)` | `destination_page, dest_index, TEXT_DRAWING` |
| `insert_block` | `page, rect = _validate_target(handle, page_index, bbox)` | `page, page_index, TEXT_DRAWING` |
| `replace_image` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, OTHER_DRAWING` |

The three `page, rect = _validate_target(...)` lines are not unique across the file. Locate each one by its operation.

Both `move_block` gates run before the source erase (`_clean_erase(source_page, source_rect)`), and nothing in `move_block` mutates the document before that erase. The coordinator confirmed this against the real body.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
OVERHANG_CASES = {
    "left": ("[-40 0 612 792]", True),
    "top": ("[0 0 612 830]", True),
    "all-four": ("[-40 -60 660 820]", True),
    "bottom": ("[0 -60 612 792]", False),
    "right": ("[0 0 660 792]", False),
    "contained": ("[40 60 580 740]", False),
}
TEXT_OPS = {
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, -100)),
    "insert_block": lambda h, b: insert_block(h, 0, (72, 300, 400, 320), "NEW", 12.0),
}
OTHER_OPS = {
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
    "delete_block": lambda h, b: delete_block(h, 0, b),
}


@pytest.mark.parametrize("case", sorted(OVERHANG_CASES))
@pytest.mark.parametrize("op", sorted(TEXT_OPS))
def test_text_operations_refuse_exactly_the_overhang_pages(op, case):
    cropbox, refused = OVERHANG_CASES[case]
    doc, handle = parse(build_page(cropbox=cropbox))
    before = fingerprint(handle)
    if refused:
        with pytest.raises(ValueError, match="CropBox"):
            TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))
        assert fingerprint(handle) == before
    else:
        TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))  # no false positive


@pytest.mark.parametrize("op", sorted(OTHER_OPS))
def test_redaction_and_erasing_still_work_on_an_overhang_page(op):
    doc, handle = parse(build_page(cropbox=OVERHANG_CASES["all-four"][0]))
    OTHER_OPS[op](handle, block(doc, "LOW-MARKER"))
    assert "LOW-MARKER" not in exported(handle)[0].get_text()


def test_text_operations_are_allowed_on_a_negative_origin_mediabox():
    # Regression guard: mediabox.contains(cropbox) would refuse this page,
    # which draws correctly.
    doc, handle = parse(build_page(mediabox="[-100 -100 512 692]"))
    replace_text(handle, 0, block(doc, "LOW-MARKER"), "LOW-MARKER")  # must not raise


ALL_TARGETED = {**TEXT_OPS, **OTHER_OPS}


# 0.5 as well as 1.5: a gate written as "unit > 1" passes every 1.5 case.
@pytest.mark.parametrize("unit", (0.5, 1.5))
@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_user_unit_page_with_the_owners_warning(op, unit):
    doc, handle = parse(build_page(user_unit=unit))
    before = fingerprint(handle)
    with pytest.raises(ValueError) as caught:
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    message = str(caught.value)
    assert "/UserUnit" in message
    assert "nothing was changed" in message
    assert "Support is planned" in message
    assert fingerprint(handle) == before


@pytest.mark.parametrize("unit", (0.5, 1.5))
def test_replace_image_refuses_a_user_unit_page(unit):
    doc, handle = parse(build_page(user_unit=unit, image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Support is planned"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_malformed_rotation(op):
    # P3, with the gate's own message: the marker sits on the page, so the
    # bbox check passes and only the gate can refuse.
    doc, handle = parse(build_page(rotate_raw="45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    assert fingerprint(handle) == before


def test_replace_image_refuses_a_malformed_rotation():
    doc, handle = parse(build_page(rotate_raw="45", image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


def test_an_inherited_malformed_rotation_is_refused():
    # /Rotate 45 set only on the /Pages parent reaches the gate through the
    # Task 2 reader's /Parent walk.
    doc, handle = parse(_inherited_rotation_page("45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert fingerprint(handle) == before


def test_move_block_refuses_when_the_source_page_uses_user_unit():
    # P4: the source is erased, and an erase paints a fill.
    doc, handle = parse(build_page(user_unit=1.5, extra_pages=1))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 0 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 100))
    assert fingerprint(handle) == before


def _plain_page_then_user_unit_page():
    source = fitz.open(stream=build_page(extra_pages=1), filetype="pdf")
    source[1].insert_text((72, 100), "PAGE-ONE", fontsize=12)
    source.xref_set_key(source[1].xref, "UserUnit", "1.5")
    data = source.tobytes()
    source.close()
    return data


def test_move_block_refuses_an_unsupported_destination_page_and_keeps_the_source():
    # P4, the other direction: a plain source page moving onto a /UserUnit
    # page. The destination gate must fire before the source is erased.
    doc, handle = parse(_plain_page_then_user_unit_page())
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 300))
    assert fingerprint(handle) == before
    assert "LOW-MARKER" in exported(handle)[0].get_text()


def test_gate_uses_the_target_pages_own_geometry():
    # Review Focus 1: page 1 uses /UserUnit, page 0 is plain. Page 0 must
    # stay fully editable, and page 1 must be refused.
    doc, handle = parse(_plain_page_then_user_unit_page())
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)  # page 0: allowed
    page_one = next(b for b in doc.pages[1].text_blocks if "PAGE-ONE" in b.text)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        redact_region(handle, 1, page_one.bbox)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured on the engine after Task 6: **31 failed, 118 passed.**
- The nine refused cases of `test_text_operations_refuse_exactly_the_overhang_pages` (left, top and all-four, for each of the three text operations) fail with `DID NOT RAISE`.
- Every case of `test_every_operation_refuses_a_user_unit_page_with_the_owners_warning` (10) and `test_replace_image_refuses_a_user_unit_page` (2) fails with `DID NOT RAISE`.
- Every case of `test_every_operation_refuses_a_malformed_rotation` (5), plus `test_replace_image_refuses_a_malformed_rotation` and `test_an_inherited_malformed_rotation_is_refused`, fails with `DID NOT RAISE`.
- Both `move_block` refusal tests and `test_gate_uses_the_target_pages_own_geometry` fail with `DID NOT RAISE`.
- Already passing, and kept as guards: the nine no-overhang cases, redaction and erasing on an overhang page, and the negative-origin MediaBox.

- [ ] **Step 3: Implement the gate helper**

Add `OTHER_DRAWING`, `TEXT_DRAWING` and `drawing_refusal` to the `engine.geometry` import in `engine/operations.py`. Then add, immediately before `def _erase_region(`:

```python
def _refuse_unsupported_drawing(page: fitz.Page, page_index: int, kind: str) -> None:
    """Raise before any mutation if this page cannot be drawn on correctly.

    See engine.geometry.drawing_refusal for the rules and the evidence. Every
    targeted operation calls this right after validating its target.
    """
    reason = drawing_refusal(page, page_index, kind)
    if reason is not None:
        raise ValueError(reason)
```

- [ ] **Step 4: Insert the seven gate calls**

Following the table above, insert one line after each named validation line. For example, `redact_region` becomes:

```python
    page, rect = _validate_target(handle, page_index, bbox)
    _refuse_unsupported_drawing(page, page_index, OTHER_DRAWING)
    _erase_region(page, rect, fill=(0, 0, 0))
```

In `move_block`, bind the destination page from its own validation, so the gate checks exactly the page that was validated. Delete the line:

```python
    destination_page = handle[dest_index]
```

and replace:

```python
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)
```

with:

```python
    destination_page, destination_rect = _validate_target(handle, dest_index, destination_bbox)
    _refuse_unsupported_drawing(destination_page, dest_index, TEXT_DRAWING)
```

Nothing between the deleted line and the validation uses `destination_page`; confirm with `grep -n destination_page engine/operations.py` before and after. The source gate goes right after `source_page, source_rect = _validate_target(handle, page_index, target.bbox)`:

```python
    _refuse_unsupported_drawing(source_page, page_index, OTHER_DRAWING)
```

Also add one sentence to the `Raises:` section of each of the six docstrings: *"or the page cannot be drawn on correctly (malformed /Rotate, /UserUnit, or — for text — a CropBox overhang); see engine.geometry.drawing_refusal."*

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 149 passed.

- [ ] **Step 6: Mutation check — each gate is load-bearing**

Back up the file first, then delete each of the seven gate calls in turn, restoring from the backup between runs:

```bash
cp engine/operations.py "$TEMP/operations.py.task7"
# delete one gate line, run the file, then:
cp "$TEMP/operations.py.task7" engine/operations.py
```

Do not use `git stash`.

Expected failure counts, measured by the coordinator:

| Gate removed | Tests that fail |
|---|---|
| `redact_region` | 5 |
| `replace_text` | 6 |
| `delete_block` | 3 |
| `move_block` source | 1 |
| `move_block` destination | 4 |
| `insert_block` | 6 |
| `replace_image` | 3 |

Paste a seven-row table into your report: the gate removed, and the names of the tests that failed. After the last restore, confirm that `git diff` shows only your intended changes, then delete the backup.

- [ ] **Step 7: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "feat: refuse drawing on pages the engine cannot render correctly

Before any mutation, every targeted operation now refuses a page with a
malformed /Rotate, with /UserUnit scaling, or -- for text drawing only -- a
CropBox whose top-left extends past the MediaBox. Redaction is still allowed
on overhang pages, where it is verified correct. The /UserUnit refusal is
worded as the owner asked: it names the cause, says nothing changed, and
says support is planned.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

### Task 8: Audit, documentation, and the regression record

**Files:**
- Create: `docs/superpowers/records/2026-09-26-page-operations/audit.md`
- Modify: `engine/parser.py` (the docstring near line 106)
- Modify: `README.md`, under `## Operations`
- Modify: `docs/superpowers/specs/2026-09-26-page-operations-design.md` (two wording corrections)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Carry out the R9 audit and write it down**

Search `engine/` for every drawing call and every use of page dimensions:

```bash
grep -n "insert_textbox\|insert_text(\|insert_image\|draw_rect\|draw_line\|add_redact_annot\|apply_redactions\|show_pdf_page" engine/*.py
grep -rn "page\.rect\|\.rect\.width\|\.rect\.height\|\.width\b\|\.height\b\|mediabox\|cropbox" engine/ webui/ --include=*.py
```

Create `audit.md` with two tables:

1. **Drawing calls.** Every hit, with its file:line, and how it is now handled. Each call is either:
   - at rotation 0 (R4 / R11); or
   - text drawing, gated by the overhang and `/UserUnit` rules; or
   - not position-dependent, such as `insert_font`, with the reason.

   Confirm there is no `draw_rect` or other drawing primitive left unhandled (R14).
2. **Dimension consumers.** Every use of page dimensions in `engine/` and `webui/`. For each, say whether it is used for coordinate math. The coordinator's grep found only `parser.py`'s `Page.width/height` and `session.get_pages_summary()`, both of which are display-only. Confirm or correct that.

- [ ] **Step 2: Document the display dimensions in the parser**

In `engine/parser.py`, add a short comment above the `width=pdf_page.rect.width,` line:

```python
                # DISPLAY dimensions: page.rect, which swaps width and height at
                # 90/270. Block bboxes are in UNROTATED space -- use
                # engine.geometry.unrotated_bounds for any coordinate math.
```

- [ ] **Step 3: Document supported page geometry in the README**

Add this paragraph at the end of the `## Operations` list in `README.md`:

```markdown
**Page geometry.** Every operation is correct on rotated pages, on pages with
a CropBox, and on fractional-size pages. The refusal check decides from the
layout PyMuPDF itself computes for the page (its own page transform and
boxes), never from the raw PDF keys, so it agrees with what gets drawn. These
configurations are refused before anything is changed, with a message that
says why:
- an invalid rotation: a `/Rotate` that is not a multiple of 90, or a negative
  `/UserUnit`, which lays the page out at a different orientation;
- page boxes PyMuPDF lays out inconsistently (malformed, or under 1pt);
- `/UserUnit` scaling (support is planned);
- page boxes beyond 2^24 points, where coordinates lose precision;
- for the three text-drawing operations only, a CropBox whose top-left extends
  past the MediaBox.

Redaction is not refused because of a CropBox overhang alone. The check reads
MuPDF's page transform through PyMuPDF's low-level binding; if a PyMuPDF
upgrade removes it, every page is refused rather than drawn wrongly. See
`docs/superpowers/specs/2026-09-26-page-operations-design.md`.
```

- [ ] **Step 4: Correct the spec's record of the false positives**

In `docs/superpowers/specs/2026-09-26-page-operations-design.md`, replace:

```markdown
gives false positives on two documents that behave correctly: a right-only overhang,
and a MediaBox with a negative origin (`[-100 -100 512 692]`). It would refuse valid,
real documents.
```

with:

```markdown
gives false positives on three documents that behave correctly: a right-only overhang,
a bottom-only overhang (raw CropBox `[0 -60 612 792]`, which PyMuPDF reports as
`(0, 0, 612, 852)` against a MediaBox of `(0, 0, 612, 792)`), and a MediaBox with a
negative origin (`[-100 -100 512 692]`). It would refuse valid, real documents.
(Corrected during Merge A: Task 2's mutation check found the third.)
```

- [ ] **Step 5: Record the regression evidence**

Add a section to `audit.md` named "Regression record", containing:

1. **The critic's probes.** They are a PyMuPDF baseline: `recheck_geometry.py` exercises its own helper copies, not the engine.

   ```bash
   cd docs/superpowers/records/2026-09-26-page-operations/probes
   timeout 600 ../../../../../.venv/Scripts/python.exe recheck_geometry.py | tail -1
   ```

   Expected: `SUMMARY {'cases': 1024, 'bounds_fail': 0, 'visible_fail': 0, 'offpage_fail': 0, 'sample_fail': 0, 'library_sample_fail': 640, 'matrix_different': 732}`.

2. **The production run.** This is the same 1,024-case matrix, run through `engine.geometry` itself, with the module's location recorded:

   ```bash
   timeout 600 ./.venv/Scripts/python.exe -c "import engine.geometry as g; print(g.__file__)"
   timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -q
   ```

   The printed path must be inside this checkout. Paste it and the pytest summary line.

3. **The Task 2 mutation, stated accurately.** Replacing `crop_origin_overhangs` with `mediabox.contains(cropbox)` fails **4** tests: the bottom, right and negative-origin cases, plus the 256-case drift test (60 mismatches).

4. **Timings.** Any timing in this plan, such as "about 4 seconds" for the matrix, was measured on the coordinator's machine and is not a requirement.

- [ ] **Step 6: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q > "$TEMP/task8-pytest.txt" 2>&1; echo "exit $?"`

Expected: exit 0, all pass. Record the final count and the exit status in `audit.md`, and put the full output file's contents in your report.

```bash
git add docs/superpowers/records/2026-09-26-page-operations/audit.md engine/parser.py README.md docs/superpowers/specs/2026-09-26-page-operations-design.md
git commit -m "docs: audit page geometry handling and document supported configurations

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

## Final whole-branch review (Fable)

This merge is privacy-critical: its failures are refused redactions and fills painted over unredacted content. So the final review runs on Fable, and it must go beyond reading the diff.

- **Mutation sweep.** Revert each of D1–D5, R3, R4, R11 and the seven gates in turn, in a scratch copy. Confirm a named test fails for each.
- **Real scans.** Take at least one real-world scanned PDF with `/Rotate` set, if one is available, and confirm the fills in the exported bytes land where the text was removed. The synthetic fixtures may not match real scanner output, where a content stream can carry its own rotation transform as well as `/Rotate`.
- **Exported bytes, not the live handle.** Check at least redaction, erase and image placement this way, re-parsed from scratch.
- **Tests left red or tightened.** Confirm none of the 227 pre-existing tests was edited to pass: `git diff master -- tests/` must show only additions.
- **Owner's instructions.** Confirm the `/UserUnit` warning wording matches R12's final ruling.

---

## REVISION after the Codex plan critique (rulings C2–C12)

The critique (REVISE BRIEF, 12 points) and every ruling on it are recorded in the SDD ledger. Tasks 3–8 above were rewritten to carry them. C1 and C5 went into Task 2's fix round instead.

**How the new text was verified.** Every test in Tasks 3–7 was run exactly as written. It ran against a staged engine for each task boundary, built from the pre-Merge-A code plus the fixes of the tasks before it. Each task's tests were run before and after its own fix. The red counts in each "confirm they fail" step are those measurements, not predictions:

| Task | Before its fix | After its fix |
|---|---|---|
| 3 | 20 failed, 28 passed | 48 passed |
| 4 | 16 failed, 52 passed | 68 passed |
| 5 | 11 failed, 75 passed | 86 passed |
| 6 | 6 failed, 100 passed | 106 passed |
| 7 | 31 failed, 118 passed | 149 passed |

With every fix applied, the full suite passed: 418 tests, including the 227 pre-Merge-A tests, unedited. The following mutations were also run:
- The D3-only revert fails 4 tests.
- Narrowing the R11 wrapper to `apply_redactions` alone fails only the 3 spy tests. The fill still lands, which confirms the critic's finding and is why the spies exist.
- Removing each of the seven gates fails 5, 6, 3, 1, 4, 6 and 3 tests respectively.

**What changed, by ruling:**
- **C2.** `fingerprint` now covers every xref object, every raw stream, and the page count. Three self-tests prove it is stable on a no-op and detects both an added annotation and a resource change. P5's "32 bytes" becomes "the trailer `/ID`".
- **C3.** Task 4 tests `_sample_background_color` directly: plain, contained and oversized pages at all four rotations. The `delete_block` end-to-end test is restricted to plain pages. The fractional test is red at all four rotations, not just 0.
- **C4.** The inherited-rotation fixture now has a contained CropBox; without it, the test was already green. Spies assert rotation 0 at both redaction calls. An injected exception at each call must leave the rotation restored. A new Task 5 mutation step proves the spies are what pin the wrapper's scope.
- **C6.**
  - `move_block` binds `destination_page` from its own `_validate_target` call.
  - New tests: a plain source moving onto a `/UserUnit` destination (fingerprint unchanged, source text kept); malformed-rotation `replace_image`; an inherited malformed rotation; and `/UserUnit` 0.5 alongside 1.5.
  - The malformed-rotation tests now match the gate's own "invalid rotation" message.
  - `git stash` is replaced by a per-file backup.
- **C7.** The straddle case is red at 90/270 before Task 3, not "already passing". A fixture test pins the marker's reported origin and size for six geometries. The size check covers every replacement span, with `pytest.approx(..., abs=0.01, rel=0)`.
- **C8.** Task 6 isolates the erase stage:
  - a spy on `replace_image`'s own `_clean_erase` call;
  - `insert_image` disabled, only after the fixture is built;
  - checks that no image remains, that a band-coloured fill lies exactly on the placement, and that the band and the nearby text survive.

  The insertion test stays separate. A left-overhang replacement guards Task 7 against over-refusal.
- **C9 / C10.**
  - Task 8 records the Task 2 mutation accurately: 4 failing tests.
  - It marks timings as machine-specific.
  - It adds a production run of the geometry matrix through `engine.geometry`, recording the module's path, beside the critic's own-helper baseline.
  - It corrects the spec: three false positives, not two.
- **C11.** `_same_colour` compares drawing colours with a 0.01 tolerance. The fractional test documents why each sample lands inside its patch.
- **C12.**
  - A guard test asserts that `engine` and `tests.geometry_helpers` resolve inside this checkout.
  - Each task's report saves the full pytest output and exit status.
  - Every task imports only the `engine.geometry` names it uses (ruling S1).

**New traps found while verifying, now written into the tasks:**
- A CropBox shifts the page coordinates that drawings are read back in. The C8 test therefore reads the band's rect from the fixture itself, never from the rect it was drawn at.
- The erase-isolation test is already green when Task 6 starts, because Task 5 fixed the erase path. On the engine before Task 5 it was measured red, at contained 90/180/270 and oversized 180/270.

## REVISION 2: the Task 2 gate design changed (rulings C15, C16)

Task 2's security re-reviews found that raw-key parsing could not keep up with MuPDF's own parser. The gate now reads PyMuPDF's interpreted geometry (C15) and MuPDF's real page transform (C16). The ledger records each bypass and the coordinator's verification: the 1,024-case matrix and 128 adversarial PDFs, compared against a drawing probe.

Consequences for the tasks above:
- **Task 7.** Its tests match the new messages. The "invalid rotation", "/UserUnit", "Support is planned", "nothing was changed" and "CropBox" phrases were all kept. No text change.
- **Task 8.** The README paragraph was updated above to describe the new refusal classes. The audit should add one row for the private-API dependency: `page._pdf_page()` plus `mupdf.pdf_page_transform`, which fail closed.
