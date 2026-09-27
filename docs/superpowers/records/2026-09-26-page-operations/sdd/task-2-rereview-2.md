# Task 2 — security re-review 2 (fix round 2, 52de01c..b08c848)

Reviewer: Fable. Read-only on the checkout. Scratch scripts: `scratchpad/fable-t2/round3a.py` (39-row table, 88 new rows, 1,024-case matrix), `round3b.py` (MuPDF ctm per rotation; redaction placement through `at_rotation_zero`), `cand2.py` (a verified repair candidate). Focused run: `tests/test_geometry.py` 95 passed, 25 skipped in 10.72 s; Test A measured 2.30 s.

### Finding Verdicts

**I1 (indirect numbers bypassed the gate) — ADDRESSED.** No raw key is read any more: `engine/geometry.py:121-139` measures the scale from `page.rect` against `visible_area` (`:95-106`). Rows `unit-indirect` (refused "uses PDF /UserUnit", probe drifts to (200, 280)) and `unit-chain16` (allowed, probe (100, 140), no drift) agree with drawing.

**M1 (chained, null, dangling references) — ADDRESSED.** `J2` allowed with no drift; `J-null` refused "lays out inconsistently" with the probe at (60, 240); `dangling` and `dangling-parent` allowed, no exception, no drift; my `crop-cycle-ref`, `unit-cycle-ref`, `rot-cycle-ref` (two-object reference cycles) allowed, no drift.

**M2 (malformed box arrays read as absent) — ADDRESSED.** `G1`, `H1`, `H2`, `I1`, `I3`, `B2` refused "CropBox", probe (60, 112); `N3` refused "CropBox", probe (60, 140); `I5` refused "inconsistently", probe (60, 932). My additional `crop-5-entries-first-4-over`, `crop-ref-elements`, `crop-nan`, `crop-exp`, `crop-ref-to-ref-array`, `media-inherit-crop-ref`: all refused "CropBox" and all drift.

**Round-1 new breakage 1 (null or cycle continuing the inheritance walk) — ADDRESSED.** There is no walk (`_inherited` deleted, diff lines 126-154). `J-null`/`J2` above; a page whose `/Parent` is itself (`parent-self-crop`, `parent-self-nocrop`) is refused "CropBox" while PyMuPDF drifts to (60, 112).

**Round-1 new breakage 2 (malformed arrays as absent) — ADDRESSED.** Same evidence as M2.

**Round-1 Minor (`_resolve` docstring) — ADDRESSED** by deleting `_resolve`.

**Out-of-scope items from round 1:**
- int32-truncated `/UserUnit` — ADDRESSED. `unit-2^32+1`: `user_unit` = 4294967296, refused "uses PDF /UserUnit", probe (4.29e11, 6.01e11).
- `/Rotate 2700000000.0` — ADDRESSED. Refused "invalid rotation", probe (652, 100). Also `2147483648`, `2147483648.0`, `-2147483648` refused; `9223372036854775808` allowed and does not drift.
- Dangling references raising — ADDRESSED (rows above, no exception).
- "(1)" message for `/UserUnit 1.0000001` — ADDRESSED for the named page (now allowed, no message) but the formatting survives: `/UserUnit 1.0000001` on `/MediaBox [0 0 100000 100000]` is refused with "scaling (1)" (`engine/geometry.py:206`, `{unit:g}`). Minor, open (New Breakage 6).

**Coordinator note (a) — delete `test_the_adversarial_table_categories_apply_to_other_drawing_too` (`tests/test_geometry.py:518-529`).** Test B already asserts, for every non-`over` row, `reason_other is not None and phrase in reason_other` (`:508`), which is strictly stronger than the second test's `reason_other is not None` (`:529`), and for `over` rows `reason_other is None` (`:505`); the `-` branch asserts `reason_other is None` (`:497`). The second test adds no assertion Test B lacks and skips 25 of 39 rows (`:525`), so every suite summary reads "25 skipped" for nothing. The brief's "also check TEXT_DRAWING vs OTHER_DRAWING" is met by Test B alone.

**Coordinator note (b) — `raw_object_page` (`tests/geometry_helpers.py:170-205`) is dead.** `grep -rn raw_object_page tests/ engine/` finds no caller (only a stale `.pyc`); `build`/`standard` (`:134-167`) supersede it. Remove it.

### Adversarial Attempts

All rows are raw-byte PDFs (`standard`/`build`, `/Root 1 0 R`). Text probe: `drift_probe` (insert at (100, 140), re-open, read the origin). Redaction probe (`round3b.py`): VISIBLE drawn by a raw content stream, bbox from `get_text` at the page's own rotation, then inside `at_rotation_zero`: `add_redact_annot(bbox, fill)` + `apply_redactions(images=2, graphics=1, text=0)`, re-open, `get_drawings` fill vs bbox. L = `/MediaBox [0 0 612 792]`.

| PDF | PyMuPDF behaviour | Gate (text / other) | Pass? |
|---|---|---|---|
| The 39-row table, every row | as the brief's table: every `-` row has no drift, every drifting row is refused | matches the table on all 39 (categories and probe) | pass |
| 1,024-case matrix, units 0.5/1/1.5/2 | 0 gate/probe mismatches; `transformation_matrix` has b = c = 0 and a > 0, d < 0 in all 1,024 — but in all 768 rotated cases it is the constant `(1, 0, 0, -1, 0, cropbox.height)`, not MuPDF's ctm | agrees | pass (with the caveat that the check is vacuous at 90/180/270) |
| L `/UserUnit -1 /Rotate 90` | rotation 90, rect 792x612, `transformation_matrix` (1,0,0,-1,0,792); MuPDF ctm (0,-1,-1,0,792,612); probe lands at (512, 652); redaction fill 45.36 pt from the bbox | None / None | **FAIL — bypass, both kinds** |
| L `/UserUnit -1 /Rotate 180` | MuPDF ctm (1,0,0,-1) — laid out as an unrotated page while PyMuPDF derotates by 180; probe (512, 652); fill off 45.36 | None / None | **FAIL — bypass** |
| L `/UserUnit -1 /Rotate 270`, `/Rotate -90`, `/Rotate 450` | probe (512, 652); fill off 45.36 | None / None | **FAIL — bypass** |
| `/MediaBox [0 0 600 600] /UserUnit -1 /Rotate 90` | probe (500, 460) | None / None | **FAIL — bypass** |
| L `/CropBox [50 50 500 700] /UserUnit -1 /Rotate 90` and `/Rotate 180` | probe (350, 510); fill off 45.36 | None / None | **FAIL — bypass** |
| L `/UserUnit 4 0 R /Rotate 90`, obj 4 = `-1` | probe (512, 652) | None / None | **FAIL — bypass** |
| L `/UserUnit -1.0000001 /Rotate 90` | probe (512.00006, 652.00006) | None / None | **FAIL — bypass** |
| L `/UserUnit -2 /Rotate 90` | rect 1584x1224, probe (1024, 1304) | unit / unit | pass (|scale| is 2) |
| L `/CropBox [100 100 100.5 100.5] /UserUnit 0.5` | MuPDF swaps the sub-point box for the unit rect: rect (0,0,0.5,0.5); `page.cropbox` keeps (100, 691.5, 100.5, 692); scale measures 1; probe (100, 20.25); redaction fill off 11.34 pt | None / None | **FAIL — bypass, both kinds** |
| L `/CropBox [100 100 100.5 100.5]` | same fallback; rect (0,0,1,1); measured scale 2 | "uses PDF /UserUnit scaling (2)" | refused by coincidence, wrong message |
| L `/CropBox [100 100 100.5 300]`; `/CropBox [-1 100 0.5 101]` | probe (200, -159); (99, 40) | incons / incons | pass |
| `/MediaBox [0 0 0.5 0.5]`; `[0 0 1 1]`; L `/CropBox [100 100 101 101]` | unit-rect fallback on both sides; no drift | None / None | pass |
| `/MediaBox [0 0 0.5 0.5] /CropBox [-40 -60 660 820]` | probe (60, -679); redaction fill exact | over / None | pass |
| L `/Rotate 135`, `224`, `134.9`, inherited `135`, square `135` | MuPDF snaps to 180: ctm (-1,0,0,1), b = c = 0; PyMuPDF rotation 0; probe (512, 652) | incons / incons | refused, but by the mirror check with the "malformed CropBox, MediaBox or /UserUnit" message; `rotation_is_valid` says True |
| L `/Rotate 225`, `-135` | snapped to 270; probe (140, 512) | rot / rot | pass |
| L `/Rotate 315`, `30`, `-45`, `90.4`, `89.6` | snapped to 0/90 like PyMuPDF; no drift | None / None | pass |
| `/MediaBox [0 0 1000000000 1000000000]` | float32: probe lands at (100, 128), 12 pt off; `get_text` cannot find VISIBLE at all | None / None | **FAIL — text misplaced, gate allows** (magnitude, not geometry; see Out-of-Scope) |
| `/MediaBox [0 0 10000000 10000000]`; `[0 0 14400 14400]`; `[1000000 1000000 1000612 1000792]` | no drift at (100, 140); redaction fill exact | None / None | pass |
| `[1000000 …] /CropBox [999990 …]` | probe (90, 140) | over / None | pass |
| L `/CropBox [-4294967336 -60 660 820]`; `[-9999…(38 digits) -60 660 820]` | `page.cropbox.x0` = -4.29e9 / -6.87e17; probe returns None (text unfindable); redaction fill exact (off 3e-5) | over / None | pass |
| `/MediaBox [0 0 nan 792]`, `[0 0 inf 792]`, L `/UserUnit nan`, `/UserUnit true`, `/Rotate (90)`, `/90`, `true`, `[90]`, L `/CropBox << /A 1 >>`, `(abc)` | MuPDF reads the token as 0 / drops the key; no drift | None / None | pass |
| L `/UserUnit 1e-30`, `0.0000000001`, `10000000000` | rect 0x0 or 6e12; probe None / (1e-8, 1.4e-8) / (1e12, 1.4e12) | unit / unit / incons | pass |
| L `/UserUnit 1.00001`, `1.000012`, `0.99999` | drift 0.001-0.0016 pt | None | pass (below tolerance) |
| L `/UserUnit 1.0001` | drift 0.01-0.014 | unit | pass |
| `/MediaBox [0 0 100000 100000] /UserUnit 1.0000001` | drift 1.5e-5 | "uses PDF /UserUnit scaling (1)" | refused (safe), message wrong |
| L `/UserUnit 2 /CropBox [0 0 306 396]`, `[0 396 306 792]`; `/UserUnit 0.5 /CropBox [-306 -396 918 1188]` | rect coincides with 612x792; probe (200, 280) / (-103, -128) | unit / unit | pass (scale measured against the visible area, not the MediaBox) |
| `/MediaBox [612 792 0 0] /Rotate 90`; `[612 792 0 0] /CropBox [612 792 -40 -60] /Rotate 270`; L `/CropBox [612 -60 -40 792] /Rotate 90`; L `/CropBox [612 830 0 0] /Rotate 180`; `/MediaBox [612 0 0 792] /CropBox [-40 0 612 792]` | `pdf_to_rect` normalises; no drift / (60,140) / (60,140) / (100,102) / (60,140); redaction fill exact | None / over / over / over / over | pass |
| L `/UserUnit 2 /CropBox [-40 -60 660 820]` | probe (120, 224) | unit / unit | pass |
| Page dict without `/Type`; Pages node whose `/Parent` is itself plus page `/Parent 2 0 R` (kids-loop) | first: refused "CropBox", drifts; second: PyMuPDF raises `FzErrorFormat: cycle in resources` on `doc[0]`, before the gate | over / None; n/a | pass (callers must expect a page-load exception) |
| Redaction placement on every row above that allows OTHER_DRAWING (plain, 90/180/270, all overhang shapes, negative-origin MediaBox, G1, I1, I3, N3, crop-inverted, media-zero, crop-empty, dangling, 1e30, 1.0000001, 1.00001, rot315, 89.6, swapped boxes, self-parent) | VISIBLE removed and the fill within 5e-4 pt of its bbox | None | pass |
| Redaction placement on the mirrored-rotated rows and `crop-tiny-unit0.5` | fill 45.36 pt / 11.34 pt from the bbox | None | **FAIL** (same two bypasses) |

### New Breakage in the Fix Diff

1. **Important (security)** — `engine/geometry.py:117-118` (`rotation_is_valid`) and `:196-197` (mirror check) read `page.transformation_matrix`. PyMuPDF only returns MuPDF's page ctm from that property when `page.rotation == 0`; at 90/180/270 it returns the constant `Matrix(1, 0, 0, -1, 0, self.cropbox.height)` (`.venv/Lib/site-packages/pymupdf/__init__.py:13311-13314`), so on every rotated page both checks are satisfied by construction, and `user_unit` (`:136-139`) sees only |scale|. The brief's premise "those values ARE MuPDF's interpretation" is false for this one property. Result: `/UserUnit -1` with any valid non-zero `/Rotate` (direct, indirect, un-normalised, with or without a CropBox) passes all four rules for TEXT and OTHER; text lands at (512, 652) and a redaction fill lands 45 pt from the text it was meant to cover. Round-1 code refused these (`unit != 1`), so this is a regression introduced by C15.
   Verified repair (`cand2.py`: 0 mismatches on the 1,024 matrix, all 39 table rows agree, every mirrored row above refused): read MuPDF's ctm directly with `mupdf.pdf_page_transform(page._pdf_page(), mupdf.FzRect(mupdf.FzRect.Fixed_UNIT), ctm)` (the very call `transformation_matrix` makes and then discards) and require its linear part to be PyMuPDF's reported rotation at one positive scale u: rotation 0 `(u,0,0,-u)`, 90 `(0,u,u,0)`, 180 `(-u,0,0,u)`, 270 `(0,-u,-u,0)`; anything else is refused. This subsumes `rotation_is_valid` (off-diagonal at rotation 0), the mirror check, `/UserUnit 0` (u <= 0) and gives u without division; keep the rect-vs-visible-area cross-check.

2. **Important (security)** — `engine/geometry.py:95-106` with `:130-135`: MuPDF replaces a laid-out box whose width or height is < 1 pt with the unit rect at the PDF origin (`pdf_page_obj_transform_box`), and PyMuPDF's `page.mediabox` mirrors that (`JM_mediabox`, `pymupdf/__init__.py:21027-21030`) but `page.cropbox` does not (`JM_cropbox`, `:19409-19427`, only the empty/infinite fallback to the MediaBox). `visible_area` therefore reports the sub-point box while MuPDF drew a 1x1 page at (0, 0). `L /CropBox [100 100 100.5 100.5] /UserUnit 0.5` measures scale 0.5/0.5 = 1 and is allowed for both kinds; the probe lands at (100, 20.25) and the redaction fill is 11.34 pt off. Repair (verified in `cand2.py`): in `user_unit`, return None when the (swapped) visible width or height is < 1.

3. **Minor** — `engine/geometry.py:109-118` docstring: "no valid rotation produces off-diagonal terms" is true, but the converse claim that every malformed `/Rotate` produces them is false: MuPDF snaps 135 <= r < 225 to 180, whose ctm `(-1,0,0,1)` has b = c = 0. Those pages are refused only by the mirror check, with the message "malformed CropBox, MediaBox or /UserUnit" (`:199-202`), naming the wrong cause; the report's mutation-4 note saw this and did not flag it. Since MuPDF's ctm for `/UserUnit -1` and `/Rotate 135` is identical, the "inconsistent" message should name `/Rotate` too, and the docstring should say a 180-snap is caught by the sign check.

4. **Minor** — `tests/test_geometry.py:338`: `assert "overhangs" in result or "error" in result` cannot fail once `not thread.is_alive()` passed, because `run()` (`:327-332`) always stores one of the two keys. PyMuPDF does not raise on this page (my `parent-self-nocrop` row returns a normal answer), so pin `result.get("overhangs") is False` and drop the accept-anything branch.

5. **Minor** — `tests/test_geometry.py:518-529` duplicate OTHER_DRAWING test with 25 skips (note a) and `tests/geometry_helpers.py:170-205` dead `raw_object_page` (note b): remove both.

6. **Minor** — `engine/geometry.py:206` `{unit:g}` prints "1" for any scale within 5e-7 of 1; a 100,000 pt page at `/UserUnit 1.0000001` is refused as "scaling (1)". Print with enough digits (`{unit:.7g}`) or say "scaled by a factor other than 1".

### Out-of-Scope Observations

- **Coordinate magnitude.** MuPDF stores geometry as float32. `/MediaBox [0 0 1000000000 1000000000]`: the probe lands at (100, 128), 12 pt off, and `get_text` cannot find VISIBLE for redaction at all; the gate allows both kinds. Measured onset: sides up to 20,000,000.3 pt show no drift at (100, 140) (the write and the read round to the same float32 grid), 100,000,000.3 drifts 4 pt, 1e9 drifts 12 pt. The gate has no magnitude bound; a rule "refuse when any coordinate of `page.rect`, `page.mediabox` or `page.cropbox` exceeds 2^24 (16,777,216 pt) in magnitude" would close it with a wide margin (the PDF spec's page limit is 14,400 units). The int64-sized CropBox rows (`x0` = -4.29e9, -6.87e17) are refused for text and their redaction fill is exact, so they are not a bypass today.
- `kids-loop` (a Pages node that is its own parent): PyMuPDF raises `FzErrorFormat: cycle in resources` on page access, before any gate. Operation callers need a page-load exception path.
- The report notes the mirror check "does double duty" as the `/UserUnit 0` guard for `:204`'s division; with repair 1 the guard is explicit (u <= 0).
- Test A runtime: 2.30 s here (report 2.19-2.31 s). Slowest tests in the file are the two pre-existing 1,024-case tests (3.3-3.5 s each).
- The 39-row table's rows `crop-inverted` and `media-swapped-*` show `pdf_to_rect` normalises corners before anything else, so "swapped corners" collapse onto ordinary rows; no separate rule needed.

### Verdict

**NOT PASSED — fix round 3 required.** Every round-1 item is closed (I1, M1, M2, both Important breakage items, the Minor docstring, int32 `/UserUnit`, `/Rotate` overflow, dangling references), the 39-row table and the 1,024-case matrix agree with drawing, and redaction placement is exact on every well-formed or overhang page the gate allows. But C15's premise fails for one property: `page.transformation_matrix` is a constant on rotated pages, so the new rotation and mirror checks are vacuous at 90/180/270 and a mirrored rotated page (`/UserUnit -1 /Rotate 90|180|270`) is allowed for both kinds while text and the redaction fill are misplaced — a regression against round 1. A second, independent bypass comes from MuPDF's sub-point-box fallback that `page.cropbox` does not mirror. Both repairs are small and verified in `cand2.py`. Required for round 3: (1) read MuPDF's ctm via `pdf_page_transform` and require the rotation-specific linear part at a positive scale; (2) refuse a visible width or height < 1 pt; (3) add rows `unit-1-rot90`, `unit-1-rot180`, `unit-1-rot270`, `unit-1-rot180-crop`, `unit-1-indirect-rot90`, `crop-tiny-unit0.5`, `crop-tiny`, `rot135`, `rot-inherited-135` to Test B and prove them red first; (4) add a redaction-placement assertion (bbox at the page's rotation, redact inside `at_rotation_zero`, fill within 0.5 pt) for every Test B row that allows OTHER_DRAWING; (5) close the Minors 3-6 and the coordinator's notes (a) and (b); (6) a ruling on the coordinate-magnitude bound.
