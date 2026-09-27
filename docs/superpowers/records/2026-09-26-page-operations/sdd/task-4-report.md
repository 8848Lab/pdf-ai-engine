# Task 4 report: Background sampling (D2, R3)

Branch: `page-operations`. Starting HEAD: `f03efe7`. Commit made: `9de0ae3`.

## Summary

Fixed `_sample_background_color` in `engine/operations.py` to sample its
four points in DISPLAY space (via `engine.geometry.to_display_matrix`,
subtracting the pixmap's own origin) instead of treating unrotated-space
points as if they were already display-space pixels, and to never infer
scale from the rounded raster size (an identity render is one pixel per
point, so no scale factor is needed at all). Added `to_display_matrix` to
the `engine.geometry` import. Appended the three Task 4 tests
(`test_background_sample_reads_the_colour_behind_the_block`,
`test_delete_block_erases_to_the_true_background_colour`,
`test_sampling_is_exact_on_a_fractional_size_page`) plus their helpers
(`_centre_pixel`, `BAND_BEHIND_LOW`, `SAMPLE_CROPS`) verbatim from the brief
to the end of `tests/test_page_geometry.py`.

## Step 1-2: tests + red run

Tests appended verbatim from the brief (Step 1). No deviation from the
brief's text.

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: `1`.

Result: **16 failed, 52 passed** — exact match to the brief's expected count
and failure list.

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\Coding\8848 Lab\pdf-ai\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collecting ... collected 68 items
...
======================== 16 failed, 52 passed in 0.47s ========================
```

Failed test ids (exact set, matching the brief):
```
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-plain]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-plain]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-plain]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[90]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[180]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[270]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[0]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270]
```

This is exactly: `test_background_sample_reads_the_colour_behind_the_block`
failing at 90/180/270 for all three crops (9), `test_delete_block_erases_to_
the_true_background_colour` failing at 90/180/270 (3, `[0]` passes), and
`test_sampling_is_exact_on_a_fractional_size_page` failing at all four
rotations (4). All Task 3 tests (the other 48 in the file) still passed.
Representative tracebacks:

```
_____ test_background_sample_reads_the_colour_behind_the_block[90-plain] ______
rotation = 90, crop = 'plain'
    ...
    rgb = tuple(round(c * 255) for c in _sample_background_color(handle[0], rect))
>   assert rgb == BAND_RGB
E   AssertionError: assert (255, 255, 255) == (178, 216, 255)

_________ test_delete_block_erases_to_the_true_background_colour[90] __________
rotation = 90
    ...
    r, g, bl = _centre_pixel(page, b.bbox)
>   assert bl > 240 and r < 200, f"erased area is {(r, g, bl)}, expected the band {BAND_RGB}"
E   AssertionError: erased area is (255, 255, 255), expected the band (178, 216, 255)
E   assert (255 > 240 and 255 < 200)

_______ test_sampling_is_exact_on_a_fractional_size_page[0] _______
rotation = 0
    ...
    rgb = tuple(round(c * 255) for c in _sample_background_color(page, fitz.Rect(40, 700, 60, 720)))
>   assert rgb == BAND_RGB
E   AssertionError: assert (255, 255, 255) == (178, 216, 255)
```

Full raw output for this run is preserved at the session's temp path
(`/tmp/task4_red.txt` in the Git Bash session that ran it); the counts and
failure ids above were read directly off it, unedited.

Per the rules, since this matched the brief's expected 16 failed / 52
passed exactly, I proceeded to implementation without stopping.

## Step 3: implementation

`engine/operations.py`:

- Import changed from `from engine.geometry import unrotated_bounds` to
  `from engine.geometry import to_display_matrix, unrotated_bounds`.
- In `_sample_background_color`, replaced the zoom-based scale inference
  with `to_display = to_display_matrix(page)`, and replaced the per-point
  pixel computation to map each unrotated-space point through `to_display`
  and subtract the pixmap's own origin (`pixmap.x`, `pixmap.y`) before
  clamping to pixel bounds. Both replacements are verbatim from the brief's
  Step 3.

```diff
-    pixmap = page.get_pixmap()
-    zoom = pixmap.width / page.rect.width
+    # Identity render: one pixel per point, in DISPLAY space. Sample points
+    # are in UNROTATED space, so each is mapped through the display matrix
+    # and the pixmap's own origin is subtracted. Scale is never inferred from
+    # raster size -- a 100.1pt page renders 101 pixels wide (spec R3).
+    pixmap = page.get_pixmap()
+    to_display = to_display_matrix(page)
@@
-        x_px = max(0, min(pixmap.width - 1, int(x_pt * zoom)))
-        y_px = max(0, min(pixmap.height - 1, int(y_pt * zoom)))
+        display = fitz.Point(x_pt, y_pt) * to_display
+        x_px = max(0, min(pixmap.width - 1, int(display.x - pixmap.x)))
+        y_px = max(0, min(pixmap.height - 1, int(display.y - pixmap.y)))
```

## Step 4: green run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: `0`.

Result: **68 passed** (matches the brief's expectation exactly).

```
tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[0-contained] PASSED [ 72%]
...
tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270] PASSED [100%]

============================= 68 passed in 0.38s ==============================
```

## Step 5: full-suite run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Exit status: `0`.

Result:

```
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 66%]
........................................................................ [ 83%]
.......................................................................  [100%]
431 passed in 13.66s
```

431 = 411 pre-existing + 20 new Task 4 parametrizations (12 for
`test_background_sample_reads_the_colour_behind_the_block`, 4 for
`test_delete_block_erases_to_the_true_background_colour`, 4 for
`test_sampling_is_exact_on_a_fractional_size_page`). None of the
pre-Merge-A 227 tests, nor `tests/test_geometry.py`, was edited (only
`engine/operations.py` and `tests/test_page_geometry.py` are in the diff —
confirmed via `git diff --stat` before commit). Rotation-0 sampling on the
integer-size page is unchanged: `zoom` was already exactly 1.0 there and
the new matrix is the identity, so both compute `int(x)`.

## Step 6: commit

```
git add engine/operations.py tests/test_page_geometry.py
git commit -m "fix: sample background colour in display space, at true scale ..."
```

Committed as `9de0ae3` on branch `page-operations`, message and
attribution exactly as given in the brief. `git status` after commit:
`nothing to commit, working tree clean`.

## Mutation check (run on the committed file, then reverted)

### (a) Revert only the rotation mapping

Change: kept the true-scale pixmap-origin subtraction, but mapped points
without `to_display` (`display = fitz.Point(x_pt, y_pt)`, dropping the
`* to_display` multiplication).

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: `1`.

Result: **15 failed, 53 passed.**

```
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[90-plain]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[180-plain]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-contained]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-oversized]
FAILED tests/test_page_geometry.py::test_background_sample_reads_the_colour_behind_the_block[270-plain]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[90]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[180]
FAILED tests/test_page_geometry.py::test_delete_block_erases_to_the_true_background_colour[270]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[270]
======================== 15 failed, 53 passed in 0.45s ========================
```

Guarded: reverting the rotation mapping alone turns 15 tests red (every
rotated case of all three Task 4 tests; rotation-0 stays green because the
display matrix is the identity there).

### (b) Revert only the scale

Change: restored `zoom = pixmap.width / page.rect.width` and multiplied
each point by `zoom` before the display-matrix mapping
(`display = fitz.Point(x_pt * zoom, y_pt * zoom) * to_display`).

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: `1`.

Result: **3 failed, 65 passed.**

```
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[0]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[90]
FAILED tests/test_page_geometry.py::test_sampling_is_exact_on_a_fractional_size_page[180]
======================== 3 failed, 65 passed in 0.44s =========================
```

Guarded: reverting the scale alone turns the fractional-size-page test red
at 3 of its 4 rotations (0, 90 and 180; 270 happens to still round to the
correct pixel for this fixture's geometry, but at least one case is red,
satisfying the requirement).

### Restore

`git checkout -- engine/operations.py` after each reversion, followed by
`git status` confirming `nothing to commit, working tree clean` both times.
Final `git log --oneline -1`: `9de0ae3 fix: sample background colour in
display space, at true scale`. A final full-suite run after restoring
confirmed **431 passed** (exit 0), identical to Step 5.

## Self-review

- Both engine changes (import line, and the two `_sample_background_color`
  replacements) are byte-for-byte the code given in the brief's Step 3.
- Both test additions were pasted verbatim from the brief's Step 1; no
  test was altered to make it pass.
- Red counts, green counts, and full-suite counts all match the brief's
  stated expectations exactly, so no NEEDS_CONTEXT stop was needed.
- The mutation check confirms both halves of the fix are load-bearing:
  removing the rotation mapping breaks every non-zero rotation (15 tests),
  and removing the true-scale computation breaks the fractional-size-page
  test at 3 of 4 rotations. Neither reversion left all tests green.
- Only `engine/operations.py` and `tests/test_page_geometry.py` are
  modified in the commit; no pre-Merge-A test and no line of
  `tests/test_geometry.py` was touched.
- No subagents were dispatched; all work (reading, editing, running
  pytest, git operations) was done directly in this session.
