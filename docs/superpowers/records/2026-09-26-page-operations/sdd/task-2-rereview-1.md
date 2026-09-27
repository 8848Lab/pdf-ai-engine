### Finding Verdicts

**I1 (Important) — NOT ADDRESSED (the named repro is fixed; the binding principle is still violated, and the fix introduces a new bypass of the same class).**
- Fixed as described: `engine/geometry.py:79-92` (`_classify`) and `:95-120` (`_resolve` loop with `seen`). An indirect `/UserUnit 2` now reads 2.0 and is refused; an indirect `/Rotate 45` on the page or on `/Pages` is refused. Tests `tests/test_geometry.py:302-330` check `page.rect`/`page.rotation` as required. RED confirmed independently against a scratch copy of 1f3500a: `user_unit` returned 1.0 for indirect 2 while `page.rect` was 1224x1584; `drawing_refusal` returned None for indirect 45.
- Still open against "the gate must agree with what PyMuPDF actually draws": `_resolve` maps a reference cycle (`:113`) and an indirect `null` (`:119`) to `("null", "null")`, which `_inherited` (`:141`) treats as "key absent" and walks on to the parent. PyMuPDF does not: `pdf_dict_get_inheritable` stops at the first node that HAS the key, whatever it resolves to. Verified by drawing (attempts J, J2, J3, J4 below): with page-level `/MediaBox` -> null object (or -> cycle), a parent `/MediaBox [-100 -100 512 692]` and `/CropBox [-40 0 612 692]`, PyMuPDF defaults the MediaBox to letter and the probe drifts to (60, 240); the gate inherits the parent's box and returns None for TEXT_DRAWING. That is a gate bypass created by this diff (pre-fix, the cycle/null read as `"other"` and the walk stopped, which matched PyMuPDF). The new test `tests/test_geometry.py:352-362` pins the wrong direction and does not verify PyMuPDF's drawing (my J2 shows no drift in exactly that scenario).
- Also unhandled in the new `_resolve`: a dangling reference (`/UserUnit 99 0 R`, `/Rotate 99 0 R`, `/CropBox 99 0 R`, `/MediaBox 99 0 R`) raises `RuntimeError: bad xref` from `doc.xref_object` (`:115`); `/Parent 99 0 R` raises `ValueError: bad xref` from `xref_get_key` (`:143`). PyMuPDF treats all of these as absent and draws unshifted. Pre-existing, but `drawing_refusal`'s contract is `str | None`, and the Task 7 caller will not know to catch two exception types.

**I2 (Important) — ADDRESSED.** `engine/geometry.py:135-139` adds the visited set and returns None on a repeat. RED confirmed against the pre-fix copy: an unguarded walk on a self-referencing `/Parent` was still alive after 3 s. Post-fix: self-cycle, a cycle through a bare reference object (B5), and a 3,000-node finite `/Parent` chain (K, 0.098 s) all terminate. Test `tests/test_geometry.py:406-426`.

**M1 — NOT ADDRESSED.** Chained indirection works (attempt A, depth 3: gate 2.0, PyMuPDF rect 1224x1584, refused). The indirect-null half was implemented in the direction opposite to PyMuPDF; see I1. Dangling references still raise.

**M2 — NOT ADDRESSED.** The crash is gone (`engine/geometry.py:167-173`; RED confirmed: pre-fix `fitz.Rect([0,0,612])` raised AssertionError), but the replacement policy "anything that isn't exactly four numbers is absent, matching PyMuPDF" (`:158-162`, test `:365-379`) is false and converts a fail-closed crash into a silent pass. MuPDF's `pdf_to_rect` reads the first four elements, resolves indirect elements, and reads a missing or non-numeric element as 0. It was "verified" only on `[0 0 612]`, whose zero-fill `(0,0,612,0)` happens not to drift. Verified bypasses (all: gate returns None for TEXT_DRAWING, PyMuPDF drifts): `CropBox [-40 -60 660]` -> drift (60, 932); `CropBox [-40 -60 660 /Foo]` -> (60, 932); `CropBox [-40 -60 660 820 0]` -> (60, 112); `CropBox [4 0 R -60 660 820]` with obj 4 = -40 -> (60, 112) (pre-fix this raised `ValueError` on `float("R")`, i.e. failed closed; now it passes); `MediaBox [0 0 612]`, `MediaBox [0 0 612 /Foo]`, `MediaBox [0 0 612 792 0]`, and MediaBox ABSENT, each with `CropBox [-40 -60 660 820]` -> (60, 112) because PyMuPDF substitutes the letter default while `crop_origin_overhangs` returns False the moment `_raw_box("MediaBox")` is None (`:222-224`). Required: emulate `pdf_to_rect` (first four, references resolved, non-numbers 0) and PyMuPDF's `JM_mediabox` letter fallback for an empty/invalid/absent MediaBox, then re-verify each case by drawing.

**M3 — ADDRESSED.** Tests `tests/test_geometry.py:382-394` check `page.rotation` / `page.rect`. My probes agree for `/UserUnit true`, `(2)`, `[2]`, `<< >>`, `1e0` (MuPDF drops the key) and `/Rotate 9e1`, `1e30`.

**M4 — ADDRESSED.** `tests/test_geometry.py:397-403`.

**M5 — ADDRESSED.** `engine/geometry.py:216-220` names bottom, right and negative-origin.

**A1 — ADDRESSED.** `tests/test_geometry.py:314-321` parametrised over `where` and asserts the page-level key is null. My B1/L1 (ancestor reached through a bare reference object, `/Rotate` via a two-hop chain) are also refused, and PyMuPDF's probe drifts on them.

**A2 — ADDRESSED.** `tests/geometry_helpers.py:82-108` nulls every inheritable key written on the parent; the inherited-MediaBox test (`tests/test_geometry.py:156-167`) uses `[100 100 712 892]` with `CropBox [50 150 600 700]`, which flips to False against the letter default; local-override (`:170-181`) and grandparent (`:184-202`, cross-checked against `page.mediabox`) cases added.

### Adversarial Attempts

Scripts: `.../scratchpad/fable-t2/adversarial.py`, `round2.py`, `red_check.py`. Every PDF is raw bytes; "drift" = `insert_text((100,140))` read back with clipping disabled. PASS = gate agrees with PyMuPDF or refuses conservatively; FAIL = PyMuPDF misdraws and the gate allows.

| # | PDF | PyMuPDF | Gate | Result |
|---|-----|---------|------|--------|
| A | `/UserUnit` chain depth 3 | rect 1224x1584, drift (200,280) | 2.0, refused | PASS |
| A | chain depth 16/50/200/5000 | MuPDF stops resolving somewhere between 8 and 16 hops: rect unscaled, no drift | follows to the end: 2.0, refused | PASS (conservative false refusal; 5000 hops 0.019 s, no hang) |
| B1 | `/Parent 4 0 R`, obj 4 = `2 0 R`, `/Pages` has `/Rotate 45` | rotation 0, rect swapped, drift (652,100) | 45, refused | PASS |
| B2 | same, `/Pages` has `/CropBox [-40 -60 660 820]` | drift (60,112) | overhang True, text refused | PASS |
| B3 | `/Parent` -> int object | fine | 0 / 1.0 / None | PASS |
| B4 | `/Parent 99 0 R` (dangling) | fine, no drift | `ValueError: bad xref` from both refusals | FAIL-CLOSED by exception (contract broken) |
| B5 | `/Parent` -> obj 4 = `3 0 R` (cycle back to the page through a reference object) | fine | terminates, None | PASS |
| B6 | two `/Pages` nodes in a `/Parent` cycle | PyMuPDF itself raises "cycle in resources" on `load_page` | never reached | n/a |
| C | `/UserUnit`, `/Rotate`, `/MediaBox`, `/CropBox` -> `99 0 R` | all treated as absent, no drift | `RuntimeError: bad xref` | FAIL-CLOSED by exception |
| C2 | `/UserUnit` -> explicit null object | unscaled | 1.0 | PASS |
| D | `/Rotate 4294967386` (2^32+90), `9223372036854775898` | rotation 90 (int32 truncation) | key prints 90 -> allowed | PASS |
| D | `/Rotate 257698037790`, `2147483738`, 23-digit int | printed value not a multiple of 90; MuPDF snaps to 0, no drift | refused | PASS (conservative) |
| D | `/Rotate 4294967341` (2^32+45) | rotation 0, swapped, drift | printed 45, refused | PASS |
| **D** | **`/Rotate 2700000000.0`** (real, multiple of 90, > INT_MAX) | `pdf_to_int` overflows: rotation 0, rect swapped, drift (652,100) -- the malformed state | 2.7e9 % 90 == 0 -> **allowed** | **FAIL (bypass)** |
| D | `/Rotate 4294967040.0` | same malformed state | float32 rounds to 4294967000 -> refused | PASS by luck |
| D | `/Rotate 90.5`, `90.0`, `89.99999999999999999`, `90.00000001`, `-0`, `+90`, `9e1`, `1e30` | as expected | agrees or refuses conservatively | PASS |
| E | `/UserUnit 1.0000001` | rect 612.00006 | refused (message prints "(1)") | PASS |
| E | `1.00000001`, `1.0`, `1.`, `1`, `true`, `(2)`, `[2]`, `<< >>`, `1e0` | unscaled | 1.0 | PASS |
| E | `0`, `-1`, `0.5`, 23-digit int | degenerate / drifting | refused | PASS |
| **E/M** | **`/UserUnit 4294967297`** (2^32+1), `8589934593`, `-4294967295` | `page.rect` = 612 x 4294967297 (int64 via `pdf_to_real`), probe at (4.29e11, 6.01e11) | `xref_get_key` prints the int32-truncated `('int', '1')` -> 1.0 -> **allowed** | **FAIL (bypass)** |
| M2 | `/UserUnit` -> obj 4 = `4294967297` | same scaling | `xref_object` prints the full int64 -> refused | PASS (direct and indirect paths disagree) |
| **G1** | **`/CropBox [4 0 R -60 660 820]`**, obj 4 = -40 | drift (60,112) | `float("R")` -> None -> **allowed** (pre-fix: raised, i.e. closed) | **FAIL (new bypass)** |
| G2/N3 | `/MediaBox [4 0 R 0 612 792]` obj 4 = -100 / 0, `/CropBox [-40 0 612 792]` | no drift / drift (60,140) | None -> allowed | PASS by luck / **FAIL** |
| **H1** | **`/CropBox [-40 -60 660 820 0]`** (5 entries) | first four used, drift (60,112) | None -> **allowed** | **FAIL (new bypass)** |
| **H2** | **`/MediaBox [0 0 612 792 0]`** + overhanging CropBox | drift (60,112) | media None -> False -> **allowed** | **FAIL (new bypass)** |
| **I1/I2** | **`/MediaBox [0 0 612]`** or **`[0 0 612 /Foo]`** + `/CropBox [-40 -60 660 820]` | letter default, drift (60,112) | media None -> **allowed** (pre-fix: raised) | **FAIL (new bypass)** |
| **I3** | **no `/MediaBox` at all** + `/CropBox [-40 -60 660 820]` | letter default, drift (60,112) | media None -> **allowed** | **FAIL (pre-existing bypass, same fix site)** |
| **I4/I5** | **`/CropBox [-40 -60 660 /Foo]`**, **`[-40 -60 660]`** | zero-filled to (-40,-60,660,0): cropbox (-40,792,660,852), drift (60,932) | None -> **allowed** (pre-fix: raised) | **FAIL (new bypass; directly contradicts the M2 docstring)** |
| I6 | `/CropBox [[-40 -60 660 820]]` | ignored, no drift | overhang True, refused | PASS (conservative) |
| **J** | page `/MediaBox` -> null object, or -> cycle 4<->5; parent `/MediaBox [-100 -100 512 692]`; `/CropBox [-40 0 612 692]` | NOT inherited: letter default, drift (60,240) | inherits parent -> False -> **allowed** | **FAIL (new bypass from the null/cycle-continues-walk rule)** |
| J | same with page `/MediaBox 99 0 R` | drift (60,240) | `RuntimeError` | fail-closed by exception |
| J2 | page `/CropBox` -> null object; parent CropBox overhangs (the fix's own test scenario) | NOT inherited: no drift | True, text refused | PASS but a false refusal; the new test pins the disagreement |
| J3/J4 | page `/Rotate` -> null / cycle; parent `/Rotate 45` | rotation 0, rect unswapped, no drift | 45, refused | PASS (conservative) |
| K | 3,000-node `/Parent` chain, `/Rotate 45` at the root | drift | refused in 0.098 s | PASS |
| L1 | grandparent via a bare reference object; `/Rotate` via 2-hop chain = 45 | drift (652,100) | refused | PASS |
| L2 | same tree; `/CropBox` via 2-hop chain overhangs; `/UserUnit 2` on the ancestor | drift (60,112); UserUnit ignored | text refused; unit 1.0 | PASS |
| N1 | `/CropBox [10 10 600]` | zero-filled, tiny strip, no drift | None -> allowed | PASS by luck |

RED claims: plausible and independently reproduced against a scratch copy of 1f3500a (I1: 1.0/0.0/None; I2: thread alive after 3 s; M2: AssertionError). GREEN: `tests/test_geometry.py` 56 passed on the checkout (run with `-p no:cacheprovider`, tree clean afterwards).

### New Breakage in the Fix Diff

1. **Important (security)** `engine/geometry.py:113,119` with `:141`: an indirect null or a reference cycle now continues the inheritance walk; PyMuPDF stops. Bypass J. Pinned by `tests/test_geometry.py:352-362`, which asserts the gate without checking PyMuPDF's drawing.
2. **Important (security)** `engine/geometry.py:167-173`: `_raw_box` returns None for any array that is not exactly four plain numbers, and `crop_origin_overhangs` (`:222-224`) then answers False. Converts the pre-fix crash (closed) into an allow on G1, H1, H2, I1, I2, I4, I5, N3. The docstring claim at `:158-162` ("matches PyMuPDF's own drawing behaviour") is false beyond `[0 0 612]`.
3. **Minor** `engine/geometry.py:96-104` and the report's self-review: `xref_object` returns the bare reference text for every non-cyclic chain too (depth 4 prints `'6 0 R'`), not only for cycles; the docstring's rationale is wrong though the loop handles it.

### Out-of-Scope Observations

- `user_unit` (`engine/geometry.py:201`) trusts `xref_get_key`'s int rendering, which is int32-truncated, while PyMuPDF scales by the int64 value: `/UserUnit 4294967297` passes the gate and draws at (4.29e11, 6.01e11). Pre-existing, security-relevant; reading the page dict via `xref_object(page.xref)` (which prints the full int64, as the indirect path already does) or cross-checking `page.rect` against `page.cropbox` would close it.
- `raw_rotation` / `drawing_refusal` (`:186-189`, `:259-265`): a real `/Rotate` >= 2^31 that is a multiple of 90 (e.g. `2700000000.0`) passes `% 90` while MuPDF's int cast overflows into the malformed swapped-rect state. Pre-existing; a bound such as `abs(rotate) > 2**31 - 1 -> refuse` closes it.
- Dangling references raise `RuntimeError`/`ValueError: bad xref` out of every reader (C, B4). Pre-existing; catching `(ValueError, RuntimeError)` around `xref_object`/`xref_get_key` and treating the value as absent matches PyMuPDF.
- MuPDF stops resolving reference chains between 8 and 16 hops (A); the gate follows any depth. Safe direction only.
- `drawing_refusal` formats `/UserUnit 1.0000001` as "scaling (1)" (`:269`, `{unit:g}`), a confusing message for the operator.
- `raw_object_page` (`tests/geometry_helpers.py:113-148`) is a good generic builder; the numbered-from-4 convention is documented. No issue.

### Verdict

**Fix round:** Findings remain open — I1, M1, M2 (each with the verified bypasses above), plus the two Important new-breakage items (which are the same two root causes) and the Minor docstring item. I2, M3, M4, M5, A1, A2 are addressed. Under the project rule every item must be fixed, the Minor `_resolve` docstring correction is an open item too. Every open item must be re-verified by drawing a probe and comparing to PyMuPDF, not by asserting the gate alone.
