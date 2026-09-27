# Task 2 — fix round 2 brief (coordinator ruling C15: interpreted-geometry gate)

Read `task-2-rereview-1.md` in this directory first. It is the security review of your round-1 fix. I2, M3, M4, M5, A1 and A2 passed. It then found verified gate bypasses: pages where PyMuPDF misdraws text, but `drawing_refusal` allows it. They share one root cause. Our code re-parses raw PDF keys, and MuPDF's own parser does something different in a long tail of cases:
- how deep it follows references, and dangling references;
- a null or a reference cycle stops its inheritance walk;
- `pdf_to_rect` takes the first four entries of a box and reads non-numbers as 0;
- it falls back to a letter-size MediaBox;
- it reads integers as int32 in some paths and int64 in others;
- it overflows on a real /Rotate.

Emulating each quirk is whack-a-mole.

**Ruling C15.** Stop reading raw keys. Decide from the geometry PyMuPDF itself has already computed for the page: `page.rotation`, `page.rect`, `page.mediabox`, `page.cropbox` and `page.transformation_matrix`. Those values ARE MuPDF's interpretation, so the gate agrees with what gets drawn by construction.

The coordinator verified the code below against a drift probe (insert text at (100, 140), re-open, read the origin back):
- the whole 1,024-case matrix at units 0.5, 1, 1.5 and 2: 0 mismatches;
- all 39 adversarial PDFs listed further down: no bypass.

The only disagreements are in the safe direction. `/UserUnit 0` produces a page that cannot be drawn at all, and the gate refuses it.

## 1. Replace the readers in `engine/geometry.py`

Delete:
- `_REFERENCE`, `_classify`, `_resolve`, `_inherited`, `_raw_box` and `raw_rotation`;
- the `re` import, if nothing else uses it.

Replace `user_unit`, `crop_origin_overhangs` and `drawing_refusal` with the code below. Keep `unrotated_bounds`, `to_display_matrix`, `at_rotation_zero`, `TEXT_DRAWING` and `OTHER_DRAWING` exactly as they are. Also update the module docstring: it should say the gate reads PyMuPDF's interpreted geometry, never raw keys, and why.

```python
# Tolerance, in points over the page's larger side, for "PyMuPDF laid this
# page out at scale 1". /UserUnit 1.0000001 moves nothing measurable and is
# allowed; /UserUnit 1.5 is refused.
_LAYOUT_TOLERANCE_PT = 0.01


def visible_area(page: fitz.Page) -> fitz.Rect:
    """The part of the page PyMuPDF shows, in the frame it reports page.cropbox in.

    PyMuPDF's page.cropbox keeps the PDF's x but measures y DOWN from the
    MediaBox's top edge, so the MediaBox in that frame is
    (mediabox.x0, 0, mediabox.x1, mediabox.height). Both boxes are PyMuPDF's
    own interpretation -- inheritance, references, malformed arrays and the
    letter-size fallback already applied -- which is the point: the gate must
    agree with what PyMuPDF draws, not with our reading of the raw keys.
    """
    mediabox = page.mediabox
    return page.cropbox & fitz.Rect(mediabox.x0, 0, mediabox.x1, mediabox.height)


def rotation_is_valid(page: fitz.Page) -> bool:
    """False when PyMuPDF is in its malformed-rotation state.

    A /Rotate that is not a multiple of 90 -- including one that overflows
    MuPDF's integer conversion, such as 2700000000.0 -- makes PyMuPDF report
    rotation 0 with a swapped rect. Its transformation matrix then has
    off-diagonal terms, which no valid rotation produces.
    """
    matrix = page.transformation_matrix
    return abs(matrix.b) < 1e-9 and abs(matrix.c) < 1e-9


def user_unit(page: fitz.Page) -> float | None:
    """The scale PyMuPDF actually lays this page out at, or None if its boxes
    are inconsistent with any single scale.

    Measured, not read: page.rect divided by the visible area (swapped at
    90/270). This catches every way /UserUnit reaches PyMuPDF -- indirect,
    chained, inherited or not, int64-sized -- and ignores every way it does
    not (a value MuPDF discards is scale 1 here, because it IS drawn at 1).
    """
    visible = visible_area(page)
    width, height = visible.width, visible.height
    if page.rotation in (90, 270):
        width, height = height, width
    if visible.is_empty or width <= 0 or height <= 0:
        return None
    scale_x, scale_y = page.rect.width / width, page.rect.height / height
    if abs(scale_x - scale_y) * max(width, height) > _LAYOUT_TOLERANCE_PT:
        return None
    return scale_x


def crop_origin_overhangs(page: fitz.Page) -> bool:
    """True when the visible area's top-left extends past the MediaBox (R5).

    In PyMuPDF's cropbox frame (see visible_area) that is: left of the
    MediaBox's x0, or above its top edge, y = 0. Text drawn on such a page
    lands in the wrong place. A bottom-only or right-only overhang, or a
    MediaBox with a negative origin, draws correctly and is not flagged --
    the three documents mediabox.contains(cropbox) wrongly refuses.
    """
    return page.cropbox.x0 < page.mediabox.x0 or page.cropbox.y0 < 0


def drawing_refusal(page: fitz.Page, page_index: int, kind: str) -> str | None:
    """<keep the existing docstring's rule list and caller note, updated to
    the four rules below and to say every rule reads PyMuPDF's interpreted
    geometry>"""
    if not rotation_is_valid(page):
        return (
            f"Page {page_index} has an invalid rotation (its /Rotate is not a "
            f"multiple of 90, as the PDF format requires), so this operation was "
            f"not applied and nothing was changed."
        )
    unit = user_unit(page)
    matrix = page.transformation_matrix
    if unit is None or not (matrix.a > 0 and matrix.d < 0):
        return (
            f"Page {page_index} has page boxes that PyMuPDF lays out "
            f"inconsistently (a malformed CropBox, MediaBox or /UserUnit), so the "
            f"editor cannot place anything on it reliably. This operation was not "
            f"applied and nothing was changed."
        )
    if abs(unit - 1) * max(page.rect.width, page.rect.height) / unit > _LAYOUT_TOLERANCE_PT:
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

**Why each check matters, from the verified runs:**
- The mirror check, `matrix.a > 0 and matrix.d < 0`, catches `/UserUnit -1`. That page lays out at scale 1 but mirrored: text lands at (512, 652), not (100, 140).
- The /UserUnit tolerance is divided by `unit` because `page.rect` is already scaled.
- The rule order is fixed: rotation first (M4 still holds), then inconsistent boxes, then /UserUnit, then the overhang.
- The four messages keep the phrases later tasks match on: "invalid rotation", "Page N uses PDF /UserUnit", "Support is planned", "nothing was changed" and "CropBox".

## 2. Tests: pin agreement with drawing, not our parser

The binding principle from round 1 stands: **every gate test must agree with what PyMuPDF draws, checked by drawing.** Rewrite `tests/test_geometry.py`'s reader and refusal tests on that basis.

**Delete** these, because they pin raw-key parsing that no longer exists:
- `test_user_unit_reads_the_page_level_value_only`
- `test_raw_rotation_reports_the_value_as_written`
- `test_a_two_level_chained_reference_resolves_to_the_final_value`
- `test_a_reference_cycle_resolves_to_null_and_terminates`
- `test_an_indirect_null_continues_the_inheritance_walk_to_the_parent`, which pinned the wrong direction (bypass J)
- `test_a_malformed_cropbox_array_is_treated_as_absent_matching_pymupdf`, which pinned bypasses H and I
- `test_a_non_numeric_rotate_defaults_to_zero_matching_pymupdf`
- `test_a_non_numeric_user_unit_defaults_to_one_matching_pymupdf`

Two of these could instead be rewritten as agreement cases; if you do that, name them for what they check. Keep, adjusting only names and expected messages:
- the 1,024-case geometry tests;
- the `at_rotation_zero` tests;
- the overhang cases;
- the inherited, indirect, local-override and grandparent box tests (A2);
- the plain page, /UserUnit, overhang and malformed-rotation refusal tests;
- the un-normalised valid rotations;
- the indirect /UserUnit and indirect /Rotate tests, including the ancestor case (A1);
- rule order (M4);
- the parent-cycle test. It must still finish within 5 s. It may now raise from PyMuPDF instead of returning; either outcome is acceptable, a hang is not.

**Add to `tests/geometry_helpers.py`:**

```python
def drift_probe(pdf_bytes: bytes):
    """Draw PROBE at (100, 140) the way the editor draws text, re-open the
    bytes, and return (drifted, origin). drifted is None if the text cannot
    be found at all (a page PyMuPDF cannot lay out)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc[0].insert_text((100, 140), "PROBE", fontsize=10)
    reopened = fitz.open(stream=doc.tobytes(), filetype="pdf")
    doc.close()
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_MEDIABOX_CLIP
    text = reopened[0].get_text("dict", clip=fitz.INFINITE_RECT(), flags=flags)
    origin = next(
        (span["origin"] for block in text["blocks"] for line in block.get("lines", [])
         for span in line["spans"] if span["text"] == "PROBE"),
        None,
    )
    reopened.close()
    if origin is None:
        return None, None
    return abs(origin[0] - 100) > 0.01 or abs(origin[1] - 140) > 0.01, tuple(origin)
```

Add a raw-bytes builder as well: catalog = object 1, pages = 2, page = 3, extra objects from 4, and `/Root 1 0 R`. Reuse your `raw_object_page` if it already produces exactly that; otherwise copy `build` and `standard` from the reviewer's `scratchpad/fable-t2/adversarial.py`. The path is `C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t2/`, where `behav3.py` and `cand.py` are the coordinator's verification.

**Test A — the matrix agrees with drawing.** Run every case of `matrix_cases(units=(0.5, 1, 1.5, 2))`:
- At unit 1, `drawing_refusal(page, 0, TEXT_DRAWING)` is `None` exactly when `drift_probe` reports no drift. When it is not `None`, it is the overhang message.
- At every other unit, the /UserUnit message names that unit.

The coordinator measured 0 mismatches. Record the runtime in your report.

**Test B — the adversarial table agrees with drawing.** Parametrise over the 39 cases below. For each case, assert two things:
1. the refusal category (TEXT_DRAWING), matched by message phrase;
2. agreement with the probe: if the gate allows TEXT_DRAWING, `drift_probe` must report `(False, …)`; if the probe reports drift, the gate must refuse.

L is `/MediaBox [0 0 612 792]`, and `std(x)` is the standard three-object document with x in the page dict. Categories: `-` allowed, `rot` invalid rotation, `unit` /UserUnit, `incons` inconsistent boxes, `over` overhang.

| id | page dict (extra objects from 4) | expected |
|---|---|---|
| rot45 | L /Rotate 45 | rot |
| rot-2.7e9 | L /Rotate 2700000000.0 | rot |
| rot-2^32+45 | L /Rotate 4294967341 | rot |
| rot-2^32+90 | L /Rotate 4294967386 | - |
| rot45-square | /MediaBox [0 0 600 600] /Rotate 45 | rot |
| rot270-square | /MediaBox [0 0 600 600] /Rotate 270 | - |
| rot-90 | L /Rotate -90 | - |
| rot450 | L /Rotate 450 | - |
| unit2 | L /UserUnit 2 | unit |
| unit-2^32+1 | L /UserUnit 4294967297 | unit |
| unit1.0000001 | L /UserUnit 1.0000001 | - |
| unit-indirect | L /UserUnit 4 0 R; obj4 = 2 | unit |
| unit-chain16 | L /UserUnit 4 0 R; objs 4..18 = `5 0 R`…`19 0 R`; obj19 = 2 | - (MuPDF stops resolving) |
| unit2-rot90 | L /UserUnit 2 /Rotate 90 | unit |
| unit2-square-rot90 | /MediaBox [0 0 600 600] /UserUnit 2 /Rotate 90 | unit |
| unit0.5 | L /UserUnit 0.5 | unit |
| unit-1 | L /UserUnit -1 | incons (mirrored) |
| unit0 | L /UserUnit 0 | refused, any category; probe returns None |
| unit1e30 | L /UserUnit 1e30 | - |
| G1 | L /CropBox [4 0 R -60 660 820]; obj4 = -40 | over |
| H1 | L /CropBox [-40 -60 660 820 0] | over |
| H2 | /MediaBox [0 0 612 792 0] /CropBox [-40 -60 660 820] | over |
| I1 | /MediaBox [0 0 612] /CropBox [-40 -60 660 820] | over |
| I3 | /CropBox [-40 -60 660 820] (no MediaBox) | over |
| I5 | L /CropBox [-40 -60 660] | incons |
| N3 | /MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]; obj4 = 0 | over |
| J-null | page: /MediaBox 4 0 R /CropBox [-40 0 612 692], obj4 = null; pages node: /MediaBox [-100 -100 512 692] | incons |
| J2 | page: L /CropBox 4 0 R, obj4 = null; pages node: /CropBox [-40 -60 660 820] | - (MuPDF does not inherit past a null) |
| B2 | page: L /Parent 4 0 R, obj4 = `2 0 R`; pages node: /CropBox [-40 -60 660 820] | over |
| dangling | L /CropBox 99 0 R /UserUnit 99 0 R /Rotate 99 0 R | - (no exception) |
| dangling-parent | L /Parent 99 0 R | - (no exception) |
| negmedia-left | /MediaBox [-100 -100 512 692] /CropBox [-140 0 512 692] | over |
| negmedia-top | /MediaBox [-100 -100 512 692] /CropBox [-100 -100 512 720] | over |
| crop-empty | L /CropBox [100 100 100 100] | - |
| crop-outside | L /CropBox [700 800 900 1000] | incons |
| media-zero | /MediaBox [0 0 0 0] | - |
| crop-inverted | L /CropBox [612 792 -40 -60] | over |
| rot90-left | L /Rotate 90 /CropBox [-40 0 612 792] | over |
| rot180-top | L /Rotate 180 /CropBox [0 0 612 830] | over |

If a row disagrees with the table when you run it, but the probe still agrees with the gate, report it: the table is wrong, not the code. If the probe disagrees with the gate, stop and report. That is a bypass.

Also check TEXT_DRAWING vs OTHER_DRAWING: every non-`over` refusal applies to OTHER_DRAWING too, and `over` does not.

## 3. Red first, then mutations

- **Red.** Before changing `engine/geometry.py`, run the new Test A and Test B against the round-1 code. Record which cases fail; the review's bypass rows (G1, H1, H2, I1, I3, I5, N3, J-null, unit-2^32+1, rot-2.7e9) must be among them. Then implement.
- **Mutations**, each run on a copy with the checkout restored afterwards. Record the failing test ids for each:
  1. Remove the mirror check.
  2. Change `page.cropbox.y0 < 0` to `page.cropbox.y0 < page.mediabox.y0`.
  3. Replace `crop_origin_overhangs` with `not page.mediabox.contains(page.cropbox)`.
  4. Make `rotation_is_valid` always return True.

## 4. Report

Append a "Fix round 2" section to `task-2-report.md`. It must contain:
- the red run and the mutation results;
- Test A's runtime;
- the full `tests/` pytest output and its exit status.

Commit on top of HEAD. Do not amend, reset or rebase. Message: `fix: decide page-drawing refusals from PyMuPDF's interpreted geometry`, with the attribution lines used in earlier commits.
