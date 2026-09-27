# Task 6 review: Image placement (R4)

## Spec compliance: ✅

- `replace_image`'s `insert_image` call now runs at rotation 0, per R4. `engine/operations.py:993-996` wraps the call in `with at_rotation_zero(page):`, replacing the bare `page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)`.
- The rect passed to `insert_image` is unchanged (still `rect` from `_validate_target`); only the page's orientation is temporarily altered, matching the brief's rationale comment (`engine/operations.py:993-995`).
- `at_rotation_zero` was already imported (`engine/operations.py:16`) — no import change was needed or made, as claimed.
- Three tests appended verbatim from the brief to `tests/test_page_geometry.py:390-473`: `test_replace_image_erases_exactly_the_placement` (R14/C8), `test_replace_image_lands_exactly_on_the_placement` (R4), `test_replace_image_works_on_a_left_overhang_page` (Task 7 guard). Supporting fixtures `BLUE`, `BAND_BEHIND_IMAGE`, `IMAGE_RECT`, `_png` also added exactly as specified.
- No pre-Merge-A test file or `tests/test_geometry.py` was touched — the diff only touches `engine/operations.py` and `tests/test_page_geometry.py` (confirmed via `git diff --stat 3c235d0..7b6506d`).
- Output assertions run on exported, re-parsed bytes: both `test_replace_image_lands_exactly_on_the_placement` and `test_replace_image_works_on_a_left_overhang_page` call `page = exported(handle)[0]` before asserting on `page.get_images()`/`get_image_rects`; `test_replace_image_erases_exactly_the_placement` also asserts against `exported(handle)[0]`.
- Counts match the brief's documented deviation: red run 6 failed / 101 passed (brief predicted 100 passed; +1 is Task 5's added test, as expected), green run 107 passed (predicted 106; same +1), full suite 470 passed. I independently reran and got the same figures (see Checks below).

## Code quality: Approved

No findings, Critical/Important/Minor. Walked through all four named risks:

1. **`insert_image` stays inside the existing `try`** — confirmed at `engine/operations.py:993-1002`: `with at_rotation_zero(page): page.insert_image(...)` is nested inside the `try:` block whose `except Exception as exc:` re-raises as `ValueError`. An exception from either `at_rotation_zero`'s `page.set_rotation(0)` or from `insert_image` itself is still caught and converted.
2. **Rotation restored on a raising `insert_image`** — `engine/geometry.py:89-93`:
   ```python
   page.set_rotation(0)
   try:
       yield
   finally:
       page.set_rotation(original)
   ```
   The `finally` runs as part of the `with` block's `__exit__`, before the exception reaches `replace_image`'s own `except`, so rotation is restored regardless of the outcome inside the `with`.
3. **Erase-stage test build/patch ordering** — `tests/test_page_geometry.py:420` (`build_page(...)`) runs before the `monkeypatch.setattr(fitz.Page, "insert_image", ...)` at line 434, matching the brief's warning that the fixture itself calls `insert_image`. `original_band` (line 424) is read from the freshly built `data` via a fresh `fitz.open`, not compared against the pre-CropBox `BAND_BEHIND_IMAGE` constant, matching the brief's second trap about CropBox coordinate shifts.
4. **Left-overhang guard test** — `tests/test_page_geometry.py:463-473` builds a page with `cropbox="[-40 0 612 792]"` (a left-origin overhang distinct from the `CROPS` fixtures) and asserts `replace_image` still lands the image correctly at every rotation, pinning current permissive behavior ahead of Task 7's refusal gate. It passes at all four rotations.

The fix is minimal, confined to the one call site named in the brief, reuses the already-tested `at_rotation_zero` primitive (no new geometry logic introduced), and the added tests are exact copies of the brief's tests with no alterations.

## Checks I ran

- `./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -q -k replace_image` → `24 passed`
- `./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -q` → `107 passed`
- `./.venv/Scripts/python.exe -m pytest tests/ -q` → `470 passed`
- `git log --oneline -3` confirms HEAD `7b6506d` on top of `3c235d0`, single commit, matching the report.
- `git status --short` on the checkout: clean (no stray edits beyond the reviewed diff).
- Read `engine/geometry.py:74-93` (`at_rotation_zero`) and `engine/operations.py:955-1010` (`replace_image`) directly to confirm the diff against the live file, not just the diff text.
- Confirmed `CROPS = {"contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}` (`tests/test_page_geometry.py:261`) to verify the left-overhang test's CropBox is a distinct case, not a duplicate of the existing fixtures.
