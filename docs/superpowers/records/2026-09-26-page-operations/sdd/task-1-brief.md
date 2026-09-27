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

