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

