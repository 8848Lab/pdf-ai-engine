# Task 2 — fix round 5 brief (ruling C18: bound the page's real extent at 2^18)

**Read first:** `task-2-rereview-3.md` in this directory. The review verified that rounds 3 and 4 close everything from review 2. It found two Important problems with the magnitude rule (rule 4 of `drawing_refusal` in `engine/geometry.py`) and two test Minors.

- **NB1 — infinite MediaBox.** With `/MediaBox [-2147483648 -2147483648 2147483520 2147483520]` (MuPDF's infinite rect) and a repaired xref, `page.mediabox`, `page.cropbox` and `page.rect` all fall back to letter size. MuPDF's transform, however, carries e/f = 2^31. Every rule passes, yet nothing drawn can be read back. Fix: the magnitude rule must also check `page.rect`'s values and the transform's `e` and `f`.
- **NB2 — the threshold.** 2^24 was measured with integer positions only. Fractional positions round to half the float32 spacing: 0.0125pt at 2^19, and 0.3pt at 2^24. Fix: the bound becomes **2^18** (262,144pt ≈ 92m, well past the PDF spec's 14,400pt page limit). The worst allowed drift is then 0.005pt, under the gate's 0.01pt tolerance.
- **Coordinator verification:** `scratchpad/fable-t2/cand5.py` (path `C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t2/`), re-run by the coordinator:
  - 223 rows, 0 bypasses;
  - the only verdict changes are rows at 2^20 and above, which become "huge", and the infinite-MediaBox attacks, which become "huge";
  - `inf+broken-xref+crop-letter` stays allowed and draws exactly.

## 1. Engine (`engine/geometry.py`)

1. Set `_MAX_COORDINATE_PT = 2 ** 18`. Rewrite its comment: fractional positions drift by up to half the float32 spacing; 0.0125pt was measured at 2^19; 2^18 keeps it at or below 0.005pt; the PDF spec's page limit is 14,400pt.
2. Rule 4 checks every value of `page.mediabox`, `page.cropbox` and `page.rect`, plus the transform's `e` and `f`. Use `page_transform(page)`, which is non-None by this point because rule 2 refuses None. Exactly as in cand5:

   ```python
   ctm = page_transform(page)
   values = [v for box in (page.mediabox, page.cropbox, page.rect) for v in box] + [ctm.e, ctm.f]
   if any(abs(v) > _MAX_COORDINATE_PT for v in values):
   ```

3. Keep the message's phrase "larger than". It already prints the constant, so it now says 262144.
4. Add to `drawing_refusal`'s docstring that it can raise:
   - `IndexError` from PyMuPDF's `page.rect` on some infinite-bound pages;
   - `FzErrorFormat` on a looping page tree.

   Callers treat an exception as a refusal. The operation-level handling is tracked for the final review (ruling C17).

## 2. Tests (`tests/test_geometry.py`)

Test B rows. Copy the row builders from the reviewer's scripts: `round4.py` `NEW4` and `cand5.py` `ATTACK`, which includes the `broken_xref` helper — add that to `tests/geometry_helpers.py`.

| id | expected |
|---|---|
| media-inf-repaired (`inf+broken-xref`) | huge |
| media-inf-repaired-rot90 | huge |
| media-inf-inherited-repaired | huge |
| media-inf-crop-letter (`inf+broken-xref+crop-letter`) | - (and add its redaction-placement row) |
| media-sym-2^24 (`[-16777216 0 16777216 792]`) | huge |
| media-2^20 | huge |
| rot135-unit-1 (`/Rotate 135 /UserUnit -1`) | - (the 180 snap and the mirror cancel; pins that this is correct) |
| media-huge-1e7 | change `-` to huge |

**New test: fractional-position drift.**
- On an allowed page whose MediaBox is offset to just under the bound, `[262000 0 262612 792]`, draw text at a fractional position such as (262100.3, 140.7).
- Re-open the page and assert the origin comes back within 0.01pt.
- Assert the same page with the offset at 2^20 is refused as "larger than".
- Measure both before writing the assertions, and put the measured drift in a comment.

**Minors:**
- **Placement test** (`:689`): tighten `offset <= 0.5` to `<= 0.01`, and filter fills by the green colour the test passes in.
- **Placement table** (`:596-646`): stop hand-copying row parameters. Share one source of `(page_extra, pages_extra, extra_objects)` with Test B, so the two tables cannot drift apart. Keep the id-sync guard or make it unnecessary.

Keep 0 skips.

## 3. Red first, then mutations

- **Red:** run the new rows and the fractional test against 84fc253 before changing the engine. `media-inf-repaired*`, `media-sym-2^24`, `media-2^20` and the 2^20 fractional case must fail. Record the results.
- **Mutations,** each on a copy, restored afterwards. Record the failing test ids for each:
  1. Drop `page.rect` and ctm e/f from the check.
  2. Restore the bound to 2^24.

## 4. Report and commit

- Append a "Fix round 5" section to `task-2-report.md` with the red run, the mutations, and the full `tests/` output with its exit status.
- Commit on top of HEAD; no amend, reset or rebase. Message:

  `fix: bound the page's real extent, including MuPDF's transform, at 2^18 points`

  plus these attribution lines:

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka
  ```
