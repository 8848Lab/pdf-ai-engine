# Task 5 report: redaction fill placement (R11)

Branch `page-operations`, started at HEAD `9de0ae3`, fix committed as `0643677`.

## Step 1: tests appended

Appended the brief's Step 1 block verbatim to the end of `tests/test_page_geometry.py`
(after `test_sampling_is_exact_on_a_fractional_size_page`): `_erase_region` import,
`GREEN`, `BLACK`, `CROPS`, `_same_colour`, `_fills`, `_on`,
`test_erase_region_paints_exactly_one_fill_on_the_target`,
`test_redact_region_black_box_lands_on_the_target`, `_inherited_rotation_page`,
`test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation`,
`test_both_redaction_calls_run_at_rotation_zero`,
`test_rotation_is_restored_when_a_redaction_call_raises`. No existing test in the
file was touched.

## Step 2: red run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 1

Result: **11 failed, 75 passed in 0.56s** — exact match to the brief's table.

Failures, matching the brief's predictions exactly:
- `test_erase_region_paints_exactly_one_fill_on_the_target`: the five **off**
  cells — `[90-contained]`, `[180-contained]`, `[180-oversized]`,
  `[270-contained]`, `[270-oversized]` — each with a "fill painted at ..., target
  was ..." message, e.g. for `[90-contained]`:
  `fill painted at (-8.0, 695.1, 74.67, 711.59), target was (32.0, 635.1, 114.67, 651.59)`.
- `test_redact_region_black_box_lands_on_the_target[180]` and `[270]` (the
  oversized row).
- `test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation` — fails on
  fill placement (`fills [Rect(-8.0, 695.1, 74.67, 711.59)], target (32.0, 635.1, 114.67, 651.59)`).
- `test_both_redaction_calls_run_at_rotation_zero[90]`, `[180]`, `[270]` — the
  spies see the page's own rotation (e.g. `{'add_redact_annot': 90, 'apply_redactions': 90}`
  instead of `0`).

Already green, as predicted: the on-target cells (`[0-contained]`, `[0-oversized]`,
`[90-oversized]`), the black box at 0 and 90, and both
`test_rotation_is_restored_when_a_redaction_call_raises` cases.

Full pytest output saved (session transcript); short summary block:

```
FAILED tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[90-contained]
FAILED tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-contained]
FAILED tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[180-oversized]
FAILED tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-contained]
FAILED tests/test_page_geometry.py::test_erase_region_paints_exactly_one_fill_on_the_target[270-oversized]
FAILED tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[180]
FAILED tests/test_page_geometry.py::test_redact_region_black_box_lands_on_the_target[270]
FAILED tests/test_page_geometry.py::test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation
FAILED tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[90]
FAILED tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[180]
FAILED tests/test_page_geometry.py::test_both_redaction_calls_run_at_rotation_zero[270]
======================== 11 failed, 75 passed in 0.56s ========================
```

No cell differed from the table, so no stop/NEEDS_CONTEXT was needed and no test
was modified.

## Step 3: fix implemented

`engine/operations.py`:
- Import changed to
  `from engine.geometry import at_rotation_zero, to_display_matrix, unrotated_bounds`
  (ruling S1).
- `_erase_region` now wraps both calls:

```python
    Both calls run at rotation 0 (spec R11): see at_rotation_zero.
    """
    # Both calls at rotation 0 (spec R11): on a rotated page with a CropBox,
    # PyMuPDF removes the right text but paints the fill elsewhere -- ~88pt
    # away on the test pages, possibly over content that was NOT removed.
    # The rect stays in unrotated coordinates; only the page's orientation
    # changes, and at_rotation_zero restores it even if a call raises.
    with at_rotation_zero(page):
        page.add_redact_annot(rect, fill=fill)
        page.apply_redactions(images=2, graphics=1, text=0)
```

The existing docstring was kept; one line was added noting the rotation-0 pair
per R11.

## Step 4: green run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 0

Result: **86 passed in 0.47s.** Matches the brief's expectation exactly.

## Commit

Committed `engine/operations.py` and `tests/test_page_geometry.py` with the
brief's exact message before running the mutation checks, per the coordinator's
instruction to commit before Step 5's mutation.

```
[page-operations 0643677] fix: paint redaction and erase fills where the content was removed
 2 files changed, 135 insertions(+), 3 deletions(-)
```

## Step 5: mutation 1 — move `add_redact_annot` out of the `with` block

Mutated the committed file to:

```python
    page.add_redact_annot(rect, fill=fill)
    with at_rotation_zero(page):
        page.apply_redactions(images=2, graphics=1, text=0)
```

Ran `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v -k test_both_redaction_calls_run_at_rotation_zero`.
Exit status: 1.

Result: **3 failed, 83 deselected** — exactly the three
`test_both_redaction_calls_run_at_rotation_zero` cases, each failing on
`add_redact_annot` seeing the page's own (unrotated-wrapper-missed) rotation
while `apply_redactions` still shows `0`. Representative failure line
(`[90]`):

```
E       AssertionError: assert {'add_redact_...edactions': 0} == {'add_redact_...edactions': 0}
E         Differing items:
E         {'add_redact_annot': 90} != {'add_redact_annot': 0}
```

(and correspondingly `180` and `270`.)

Restored with `git checkout -- engine/operations.py`; `git status` reported
`nothing to commit, working tree clean`.

## Step 6 (coordinator's "second mutation"): remove the `with` wrapper entirely

Mutated the committed file to:

```python
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)
```

Ran `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`.
Exit status: 1.

Result: **11 failed, 75 passed in 0.56s** — identical failure set to the
original Step 2 red run (all 5 "off" fill-placement cells, both oversized
black-box rotations, the inherited-rotation test, and all three
`test_both_redaction_calls_run_at_rotation_zero` cases). This confirms removing
the wrapper reproduces the original defect exactly.

Restored with `git checkout -- engine/operations.py`; `git status` reported
`nothing to commit, working tree clean`.

## Full-suite run

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Exit status: 0

Result: **449 passed in 14.15s.** All tests pass, including the 86 in
`tests/test_page_geometry.py` and every pre-existing test elsewhere in the
suite. No pre-Merge-A test or `tests/test_geometry.py` was modified.

## Self-review

- Followed the brief's exact code for both the tests and the fix; did not
  alter any assertion or expected count.
- Red run matched the brief's table cell-for-cell; no NEEDS_CONTEXT was
  triggered.
- Commit happened before the mutation checks (per coordinator instruction,
  which supersedes the brief's Step 5/Step 6 ordering), using the brief's
  exact commit message and attribution.
- Both mutations were applied to the already-committed file and fully
  restored via `git checkout --`, with `git status` confirmed clean after
  each. Neither mutation is present in the final commit.
- No subagents were dispatched; all work was done directly.
- Only `engine/operations.py` and `tests/test_page_geometry.py` were changed;
  no pre-Merge-A test and no line of `tests/test_geometry.py` was touched.
- One residual note: this task's instructions restructured the brief's
  Step 5/Step 6 order (commit first, then run both mutations, then the full
  suite) rather than mutate-then-commit. That ordering was followed as
  directed; the final commit content is identical either way since the
  mutations were never left in place.

## Fix round 1

Review at `.superpowers/sdd/2026-09-26-page-geometry-correctness/task-5-review.md`
(reviewer Fable 5.1, range `9de0ae3..0643677`). Spec compliance was ✅; every
finding was on tests or comments. All were fixed on top of `0643677`.

### I1 (Important) — inherited-rotation test never reached the inherited case

`parse()` calls `page.get_text("dict")`, which on PyMuPDF 1.28.2 writes a
normalised page-level `/Rotate` as a side effect, so by the time
`redact_region` ran on the parsed handle the key was already explicit and
`at_rotation_zero` saw an ordinary rotation, not an inherited one.

- Corrected `test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation`'s
  comment to say what it actually exercises (the contained-crop fill on a
  page whose `/Rotate` `parse()` has already made explicit), instead of
  claiming to cover the inheritance case.
- Added `test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation`,
  the reviewer's exact code: it bypasses `parse()` entirely, asserts the page
  key is `("null", "null")` before, runs `redact_region` on a bbox measured
  via `find_span_bbox` on a throwaway probe copy, then asserts on the
  exported bytes: `out.rotation == 90`, the page key is now
  `("int", "90")`, exactly one black fill on target, and the text gone.
  Imported `find_span_bbox` from `tests.geometry_helpers` (it already existed
  there) to support this.

**Red first.** Temporarily removed the `with at_rotation_zero(page):` wrapper
in `_erase_region` and ran
`timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v -k test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation`.
Exit status: 1.

```
FAILED tests/test_page_geometry.py::test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation
E       AssertionError: fills [Rect(-8.0, 695.0999755859375, 74.66799926757812, 711.5880126953125)], target (32.0, 635.0999755859375, 114.66799926757812, 651.5880126953125)
====================== 1 failed, 86 deselected in 0.12s =======================
```

Restored the wrapper immediately after.

### M1 — compound asserts hid which property failed

Split `assert len(fills) == 1 and _on(fills[0], target)` at
`test_redact_region_black_box_lands_on_the_target` (was line 309) and
`test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation` (was line
341) into two asserts each, in the style already used at
`test_erase_region_paints_exactly_one_fill_on_the_target` (lines 296-298):
one `assert len(fills) == 1, f"expected one fill, got {fills}"` and one
`assert _on(fills[0], target), f"..."`. The new raw-handle test from I1 keeps
the reviewer's exact compound-assert form, as given in the review.

### M2 — rotation-intact assertion was on the live handle only

Added `assert page.rotation == rotation` to
`test_erase_region_paints_exactly_one_fill_on_the_target`, alongside the
existing `assert handle[0].rotation == rotation`, so the rotation claim is
also checked on the exported, re-parsed page.

### M3 — comment/docstring understated the trigger

Reworded, comment/docstring only, in both places the review named:
- `engine/operations.py:206-209` (the `_erase_region` inline comment):
  "on a rotated page with a CropBox" → "on a rotated page whose CropBox or
  MediaBox origin is not (0, 0)".
- `engine/geometry.py`'s `at_rotation_zero` docstring: same rewording. No
  other line in `engine/geometry.py` was touched (confirmed via
  `git diff engine/geometry.py` — a pure comment-text diff).

### Full re-run after fix round 1

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Exit status: 0
Result: **87 passed in 0.50s** (86 + the one new raw-handle test).

Command: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Exit status: 0
Result: **450 passed in 14.04s** (449 + the one new test). All green, no
pre-Merge-A test or `tests/test_geometry.py` touched.

### Commit

```
[page-operations 3c235d0] fix: address task 5 review findings on tests and comments
 3 files changed, 36 insertions(+), 16 deletions(-)
```

Committed on top of `0643677` (no amend), `git status` confirmed clean
afterward.

### Self-review (fix round 1)

- All four findings (I1, M1, M2, M3) addressed exactly as specified; no
  scope crept beyond what was asked (e.g. did not hoist the `_erase_region`
  import per the reviewer's "not flagged" aside, since that was explicitly
  not a finding).
- Red-first was honored for the new I1 test before it was added to the
  green suite.
- `engine/geometry.py` diff is comment-only, matching the instruction to
  change nothing else there.
- No subagents were dispatched.
