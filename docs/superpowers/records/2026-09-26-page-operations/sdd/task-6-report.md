# Task 6 report: Image placement (R4)

Branch `page-operations`, starting HEAD `3c235d0`. Commit produced: `7b6506d fix: place replacement images correctly on rotated, cropped pages`.

## Step 1: Tests appended

Appended the Task 6 tests verbatim from the brief to the end of
`tests/test_page_geometry.py`: `BLUE`, `BAND_BEHIND_IMAGE`, `IMAGE_RECT`, `_png`,
`test_replace_image_erases_exactly_the_placement`,
`test_replace_image_lands_exactly_on_the_placement`,
`test_replace_image_works_on_a_left_overhang_page`.
All consumed names (`at_rotation_zero` import in `engine/operations.py`, `build_page`,
`_centre_pixel`, `CROPS`, `BAND`, `_fills`, `_on`, `exported`, `ROTATIONS`, `parse`,
`replace_image`) already existed from Tasks 1, 3, 4, 5.

## Step 2: Red run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 1

Result: **6 failed, 101 passed** — matches the corrected expectation given in the
task context (100 -> 101 passed because of the extra test Task 5's fix round 1 added).

Failing test ids (exactly the six the brief lists):
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized]

```
======================== 6 failed, 101 passed in 0.71s ========================
```

### Full red-run output

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 107 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  0%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  1%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  3%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [  4%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [  5%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [  6%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [  7%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [  9%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 10%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] PASSED [ 11%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 12%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] PASSED [ 13%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 15%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] PASSED [ 16%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 17%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] PASSED [ 18%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 19%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 21%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 23%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] PASSED [ 24%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] PASSED [ 26%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] PASSED [ 29%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 30%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] PASSED [ 31%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] PASSED [ 32%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] PASSED [ 33%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 34%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 35%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 36%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 37%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 38%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] PASSED [ 39%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 40%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] PASSED [ 41%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size PASSED [ 42%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page PASSED [ 42%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] PASSED [ 43%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] PASSED [ 44%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-contained] PASSED [ 45%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-oversized] PASSED [ 46%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-plain] PASSED [ 47%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-contained] PASSED [ 48%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-oversized] PASSED [ 49%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-plain] PASSED [ 50%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-contained] PASSED [ 51%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-oversized] PASSED [ 52%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-plain] PASSED [ 53%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-contained] PASSED [ 54%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-oversized] PASSED [ 55%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-plain] PASSED [ 56%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[0] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[90] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[180] PASSED [ 58%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[270] PASSED [ 59%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[0] PASSED [ 60%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90] PASSED [ 61%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180] PASSED [ 62%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270] PASSED [ 63%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-contained] PASSED [ 64%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-oversized] PASSED [ 65%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-contained] PASSED [ 66%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-oversized] PASSED [ 67%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-contained] PASSED [ 68%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-oversized] PASSED [ 69%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-contained] PASSED [ 70%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-oversized] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[0] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[90] PASSED [ 72%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[180] PASSED [ 73%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[270] PASSED [ 74%]
tests/test_page_geometry.py::test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation PASSED [ 75%]
tests/test_page_geometry.py::test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation PASSED [ 76%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[90] PASSED [ 77%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[180] PASSED [ 78%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[270] PASSED [ 79%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[add_redact_annot] PASSED [ 80%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[apply_redactions] PASSED [ 81%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-contained] PASSED [ 82%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-oversized] PASSED [ 83%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-contained] PASSED [ 84%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-oversized] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-contained] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-oversized] PASSED [ 86%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-contained] PASSED [ 87%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-oversized] PASSED [ 88%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-contained] PASSED [ 89%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-oversized] PASSED [ 90%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained] FAILED [ 91%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized] FAILED [ 92%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained] FAILED [ 93%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized] FAILED [ 94%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained] FAILED [ 95%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized] FAILED [ 96%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[0] PASSED [ 97%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[90] PASSED [ 98%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[180] PASSED [ 99%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[270] PASSED [100%]

================================== FAILURES ===================================
_______ test_replace_image_lands_exactly_on_the_placement[90-contained] _______

rotation = 90, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
_______ test_replace_image_lands_exactly_on_the_placement[90-oversized] _______

rotation = 90, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[180-contained] _______

rotation = 180, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[180-oversized] _______

rotation = 180, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[270-contained] _______

rotation = 270, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[270-oversized] _______

rotation = 270, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized]
======================== 6 failed, 101 passed in 0.71s ========================
```

## Step 3: Fix implemented

In `engine/operations.py`, `replace_image` (the `insert_image` call, originally line 992), wrapped the call in `at_rotation_zero(page)`, inside the existing `try`, exactly per the brief:

```python
    _clean_erase(page, rect)
    try:
        # At rotation 0 (spec R4): on a rotated page with a CropBox,
        # insert_image lands 40-52pt from the rect it was given. The rect is
        # unchanged; only the page's orientation is, and it is restored.
        with at_rotation_zero(page):
            page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
```

No import change needed: `at_rotation_zero` was already imported by Task 5.

## Step 4: Green run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 0

Result: **107 passed** — matches the corrected expectation (106 -> 107 for the same reason as the red-run adjustment).

### Full green-run output

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 107 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  0%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  1%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  3%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [  4%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [  5%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [  6%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [  7%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [  9%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 10%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] PASSED [ 11%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 12%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] PASSED [ 13%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 15%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] PASSED [ 16%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 17%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] PASSED [ 18%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 19%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 21%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 23%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] PASSED [ 24%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] PASSED [ 26%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] PASSED [ 29%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 30%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] PASSED [ 31%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] PASSED [ 32%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] PASSED [ 33%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 34%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 35%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 36%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 37%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 38%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] PASSED [ 39%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 40%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] PASSED [ 41%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size PASSED [ 42%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page PASSED [ 42%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] PASSED [ 43%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] PASSED [ 44%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-contained] PASSED [ 45%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-oversized] PASSED [ 46%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-plain] PASSED [ 47%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-contained] PASSED [ 48%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-oversized] PASSED [ 49%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-plain] PASSED [ 50%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-contained] PASSED [ 51%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-oversized] PASSED [ 52%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-plain] PASSED [ 53%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-contained] PASSED [ 54%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-oversized] PASSED [ 55%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-plain] PASSED [ 56%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[0] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[90] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[180] PASSED [ 58%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[270] PASSED [ 59%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[0] PASSED [ 60%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90] PASSED [ 61%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180] PASSED [ 62%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270] PASSED [ 63%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-contained] PASSED [ 64%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-oversized] PASSED [ 65%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-contained] PASSED [ 66%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-oversized] PASSED [ 67%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-contained] PASSED [ 68%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-oversized] PASSED [ 69%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-contained] PASSED [ 70%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-oversized] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[0] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[90] PASSED [ 72%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[180] PASSED [ 73%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[270] PASSED [ 74%]
tests/test_page_geometry.py::test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation PASSED [ 75%]
tests/test_page_geometry.py::test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation PASSED [ 76%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[90] PASSED [ 77%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[180] PASSED [ 78%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[270] PASSED [ 79%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[add_redact_annot] PASSED [ 80%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[apply_redactions] PASSED [ 81%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-contained] PASSED [ 82%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-oversized] PASSED [ 83%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-contained] PASSED [ 84%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-oversized] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-contained] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-oversized] PASSED [ 86%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-contained] PASSED [ 87%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-oversized] PASSED [ 88%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-contained] PASSED [ 89%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-oversized] PASSED [ 90%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained] PASSED [ 91%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized] PASSED [ 92%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained] PASSED [ 93%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized] PASSED [ 94%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained] PASSED [ 95%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized] PASSED [ 96%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[0] PASSED [ 97%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[90] PASSED [ 98%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[180] PASSED [ 99%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[270] PASSED [100%]

============================= 107 passed in 0.62s =============================
```

## Step 5: Full suite

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Exit status: 0

Result: **470 passed**. The task context stated the full suite currently passed 450 (before this task's tests were appended); the three new Task 6 test functions add 20 parametrized cases (8 + 8 + 4), and 450 + 20 = 470, consistent with the observed total. No pre-existing test file, including `tests/test_geometry.py` and the 227 pre-Merge-A tests, was modified.

### Full-suite output

```
........................................................................ [ 15%]
........................................................................ [ 30%]
........................................................................ [ 45%]
........................................................................ [ 61%]
........................................................................ [ 76%]
........................................................................ [ 91%]
......................................                                   [100%]
470 passed in 13.72s
```

## Commit

commit 7b6506d36e1b126d90045d8f13675464878cfd68
fix: place replacement images correctly on rotated, cropped pages

Since replace_image shipped, a replacement on a page with both a CropBox and
rotation landed 40-52pt from the requested spot, leaving the placement
blank. The image is now inserted at rotation 0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka


`git status` after committing: clean (nothing to commit, working tree clean).

## Mutation check

Performed on the committed `engine/operations.py` (commit `7b6506d`): removed `with at_rotation_zero(page):` around the `insert_image` call (dedented the call back into the bare `try` block), then reran `tests/test_page_geometry.py`.

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 1

Result: **6 failed, 101 passed** — the mutation killed exactly the same six tests as the original red run (the `test_replace_image_lands_exactly_on_the_placement` cases for rotations 90/180/270 x both crops). `test_replace_image_erases_exactly_the_placement` and `test_replace_image_works_on_a_left_overhang_page` stayed green, confirming the wrapper is precisely what those two guard against losing while the placement test is what it protects.

Restored the file with `git checkout -- engine/operations.py`. `git status` afterward: clean (nothing to commit, working tree clean). `git log` confirms HEAD is still `7b6506d` with no extra commits.

### Full mutation-run output

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 107 items

tests/test_page_geometry.py::test_imports_resolve_inside_this_checkout PASSED [  0%]
tests/test_page_geometry.py::test_fingerprint_is_stable_when_nothing_changes PASSED [  1%]
tests/test_page_geometry.py::test_fingerprint_detects_an_added_annotation PASSED [  2%]
tests/test_page_geometry.py::test_fingerprint_detects_a_resource_change PASSED [  3%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[contained-crop] PASSED [  4%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[malformed-rotate-45] PASSED [  5%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[negative-origin-mediabox] PASSED [  6%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[plain] PASSED [  7%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[rotated-90] PASSED [  8%]
tests/test_page_geometry.py::test_fixture_places_the_marker_where_the_tests_assume[user-unit-1.5] PASSED [  9%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-0] PASSED [ 10%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-90] PASSED [ 11%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-180] PASSED [ 12%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[delete_block-270] PASSED [ 13%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-0] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-90] PASSED [ 14%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-180] PASSED [ 15%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[insert_block-270] PASSED [ 16%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-0] PASSED [ 17%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-90] PASSED [ 18%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-180] PASSED [ 19%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[move_block-270] PASSED [ 20%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-0] PASSED [ 21%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-90] PASSED [ 22%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-180] PASSED [ 23%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[redact_region-270] PASSED [ 24%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-0] PASSED [ 25%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-90] PASSED [ 26%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-180] PASSED [ 27%]
tests/test_page_geometry.py::test_every_block_operation_accepts_a_block_low_on_the_page[replace_text-270] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[0] PASSED [ 28%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[90] PASSED [ 29%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[180] PASSED [ 30%]
tests/test_page_geometry.py::test_replace_image_accepts_an_image_low_on_the_page[270] PASSED [ 31%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[90] PASSED [ 32%]
tests/test_page_geometry.py::test_a_bbox_inside_the_swapped_rect_but_off_the_real_page_is_rejected[270] PASSED [ 33%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[0] PASSED [ 34%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[90] PASSED [ 35%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[180] PASSED [ 36%]
tests/test_page_geometry.py::test_a_genuinely_off_page_bbox_is_still_rejected[270] PASSED [ 37%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[0] PASSED [ 38%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[90] PASSED [ 39%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[180] PASSED [ 40%]
tests/test_page_geometry.py::test_redact_accepts_a_bbox_straddling_the_edge_on_a_rotated_page[270] PASSED [ 41%]
tests/test_page_geometry.py::test_identical_replacement_low_on_a_rotated_page_keeps_its_size PASSED [ 42%]
tests/test_page_geometry.py::test_insert_block_fits_a_tight_box_low_on_a_rotated_page PASSED [ 42%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[90] PASSED [ 43%]
tests/test_page_geometry.py::test_move_block_accepts_a_destination_low_on_a_rotated_page[270] PASSED [ 44%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-contained] PASSED [ 45%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-oversized] PASSED [ 46%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-plain] PASSED [ 47%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-contained] PASSED [ 48%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-oversized] PASSED [ 49%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-plain] PASSED [ 50%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-contained] PASSED [ 51%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-oversized] PASSED [ 52%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-plain] PASSED [ 53%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-contained] PASSED [ 54%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-oversized] PASSED [ 55%]
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-plain] PASSED [ 56%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[0] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[90] PASSED [ 57%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[180] PASSED [ 58%]
tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[270] PASSED [ 59%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[0] PASSED [ 60%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90] PASSED [ 61%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180] PASSED [ 62%]
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270] PASSED [ 63%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-contained] PASSED [ 64%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[0-oversized] PASSED [ 65%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-contained] PASSED [ 66%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-oversized] PASSED [ 67%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-contained] PASSED [ 68%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-oversized] PASSED [ 69%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-contained] PASSED [ 70%]
tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-oversized] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[0] PASSED [ 71%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[90] PASSED [ 72%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[180] PASSED [ 73%]
tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[270] PASSED [ 74%]
tests/test_page_geometry.py::test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation PASSED [ 75%]
tests/test_page_geometry.py::test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation PASSED [ 76%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[90] PASSED [ 77%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[180] PASSED [ 78%]
tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[270] PASSED [ 79%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[add_redact_annot] PASSED [ 80%]
tests/test_page_geometry.py::test_rotation_is_restored_when_a_redaction_call_raises[apply_redactions] PASSED [ 81%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-contained] PASSED [ 82%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[0-oversized] PASSED [ 83%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-contained] PASSED [ 84%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[90-oversized] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-contained] PASSED [ 85%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[180-oversized] PASSED [ 86%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-contained] PASSED [ 87%]
tests/test_page_geometry.py::test_replace_image_erases_exactly_the_placement[270-oversized] PASSED [ 88%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-contained] PASSED [ 89%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[0-oversized] PASSED [ 90%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained] FAILED [ 91%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized] FAILED [ 92%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained] FAILED [ 93%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized] FAILED [ 94%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained] FAILED [ 95%]
tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized] FAILED [ 96%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[0] PASSED [ 97%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[90] PASSED [ 98%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[180] PASSED [ 99%]
tests/test_page_geometry.py::test_replace_image_works_on_a_left_overhang_page[270] PASSED [100%]

================================== FAILURES ===================================
_______ test_replace_image_lands_exactly_on_the_placement[90-contained] _______

rotation = 90, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
_______ test_replace_image_lands_exactly_on_the_placement[90-oversized] _______

rotation = 90, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[180-contained] _______

rotation = 180, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[180-oversized] _______

rotation = 180, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[270-contained] _______

rotation = 270, crop = 'contained'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (-8.0, 408.0, 56.0, 472.0), placement was (32.0, 348.0, 96.0, 412.0)
E       assert False
E        +  where False = _on(Rect(-8.0, 408.0, 56.0, 472.0), (32.0, 348.0, 96.0, 412.0))
E        +    where (32.0, 348.0, 96.0, 412.0) = Image(bbox=(32.0, 348.0, 96.0, 412.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
______ test_replace_image_lands_exactly_on_the_placement[270-oversized] _______

rotation = 270, crop = 'oversized'

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
>       assert _on(placements[0], target.bbox), (
            f"image landed at {tuple(placements[0])}, placement was {target.bbox}"
        )
E       AssertionError: image landed at (72.0, 312.0, 136.0, 376.0), placement was (72.0, 400.0, 136.0, 464.0)
E       assert False
E        +  where False = _on(Rect(72.0, 312.0, 136.0, 376.0), (72.0, 400.0, 136.0, 464.0))
E        +    where (72.0, 400.0, 136.0, 464.0) = Image(bbox=(72.0, 400.0, 136.0, 464.0), xref=7, width=8, height=8, placement_count=1, document_placement_count=1, document_page_count=1).bbox

tests\test_page_geometry.py:464: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[90-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[180-oversized]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-contained]
FAILED tests/test_page_geometry.py::test_replace_image_lands_exactly_on_the_placement[270-oversized]
======================== 6 failed, 101 passed in 0.65s ========================
```

## Self-review

- Tests were copied verbatim from the brief, appended at the end of the file, nothing pre-existing was touched.
- Red counts (6 failed, 101 passed) and the six failing ids matched the corrected expectation in the coordinator's context note exactly, so no NEEDS_CONTEXT stop was needed.
- The fix is the brief's exact code, in the exact location, inside the existing `try` so a failure inside the wrapped call still becomes a `ValueError` via the existing `except` clause (confirmed by inspection: the `with` block is nested inside `try`, not around it).
- Green count (107 passed) and full-suite count (470 passed) both matched expectations once adjusted for the one extra Task 5 test noted in the context.
- Mutation check killed exactly the six target tests and nothing else, which is the expected signature for this fix: strong evidence the wrapper is load-bearing and the tests are not vacuously passing.
- No pre-Merge-A test or `tests/test_geometry.py` was edited; `git diff` before committing only touched `engine/operations.py` and `tests/test_page_geometry.py`.
- No subagents were dispatched; all work done directly in this session.
- Working tree is clean after the mutation check restore; HEAD is `7b6506d`, one commit ahead of the starting `3c235d0`.
