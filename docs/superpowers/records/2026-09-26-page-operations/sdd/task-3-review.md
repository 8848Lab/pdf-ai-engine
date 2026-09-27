# Task 3 review: bound checks (D1, D3, D4, D5), b539129..6480eac

## Spec compliance: ✅

The four code changes, the import, `build_page` and `tests/test_page_geometry.py` match the brief word for word.

- The import is `from engine.geometry import unrotated_bounds` only (`engine/operations.py:16`), as ruling S1 requires.
- D1 is at `engine/operations.py:179-184`, D3 at `:357-359`, D4 at `:764-769` and D5 at `:838-843`. The rest of each error message is unchanged.
- `tests/geometry_helpers.py` gains only the appended `build_page`, with no other lines changed. No pre-Merge-A test was edited: the diff under `tests/` is 246 insertions and 0 deletions.
- Output assertions go through `exported()`, which re-parses the exported bytes. The `fingerprint()` docstring states the rule, and no test compares exported bytes.
- The report's red/green/mutation counts match the brief: 20F/28P, then 48P, then exactly 4F in the D3-only mutation. It shows the full output and exit status for each run. The full suite ran 411 passed, exit 0, and the report explains why 411 differs from the brief's 363.

Missing: none. Extra: none. Misunderstood: none.

## Code quality: Needs fixes (Minor only)

**Critical:** none. **Important:** none.

**Minor**
1. `engine/operations.py:727-728` (the `move_block` docstring, Raises): it still says the destination must be "fully contained in the destination page's rect". The check now uses the unrotated page bounds, and on a rotated page "the page's rect" reads as `page.rect`, which this commit deliberately stopped using. Fix: reword it to "(not fully contained in the destination page's unrotated bounds, see engine.geometry.unrotated_bounds)".
2. `engine/operations.py:821-822` (the `insert_block` docstring, Raises): the same stale wording, "not fully contained in the page's rect". Fix: reword it to "(not fully contained in the page's unrotated bounds)".

## Named risk: other `page.rect` comparisons in operations.py

I grepped `engine/operations.py` at 6480eac for `.rect`, `intersects(`, `contains(`, `mediabox`, `cropbox` and `rotation`.

- The only `page.rect` left is `:236`, `zoom = pixmap.width / page.rect.width` in `_sample_background_color`. That is D2, which spec F3 and Merge A assign to a later task (the display-matrix transform of the sample points). It is not a bound check and is out of scope for Task 3.
- Every `intersects` and `contains` against the page now uses `unrotated_bounds` (`:180`, `:765`, `:839`).
- `move_block`'s destination also passes through `_validate_target` (D1), so both of its checks agree.
- The `intersects` at `:916` is only a docstring mention.

## Mutation reasoning (whether each site has its own guard)

- **D1 alone:** guarded by the swapped-rect rejection tests and the straddle tests at 90 and 270.
- **D3 alone:** the implementer executed this mutation and got exactly 4 failures.
- **D4 alone:** reverting it with D1 kept would make `move_block` to (72,740) fail at 90 and 270. The 612-high `page.rect` does not contain it.
- **D5 alone:** `insert_block (72,740,400,760)` at 90 and 270 would fail the same way.

The D4 and D5 results are reasoned, not executed.

## Checks run
- Read the brief, the report (its result sections and outputs) and the full diff.
- `git show 6480eac:engine/operations.py | grep` for `.rect`, `intersects`, `contains`, box and rotation terms, then read `:205-260` (the sampler) and the docstrings of `move_block` and `insert_block`.
- Read `engine/geometry.py:42-58` (`unrotated_bounds`) to confirm its origin-0 un-swapped extent matches the bbox space.
- Ran `git diff --stat b539129 6480eac -- tests/`: insertions only.
- Ran `git status`: the tree is clean at 6480eac, so the D3 mutation was restored.
- I re-ran no tests. The report's full outputs were enough, and no specific doubt came up.
