# Task 2 Report: Box, unit and rotation readers, and the refusal rules

## What was implemented

Appended to `engine/geometry.py` (verbatim from the brief):
- `_resolve(doc, kind, value)` — follows one level of indirect reference (`N 0 R`).
- `_inherited(page, key)` — walks the `/Parent` chain to resolve inheritable
  page-tree attributes (`/MediaBox`, `/CropBox`, `/Rotate`), resolving indirection at
  each node.
- `_raw_box(page, key)` — a box as written in raw PDF user space (y-up), inheritance
  resolved, normalized.
- `raw_rotation(page) -> float` — the `/Rotate` value as written (inheritance
  resolved), defaulting to 0; does not hide malformed (non-multiple-of-90) values the
  way `page.rotation` does.
- `user_unit(page) -> float` — `/UserUnit` read at page level only (not inherited,
  matching PyMuPDF's own non-inheriting behaviour), defaulting to 1.
- `crop_origin_overhangs(page) -> bool` — True when the CropBox's top-left corner
  lies outside the MediaBox (`crop.x0 < media.x0 or crop.y1 > media.y1`), which is
  where PyMuPDF's `insert_text`/`insert_textbox` actually drift.
- `TEXT_DRAWING` / `OTHER_DRAWING` constants.
- `drawing_refusal(page, page_index, kind) -> str | None` — the refusal-rule
  triage: invalid rotation refuses everything; `/UserUnit != 1` refuses everything;
  a CropBox top-left overhang refuses `TEXT_DRAWING` only.

Appended to `tests/geometry_helpers.py`:
- `box_page(*, where="page", indirect=(), **keys)` — builds a plain 612x792 page
  with raw keys written either on the page or on the parent `/Pages` node (to
  exercise inheritance), optionally as indirect references.

Appended to `tests/test_geometry.py`: the 34-test suite from the brief (8
`crop_origin_overhangs` cases + 3 inheritance/indirection tests + the 256-case
unit-1 drift-matching test + 4 `user_unit` cases + 5 `raw_rotation` cases + the
plain-page/`UserUnit`/overhang/malformed-rotation/un-normalised-rotation
`drawing_refusal` tests).

`engine/operations.py` was not touched, as instructed (Task 7 wires the refusal in).

## Test results

- New file alone: `tests/test_geometry.py` — 42 passed (8 from Task 1 + 34 new).
- Full suite: `tests/` — 269 passed (235 existing + 34 new). No existing test was
  modified.

## TDD evidence

**RED** — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```
Output (tail):
```
ERROR collecting tests/test_geometry.py
tests\test_geometry.py:107: in <module>
    from engine.geometry import (  # noqa: E402
E   ImportError: cannot import name 'OTHER_DRAWING' from 'engine.geometry' (D:\Coding\8848 Lab\pdf-ai\engine\geometry.py)
Interrupted: 1 error during collection
```
Matches the brief's expected failure reason exactly.

**GREEN** — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```
Output (tail):
```
collected 42 items
... (all PASSED) ...
============================= 42 passed in 8.11s ==============================
```

Full suite — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
Output:
```
........................................................................ [ 26%]
........................................................................ [ 53%]
........................................................................ [ 80%]
.....................................................                    [100%]
269 passed in 10.33s
```

Committed at this point (commit `1f3500a`), per the coordinator's step-order ruling
(commit before any mutation experiment).

## Mutation check

Change made: replaced the body of `crop_origin_overhangs` with
`return not page.mediabox.contains(page.cropbox)`.

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k test_crop_origin_overhangs_matches_where_text_actually_drifts
```

Result: **3 failures**, not the 2 the brief predicted:
```
FAILED tests/test_geometry.py::test_crop_origin_overhangs_matches_where_text_actually_drifts[bottom]
FAILED tests/test_geometry.py::test_crop_origin_overhangs_matches_where_text_actually_drifts[right]
FAILED tests/test_geometry.py::test_crop_origin_overhangs_matches_where_text_actually_drifts[negative-origin-mediabox]
```
5 passed, 34 deselected (the other parametrized ids and unrelated tests).

The brief (and the coordinator's ruling) expected only `right` and
`negative-origin-mediabox` to fail. I additionally observed `bottom` failing. I
investigated to confirm this wasn't a mistake on my part: with
`CropBox="[0 -60 612 792]"` (bottom-only overhang, raw PDF y-up coordinates),
`page.mediabox` is `Rect(0, 0, 612, 792)` but `page.cropbox` comes back as
`Rect(0, 0, 612, 852)` — PyMuPDF's y-flip for its display-space cropbox turns a
raw bottom overhang into a taller box (852 > 792) rather than a top-left offset,
so `mediabox.contains(cropbox)` is False even though raw top-left coordinates
never drift. This is the same class of "the two frames disagree" problem the
brief's own comments describe for the right-only and negative-origin-mediabox
cases, just a third instance of it. I'm flagging this as a finding rather than
treating it as a task failure — the mutation check's job is to confirm the
guarded function is not equivalent to the naive one, which it emphatically is not.

File restored:
```
git checkout -- engine/geometry.py
git status --short   # (no output — clean)
```
Confirmed clean, and reran the full suite (269 passed) after restoring to be sure
the working tree matches the committed state.

## Files changed

- `D:/Coding/8848 Lab/pdf-ai/engine/geometry.py` (146 lines appended)
- `D:/Coding/8848 Lab/pdf-ai/tests/geometry_helpers.py` (25 lines appended: `box_page`)
- `D:/Coding/8848 Lab/pdf-ai/tests/test_geometry.py` (144 lines appended: imports + 34 tests)

Commit: `1f3500a` — "feat: read page boxes, units and rotation, and decide when
drawing is unsafe" (branch `page-operations`).

## Self-review findings

- All appended code and tests were transcribed verbatim from the brief; diffed
  against the brief's code blocks line by line — no discrepancies.
- The mid-file `from engine.geometry import (...)` / `from tests.geometry_helpers
  import box_page` block lands after existing test functions rather than at the
  top of `tests/test_geometry.py`, with `# noqa: E402` on both — this is exactly
  as specified in the brief's Step 2 code block, not an artifact of my editing.
- `engine/operations.py` was not modified, consistent with the task boundary
  (Task 7 wires refusal in).
- No changes to `pyproject.toml`, no `tests/__init__.py` added, no fixture
  generator run.
- Working tree is clean at commit `1f3500a`; no leftover mutation.

## Concerns

- The mutation check's actual failing set (`bottom`, `right`,
  `negative-origin-mediabox`) is a strict superset of what the brief predicted
  (`right`, `negative-origin-mediabox`). This doesn't affect correctness of the
  implementation — `crop_origin_overhangs` itself is untouched and all 269 tests
  pass — but the brief's Step 6 expectation text is slightly inaccurate against
  PyMuPDF 1.28.2's actual `page.mediabox`/`page.cropbox` behaviour. Worth a note
  back to the plan owner if the brief's wording is meant to be exact documentation
  rather than a rough expectation.
- No other concerns; scope, tests, and commit all match the brief and the
  coordinator's step-order ruling.

## Fix round 1

Commit: `52de01c` — "fix: close the indirect-reference gate bypass and the
/Parent cycle hang", on top of the coordinator's docs-only `1770621` (plan file),
both on top of `1f3500a`. Not an amend/reset/rebase.

### Process note on RED for I1/I2

I had already written the fix in `engine/geometry.py` before writing the new
tests (normal for a fix-round: the bug is already understood). To still prove
RED for the stated reason before GREEN, I captured the fixed file's exact
content, temporarily overwrote `engine/geometry.py` with `git show
HEAD:engine/geometry.py` (the pre-fix, already-committed version — no stash,
checkout or restore over uncommitted work; this was a plain file overwrite I
could undo myself, since I'd captured the fixed content first), ran the new
tests against it, then wrote the captured fixed content back and reran for
GREEN. `tests/geometry_helpers.py` (with the A2 `box_page` fix and the new
`raw_object_page` helper) was left in place throughout, since it's test
infrastructure, not the code under test.

### I1: indirect numbers bypassed the gate

**Changed:** `engine/geometry.py` — added `_REFERENCE` (regex for `N G R`) and
`_classify` (labels a raw object body `null`/`array`/`int`/`float`/`other`).
Rewrote `_resolve` to loop: read the referenced object's text, and if that text
is itself a reference, keep following (guarded by a `seen` set of visited
xrefs, which resolves a cycle to `("null", "null")` instead of looping). Direct
values from `xref_get_key` are returned unchanged, as before.

I verified `doc.xref_object()`'s actual behaviour first, since the brief asked
me to: a single indirect number (`update_object(ref, "2")`) round-trips as the
literal text `"2"`, so `_classify` handles it directly. A **non-cyclic** chain
built via `update_object(ref2, "5 0 R")` does **not** stay a reference:
PyMuPDF's `update_object` silently drops the generation and `R`, keeping only
the leading integer as a bare number — so it cannot be used to build a genuine
multi-hop reference chain. A **cyclic** pair built the same way collapses the
same way (to a bare int), so cycles can't be built via `update_object` either.
Building both a genuine two-hop chain and a genuine cycle therefore required
writing raw PDF bytes directly (MuPDF's own parser preserves `"5 0 R"` as an
object body when it comes from a real PDF file, and returns the reference text
itself, unresolved, when it detects a cycle) — this is `raw_object_page` in
`tests/geometry_helpers.py`.

RED — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k "test_an_indirect_user_unit_is_read_refused_and_matches_pymupdfs_scaling or test_an_indirect_rotate_45_refuses_every_kind or test_an_indirect_rotate_90_is_not_refused or test_a_two_level_chained_reference_resolves_to_the_final_value or test_an_indirect_null_continues_the_inheritance_walk_to_the_parent"
```
Output (against the pre-fix `_resolve`):
```
FAILED tests/test_geometry.py::test_an_indirect_user_unit_is_read_refused_and_matches_pymupdfs_scaling
  assert 1.0 == 2.0  (user_unit returned the default instead of 2.0)
FAILED tests/test_geometry.py::test_an_indirect_rotate_45_refuses_every_kind[page]
FAILED tests/test_geometry.py::test_an_indirect_rotate_45_refuses_every_kind[parent]
  assert reason is not None  (drawing_refusal returned None -- the bypass)
FAILED tests/test_geometry.py::test_an_indirect_rotate_90_is_not_refused
  assert 0.0 == 90.0  (raw_rotation returned the default instead of 90.0)
FAILED tests/test_geometry.py::test_a_two_level_chained_reference_resolves_to_the_final_value
  assert 1.0 == 2.0
FAILED tests/test_geometry.py::test_an_indirect_null_continues_the_inheritance_walk_to_the_parent
  assert False is True  (walk stopped instead of continuing to the parent)
5 failed (of these 5 selected), plus 2 more selected tests passed incidentally
```

GREEN — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```
Output (tail): `56 passed in 8.15s` (full new file, fixed code).

### I2: `_inherited` looped forever on a `/Parent` cycle

**Changed:** `engine/geometry.py` `_inherited` — added a `seen` set of
visited xrefs to the `/Parent`-chain `while` loop; a repeated xref returns
`None` instead of continuing.

New test `test_a_parent_cycle_does_not_hang` builds a self-referencing
`/Parent` (`doc.xref_set_key(parent, "Parent", f"{parent} 0 R")`) on a page
with no `/CropBox` anywhere (forcing the full walk), runs
`crop_origin_overhangs(page)` in a daemon thread, and asserts the thread is no
longer alive after `join(timeout=5)`. Per the coordinator's instruction,
`page.rect` is never touched in this test.

RED — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k test_a_parent_cycle_does_not_hang
```
Output (against the pre-fix `_inherited`):
```
FAILED tests/test_geometry.py::test_a_parent_cycle_does_not_hang
  assert not thread.is_alive()
  assert not True
   +  where True = is_alive()
```
The thread was still running after the 5s join, i.e. the walk had genuinely
hung — reproduced as described.

GREEN — same command against the fixed `_inherited`: `1 passed` (thread
terminates well within 5s; `result["overhangs"] is False`, since neither
`/CropBox` nor `/MediaBox` is reachable through the broken chain the walk
correctly gives up on).

### M2: `_raw_box` crashed on a malformed array

**Changed:** `engine/geometry.py` `_raw_box` — now parses the array's numbers
inside a `try/except ValueError`, and returns `None` unless parsing yields
exactly four numbers (covers both a non-numeric entry and the wrong count).

**PyMuPDF behaviour checked:** built a page with `CropBox="[0 0 612]"` (three
entries). `page.mediabox`/`page.cropbox`/`page.rect` all report the plain,
unaffected `Rect(0, 0, 612, 792)` (PyMuPDF silently falls back). More directly,
I drew a probe: `page.insert_text((100, 140), "PROBE", fontsize=10)`, then read
it back with `page.get_text("dict", clip=fitz.INFINITE_RECT(), flags=fitz.TEXTFLAGS_DICT
& ~fitz.TEXT_MEDIABOX_CLIP)` (clipping disabled, matching the pattern the
existing matrix test already uses for off-page text) — the origin came back as
exactly `(100.0, 140.0)`, i.e. no drift. (Separately, with the default clip
flags, `get_text()` returns nothing at all for this page — the malformed
CropBox does affect extraction's *visibility* clipping, but not *drawing
position*, which is the only thing `crop_origin_overhangs` is about; the test
uses the same clip-disabling pattern the existing matrix test already relies
on for exactly this reason.) `_raw_box` returning `None` here — so
`crop_origin_overhangs` treats the box as absent and reports no overhang —
agrees with this observed drawing behaviour.

RED — command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k test_a_malformed_cropbox_array_is_treated_as_absent_matching_pymupdf
```
Output (against the pre-fix `_raw_box`):
```
FAILED tests/test_geometry.py::test_a_malformed_cropbox_array_is_treated_as_absent_matching_pymupdf
engine\geometry.py:115: in _raw_box
    box = fitz.Rect([float(v) for v in found[1].strip("[] \n").split()])
...
AssertionError   (inside PyMuPDF's own Rect constructor, util_make_rect --
                   it asserts len(ret) == 4 and crashes on 3 numbers)
```
This reproduces the crash the finding describes.

GREEN — same command against the fixed `_raw_box`: `1 passed`.

### M3: non-numeric /Rotate and /UserUnit silently defaulted

**Changed:** no code change needed — `raw_rotation`/`user_unit` already
defaulted correctly for a direct (non-indirect) non-numeric value, because
`xref_get_key` classifies e.g. a PDF name as `"name"`, which was never in the
old `_resolve`'s indirection path and was never treated as `"int"`/`"float"`
by the two readers. Added two pinning tests, since none existed.

**PyMuPDF behaviour checked:**
- `box_page(Rotate="/Foo")` (a PDF name): `page.rotation == 0` (confirmed by
  direct query) — matches `raw_rotation(page) == 0.0`.
- `box_page(UserUnit="/Foo")`: `page.rect == Rect(0, 0, 612, 792)` (unscaled)
  — matches `user_unit(page) == 1.0`.

RED/GREEN: these two tests (`test_a_non_numeric_rotate_defaults_to_zero_matching_pymupdf`,
`test_a_non_numeric_user_unit_defaults_to_one_matching_pymupdf`) passed even
against the pre-fix code (confirmed during the I1/I2 RED run above — they were
part of the "7 passed" alongside the A2 tests) since M3 was never actually
broken, only untested; they are included as pinning tests per the coordinator's
instruction, not as regression proof.

### M4: no test pinned the refusal-check order

**Changed:** no code change (the order was already correct in
`drawing_refusal`: rotation check, then `/UserUnit`, then CropBox). Added
`test_the_rotation_check_runs_before_the_user_unit_check`: a page with both
`Rotate="45"` and `UserUnit="2"` must report the "invalid rotation" message,
not the `/UserUnit` one. Passed immediately (order was already right); included
as a pinning test per the coordinator's instruction.

### M5: `crop_origin_overhangs` docstring named only two false positives

**Changed:** `engine/geometry.py` docstring now reads: "that flags a
bottom-only overhang, a right-only overhang and a negative-origin MediaBox,
none of which actually drift" (was: only right-only and negative-origin),
matching the three failing case ids from Task 2's original mutation check
(`bottom`, `right`, `negative-origin-mediabox`).

### A1: extend I1's tests to an ancestor

**Changed:** `test_an_indirect_rotate_45_refuses_every_kind` is now
parametrized over `where=["page", "parent"]`; for `"parent"` it also asserts
`doc.xref_get_key(page.xref, "Rotate") == ("null", "null")` before checking the
refusal. No ancestor `/UserUnit` case was added, per the coordinator's
instruction (PyMuPDF does not read `/UserUnit` from an ancestor at all).

RED (parent case only) — same run as I1 above: both `[page]` and `[parent]`
parametrizations of this test failed against the pre-fix `_resolve` (`assert
reason is not None` / `assert (None is not None)`), confirming the bypass
reproduces on an ancestor too. GREEN: both pass against the fixed code.

### A2: `box_page` didn't exercise inheritance for MediaBox

**Changed:**
- (a) `tests/geometry_helpers.py` `box_page`: when `where="parent"`, it now
  nulls the page's own copy of **every** inheritable key being written
  (`/MediaBox`, `/CropBox`, `/Rotate`), not just `/Rotate` — `new_page` writes
  an explicit page-level `/MediaBox` too, which the old code left in place to
  silently win over the parent's.
- (b) Every inheritance test now asserts the nulled key directly, e.g.
  `assert doc.xref_get_key(page.xref, "MediaBox") == ("null", "null")`.
- (c) `test_crop_origin_overhangs_resolves_an_inherited_mediabox` rewritten:
  parent `MediaBox="[100 100 712 892]"` (distinct from the default), page-level
  `CropBox="[50 150 600 700]"` chosen so the answer is `True` against the
  parent's box (`crop.x0=50 < 100`) but would be `False` against the default
  `[0 0 612 792]` a reader that failed to find the inherited box would fall
  back to.
- (d) New `test_crop_origin_overhangs_a_local_mediabox_overrides_the_inherited_one`:
  same parent MediaBox and CropBox, but the page also sets its own MediaBox
  back to `[0 0 612 792]` — expects `False` (local box wins).
- (e) New `test_crop_origin_overhangs_resolves_a_grandparent_mediabox`: built a
  real two-level tree by hand — a new `/Pages` dict as grandparent, its
  `/Kids` pointing at the existing parent, and the parent's own `/Parent`
  rewired to point at it — with the MediaBox set only on the grandparent.
  I did not need to report an inability to build this: it worked cleanly, and
  I additionally confirmed `page.mediabox == Rect(100, 100, 712, 892)`
  (PyMuPDF's own getter) resolves through the same two-level chain, as a
  sanity check that the constructed tree is a genuine, valid inheritance
  chain and not an artifact of our own reader.

These three tests are test-helper/test-correctness fixes, not engine bug
fixes -- `box_page`'s nulling logic lives entirely in `tests/geometry_helpers.py`,
which was not reverted during the I1/I2 RED demonstration above, so they show
as passing in that same RED run (they were never expected to fail there).

### Full-suite confirmation

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
Output: `283 passed in 10.33s` (235 pre-Task-2 + 34 Task-2-original + 14 new
this round). No existing test was modified.

### Files changed (fix round 1)

- `D:/Coding/8848 Lab/pdf-ai/engine/geometry.py` (+71/-9 lines: `_classify`,
  rewritten `_resolve`, cycle-guarded `_inherited`, four-number-strict
  `_raw_box`, M5 docstring)
- `D:/Coding/8848 Lab/pdf-ai/tests/geometry_helpers.py` (+~45 lines: A2 `box_page`
  fix, new `raw_object_page` helper)
- `D:/Coding/8848 Lab/pdf-ai/tests/test_geometry.py` (+~180 lines: 14 new tests,
  1 test rewritten, `threading` import, `raw_object_page` import)

### Self-review (fix round 1)

- Re-read the full diff of `engine/geometry.py` against the coordinator's
  suggested `_resolve`/`_classify` shape: matches, with the same regex and the
  same cycle-guard idea; adapted only in that `_resolve`'s own docstring now
  explains why the loop is reachable at all (MuPDF auto-resolves a non-cyclic
  chain internally, only a cycle causes `xref_object` to hand back reference
  text) rather than silently deviating from the suggestion.
- Confirmed `_inherited`'s new `seen` check happens at the top of the loop
  body (before resolving the key), so a self-referencing page's own xref
  would also be caught, not just a /Parent self-loop one hop up.
- Confirmed `UserUnit` is never added to `box_page`'s parent-nulling tuple, so
  A2(a) does not accidentally introduce an ancestor-`/UserUnit`-refuses case.
- Confirmed no test double-closes a `doc` or leaves one unclosed on a
  passing path; each new test ends with `doc.close()` except
  `test_a_parent_cycle_does_not_hang`'s post-assertion close, which only runs
  if the assertion above it didn't already fail the test (acceptable: on
  failure the daemon thread doesn't block process/test-runner exit either
  way).

### Concerns (fix round 1)

- None new. The Task 2 concern already on record (the original brief's Step 6
  predicting 2 mutation-check failures instead of 3) stands unchanged; this
  round did not touch `crop_origin_overhangs`'s logic, only its docstring
  (M5), which now states the corrected three-item list.

## Fix round 2 (coordinator ruling C15)

Commit: `b08c848` — "fix: decide page-drawing refusals from PyMuPDF's
interpreted geometry", on top of `52de01c` (fix round 1). Not an
amend/reset/rebase.

The round-1 security re-review (`task-2-rereview-1.md`) found that I1, M1 and
M2 were still open, with **verified gate bypasses** (PyMuPDF misdraws text but
`drawing_refusal` allows it): re-parsing raw PDF keys could not keep pace with
every quirk of MuPDF's own parser (reference depth, dangling references,
null/cycle inheritance-walk stopping, malformed-box entry reading, the
letter-size MediaBox fallback, int32-vs-int64 reads, /Rotate overflow). The
coordinator's ruling C15 replaced that whole approach: the gate now reads only
PyMuPDF's own already-interpreted geometry (`page.rotation`, `page.rect`,
`page.mediabox`, `page.cropbox`, `page.transformation_matrix`) and never a raw
key, so it agrees with what gets drawn by construction.

### What changed in `engine/geometry.py`

Per the brief, transcribed verbatim:
- Deleted `_REFERENCE`, `_classify`, `_resolve`, `_inherited`, `_raw_box`,
  `raw_rotation`, and the now-unused `import re`.
- Added `_LAYOUT_TOLERANCE_PT`, `visible_area(page)`, `rotation_is_valid(page)`.
- Replaced `user_unit` (now `float | None`, a *measured* scale rather than a
  read key), `crop_origin_overhangs` (now reads `page.cropbox`/`page.mediabox`
  directly), and `drawing_refusal` (now four ordered checks: invalid rotation,
  inconsistent boxes/mirrored page, `/UserUnit` scaling, CropBox overhang).
- Updated the module docstring to state the gate reads PyMuPDF's interpreted
  geometry, never raw keys, and why (ruling C15).
- `unrotated_bounds`, `to_display_matrix`, `at_rotation_zero`, `TEXT_DRAWING`,
  `OTHER_DRAWING` untouched.

### What changed in the tests

`tests/geometry_helpers.py`: added `drift_probe` (verbatim from the brief),
and `build`/`standard` (the reviewer's raw-bytes builders from
`adversarial.py`, needed because `standard()`'s page dict must stay free to
omit or override `/MediaBox`/`/Parent` per adversarial row — `raw_object_page`
from fix round 1 always injects a hardcoded `/MediaBox`, so it could not build
several of the required rows, e.g. I3 "no MediaBox at all" or B2's duplicate
`/Parent`). `raw_object_page` itself is left in place but is now unused by
`test_geometry.py` (its two callers, the chain and cycle raw-reader tests,
were deleted below); I did not remove it from `geometry_helpers.py` since
nothing in the brief asked for that and it's harmless.

`tests/test_geometry.py`:
- Deleted, exactly the brief's list: `test_user_unit_reads_the_page_level_value_only`,
  `test_raw_rotation_reports_the_value_as_written`,
  `test_a_two_level_chained_reference_resolves_to_the_final_value`,
  `test_a_reference_cycle_resolves_to_null_and_terminates`,
  `test_an_indirect_null_continues_the_inheritance_walk_to_the_parent`,
  `test_a_malformed_cropbox_array_is_treated_as_absent_matching_pymupdf`,
  `test_a_non_numeric_rotate_defaults_to_zero_matching_pymupdf`,
  `test_a_non_numeric_user_unit_defaults_to_one_matching_pymupdf`. I did not
  rewrite the last two as agreement cases (the brief made this optional, "if
  you do that"); Test B's table already covers the same spirit with rows like
  `unit1e30` and the `rot*` overflow rows.
- Adjusted two kept tests that called now-deleted functions:
  `test_an_indirect_rotate_90_is_not_refused` (dropped the `raw_rotation(page)
  == 90.0` assertion, kept `page.rotation == 90` and the refusal check), and
  `test_a_parent_cycle_does_not_hang` (the new `crop_origin_overhangs` never
  walks `/Parent` by hand, so the only thing that can still hang is PyMuPDF's
  own `reload_page`/attribute read on a self-referencing `/Parent`; the test
  now runs both inside the timed thread and accepts either a normal result or
  any exception, per the brief -- "either outcome is acceptable, a hang is
  not").
- All other kept tests (the 1,024-case geometry tests, `at_rotation_zero`, the
  overhang/A2 cases, the plain-page/UserUnit/overhang/malformed-rotation
  refusal tests, un-normalised rotations, the indirect UserUnit/Rotate tests
  including A1, M4's order test) needed no code changes — they call
  `crop_origin_overhangs`/`drawing_refusal`/`user_unit` with the same
  signatures, and passed unedited against the new implementation.
- Added Test A (`test_the_matrix_agrees_with_pymupdfs_own_drawing`) and Test B
  (`test_the_adversarial_table_agrees_with_pymupdfs_own_drawing`, parametrized
  over the 39-row table, plus a second parametrized test,
  `test_the_adversarial_table_categories_apply_to_other_drawing_too`, that
  states the OTHER_DRAWING-category rule explicitly rather than only inline).

### Red run (against the round-1 code, before implementing)

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k "test_the_adversarial_table_agrees_with_pymupdfs_own_drawing or test_the_matrix_agrees_with_pymupdfs_own_drawing"
```
Result: **17 failed, 23 passed** (Test B parametrizations + Test A). The
brief's required bypass rows — `G1, H1, H2, I1, I3, I5, N3, J-null,
unit-2^32+1, rot-2.7e9` — were **all 10 present** among the 17 failures, along
with 7 more (`unit1.0000001, unit-chain16, unit-1, J2, dangling,
dangling-parent, crop-outside`) that also disagreed with round-1's raw-key
reader. Test A (the 1,024-case matrix) **passed** against round-1 code — this
is expected and not a problem: round-1's reader was already tuned to agree
with PyMuPDF on the "clean" matrix (simple, well-formed boxes); the
adversarial malformations are what it got wrong, and Test B is what catches
that. The brief's RED requirement only bound the 10 named rows to be among the
*failures*, which they were.

### Green run (after implementing)

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v
```
Result: `95 passed, 25 skipped in 10.66s` (120 collected). The 25 skips are
`test_the_adversarial_table_categories_apply_to_other_drawing_too` rows whose
category is `any`/`-`/`over` (explicitly skipped -- those are already checked
inline by Test B). Every specified test passed on the **first attempt** after
transcribing the brief's code verbatim, consistent with the brief's claim that
the code was already verified by the coordinator against a drift probe on the
full matrix and all 39 adversarial PDFs.

**Test A's runtime:** 2.19s–2.31s across repeated runs (1,024 cases, all four
units) -- recorded via a `print` inside the test, visible with `-s`:
```
test_the_matrix_agrees_with_pymupdfs_own_drawing: 2.19s for 1024 cases
```

### Mutations (each on the checked-out fixed file, restored after)

All four run individually; after each, `engine/geometry.py` was restored from
a saved copy of the fixed file and `git status --short` confirmed clean before
the next mutation.

1. **Remove the mirror check** (`if unit is None or not (matrix.a > 0 and
   matrix.d < 0):` -> `if unit is None:`). Failing test ids:
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1]`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit0]`
   - `test_the_adversarial_table_categories_apply_to_other_drawing_too[unit-1]`
   3 failed, 92 passed, 25 skipped. `unit0` failed with an uncaught
   `ZeroDivisionError` at the `/UserUnit` tolerance line, not an assertion --
   without the mirror check, `/UserUnit 0` (which apparently also produces a
   non-`(a>0, d<0)` matrix) no longer gets caught by the "inconsistent boxes"
   return and falls through to `abs(unit - 1) * ... / unit` with `unit ==
   0.0`. So the mirror check is doing double duty: it's both the documented
   catch for a mirrored page (`/UserUnit -1`) and an incidental guard against
   dividing by an exact-zero unit.

2. **`page.cropbox.y0 < 0` -> `page.cropbox.y0 < page.mediabox.y0`**. Failing
   test ids:
   - `test_the_predicate_matches_observed_text_drift_on_all_256_unit_one_cases`
   - `test_the_matrix_agrees_with_pymupdfs_own_drawing`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[negmedia-top]`
   3 failed, 92 passed, 25 skipped. (The four parametrized
   `test_crop_origin_overhangs_matches_where_text_actually_drifts` cases that
   probe top-overhangs directly -- `top`, `all-four` -- still passed here:
   `page.mediabox.y0` is 0 for a plain page, so this mutation is only
   distinguishable from the original on a MediaBox with a non-zero y0, which
   those two cases don't have. `negmedia-top` does, which is why it's the one
   table row that catches it.)

3. **Replace `crop_origin_overhangs` with `not
   page.mediabox.contains(page.cropbox)`**. Failing test ids:
   - `test_crop_origin_overhangs_matches_where_text_actually_drifts[bottom]`
   - `test_crop_origin_overhangs_matches_where_text_actually_drifts[right]`
   - `test_crop_origin_overhangs_matches_where_text_actually_drifts[negative-origin-mediabox]`
   - `test_the_predicate_matches_observed_text_drift_on_all_256_unit_one_cases`
   - `test_the_matrix_agrees_with_pymupdfs_own_drawing`
   5 failed, 90 passed, 25 skipped. Same three case ids as fix round 1's
   original mutation check (bottom/right/negative-origin), now additionally
   caught at scale by the two matrix-driven tests.

4. **Make `rotation_is_valid` always return `True`**. Failing test ids:
   - `test_a_malformed_rotation_refuses_every_kind[text-page]`
   - `test_a_malformed_rotation_refuses_every_kind[text-parent]`
   - `test_a_malformed_rotation_refuses_every_kind[other-page]`
   - `test_a_malformed_rotation_refuses_every_kind[other-parent]`
   - `test_an_indirect_rotate_45_refuses_every_kind[page]`
   - `test_an_indirect_rotate_45_refuses_every_kind[parent]`
   - `test_the_rotation_check_runs_before_the_user_unit_check`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot45]`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-2.7e9]`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-2^32+45]`
   - `test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot45-square]`
   11 failed, 84 passed, 25 skipped. Not a full bypass in every case: some
   malformed-rotation pages still get refused, just via the "inconsistent
   boxes" message instead of "invalid rotation" (their `user_unit` also comes
   back `None` once rotation is malformed), which is why the tests fail on
   wrong-message-phrase rather than on an allowed drift. `rot-2^32+90` did not
   fail (expected `-`, i.e. that row is supposed to be allowed either way).

After the fourth mutation, `engine/geometry.py` was restored and
`git status --short` was confirmed clean before running the full suite and
committing.

### Full suite

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
Output:
```
........................................................................ [ 20%]
........................................................................ [ 41%]
.......s.sss..s.s....sssssss.s.sssssss.ssss............................. [ 62%]
........................................................................ [ 82%]
...........................................................              [100%]
322 passed, 25 skipped in 28.65s
```
Exit status: `0`.

### Files changed (fix round 2)

- `D:/Coding/8848 Lab/pdf-ai/engine/geometry.py` (+83/-146 net lines: readers
  replaced per ruling C15)
- `D:/Coding/8848 Lab/pdf-ai/tests/geometry_helpers.py` (+57 lines:
  `drift_probe`, `build`, `standard`)
- `D:/Coding/8848 Lab/pdf-ai/tests/test_geometry.py` (net +313/-250: 8 tests
  deleted, 2 adjusted, Test A and Test B added, ~120 tests collected)

### Self-review (fix round 2)

- Diffed `engine/geometry.py` against the brief's code block line by line —
  matches, including the exact tolerance arithmetic and rule order.
- Confirmed `unrotated_bounds`, `to_display_matrix`, `at_rotation_zero`,
  `TEXT_DRAWING`, `OTHER_DRAWING` are byte-for-byte unchanged from fix round 1.
- Confirmed `engine/operations.py` was not touched.
- Verified the two special-cased adversarial rows (`B2`, `dangling-parent`)
  use `build()` directly rather than `standard()`, because `standard()`
  hardcodes `/Parent 2 0 R` in the page dict and duplicating that key would
  make the construction ambiguous — matching the reviewer's own `adversarial.py`
  construction for B2/B4 exactly.
- Verified `unit-chain16`'s object numbering: `obj4="5 0 R"` ... `obj18="19 0
  R"`, `obj19="2"` (15 chained hops then a concrete value), matching the
  brief's "objs 4..18 = 5 0 R...19 0 R; obj19 = 2".
- Re-read `test_a_parent_cycle_does_not_hang` to confirm the timed thread
  wraps *both* `doc.reload_page` and `crop_origin_overhangs`, not just the
  latter — otherwise a hang inside `reload_page` itself would not be caught.
- Confirmed no test leaks an open `fitz.Document`/`Page` on a failing path in
  a way that would compound across the 39-row parametrization (each opens its
  own `fitz.open(stream=...)` and closes it before returning or raising).

### Concerns (fix round 2)

- `raw_object_page` (added in fix round 1) is now unused within
  `test_geometry.py`. I left it in `tests/geometry_helpers.py` since removing
  it wasn't requested and it's still a reasonable, documented builder; flagging
  it in case a later task wants it removed as dead code.
- The `test_the_adversarial_table_categories_apply_to_other_drawing_too` test
  skips 25 of its 39 parametrizations (the `any`/`-`/`over` categories, whose
  OTHER_DRAWING behaviour is already asserted inline in Test B). This is
  intentional (avoids duplicate assertions) but means the raw pytest summary
  shows `25 skipped`, which I've called out explicitly in every test count
  above so it isn't mistaken for a gap in coverage.
- Per the brief's own instruction ("If a row disagrees with the table when you
  run it, but the probe still agrees with the gate, report it"): no row
  disagreed with the table on the first run — all 39 rows matched their
  predicted category and the probe agreed with the gate in both directions on
  the first attempt. Nothing to report there.

## Fix round 3 (coordinator ruling C16)

Commit: `a8b2406` — "fix: read MuPDF's own page transform so rotated, mirrored
and tiny-box pages are refused", on top of `b08c848` (fix round 2). Not an
amend/reset/rebase.

The second security re-review (`task-2-rereview-2.md`) closed every round-1
item but found two new, Important bypasses in the C15 design: (1)
`page.transformation_matrix` is a fixed constant on rotated pages (PyMuPDF
derives it from MuPDF's real transform only at rotation 0), so
`rotation_is_valid` and the mirror check were vacuous at 90/180/270 -- a
negative `/UserUnit` combined with any valid rotation passed all four round-2
rules, and both text and a redaction fill landed in the wrong place; (2)
MuPDF replaces a box under 1pt wide/tall with the unit rect, and
`page.mediabox` mirrors that substitution but `page.cropbox` does not, so
`visible_area` could report a stale sub-point box. Ruling C16: read MuPDF's
real page transform through the low-level `mupdf` binding (`pdf_page_transform`,
via the private `page._pdf_page()`, since PyMuPDF has no public accessor for
it), and require its linear part to match PyMuPDF's reported rotation at one
positive scale.

### What changed in `engine/geometry.py`

Per the brief, transcribed verbatim:
- Deleted `rotation_is_valid` and `user_unit`.
- Kept `visible_area` and `crop_origin_overhangs` unchanged.
- Added `_ROTATION_PATTERNS`, `_MAX_COORDINATE_PT`, `page_transform` (the
  low-level MuPDF transform read, failing closed to `None` on
  `AttributeError`/`TypeError`), `layout_orientation` (the (rotation, scale)
  MuPDF actually lays the page out at, or `None`).
- Replaced `drawing_refusal`'s body with the brief's five-rule version:
  invalid rotation (now via `layout_orientation` disagreeing with
  `page.rotation`, which also catches a negative `/UserUnit` -- the same
  linear transform as a 180-degree turn, hence the shared message), then
  inconsistent boxes (no valid orientation, an empty or sub-point visible
  area, or a size mismatch against `page.rect`), then `/UserUnit` scaling
  (message now `{unit:.7g}` instead of `{unit:g}`), then the new coordinate-
  magnitude rule (`> 2**24` points on either box), then the CropBox overhang.
- Updated the module docstring (ruling C16 paragraph) and `drawing_refusal`'s
  docstring rule list to the five rules above.
- `unrotated_bounds`, `to_display_matrix`, `at_rotation_zero`, `TEXT_DRAWING`,
  `OTHER_DRAWING` untouched; `engine/operations.py` untouched.

### What changed in the tests

`tests/geometry_helpers.py`:
- Deleted `raw_object_page` (dead per the coordinator's note (b) -- `grep -rn
  raw_object_page tests/ engine/` found no caller once fix round 2's two
  callers were removed there).
- Added `with_text(page_extra, pages_extra, extra_objects)` (the reviewer's
  `round3b.py` builder, adapted): `standard()`'s three-object document plus a
  real content stream and Helvetica font, so there is a span to redact.
- Added `find_span_bbox(page, word)`, the bbox-lookup half of the reviewer's
  `find_bbox`, generalised to take the word to search for.

`tests/test_geometry.py`:
- Test B table: changed `unit-1`'s expected category from `incons` to `rot`
  (a negative `/UserUnit` and a 180-turn are the same transform now). Added a
  `huge` category (phrase `"larger than"`). Added the 13 rows the brief's
  table names, each copied from the reviewer's `round3a.py` `NEW_ROWS` by id:
  `unit-1-rot90`, `unit-1-rot180`, `unit-1-rot270`, `unit-1-rot180-crop`,
  `unit-1-indirect-rot90`, `rot135`, `rot-inherited-135`, `crop-tiny`,
  `crop-tiny-unit0.5`, `media-huge`, `media-huge-1e7`, `rot315`,
  `unit-1.0000001-huge`.
- Deleted `test_the_adversarial_table_categories_apply_to_other_drawing_too`
  per the coordinator's note (a) (Test B's inline OTHER_DRAWING assertion is
  strictly stronger and this duplicate skipped 25 of 39 rows for nothing).
- Rewrote `test_a_parent_cycle_does_not_hang`'s final assertion. The old
  `assert "overhangs" in result or "error" in result` could never fail once
  `not thread.is_alive()` had passed, because `run()` always sets one of the
  two keys (review Minor 4). Measured what this exact construction (a
  `/Pages` node whose own `/Parent` points to itself) actually produces:
  `doc.reload_page` raises `RuntimeError: cycle in resources` -- pinned as
  `assert "cycle in resources" in result.get("error", "")`.
- Added `test_page_transform_returns_a_matrix_on_a_plain_page`, pinning the
  low-level API and its exact value on a plain page (`(1, 0, 0, -1, 0, 792)`).
- Added `test_every_other_allowed_table_row_has_a_redaction_placement_case`
  and `test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing`
  (review item 4): for every `_ADVERSARIAL_TABLE` row whose expected category
  is `-` or `over` (i.e. the fixed gate allows `OTHER_DRAWING`), draws a real
  "VISIBLE" span through `with_text` using the *same* page/pages/extra-object
  parameters as the Test B row, confirms the gate still allows
  `OTHER_DRAWING`, redacts through `engine.operations._erase_region` wrapped
  in `at_rotation_zero` (Task 5 does not exist yet to do that itself), and
  asserts the fill lands within 0.5pt of the original span's bbox. The guard
  test keeps the redaction-row set from silently drifting out of sync with
  the table as rows are added or recategorised.
- `unit-1.0000001-huge`'s Test B case gained one extra assertion (see "Note on
  Minor 6" below) instead of the literal "must print more than (1)" the
  brief's inline table note asks for.
- Updated `test_the_rotation_check_runs_before_the_user_unit_check`: the new
  invalid-rotation message legitimately mentions "/UserUnit" in passing (a
  negative `/UserUnit` shares the bad-rotation transform), so the assertion
  now checks for the absence of the *separate* `/UserUnit`-scaling rule's
  phrase (`"uses PDF /UserUnit scaling"`) instead of the bare substring.
- Updated section-header comments to describe ruling C16 and its relationship
  to C15; updated the module import to drop `raw_rotation`/`user_unit`-style
  names no longer exported and add `page_transform`,
  `engine.operations._erase_region`, and the new helpers.
- Skip count in `tests/test_geometry.py`: **0** (was 25 after fix round 2).

### Note on Minor 6 (`{unit:g}` -> `{unit:.7g}`)

Implemented verbatim per the brief. However, for the exact adversarial value
in `unit-1.0000001-huge` (`/MediaBox [0 0 100000 100000] /UserUnit
1.0000001`), the measured scale is `1.0000001192092896` (MuPDF's float32
rounding), and `{unit:.7g}` of that value is still `"1"` -- seven significant
figures round down before reaching the digit that would show it isn't exactly
1. I verified this directly (`layout_orientation` returns
`(0, 1.0000001192092896)`; `format(1.0000001192092896, ".7g") == "1"`) rather
than assuming the brief's format string alone closed the finding. Per the
established pattern from earlier rounds ("if a row disagrees but the probe
agrees, report it, don't silently patch coordinator-verified code"), I did
not deviate from the verbatim `.7g` format. Instead, the Test B case for this
row asserts `"(1)" in reason_text` -- a regression canary documenting today's
actual behaviour, with a comment explaining it will start failing (usefully)
the day a future change makes the digit count sufficient. The category and
refusal themselves are correct; only the display precision falls short of the
table's aspiration for this one value.

### Red run (against b08c848, before implementing)

Since `page_transform` doesn't exist in the round-2 code, importing it at
module scope would fail collection outright; to get a meaningful per-test RED
signal I temporarily removed just that one name from the top-of-file import
(and left the one test that needs it, `test_page_transform_...`, to fail
naturally), re-verifying afterward that the real revert-and-restore left the
working tree byte-identical to the committed state.

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -v -k "test_the_adversarial_table_agrees_with_pymupdfs_own_drawing or test_redaction_lands_correctly or test_the_matrix_agrees or test_page_transform"
```
Result: **12 failed, 68 passed, 42 deselected**. Failing ids:
```
test_page_transform_returns_a_matrix_on_a_plain_page      (NameError, expected: function doesn't exist pre-fix)
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot90]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot180]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot270]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot180-crop]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-indirect-rot90]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot135]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-inherited-135]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[crop-tiny]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[crop-tiny-unit0.5]
test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-huge]
```
The brief's required failures -- "the unit-1-rot* rows and crop-tiny-unit0.5
must fail as bypasses, and media-huge must fail" -- are **all present**:
`unit-1-rot90/180/270/180-crop/indirect-rot90` (5), `crop-tiny-unit0.5` (1),
`media-huge` (1) = 7 of the 7 named, plus 4 more genuine round-2 failures
(`unit-1`, `rot135`, `rot-inherited-135`, `crop-tiny`) my own added rows
uncovered. Three of my 13 new/changed rows did **not** fail against round-2
code (`media-huge-1e7`, `rot315`, `unit-1.0000001-huge`) -- expected, since
none of those three exercise the rotated-mirror or sub-point-box bug
specifically (round-2's simpler checks already handled them correctly).

`test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing`'s
26 parametrizations **all passed** against round-2 code. This is expected,
not a gap: that test's row set is built from the *fixed* table's `-`/`over`
categories, which for these 26 ids is identical on round-2 and round-3 (the
C16 fix only recategorises `unit-1*`/`rot135*`/`crop-tiny*`/`media-huge`, none
of which are in the redaction-allowed set on either side of the fix). The
round-2 -> round-3 regression was entirely "wrongly ALLOWS a row" (caught
exhaustively by the Test B category failures above), not "misplaces a fill on
a row it correctly allows" -- so the redaction-placement test's job is
complementary, not overlapping. To independently corroborate the review's own
redaction-placement evidence for the two closed bypasses, I reproduced it by
hand against round-2 code, outside the standing test suite:

```
unit-1-rot90 round-2 other-refusal: None bbox (466.64, 596.41, 512.0, 612.9) gone True
  fill Rect(421.28, 612.9, 466.64, 629.39) offset 45.3599853515625
crop-tiny-unit0.5 round-2 other-refusal: None bbox (50.0, -305.95, 72.68, -297.71) gone True
  fill Rect(50.0, -301.83, 61.34, -297.71) offset 11.339996337890625
```
Both numbers match the review's reported 45.36pt and 11.34pt offsets exactly,
confirming the same two bypasses independently.

### Green run (after implementing)

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -q
```
Result: `122 passed in 11.05s` -- **0 skipped**, as required.

### Mutations (each on the checked-out fixed file, restored after)

All four run individually against a saved copy of the fixed file, restored
(and diffed byte-identical) before the next mutation.

1. **`page_transform` -> `return page.transformation_matrix`** (the round-2
   behaviour). **19 failed, 103 passed**:
   ```
   test_un_normalised_but_valid_rotations_are_not_refused[-90]
   test_un_normalised_but_valid_rotations_are_not_refused[450]
   test_un_normalised_but_valid_rotations_are_not_refused[-270]
   test_an_indirect_rotate_90_is_not_refused
   test_the_matrix_agrees_with_pymupdfs_own_drawing
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-2^32+90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot270-square]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot450]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit2-rot90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit2-square-rot90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot90-left]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot180-top]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot-2^32+90]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot270-square]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot-90]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot450]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot90-left]
   test_redaction_lands_correctly_on_every_row_the_gate_allows_for_other_drawing[rot180-top]
   ```
   With the fixed constant back in place, every genuinely-rotated page's
   `layout[0]` reads as the wrong (constant-derived) orientation, so valid
   rotations are now wrongly *refused* (the safe direction) rather than
   letting a mirrored one through -- confirming `page_transform`'s low-level
   read is what makes rotation detection meaningful at all.

2. **Drop the `width < 1 or height < 1` check.** **0 failed, 122 passed** --
   no test id fails. Investigated why: for both `crop-tiny` and
   `crop-tiny-unit0.5`, MuPDF's unit-rect substitution also changes
   `page.rect` (to `(0,0,1,1)` and `(0,0,0.5,0.5)` respectively) while
   `visible_area()` still reports the un-substituted sub-point box (`page.cropbox`
   does not mirror the substitution -- the same fact the brief's finding #2
   is about). The size-consistency check two lines below
   (`abs(page.rect.width - unit*width) > TOL`) independently catches the
   resulting mismatch in both cases, so removing the `< 1` guard alone
   produces no observable regression against the current 122-test suite. This
   doesn't mean the guard is redundant in general -- a row where the
   substituted `page.rect` and the un-substituted `visible_area` happen to
   agree by coincidence (e.g. a sub-point box whose /UserUnit exactly
   compensates) would still need it, and no row in the brief's table or my
   own constructs that coincidence -- so I removed it, observed the true
   result (no failures), and I am reporting that honestly here rather than
   inventing a failing test id that didn't occur.

3. **Drop the magnitude rule** (the `_MAX_COORDINATE_PT` block). **1 failed,
   121 passed**:
   ```
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-huge]
   ```

4. **`layout[0] != page.rotation` -> `False`.** **19 failed, 103 passed**:
   ```
   test_a_malformed_rotation_refuses_every_kind[text-page]
   test_a_malformed_rotation_refuses_every_kind[text-parent]
   test_a_malformed_rotation_refuses_every_kind[other-page]
   test_a_malformed_rotation_refuses_every_kind[other-parent]
   test_an_indirect_rotate_45_refuses_every_kind[page]
   test_an_indirect_rotate_45_refuses_every_kind[parent]
   test_the_rotation_check_runs_before_the_user_unit_check
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot45]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-2.7e9]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-2^32+45]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot45-square]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot180]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot270]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-rot180-crop]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1-indirect-rot90]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot135]
   test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[rot-inherited-135]
   ```

After the fourth mutation, `engine/geometry.py` was restored (confirmed
byte-identical to the saved fixed copy) before running the full suite and
committing.

### Full suite

Command:
```
timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q
```
Output:
```
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 61%]
........................................................................ [ 82%]
.............................................................            [100%]
349 passed in 25.84s
```
Exit status: `0`.

### Files changed (fix round 3)

- `D:/Coding/8848 Lab/pdf-ai/engine/geometry.py` (readers replaced per ruling
  C16: `rotation_is_valid`/`user_unit` deleted, `page_transform`/
  `layout_orientation` added, `drawing_refusal` rewritten to five rules)
- `D:/Coding/8848 Lab/pdf-ai/tests/geometry_helpers.py` (`raw_object_page`
  deleted; `with_text`, `find_span_bbox` added)
- `D:/Coding/8848 Lab/pdf-ai/tests/test_geometry.py` (net +223/-... lines: 13
  new Test B rows, 1 recategorised, 1 duplicate test deleted, 2 tests
  strengthened/fixed, 2 new tests, a 26-row redaction-placement parametrized
  test plus its sync guard; 0 skipped, up from 25)

### Self-review (fix round 3)

- Diffed `engine/geometry.py` against the brief's code block line by line --
  matches, including the exact `_ROTATION_PATTERNS`/tolerance arithmetic and
  the five-rule order.
- Confirmed `visible_area` and `crop_origin_overhangs` are byte-for-byte
  unchanged from fix round 2, per the brief's explicit "keep exactly as they
  are."
- Confirmed `engine/operations.py` was not touched -- `_erase_region` is only
  imported and called from the new test, never modified.
- Verified `_REDACTION_ALLOWED_ROWS`' 26 ids are exactly the `_ADVERSARIAL_TABLE`
  rows whose expected category is `-` or `over`, via a standing test
  (`test_every_other_allowed_table_row_has_a_redaction_placement_case`)
  rather than a one-time manual check, so future row changes can't silently
  desync the two lists.
- Confirmed the B2 and `dangling-parent` redaction rows use `build()` directly
  with a hand-written `/Contents`+font structure (mirroring the `_adversarial_b2`/
  `_adversarial_dangling_parent` pattern from fix round 2), since `with_text`,
  like `standard`, hardcodes a single `/Parent 2 0 R` and cannot express
  their custom `/Parent`.
- Re-verified `test_a_parent_cycle_does_not_hang`'s new pinned value by
  running the exact construction standalone (not just trusting the test's own
  pass/fail): `RuntimeError: cycle in resources`, confirmed.
- Checked that no test in the file still imports or references
  `rotation_is_valid`, `user_unit`, or `raw_object_page`.

### Concerns (fix round 3)

- Minor 6 (`{unit:g}` -> `{unit:.7g}`) is implemented exactly as the brief's
  verbatim code specifies, but does not fully close the finding for the
  specific `unit-1.0000001-huge` adversarial value, as detailed above --
  flagged as a regression-canary assertion rather than silently patched.
- Mutation 2 (dropping the sub-point `< 1` check) produced zero test
  failures against the current suite; the check is not proven load-bearing by
  any test I have, only by the reasoning above (a coincidental-scale row would
  need it, and none exists in the table). If the coordinator wants this
  proven by an executed test rather than reasoning (per this project's own
  "prove tests fail first" standard), a row like `/CropBox [100 100 100.5
  100.5] /UserUnit 2` (chosen so `unit * width == page.rect.width` in the
  substituted frame) would need to be added and would need independent
  verification of what MuPDF actually does with it -- I did not add it
  without that verification, since fabricating an unverified row would
  violate the same standard.
- `raw_object_page` was deleted per the coordinator's note (b); no other
  caller existed anywhere in the repo (`grep -rn raw_object_page tests/
  engine/` confirmed empty before deletion).


## Fix round 4

Commit: `84fc253` (on top of a8b2406; no amend/reset/rebase).
Files touched: `engine/geometry.py` (one format spec), `tests/test_geometry.py`.

### F1 — sub-point crop check now pinned by a row that needs it
- Added Test B row `crop-0.995`: `/MediaBox [0 0 612 792] /CropBox [100 100 100.995 100.995]`, category `incons`, next to the `crop-tiny` rows, with a comment explaining why only the `< 1` check catches it.
- Mutation 2 re-run on a backup copy (`engine/geometry.py` copied to the scratchpad, the line `or width < 1 or height < 1 ...` replaced with a comment, then the backup copied back; `git diff engine/geometry.py` empty afterwards).

Red run (mutation applied, `pytest tests/test_geometry.py -k "crop-" -q`):

```
>       assert reason_text is not None and phrase in reason_text, \
E       AssertionError: crop-0.995: expected a 'incons' refusal, got None
E       assert (None is not None)
tests\test_geometry.py:568: AssertionError
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[crop-0.995]
1 failed, 7 passed, 115 deselected in 0.12s
exit 1
```

Only `crop-0.995` fails; the older `crop-tiny` rows still pass under the mutation (as round 3 found), confirming the new row is the one that pins the check. Also, across the whole adversarial table under the mutation, the only other failure was `unit-1.0000001-huge`, which was the F2 canary (red for its own reason, below).

Green run (check restored, same command): `8 passed, 115 deselected in 0.08s`, exit 0.

### F2 — full /UserUnit scale in the message
- Red first: with the canary changed to `assert "scaling (1)" not in reason_text` and `{unit:.7g}` still in place:

```
E             'scaling (1)' is contained here:
E               Page 0 uses PDF /UserUnit scaling (1), which the editor does not support yet, so this operation was not applied and nothing was changed. Support is planned.
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[unit-1.0000001-huge]
1 failed, 1 passed, 121 deselected in 0.13s
```

- Changed `{unit:.7g}` to `{unit:.10g}` in `drawing_refusal`. `f'{1.0000001192092896:.10g}'` prints `1.000000119`. The canary now passes; the round-3 comment block describing the "(1)" residual was replaced with a short note on the new behaviour.

### Full suite (`./.venv/Scripts/python.exe -m pytest tests/`)

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 350 items

tests\test_ai.py ...........................                             [  7%]
tests\test_ai_provider_ollama.py ............                            [ 11%]
tests\test_ai_provider_openai_compatible.py ............                 [ 14%]
tests\test_document.py ......                                            [ 16%]
tests\test_export.py .......                                             [ 18%]
tests\test_fixtures_exist.py ...                                         [ 19%]
tests\test_geometry.py ................................................. [ 33%]
........................................................................ [ 53%]
..                                                                       [ 54%]
tests\test_operations.py ............................................... [ 67%]
...................................                                      [ 77%]
tests\test_parser.py ...............                                     [ 82%]
tests\test_visual_regression.py ..........                               [ 84%]
tests\test_webui.py .................................................... [ 99%]
.                                                                        [100%]

============================ 350 passed in 13.09s =============================
exit status: 0
```

## Fix round 5 (coordinator ruling C18)

Commit: `d545d86 fix: bound the page's real extent, including MuPDF's transform, at 2^18 points` (on top of `fe3eca1`; no amend/reset/rebase).

### What changed

**Engine (`engine/geometry.py`)**
- `_MAX_COORDINATE_PT = 2 ** 18`, with the comment rewritten: fractional positions drift by up to half the float32 spacing; 0.0125pt measured from 2^19 on (0.3pt at 2^24); 2^18 keeps it at or below 0.005pt; the PDF spec's page limit is 14,400pt.
- Rule 4 now checks every value of `page.mediabox`, `page.cropbox` and `page.rect` plus MuPDF's transform `e`/`f`, exactly as in `cand5.py` (`ctm = page_transform(page)`; non-None there because rule 2 refuses a None layout).
- Message keeps "larger than"; it now prints 262144.
- Docstring: rule 4 rewritten (new bound, the reason, why page.rect and the transform translation count); new paragraph that `drawing_refusal` can raise `IndexError` (PyMuPDF `page.rect` on some infinite-bound pages) and `FzErrorFormat` (looping page tree), callers treat an exception as a refusal, operation-level handling tracked under C17.

**Helpers (`tests/geometry_helpers.py`)**
- `broken_xref(pdf_bytes)` copied from `cand5.py` (startxref -> 999999, so MuPDF repairs on open).
- `standard` and `with_text` gain `parent="2 0 R"`, so B2 and dangling-parent no longer need hand-built `build([...])` copies.

**Tests (`tests/test_geometry.py`)**
- Test B table rows are now `(id, _Spec(page_extra, pages_extra, extra_objects, parent, repaired), expected)`. `_Spec.standard()` builds the Test B page, `_Spec.with_text()` the redaction page. `_REDACTION_ALLOWED_ROWS` is derived from the table (every `-`/`over` row), so the two cannot drift apart; the id-sync guard test `test_every_other_allowed_table_row_has_a_redaction_placement_case` is removed as unnecessary (brief: "keep ... or make it unnecessary"). `_adversarial_b2` / `_adversarial_dangling_parent` removed; `build` no longer imported.
- New/changed rows: `media-inf-repaired` (huge), `media-inf-repaired-rot90` (huge), `media-inf-inherited-repaired` (huge), `media-inf-crop-letter` (`-`, repaired; gets a redaction-placement row automatically), `media-sym-2^24` (huge), `media-2^20` (huge), `rot135-unit-1` (`-`; also gets a redaction row), `media-huge-1e7` `-` -> huge (so it leaves the redaction list).
- Redaction placement test: tolerance `<= 0.5` -> `<= 0.01`; fills filtered by `drawing["fill"] == (0, 1, 0)`.
- New `test_a_fractional_position_reads_back_within_tolerance_on_every_allowed_page[261500|1048576]` (see deviation below).
- 0 skips.

### Deviation from the brief: the fractional-test page

The brief's page `[262000 0 262612 792]` is NOT allowed under the new rule: its MediaBox x1 = 262612 > 262144, so rule 4 refuses it. Measured before writing the test (current engine at the time, PyMuPDF 1.28.2):

| MediaBox | point (page space) | origin read back | drift | 
|---|---|---|---|
| `[262000 0 262612 792]` | (100.3, 140.7) | (100.2969, 140.7) | 0.0031 |
| `[262000 0 262612 792]` | (262100.3, 140.7) (off-page; the literal brief point) | (262100.3125, 140.7) | 0.0125 |
| `[261500 0 262112 792]` | (100.3, 140.7) | (100.2969, 140.7) | 0.0031 |
| `[261500 0 262112 792]` | (511.7, 140.7) | (511.7031, 140.7) | 0.0031 |
| `[1048576 0 1049188 792]` | (100.3, 140.7) | (100.25, 140.7) | 0.05 |
| `[1048000 0 1048612 792]` | (100.3, 140.7) | (100.3125, 140.7) | 0.0125 |

So the test uses offset **261500** (`[261500 0 262112 792]`, every value within 2^18, far edge 262112) and draws at page (511.7, 140.7) = PDF x 262011.7: allowed for both kinds, drift 0.0031pt (asserted <= 0.01). The 2^20 case is `[1048576 0 1049188 792]` at the same point: drift 0.05pt (asserted > 0.01) and refused "larger than" for both kinds. Note the brief's point (262100.3, 140.7) is a page-space coordinate far off a 612pt page; I read its intent as PDF x ~= 262100 and used the page-space point that lands there.

### Red run (new tests against the 84fc253 engine; `git diff --quiet 84fc253 -- engine/` confirmed the engine was unchanged)

`./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -q --tb=line`:

```
E   AssertionError: media-huge-1e7: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-huge-1e7: expected a 'huge' refusal, got None
E   AssertionError: media-2^20: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-2^20: expected a 'huge' refusal, got None
E   AssertionError: media-sym-2^24: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-sym-2^24: expected a 'huge' refusal, got None
E   AssertionError: media-inf-repaired: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-inf-repaired: expected a 'huge' refusal, got None
E   AssertionError: media-inf-repaired-rot90: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-inf-repaired-rot90: expected a 'huge' refusal, got None
E   AssertionError: media-inf-inherited-repaired: expected a 'huge' refusal, got None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:594: AssertionError: media-inf-inherited-repaired: expected a 'huge' refusal, got None
E   AssertionError: None
D:\Coding\8848 Lab\pdf-ai\tests\test_geometry.py:707: AssertionError: None
7 failed, 125 passed in 11.05s
```

That is: `media-huge-1e7`, `media-2^20`, `media-sym-2^24`, `media-inf-repaired`, `media-inf-repaired-rot90`, `media-inf-inherited-repaired` and the fractional `[1048576]` case fail, as the brief requires. Everything else passed on the old engine, including the new redaction rows for `media-inf-crop-letter` and `rot135-unit-1`, the tightened 0.01 tolerance and green-fill filter on all 27 redaction rows (26 before, minus media-huge-1e7, plus the two new ones), `rot135-unit-1` and `media-inf-crop-letter` Test B rows (both correctly allowed), and the fractional `[261500]` case.

After the engine change: `tests/test_geometry.py` 132 passed.

### Mutations (each on the working copy after backing it up to the scratchpad, restored with `cp` and verified with `cmp` afterwards; full `tests/`)

1. Drop `page.rect` and ctm e/f (`values = [v for box in (page.mediabox, page.cropbox) for v in box]`):
```
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-inf-repaired]
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-inf-repaired-rot90]
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-inf-inherited-repaired]
3 failed, 356 passed in 13.69s
```
   `media-sym-2^24` is NOT caught by this mutation: its MediaBox x0 = -16777216 is already past 2^18, so at the new bound the box check alone refuses it. It is load-bearing only against mutation-2-style bound changes (see below).

2. Restore the bound to 2^24:
```
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-huge-1e7]
FAILED tests/test_geometry.py::test_the_adversarial_table_agrees_with_pymupdfs_own_drawing[media-2^20]
FAILED tests/test_geometry.py::test_a_fractional_position_reads_back_within_tolerance_on_every_allowed_page[1048576]
3 failed, 356 passed in 13.13s
```
   `media-sym-2^24` passes under this mutation because `page.rect` (width 2^25) is still in the check and exceeds 2^24 -- i.e. that row pins the page.rect/transform extension at the old bound; the 2^18 bound itself is pinned by `media-huge-1e7`, `media-2^20` and the fractional 2^20 case.

### Full suite (`./.venv/Scripts/python.exe -m pytest tests/`)

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\Coding\8848 Lab\pdf-ai
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 359 items

tests\test_ai.py ...........................                             [  7%]
tests\test_ai_provider_ollama.py ............                            [ 10%]
tests\test_ai_provider_openai_compatible.py ............                 [ 14%]
tests\test_document.py ......                                            [ 15%]
tests\test_export.py .......                                             [ 17%]
tests\test_fixtures_exist.py ...                                         [ 18%]
tests\test_geometry.py ................................................. [ 32%]
........................................................................ [ 52%]
...........                                                              [ 55%]
tests\test_operations.py ............................................... [ 68%]
...................................                                      [ 78%]
tests\test_parser.py ...............                                     [ 82%]
tests\test_visual_regression.py ..........                               [ 85%]
tests\test_webui.py .................................................... [ 99%]
.                                                                        [100%]

============================ 359 passed in 13.57s =============================
exit status: 0
```

### Concerns

- The brief's fractional page `[262000 0 262612 792]` is refused by the rule the brief itself specifies; the test uses `[261500 0 262112 792]` instead (details above).
- `drawing_refusal` can still raise (`IndexError`, `FzErrorFormat`); documented only, operation-level handling is C17 for the final review.
- `media-inf-*-repaired` rows depend on MuPDF's warning buffer being non-empty after the repair; they are deterministic because the repair happens on every open of these bytes, but the bare infinite-MediaBox page (no repair) still raises `IndexError` from `page.rect` and is not a table row.
