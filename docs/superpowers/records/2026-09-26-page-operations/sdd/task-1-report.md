# Task 1 Report: Geometry helpers — bounds, display matrix, rotation-0 context

## What I implemented

Exactly the three files specified in the brief, transcribed verbatim from the
brief's code blocks:

- `engine/geometry.py` — `unrotated_bounds(page)`, `to_display_matrix(page)`,
  `at_rotation_zero(page)` context manager.
- `tests/geometry_helpers.py` — `matrix_cases`, `matrix_page`, `reopen`,
  and the constants `ROTATIONS`, `BAND`, `BAND_RGB`.
- `tests/test_geometry.py` — 8 tests: the two 1,024-configuration matrix
  tests, the ordinary-page pin test, and the four `at_rotation_zero`
  behaviour tests (parametrized over rotation, plus the raise-restores test).

No other files were touched. `engine/operations.py` was left untouched per
the brief (wiring is later tasks' job).

## Test results

Final full-suite run (after mutation restore):

```
235 passed in 9.21s
```

227 pre-existing + 8 new, as expected.

## TDD evidence

### RED

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```

Output (tail):
```
ERRORS ====================================
___________________ ERROR collecting tests/test_geometry.py ___________________
ImportError while importing test module 'D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py'.
...
tests\test_geometry.py:10: in <module>
    from engine.geometry import at_rotation_zero, to_display_matrix, unrotated_bounds
E   ModuleNotFoundError: No module named 'engine.geometry'
=========================== short test summary info ===========================
ERROR tests/test_geometry.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================== 1 error in 0.14s ===============================
```

This is exactly the expected failure: `engine/geometry.py` did not exist yet,
so the test module could not even be collected. This confirms the test file
genuinely depends on the not-yet-written implementation.

### GREEN

Command (after writing `engine/geometry.py`):
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```

Output:
```
collected 8 items

tests/test_geometry.py::test_unrotated_bounds_hold_across_the_1024_case_matrix PASSED [ 12%]
tests/test_geometry.py::test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix PASSED [ 25%]
tests/test_geometry.py::test_to_display_matrix_equals_the_library_matrix_on_an_ordinary_page PASSED [ 37%]
tests/test_geometry.py::test_at_rotation_zero_draws_unrotated_and_restores[0] PASSED [ 50%]
tests/test_geometry.py::test_at_rotation_zero_draws_unrotated_and_restores[90] PASSED [ 62%]
tests/test_geometry.py::test_at_rotation_zero_draws_unrotated_and_restores[180] PASSED [ 75%]
tests/test_geometry.py::test_at_rotation_zero_draws_unrotated_and_restores[270] PASSED [ 87%]
tests/test_geometry.py::test_at_rotation_zero_restores_rotation_when_the_body_raises PASSED [100%]

============================== 8 passed in 7.02s ==============================
```

Full suite, run once before committing:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
```
235 passed in 9.29s
```

## Commit

Committed before the mutation experiment, per the coordinator's step-order
ruling:

```
0148cf7 feat: add page geometry helpers for rotated, cropped and scaled pages
```

Attribution lines included exactly as specified:
```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka
```

Only the three intended files were staged and committed
(`engine/geometry.py`, `tests/geometry_helpers.py`, `tests/test_geometry.py`);
the pre-existing untracked `qa_scenarios.md` was left alone.

## Mutation check

Mutated `to_display_matrix` in `engine/geometry.py` to:

```python
def to_display_matrix(page: fitz.Page) -> fitz.Matrix:
    """..."""
    return page.rotation_matrix
```

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py::test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix -v
```

Result: **FAILED**, with **640 failures** — matching the brief's expected
count exactly:

```
AssertionError: 640 failures, first five: ['origin=(0,0) mask=0 unit=0.5 rot=90: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=0.5 rot=180: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=0.5 rot=270: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=1.5 rot=90: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=1.5 rot=180: sampled (255, 255, 255)']
```

Restored the file:
```
git checkout -- engine/geometry.py
```

Confirmed clean tree afterward:
```
git status --short   # no output
git diff HEAD -- engine/geometry.py   # no output (identical to committed version)
```

Re-ran the full suite after restore to confirm nothing was left broken:
```
235 passed in 9.21s
```

## Files changed

- `D:/Coding/8848 Lab/pdf-ai/engine/geometry.py` (new)
- `D:/Coding/8848 Lab/pdf-ai/tests/geometry_helpers.py` (new)
- `D:/Coding/8848 Lab/pdf-ai/tests/test_geometry.py` (new)

## Self-review findings

- Compared the committed `git show HEAD` diff line-by-line against the
  brief's code blocks: all three files are verbatim transcriptions, no
  improvisation or added scope.
- `engine/operations.py` was not touched, as instructed — this task only
  produces the standalone helpers; wiring is for later tasks.
- No `tests/__init__.py` was created; `from tests.geometry_helpers import
  ...` in `tests/test_geometry.py` works via `pyproject.toml`'s
  `pythonpath = ["."]`, matching existing test-suite conventions.
- Did not touch `pyproject.toml`, did not run
  `tests/fixtures/generate_fixtures.py`, and stayed on branch
  `page-operations` throughout.
- Test output is pristine: no warnings, no deprecation notices, no stderr
  noise in any of the runs above.
- Every test asserts genuine behaviour: the two 1,024-case matrix tests
  check real geometric/pixel correctness (not tautologies), the "equals
  library matrix" test pins that the correction is a no-op on ordinary
  pages (regression guard against overcorrecting), and the two
  `at_rotation_zero` tests check both the happy path and exception-safety
  of the context manager. The mutation check independently confirms the
  second matrix test is not vacuous (640 real failures when the fix is
  reverted to the naive `page.rotation_matrix`).
- No git config, hooks, or `pyproject.toml` changes were made.

## Concerns

None. The RED failure, GREEN pass, full-suite pass (235), and mutation
failure count (640) all matched the brief's stated expectations exactly, with
no deviations required.

## Fix round 1

Review approved the task with no Critical or Important findings. Two minor
findings were fixed, both in `tests/test_geometry.py` only;
`engine/geometry.py` was not touched by the fix itself (only mutated and
restored for the re-check).

### What changed

1. **Misleading test name (Finding 1).** Renamed
   `test_at_rotation_zero_draws_unrotated_and_restores` to
   `test_at_rotation_zero_unrotates_the_page_then_restores_it`, since the
   test only checks `page.rotation` and draws nothing. Body and
   parametrisation over `ROTATIONS` (including the rotation-0 early-return
   guard case) left exactly as they were.

2. **Thin sampling margin (Finding 2).** In
   `test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix`,
   moved the sample point from `(80, 85)` — 3pt inside the band's lower edge
   — to `(120, 70)`, which is at least 12pt inside the band
   `(35..135, 58..88)` on every side and clear of the `VISIBLE` glyphs
   (which start at x=40 and sit on a baseline near y=80). Added a one-line
   comment above the call explaining the choice and that it avoids the text.

### Covering test run

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```

Output:
```
collected 8 items

tests/test_geometry.py::test_unrotated_bounds_hold_across_the_1024_case_matrix PASSED [ 12%]
tests/test_geometry.py::test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix PASSED [ 25%]
tests/test_geometry.py::test_to_display_matrix_equals_the_library_matrix_on_an_ordinary_page PASSED [ 37%]
tests/test_geometry.py::test_at_rotation_zero_unrotates_the_page_then_restores_it[0] PASSED [ 50%]
tests/test_geometry.py::test_at_rotation_zero_unrotates_the_page_then_restores_it[90] PASSED [ 62%]
tests/test_geometry.py::test_at_rotation_zero_unrotates_the_page_then_restores_it[180] PASSED [ 75%]
tests/test_geometry.py::test_at_rotation_zero_unrotates_the_page_then_restores_it[270] PASSED [ 87%]
tests/test_geometry.py::test_at_rotation_zero_restores_rotation_when_the_body_raises PASSED [100%]

============================== 8 passed in 7.02s ==============================
```

The sampling test passed across all 1,024 cases at the new point `(120, 70)`.

Full suite, run once before committing:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
```
235 passed in 9.27s
```

### Commit

```
9141394 fix: rename misleading test and widen the sampling margin in test_geometry
```

Only `tests/test_geometry.py` was staged and committed; `engine/geometry.py`
was not part of this commit.

### Mutation check at the new point

Mutated `to_display_matrix` in `engine/geometry.py` to:

```python
def to_display_matrix(page: fitz.Page) -> fitz.Matrix:
    """..."""
    return page.rotation_matrix
```

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py::test_to_display_matrix_samples_the_true_colour_across_the_1024_case_matrix -v
```

Result: **FAILED**, with **640 failures** at the new point `(120, 70)` —
identical to the original count, and well above zero:

```
AssertionError: 640 failures, first five: ['origin=(0,0) mask=0 unit=0.5 rot=90: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=0.5 rot=180: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=0.5 rot=270: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=1.5 rot=90: sampled (255, 255, 255)', 'origin=(0,0) mask=0 unit=1.5 rot=180: sampled (255, 255, 255)']
```

### Restore confirmation

```
git checkout -- engine/geometry.py
git status --short   # no output
git diff HEAD -- engine/geometry.py   # no output (identical to committed version)
```

Re-ran the full suite after restore to confirm nothing was left broken:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
```
235 passed in 9.19s
```

Tree confirmed clean; `git log -3` shows:
```
9141394 fix: rename misleading test and widen the sampling margin in test_geometry
0148cf7 feat: add page geometry helpers for rotated, cropped and scaled pages
efd26a9 docs: implementation plan for page geometry correctness (Merge A)
```
