# Task 3 report: Bound checks (D1, D3, D4, D5)

Branch: `page-operations`. Starting HEAD: `b539129`.

## Summary

Implemented D1 (`_validate_target`), D3 (`_insertion_rect`), D4
(`move_block`'s containment check) and D5 (`insert_block`'s containment
check) in `engine/operations.py`, using `engine.geometry.unrotated_bounds`
instead of `page.rect` for all bound/containment comparisons. Added
`tests/geometry_helpers.py::build_page` and `tests/test_page_geometry.py`
exactly as specified in the brief.

## Step 1-2: helper + failing tests

`build_page` appended to the end of `tests/geometry_helpers.py` (no new
imports needed -- `fitz` and `BAND` were already present in that file).
`tests/test_page_geometry.py` created verbatim from the brief.

## Step 3: Red run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v > <file> 2>&1; echo "exit $?"`

Result: **20 failed, 28 passed** -- exact match to the brief's expected red
list and counts. Full output below.

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 48 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  4%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  6%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [ 10%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [ 12%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [ 14%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [ 16%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [ 18%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] FAILED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] FAILED [ 29%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 31%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] FAILED [ 33%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 35%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] FAILED [ 37%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 39%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] FAILED [ 41%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 43%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] FAILED [ 45%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 47%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] FAILED [ 50%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 52%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] FAILED [ 54%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 56%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] FAILED [ 58%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 60%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] FAILED [ 62%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 64%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] FAILED [ 66%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 68%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] FAILED [ 70%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] FAILED [ 72%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] FAILED [ 75%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 77%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 79%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 81%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 83%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 85%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] FAILED [ 87%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 89%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] FAILED [ 91%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size FAILED [ 93%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page FAILED [ 95%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] FAILED [ 97%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] FAILED [100%]

================================== FAILURES ===================================
_ test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] _

op = 'delete_block', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:120: in <lambda>
    "delete_block": lambda h, b: delete_block(h, 0, b),
                                 ^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:691: in delete_block
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 22>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] _

op = 'delete_block', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:120: in <lambda>
    "delete_block": lambda h, b: delete_block(h, 0, b),
                                 ^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:691: in delete_block
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 26>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] _

op = 'insert_block', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:122: in <lambda>
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:832: in insert_block
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 30>), page_index = 0
bbox = (72, 740, 400, 760)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72, 740, 400, 760) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] _

op = 'insert_block', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:122: in <lambda>
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:832: in insert_block
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 34>), page_index = 0
bbox = (72, 740, 400, 760)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72, 740, 400, 760) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
__ test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] __

op = 'move_block', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:121: in <lambda>
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, 20)),
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:741: in move_block
    source_page, source_rect = _validate_target(handle, page_index, target.bbox)
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 38>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] __

op = 'move_block', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:121: in <lambda>
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, 20)),
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:741: in move_block
    source_page, source_rect = _validate_target(handle, page_index, target.bbox)
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 42>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] _

op = 'redact_region', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:118: in <lambda>
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:531: in redact_region
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 46>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] _

op = 'redact_region', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:118: in <lambda>
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:531: in redact_region
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 50>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] _

op = 'replace_text', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:119: in <lambda>
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:612: in replace_text
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 54>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] _

op = 'replace_text', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:119: in <lambda>
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\operations.py:612: in replace_text
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 58>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
___________ test_replace_image_accepts_an_image_low_on_the_page[90] ___________

rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    def test_replace_image_accepts_an_image_low_on_the_page(rotation):
        # The sixth operation that validates a target (spec E1). No CropBox here,
        # so insert_image already lands correctly (spec F2); only D1 is in play.
        doc, handle = parse(build_page(rotation=rotation, texts=(), image_rect=(72, 700, 136, 764)))
>       replace_image(handle, 0, doc.pages[0].images[0], solid_png(8, 8, (30, 30, 220)))

tests\test_page_geometry.py:138: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:936: in replace_image
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 62>), page_index = 0
bbox = (72.0, 700.0, 136.0, 764.0)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 700.0, 136.0, 764.0) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
__________ test_replace_image_accepts_an_image_low_on_the_page[270] ___________

rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    def test_replace_image_accepts_an_image_low_on_the_page(rotation):
        # The sixth operation that validates a target (spec E1). No CropBox here,
        # so insert_image already lands correctly (spec F2); only D1 is in play.
        doc, handle = parse(build_page(rotation=rotation, texts=(), image_rect=(72, 700, 136, 764)))
>       replace_image(handle, 0, doc.pages[0].images[0], solid_png(8, 8, (30, 30, 220)))

tests\test_page_geometry.py:138: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:936: in replace_image
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 66>), page_index = 0
bbox = (72.0, 700.0, 136.0, 764.0)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 700.0, 136.0, 764.0) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
__ test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] __

rotation = 90

    @pytest.mark.parametrize("rotation", (90, 270))
    def test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected(rotation):
        # x=650 is inside a rotated page.rect (792 wide) but beyond the real,
        # unrotated page (612 wide). The old check accepted it.
        doc, handle = parse(build_page(rotation=rotation))
>       with pytest.raises(ValueError, match="entirely off-page"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE ValueError

tests\test_page_geometry.py:146: Failed
_ test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] __

rotation = 270

    @pytest.mark.parametrize("rotation", (90, 270))
    def test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected(rotation):
        # x=650 is inside a rotated page.rect (792 wide) but beyond the real,
        # unrotated page (612 wide). The old check accepted it.
        doc, handle = parse(build_page(rotation=rotation))
>       with pytest.raises(ValueError, match="entirely off-page"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE ValueError

tests\test_page_geometry.py:146: Failed
____ test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] _____

rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    def test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page(rotation):
        # Review Focus 2: redact_region uses intersects, not contains, so a bbox
        # overhanging the page's right edge (x=612) is still a valid target. At
        # 90/270 the old check compared it with the swapped rect (612 high), where
        # y=690 is already off-page, and rejected it.
        doc, handle = parse(build_page(rotation=rotation))
>       redact_region(handle, 0, (580, 690, 640, 710))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:164: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:531: in redact_region
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 82>), page_index = 0
bbox = (580, 690, 640, 710)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (580, 690, 640, 710) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
____ test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] ____

rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    def test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page(rotation):
        # Review Focus 2: redact_region uses intersects, not contains, so a bbox
        # overhanging the page's right edge (x=612) is still a valid target. At
        # 90/270 the old check compared it with the swapped rect (612 high), where
        # y=690 is already off-page, and rejected it.
        doc, handle = parse(build_page(rotation=rotation))
>       redact_region(handle, 0, (580, 690, 640, 710))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:164: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:531: in redact_region
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 86>), page_index = 0
bbox = (580, 690, 640, 710)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (580, 690, 640, 710) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_______ test_identical_replacement_low_on_a_rotated_page_keeps_its_size _______

    def test_identical_replacement_low_on_a_rotated_page_keeps_its_size():
        # D3: the old growth cap used the rotated height (612), losing the
        # headroom a low block needs, so the replacement shrank. Every span of
        # the replacement is checked, not only the first.
        doc, handle = parse(build_page(rotation=90))
        b = block(doc, "LOW-MARKER")
>       replace_text(handle, 0, b, b.text)

tests\test_page_geometry.py:173: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:612: in replace_text
    page, rect = _validate_target(handle, page_index, target.bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 88>), page_index = 0
bbox = (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72.0, 687.0999755859375, 154.66799926757812, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
__________ test_insert_block_fits_a_tight_box_low_on_a_rotated_page ___________

    def test_insert_block_fits_a_tight_box_low_on_a_rotated_page():
        # E2: insert_block has no shrink loop, so on the old code lost headroom
        # made it RAISE "does not fit" for text that fits unrotated.
        doc, handle = parse(build_page(rotation=90))
        b = block(doc, "LOW-MARKER")
>       insert_block(handle, 0, (300, b.bbox[1], 560, b.bbox[3]), "FITS", b.size)

tests\test_page_geometry.py:185: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:832: in insert_block
    page, rect = _validate_target(handle, page_index, bbox)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 90>), page_index = 0
bbox = (300, 687.0999755859375, 560, 703.5880126953125)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (300, 687.0999755859375, 560, 703.5880126953125) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
_______ test_move_block_accepts_a_destination_low_on_a_rotated_page[90] _______

rotation = 90

    @pytest.mark.parametrize("rotation", (90, 270))
    def test_move_block_accepts_a_destination_low_on_a_rotated_page(rotation):
        # D4: masked by D1 on the old code, and would surface as soon as D1 was
        # fixed alone.
        doc, handle = parse(build_page(rotation=rotation, texts=((72, 100, "TOP-MARKER"),)))
>       move_block(handle, 0, block(doc, "TOP-MARKER"), target_position=(72, 740))

tests\test_page_geometry.py:194: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:759: in move_block
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 92>), page_index = 0
bbox = (72, 740, 152.00399780273438, 756.4879989624023)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72, 740, 152.00399780273438, 756.4879989624023) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
______ test_move_block_accepts_a_destination_low_on_a_rotated_page[270] _______

rotation = 270

    @pytest.mark.parametrize("rotation", (90, 270))
    def test_move_block_accepts_a_destination_low_on_a_rotated_page(rotation):
        # D4: masked by D1 on the old code, and would surface as soon as D1 was
        # fixed alone.
        doc, handle = parse(build_page(rotation=rotation, texts=((72, 100, "TOP-MARKER"),)))
>       move_block(handle, 0, block(doc, "TOP-MARKER"), target_position=(72, 740))

tests\test_page_geometry.py:194: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
engine\operations.py:759: in move_block
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 94>), page_index = 0
bbox = (72, 740, 152.00399780273438, 756.4879989624023)

    def _validate_target(
        handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
    ) -> tuple[fitz.Page, fitz.Rect]:
        """Shared page_index/bbox validation for every mutating operation.
    
        Raises:
            ValueError: page_index out of range, or bbox degenerate (empty/
                zero-area after normalization) or does not intersect the
                target page at all. A bad target is a caller bug -- every
                operation using this helper fails loudly rather than
                silently no-op'ing or producing output that looks right but
                isn't.
        """
        if page_index < 0 or page_index >= handle.page_count:
            raise ValueError(
                f"page_index {page_index} is out of range for a document with "
                f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
            )
    
        page = handle[page_index]
    
        # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
        # swapping them into min/max order. It does NOT fix a zero-area or
        # off-page rect -- those are caught explicitly below.
        rect = fitz.Rect(bbox)
        rect.normalize()
    
        if rect.is_empty:
            raise ValueError(
                f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
                f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
                f"invalid geometry"
            )
        if not rect.intersects(page.rect):
>           raise ValueError(
                f"bbox {tuple(bbox)} does not intersect page {page_index} "
                f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
            )
E           ValueError: bbox (72, 740, 152.00399780273438, 756.4879989624023) does not intersect page 0 (page rect is (0.0, 0.0, 792.0, 612.0)) -- it is entirely off-page

engine\operations.py:179: ValueError
=========================== short test summary info ===========================
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270]
FAILED tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90]
FAILED tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270]
FAILED tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90]
FAILED tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270]
FAILED tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90]
FAILED tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270]
FAILED tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size
FAILED tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90]
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270]
======================== 20 failed, 28 passed in 0.46s ========================
exit 1
```

## Step 4: Implementation

`engine/operations.py`:
- Added `from engine.geometry import unrotated_bounds` after
  `from engine.document import Image, TextBlock`.
- D1 in `_validate_target`: replaced the `page.rect` intersects check with
  `bounds = unrotated_bounds(page)` / `rect.intersects(bounds)`, and the
  error message now reports "page bounds are {bounds}".
- D3 in `_insertion_rect`: replaced `page.rect.x1` / `page.rect.y1` caps
  with `bounds = unrotated_bounds(page)` / `bounds.x1` / `bounds.y1`.
- D4 in `move_block`: replaced `destination_page.rect.contains(...)` with
  `destination_bounds = unrotated_bounds(destination_page)` /
  `destination_bounds.contains(destination_rect)`, message now reports
  "page bounds {destination_bounds}".
- D5 in `insert_block`: replaced `page.rect.contains(rect)` with
  `bounds = unrotated_bounds(page)` / `bounds.contains(rect)`, message now
  reports "page bounds {bounds}".

All other message lines left untouched.

## Step 5: Green run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v > <file> 2>&1; echo "exit $?"`

Result: **48 passed** -- exact match to the brief's expectation. Full
output below.

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 48 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  4%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  6%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [ 10%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [ 12%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [ 14%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [ 16%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [ 18%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] PASSED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] PASSED [ 29%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 31%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] PASSED [ 33%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 35%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] PASSED [ 37%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 39%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] PASSED [ 41%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 43%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] PASSED [ 45%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 47%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] PASSED [ 50%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 52%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] PASSED [ 54%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 56%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] PASSED [ 58%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 60%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] PASSED [ 62%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 64%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] PASSED [ 66%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 68%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] PASSED [ 70%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] PASSED [ 72%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] PASSED [ 75%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 77%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 79%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 81%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 83%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 85%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] PASSED [ 87%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 89%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] PASSED [ 91%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size PASSED [ 93%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page PASSED [ 95%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] PASSED [ 97%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] PASSED [100%]

============================= 48 passed in 0.30s ==============================
exit 0
```

## Commit (before the mutation check)

```
6480eac fix: bound checks use the unrotated page extent
```

Files: `engine/operations.py`, `tests/geometry_helpers.py`,
`tests/test_page_geometry.py`. Commit message and attribution lines taken
verbatim from the brief.

## Step 6: Mutation check -- D3 reverted alone

Reverted only the two `_insertion_rect` bound lines to `page.rect.x1` /
`page.rect.y1` (removing the now-unused `bounds = unrotated_bounds(page)`
line in that function), keeping D1/D4/D5 fixed. Ran:

`timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v > <file> 2>&1; echo "exit $?"`

Result: **exactly 4 failed, 44 passed** -- matches the brief's prediction
precisely:
- `test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]`
- `test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270]`
- `test_identical_replacement_low_on_a_rotated_page_keeps_its_size`
- `test_insert_block_fits_a_tight_box_low_on_a_rotated_page`

Failure messages:

```
ValueError: text (8 chars) does not fit within bbox (72, 740, 400, 760) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox
[insert_block-90]

ValueError: text (8 chars) does not fit within bbox (72, 740, 400, 760) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox
[insert_block-270]

AssertionError: LOW-MARKER
assert 9.720000267028809 == 12.0 +- 0.01
  comparison failed
  Obtained: 9.720000267028809
  Expected: 12.0 +- 0.01
[test_identical_replacement_low_on_a_rotated_page_keeps_its_size, on size]

ValueError: text (4 chars) does not fit within bbox (300, 687.0999755859375, 560, 703.5880126953125) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox
[test_insert_block_fits_a_tight_box_low_on_a_rotated_page, with "does not fit"]
```

Full run output below.

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 48 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  4%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  6%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [ 10%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [ 12%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [ 14%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [ 16%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [ 18%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] PASSED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] PASSED [ 29%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 31%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] FAILED [ 33%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 35%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] FAILED [ 37%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 39%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] PASSED [ 41%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 43%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] PASSED [ 45%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 47%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] PASSED [ 50%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 52%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] PASSED [ 54%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 56%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] PASSED [ 58%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 60%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] PASSED [ 62%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 64%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] PASSED [ 66%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 68%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] PASSED [ 70%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] PASSED [ 72%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] PASSED [ 75%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 77%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 79%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 81%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 83%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 85%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] PASSED [ 87%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 89%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] PASSED [ 91%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size FAILED [ 93%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page FAILED [ 95%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] PASSED [ 97%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] PASSED [100%]

================================== FAILURES ===================================
_ test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] _

op = 'insert_block', rotation = 90

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:122: in <lambda>
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 30>), page_index = 0
bbox = (72, 740, 400, 760), text = 'INSERTED', size = 12.0, font = None

    def insert_block(
        handle: fitz.Document,
        page_index: int,
        bbox: tuple[float, float, float, float],
        text: str,
        size: float,
        font: str | None = None,
    ) -> None:
        """Draw brand-new text into an empty region of a page -- for adding
        content that has no existing block to replace. Unlike replace_text/
        move_block, there is no shrink-retry: size is an explicit, deliberate
        choice, and a poor fit is a caller error to fix (a smaller size or a
        larger bbox), not something this function silently overrides.
    
        Font resolution: font defaults to "helvetica" when omitted. Only
        Tiers 2/3 of _select_font's cascade apply -- there is no source block
        to extract an embedded font from (Tier 1). A font value that is
        already a Base-14 name is used as-is; one that is not gets the same
        bold/italic-matched Base-14 substitute _base14_style_match already
        computes for replace_text's non-Base-14 target.font case (e.g. a
        caller-supplied "Arial-Bold" resolves to "helvetica-bold", not a
        failed lookup for an embedded resource of that name, since none
        exists to find). If even the style-matched Base-14 font can't render
        every character of text, the bundled broad-coverage font (Tier 3) is
        tried before raising.
    
        Raises:
            ValueError: text is empty; size is not positive; bbox is
                degenerate or fully off-page (see _validate_target); bbox is
                only partially on-page (not fully contained in the page's
                rect); no available font (a Base-14 name/style match, or the
                bundled broad-coverage font) can render every character of
                text; or text does not fit bbox at size -- named explicitly,
                since no shrink is attempted. Nothing is ever drawn before this
                function's validation completes, so a raise always leaves the document's
                visible content unmodified -- though if font resolution reached the
                Tier-3 bundled fallback font, that font resource may remain registered
                on the page even if the later draw-fit check fails (a small, one-time,
                non-cumulative cost; PyMuPDF's own resource garbage collection cannot
                reclaim a resource still referenced from the page, even an unused one).
        """
        if not text:
            raise ValueError("text must be non-empty -- nothing to insert")
    
        page, rect = _validate_target(handle, page_index, bbox)
    
        bounds = unrotated_bounds(page)
        if not bounds.contains(rect):
            raise ValueError(
                f"bbox {tuple(bbox)} is not fully inside page {page_index} "
                f"(page bounds {tuple(bounds)}) -- insert_block does not place "
                f"content off-page. Nothing has been modified."
            )
    
        if size <= 0:
            raise ValueError(f"size must be positive, got {size}")
    
        # ---- font resolution: Tier 2/3 only, no source block for Tier 1 ----
        font_key = (font or "helvetica").lower()
        if font_key not in fitz.Base14_fontdict:
            font_key = _base14_style_match(font_key)
        base14_font = _base14_font(font_key)
        if not _missing_glyphs(base14_font, text):
            resolved_fontname, resolved_font = font_key, base14_font
        else:
            fallback_font = _bundled_fallback_font()
            missing = _missing_glyphs(fallback_font, text)
            if missing:
                missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
                raise ValueError(
                    f"text contains character(s) that no available font can render: "
                    f"{missing_display} -- tried {font_key!r} and PyMuPDF's bundled "
                    f"broad-coverage font. Nothing has been modified."
                )
            resolved_fontname, resolved_font = _FALLBACK_FONT_ALIAS, fallback_font
    
        try:
            insert_rect = _insertion_rect(page, rect, resolved_font, size)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
            raise ValueError(
                f"failed to compute the insertion box for bbox {tuple(bbox)} in "
                f"{font_key!r} at {size}pt: {type(exc).__name__}: {exc}. "
                f"Nothing has been modified."
            ) from exc
    
        # ---- single attempt, no shrink-retry -- size was an explicit choice ----
        if resolved_fontname not in fitz.Base14_fontdict:
            page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
        remaining_space = page.insert_textbox(
            insert_rect, text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0),
        )
        if remaining_space < 0:
>           raise ValueError(
                f"text ({len(text)} chars) does not fit within bbox {tuple(bbox)} "
                f"at {size}pt -- insert_block does not shrink to fit; choose a "
                f"smaller size or a larger bbox"
            )
E           ValueError: text (8 chars) does not fit within bbox (72, 740, 400, 760) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox

engine\operations.py:883: ValueError
_ test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] _

op = 'insert_block', rotation = 270

    @pytest.mark.parametrize("rotation", ROTATIONS)
    @pytest.mark.parametrize("op", sorted(LOW_OPS))
    def test_every_block_operation_accepts_a_block_low_on_the_page(op, rotation):
        doc, handle = parse(build_page(rotation=rotation))
>       LOW_OPS[op](handle, block(doc, "LOW-MARKER"))  # must not raise
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests\test_page_geometry.py:130: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests\test_page_geometry.py:122: in <lambda>
    "insert_block": lambda h, b: insert_block(h, 0, (72, 740, 400, 760), "INSERTED", 12.0),
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 34>), page_index = 0
bbox = (72, 740, 400, 760), text = 'INSERTED', size = 12.0, font = None

    def insert_block(
        handle: fitz.Document,
        page_index: int,
        bbox: tuple[float, float, float, float],
        text: str,
        size: float,
        font: str | None = None,
    ) -> None:
        """Draw brand-new text into an empty region of a page -- for adding
        content that has no existing block to replace. Unlike replace_text/
        move_block, there is no shrink-retry: size is an explicit, deliberate
        choice, and a poor fit is a caller error to fix (a smaller size or a
        larger bbox), not something this function silently overrides.
    
        Font resolution: font defaults to "helvetica" when omitted. Only
        Tiers 2/3 of _select_font's cascade apply -- there is no source block
        to extract an embedded font from (Tier 1). A font value that is
        already a Base-14 name is used as-is; one that is not gets the same
        bold/italic-matched Base-14 substitute _base14_style_match already
        computes for replace_text's non-Base-14 target.font case (e.g. a
        caller-supplied "Arial-Bold" resolves to "helvetica-bold", not a
        failed lookup for an embedded resource of that name, since none
        exists to find). If even the style-matched Base-14 font can't render
        every character of text, the bundled broad-coverage font (Tier 3) is
        tried before raising.
    
        Raises:
            ValueError: text is empty; size is not positive; bbox is
                degenerate or fully off-page (see _validate_target); bbox is
                only partially on-page (not fully contained in the page's
                rect); no available font (a Base-14 name/style match, or the
                bundled broad-coverage font) can render every character of
                text; or text does not fit bbox at size -- named explicitly,
                since no shrink is attempted. Nothing is ever drawn before this
                function's validation completes, so a raise always leaves the document's
                visible content unmodified -- though if font resolution reached the
                Tier-3 bundled fallback font, that font resource may remain registered
                on the page even if the later draw-fit check fails (a small, one-time,
                non-cumulative cost; PyMuPDF's own resource garbage collection cannot
                reclaim a resource still referenced from the page, even an unused one).
        """
        if not text:
            raise ValueError("text must be non-empty -- nothing to insert")
    
        page, rect = _validate_target(handle, page_index, bbox)
    
        bounds = unrotated_bounds(page)
        if not bounds.contains(rect):
            raise ValueError(
                f"bbox {tuple(bbox)} is not fully inside page {page_index} "
                f"(page bounds {tuple(bounds)}) -- insert_block does not place "
                f"content off-page. Nothing has been modified."
            )
    
        if size <= 0:
            raise ValueError(f"size must be positive, got {size}")
    
        # ---- font resolution: Tier 2/3 only, no source block for Tier 1 ----
        font_key = (font or "helvetica").lower()
        if font_key not in fitz.Base14_fontdict:
            font_key = _base14_style_match(font_key)
        base14_font = _base14_font(font_key)
        if not _missing_glyphs(base14_font, text):
            resolved_fontname, resolved_font = font_key, base14_font
        else:
            fallback_font = _bundled_fallback_font()
            missing = _missing_glyphs(fallback_font, text)
            if missing:
                missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
                raise ValueError(
                    f"text contains character(s) that no available font can render: "
                    f"{missing_display} -- tried {font_key!r} and PyMuPDF's bundled "
                    f"broad-coverage font. Nothing has been modified."
                )
            resolved_fontname, resolved_font = _FALLBACK_FONT_ALIAS, fallback_font
    
        try:
            insert_rect = _insertion_rect(page, rect, resolved_font, size)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
            raise ValueError(
                f"failed to compute the insertion box for bbox {tuple(bbox)} in "
                f"{font_key!r} at {size}pt: {type(exc).__name__}: {exc}. "
                f"Nothing has been modified."
            ) from exc
    
        # ---- single attempt, no shrink-retry -- size was an explicit choice ----
        if resolved_fontname not in fitz.Base14_fontdict:
            page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
        remaining_space = page.insert_textbox(
            insert_rect, text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0),
        )
        if remaining_space < 0:
>           raise ValueError(
                f"text ({len(text)} chars) does not fit within bbox {tuple(bbox)} "
                f"at {size}pt -- insert_block does not shrink to fit; choose a "
                f"smaller size or a larger bbox"
            )
E           ValueError: text (8 chars) does not fit within bbox (72, 740, 400, 760) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox

engine\operations.py:883: ValueError
_______ test_identical_replacement_low_on_a_rotated_page_keeps_its_size _______

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
>           assert span["size"] == pytest.approx(b.size, abs=0.01, rel=0), span["text"]
E           AssertionError: LOW-MARKER
E           assert 9.720000267028809 == 12.0 � 0.01
E             
E             comparison failed
E             Obtained: 9.720000267028809
E             Expected: 12.0 � 0.01

tests\test_page_geometry.py:177: AssertionError
__________ test_insert_block_fits_a_tight_box_low_on_a_rotated_page ___________

    def test_insert_block_fits_a_tight_box_low_on_a_rotated_page():
        # E2: insert_block has no shrink loop, so on the old code lost headroom
        # made it RAISE "does not fit" for text that fits unrotated.
        doc, handle = parse(build_page(rotation=90))
        b = block(doc, "LOW-MARKER")
>       insert_block(handle, 0, (300, b.bbox[1], 560, b.bbox[3]), "FITS", b.size)

tests\test_page_geometry.py:185: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

handle = Document('None', <memory, doc# 92>), page_index = 0
bbox = (300, 687.0999755859375, 560, 703.5880126953125), text = 'FITS'
size = 12.0, font = None

    def insert_block(
        handle: fitz.Document,
        page_index: int,
        bbox: tuple[float, float, float, float],
        text: str,
        size: float,
        font: str | None = None,
    ) -> None:
        """Draw brand-new text into an empty region of a page -- for adding
        content that has no existing block to replace. Unlike replace_text/
        move_block, there is no shrink-retry: size is an explicit, deliberate
        choice, and a poor fit is a caller error to fix (a smaller size or a
        larger bbox), not something this function silently overrides.
    
        Font resolution: font defaults to "helvetica" when omitted. Only
        Tiers 2/3 of _select_font's cascade apply -- there is no source block
        to extract an embedded font from (Tier 1). A font value that is
        already a Base-14 name is used as-is; one that is not gets the same
        bold/italic-matched Base-14 substitute _base14_style_match already
        computes for replace_text's non-Base-14 target.font case (e.g. a
        caller-supplied "Arial-Bold" resolves to "helvetica-bold", not a
        failed lookup for an embedded resource of that name, since none
        exists to find). If even the style-matched Base-14 font can't render
        every character of text, the bundled broad-coverage font (Tier 3) is
        tried before raising.
    
        Raises:
            ValueError: text is empty; size is not positive; bbox is
                degenerate or fully off-page (see _validate_target); bbox is
                only partially on-page (not fully contained in the page's
                rect); no available font (a Base-14 name/style match, or the
                bundled broad-coverage font) can render every character of
                text; or text does not fit bbox at size -- named explicitly,
                since no shrink is attempted. Nothing is ever drawn before this
                function's validation completes, so a raise always leaves the document's
                visible content unmodified -- though if font resolution reached the
                Tier-3 bundled fallback font, that font resource may remain registered
                on the page even if the later draw-fit check fails (a small, one-time,
                non-cumulative cost; PyMuPDF's own resource garbage collection cannot
                reclaim a resource still referenced from the page, even an unused one).
        """
        if not text:
            raise ValueError("text must be non-empty -- nothing to insert")
    
        page, rect = _validate_target(handle, page_index, bbox)
    
        bounds = unrotated_bounds(page)
        if not bounds.contains(rect):
            raise ValueError(
                f"bbox {tuple(bbox)} is not fully inside page {page_index} "
                f"(page bounds {tuple(bounds)}) -- insert_block does not place "
                f"content off-page. Nothing has been modified."
            )
    
        if size <= 0:
            raise ValueError(f"size must be positive, got {size}")
    
        # ---- font resolution: Tier 2/3 only, no source block for Tier 1 ----
        font_key = (font or "helvetica").lower()
        if font_key not in fitz.Base14_fontdict:
            font_key = _base14_style_match(font_key)
        base14_font = _base14_font(font_key)
        if not _missing_glyphs(base14_font, text):
            resolved_fontname, resolved_font = font_key, base14_font
        else:
            fallback_font = _bundled_fallback_font()
            missing = _missing_glyphs(fallback_font, text)
            if missing:
                missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
                raise ValueError(
                    f"text contains character(s) that no available font can render: "
                    f"{missing_display} -- tried {font_key!r} and PyMuPDF's bundled "
                    f"broad-coverage font. Nothing has been modified."
                )
            resolved_fontname, resolved_font = _FALLBACK_FONT_ALIAS, fallback_font
    
        try:
            insert_rect = _insertion_rect(page, rect, resolved_font, size)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
            raise ValueError(
                f"failed to compute the insertion box for bbox {tuple(bbox)} in "
                f"{font_key!r} at {size}pt: {type(exc).__name__}: {exc}. "
                f"Nothing has been modified."
            ) from exc
    
        # ---- single attempt, no shrink-retry -- size was an explicit choice ----
        if resolved_fontname not in fitz.Base14_fontdict:
            page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
        remaining_space = page.insert_textbox(
            insert_rect, text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0),
        )
        if remaining_space < 0:
>           raise ValueError(
                f"text ({len(text)} chars) does not fit within bbox {tuple(bbox)} "
                f"at {size}pt -- insert_block does not shrink to fit; choose a "
                f"smaller size or a larger bbox"
            )
E           ValueError: text (4 chars) does not fit within bbox (300, 687.0999755859375, 560, 703.5880126953125) at 12.0pt -- insert_block does not shrink to fit; choose a smaller size or a larger bbox

engine\operations.py:883: ValueError
=========================== short test summary info ===========================
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270]
FAILED tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size
FAILED tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page
======================== 4 failed, 44 passed in 0.35s =========================
exit 1
```

Restored D3 with `git checkout -- engine/operations.py`. `git status`
confirmed working tree clean (no diff from the committed `6480eac`).

## Step 7: Full suite

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q > <file> 2>&1; echo "exit $?"`

Result: **411 passed**, exit 0. (Full suite total is 411, not 363 -- Tasks 1
and 2's `tests/test_geometry.py` and other additions landed on this branch
before Task 3 started; none of the pre-existing tests were edited by this
task, confirmed by `git show --stat HEAD` touching only
`engine/operations.py`, `tests/geometry_helpers.py` (append-only diff) and
the new `tests/test_page_geometry.py`.)

```
........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 52%]
........................................................................ [ 70%]
........................................................................ [ 87%]
...................................................                      [100%]
411 passed in 13.68s
exit 0
```

## Self-review

- Red counts, green counts, and mutation-check counts all matched the
  brief's measured expectations exactly; no test was altered to force a
  match.
- The D3 mutation was applied and reverted in isolation, on the already
  committed file, then verified via `git status` (clean) before moving on,
  per the task rules.
- `git diff b539129 HEAD --stat` shows only the three files the brief named
  as in-scope; `tests/geometry_helpers.py`'s diff is purely an append (the
  new `build_page` function at the end), so none of the helpers Tasks 1-2
  or earlier tasks depend on were touched.
- No subagents were dispatched at any point in this task.
- One small deviation from the brief's literal Step 6 instruction: after
  reverting the two D3 bound lines back to `page.rect.x1`/`page.rect.y1`, I
  also removed the now-dead `bounds = unrotated_bounds(page)` line in
  `_insertion_rect` (rather than leaving an unused local). This has no
  effect on behavior or on the mutation-check result -- D1's `bounds`
  computation in `_validate_target` was left untouched -- and the file was
  reverted to the clean committed state afterward regardless.

## Fix round 1

Review: `task-3-review.md`. Spec compliance ✅; two Minor docstring findings
to fix, plus a coordinator-requested evidence step (execute the D1/D4/D5
mutations that the review had only reasoned about, not run).

### Minor fixes

1. `move_block`'s `Raises` docstring (was `engine/operations.py:727-728`,
   now `:727-729` after the wording grew by one line): changed "not fully
   contained in the destination page's rect" to "not fully contained in the
   destination page's unrotated bounds, see engine.geometry.unrotated_bounds".
2. `insert_block`'s `Raises` docstring (was `:821-822`, now `:822`): changed
   "not fully contained in the page's rect" to "not fully contained in the
   page's unrotated bounds".

Full suite after the docstring fix: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
→ **411 passed**, exit 0 (see `full suite (fix round 1)` output below).

Committed as `f03efe7` ("fix: describe bound-check failures by unrotated
bounds, not page.rect"), on top of `6480eac`, no amend. `git status` clean
afterward.

### Evidence step: D1, D4, D5 reverted alone (on the committed file at f03efe7)

Each revert changed only that one site back to its old `page.rect` form,
keeping the other three (D1/D3/D4/D5 minus the one under test) as
`unrotated_bounds`. Ran `tests/test_page_geometry.py -v` after each, then
restored with `git checkout -- engine/operations.py` and confirmed
`git status` clean before the next revert.

**D1 alone** (`_validate_target`'s `rect.intersects(bounds)` reverted to
`rect.intersects(page.rect)`, error text reverted to "page rect is..."):
**20 failed, 28 passed** -- identical to the original Step-3 red list,
because D1 is the first gate every operation passes through:

```
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270]
FAILED tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90]
FAILED tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270]
FAILED tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90]
FAILED tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270]
FAILED tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90]
FAILED tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270]
FAILED tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size
FAILED tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90]
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270]
20 failed, 28 passed in 0.48s, exit 1
```

**D4 alone** (`move_block`'s `destination_bounds.contains(...)` reverted to
`destination_page.rect.contains(...)`, error text reverted to "page rect
{destination_page.rect}"): **4 failed, 44 passed** -- confirms the review's
reasoned prediction exactly:

```
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270]
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90]
FAILED tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270]
4 failed, 44 passed in 0.33s, exit 1
```

**D5 alone** (`insert_block`'s `bounds.contains(rect)` reverted to
`page.rect.contains(rect)`, error text reverted to "page rect
{page.rect}"): **3 failed, 45 passed** -- also confirms the review's
reasoned prediction (the review named the same two `insert_block-90/270`
cases; `test_insert_block_fits_a_tight_box_low_on_a_rotated_page` fails
too, since its tight box at (300, b.bbox[1], 560, b.bbox[3]) on a 90°
rotated page is also outside the swapped `page.rect`):

```
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90]
FAILED tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270]
FAILED tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page
3 failed, 45 passed in 0.34s, exit 1
```

Every revert turned at least one test red, so no tests needed to be added.
After the D5 run, `git checkout -- engine/operations.py` restored the file
and `git status` showed a clean tree at `f03efe7`.

### Full suite, final state (fix round 1)

```

........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 52%]
........................................................................ [ 70%]
........................................................................ [ 87%]
...................................................                      [100%]
411 passed in 13.52s
exit 0
```

### Fix round 1 self-review

- Both docstring wordings match the review's requested text verbatim
  (word for word, including "see engine.geometry.unrotated_bounds" on the
  `move_block` one).
- D1/D4/D5 were reverted and tested one at a time, each restored via
  `git checkout -- engine/operations.py` with a clean `git status` before
  the next, exactly as instructed; none was combined with another revert.
- All three reverts produced at least one failing test, so nothing was
  added to the suite.
- The docstring commit (`f03efe7`) is a new commit on top of `6480eac`, not
  an amend; `git status` is clean at HEAD.
- No subagents were used for this fix round.
