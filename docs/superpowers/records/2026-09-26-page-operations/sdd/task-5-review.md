# Task 5 review: redaction fill placement (R11)

Range 9de0ae3..0643677. Reviewer: Fable 5.1. Privacy tier, task-scoped.

## Verdicts

- **Spec compliance: ✅** (all items below verified)
- **Code quality: Needs fixes** — 0 Critical, 1 Important, 3 Minor. The engine change is correct and complete; the findings are on the tests.

## Spec compliance

| Requirement | Result | Evidence |
|---|---|---|
| Both redaction calls run at rotation 0 (R11) | ✅ | `engine/operations.py:211-213`: `with at_rotation_zero(page):` wraps `add_redact_annot` and `apply_redactions`. Spy test `tests/test_page_geometry.py:344-364` pins both; replicated the Step 5 mutation in-process (add outside the wrapper): the 3 spy cases fail on `add_redact_annot: 90/180/270`, exactly as the report says. |
| `_erase_region` keeps its `(page, rect, fill) -> None` signature | ✅ | `engine/operations.py:189` |
| Docstring kept, one line added | ✅ | `engine/operations.py:204` |
| Imports only the `engine.geometry` names it uses (S1) | ✅ | `engine/operations.py:16`: `at_rotation_zero` (l.211), `to_display_matrix` (l.248), `unrotated_bounds` (l.180, l.777) are each used. |
| No pre-Merge-A test or `tests/test_geometry.py` edited | ✅ | `git diff --stat 9de0ae3 0643677`: only `engine/operations.py` and `tests/test_page_geometry.py`; the test-file hunk is a pure append from line 257. |
| Output assertions through exported, re-parsed bytes | ✅ with one Minor | Text-gone and fill assertions all go through `exported(handle)[0]`. The "rotation restored" assertion at `tests/test_page_geometry.py:300` is on the live handle only (Minor M2). |
| Tests appended as specified; red/green matches the brief's table | ✅ | Ran the 18 new tests at HEAD: pass. `tests/test_page_geometry.py` + `tests/test_geometry.py`: 222 passed. Red-run counts (11 failed / 75 passed) are the report's claim; I did not rebuild the pre-fix state file-for-file, but neutralising `at_rotation_zero` in-process reproduces the same failure pattern on my wider matrix (see Probes). |

## Code quality findings

### I1 (Important) — the "inherited rotation" test never reaches the inherited case
`tests/test_page_geometry.py:327-341`, comment at 329-333.

The builder `_inherited_rotation_page` is correct: its bytes have `/Rotate` only on `/Pages` (verified: page key `null`, parent `90`). But `parse()` calls `page.get_text("dict")` (`engine/parser.py:68`), and on PyMuPDF 1.28.2 `get_text("dict")` / `get_textpage()` / `get_drawings()` **write a normalised page-level `/Rotate`** onto the page as a side effect (bisected call-by-call; `page.rect`, `page.rotation`, `get_pixmap`, `get_images`, `clean_contents` do not). So by the time `redact_region` runs, `handle.xref_get_key(page.xref, "Rotate") == ("int", "90")`, and `at_rotation_zero` sees an ordinary explicit rotation. The comment's stated mechanism ("at_rotation_zero writes a page-level /Rotate while drawing and restores it, so the page may end with an explicit value where it had an inherited one") is real in isolation (verified: on a raw inherited page, the wrapper alone leaves `/Rotate 90` explicit, effective rotation unchanged) but is never what this test exercises. The test currently duplicates `[90-contained]` of the erase test with a different builder, while claiming Review Focus 3 coverage.

**Fix.** Keep the test, but make its comment true and add the inherited case on a handle that bypasses `parse`:

```python
def test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation():
    # Built with /Rotate only on /Pages, but parse()'s get_text("dict") writes
    # a page-level /Rotate on PyMuPDF 1.28.2, so by the time redact_region runs
    # the key is explicit. This pins the contained-crop fill at 90 on such a
    # page; the inheritance itself is exercised below on a raw handle.
    ...unchanged body...


def test_redaction_on_a_raw_inherited_rotation_page_keeps_the_effective_rotation():
    # No parse(): the page really has no /Rotate of its own when the wrapper
    # runs. Effective rotation must survive the export; the page-level key it
    # leaves behind is documented here, not hidden.
    data = _inherited_rotation_page("90", cropbox=CROPS["contained"])
    probe = fitz.open(stream=data, filetype="pdf")           # get_text writes the key, so
    target = find_span_bbox(probe[0], "LOW-MARKER")          # measure on a throwaway copy
    handle = fitz.open(stream=data, filetype="pdf")
    assert handle.xref_get_key(handle[0].xref, "Rotate") == ("null", "null")
    redact_region(handle, 0, tuple(target))
    out = exported(handle)[0]
    assert out.rotation == 90
    assert out.parent.xref_get_key(out.xref, "Rotate") == ("int", "90")
    fills = _fills(out, BLACK)
    assert len(fills) == 1 and _on(fills[0], target), f"fills {fills}, target {tuple(target)}"
```
(`find_span_bbox` is already in `tests/geometry_helpers.py`.) I ran the equivalent by hand: it passes at HEAD.

### M1 (Minor) — compound assert hides which property failed
`tests/test_page_geometry.py:309` (and the same shape at 341): `assert len(fills) == 1 and _on(fills[0], target)`. On failure the count and the placement are indistinguishable, unlike the sibling test at 296-298. **Fix:** split into two asserts with the same messages the erase test uses.

### M2 (Minor) — rotation-intact assertion on the live handle only
`tests/test_page_geometry.py:300`: `assert handle[0].rotation == rotation`. The exported page is already in `page`; the output claim should be made there. **Fix:** add `assert page.rotation == rotation` (keep the live-handle one if wanted; it is what the `finally` restores). Verified on export for every probe cell, so this is a test-strength fix, not a defect.

### M3 (Minor) — the "why" comment understates the trigger
`engine/operations.py:206-207` says the fill is misplaced "on a rotated page with a CropBox". With the wrapper neutralised, a page with **no CropBox** and a negative-origin MediaBox (`[-100 -200 512 592]`) misplaces the fill at 90 too (probe 1). **Fix:** "on a rotated page whose CropBox or MediaBox origin is not (0, 0)". (Same wording lives in `at_rotation_zero`'s docstring in `engine/geometry.py`, out of this task's files; note it for the final review.)

Not flagged: the docstring line at l.204 plus the five-line comment at 206-210 say the same thing twice, but both were mandated verbatim by the brief. The mid-file `# noqa: E402` import at `tests/test_page_geometry.py:257` was also mandated; hoisting `_erase_region` into the existing `from engine.operations import (...)` block at l.15 would be cleaner and is worth doing while touching the file for M1/M2, but I do not count it as a finding.

## Probes (all on exported, re-parsed bytes)

Scratch: `.../scratchpad/fable-t5/probe1_matrix.py`, `probe1_nofix.py`, `probe2_rotation_state.py`, `probe3_scan.py`, `test_mutation_inprocess.py`.

| # | Probe | What PyMuPDF did | Result |
|---|---|---|---|
| 1a | `redact_region`, `delete_block`, `replace_text` (erase), `move_block` (source erase) × rotations 0/90/180/270 × crops {contained, oversized, left overhang `[-40 60 580 740]`, top overhang `[40 60 580 840]`, negative-origin MediaBox `[-100 -200 512 592]`, negative MediaBox + contained crop} = 96 cells. Checked: marker text extractably gone (unclipped `get_text`), exactly one fill of the expected colour, that fill within 1pt of the target, no other filled drawing, no `/Annots` left, exported `page.rotation` unchanged. | Every cell: text gone, one fill on target, rotation intact, no leftover redact annots. `replace_text`'s fill is 0.05pt wider (the precision pad), inside tolerance. | **96/96 pass** |
| 1b | Same 96 with `at_rotation_zero` replaced by `nullcontext` in-process (no checkout edit) | Text still removed everywhere; fill misplaced in 68 cells — every 90/180/270 cell on contained, left, top and both negative-MediaBox variants, and 180/270 on oversized. Matches the brief's table and extends it. | 28/96 pass — probe detects the defect |
| 2a | Explicit page `/Rotate` 90, 180, 270, -90, 450, 0 with contained crop; redact; export | Effective rotation preserved; raw key is the normalised value (-90 → 270, 450 → 90) but it was already normalised by `parse()` before the redaction, so the wrapper changed nothing observable. Fill on target. | pass |
| 2b | Indirect `/Rotate N 0 R` | Same: direct `90` after parse, unchanged by redaction, fill on target | pass |
| 2c | Inherited `/Rotate` on `/Pages` only (90/180/270), contained crop | Effective rotation preserved, fill on target, no stray key **from the redaction**: the page-level key was already written by `parse()` (see I1). | pass for the engine; I1 for the test |
| 2d | Two-page inherited-rotation doc, only page 0 redacted, then a **parent-level** `/Rotate 180` edit | Neither page follows the parent: both had explicit keys after `parse()`, before any redaction. | Observation, not a Task 5 defect |
| 2e | Same, then a **page-level** rotate (`set_rotation(rotation + 90)`) on each page | Both pages at 180, explicit keys. A Merge B page-level rotate is unaffected. | pass |
| 2f | `at_rotation_zero` alone on a raw inherited page (no parse) | Inside: page key `0`, eff 0. After: page key explicit `90`, eff 90, MediaBox/CropBox untouched. So the wrapper *would* materialise the key if anything reached it un-parsed; nothing in this pipeline does. | pass; behaviour documented |
| 3 | Scan-like page: full-page 16×16 grey image + `LOW-MARKER` + `KEEP-ME`, all drawn under a content-stream `cm` (90° CCW, 180°, 270°, identity) × `/Rotate` 0/90/180/270 × crop {none, contained, oversized} = 48 cells; `redact_region` on the (vertical, for the 90/270 `cm`) marker bbox | Marker gone, `KEEP-ME` kept, exactly one black fill on the target, rendered pixel at the target centre is black, image pixel near `KEEP-ME` still grey, and 4-6 of 256 image pixels blanked (the ones under the target) in every cell. | **48/48 pass** |
| 4 | Report's Step 5 mutation replicated in-process (`add_redact_annot` outside the wrapper) against the new tests | Only the 3 spy cases fail; all 8 fill-placement cells and 4 black-box cells still pass. | Confirms the report, and that the spy test is the sole pin on the `add_redact_annot` half |

## Out-of-scope observations

1. **`parse()` rewrites every page's `/Rotate`.** `get_text("dict")` on PyMuPDF 1.28.2 writes a normalised page-level `/Rotate` on each page it touches (also `get_textpage`, `get_drawings`; not `/MediaBox` or `/CropBox`). Consequences for Merge B: an editor document never carries inherited rotation after load; a page-level rotate op is safe; a parent-level rotate op would be a silent no-op. Anything that fingerprints "nothing changed" across a parse must expect this key to appear.
2. **`drawing_refusal` is not wired into `engine/operations.py` yet** (no call site outside `engine/geometry.py`), so today `replace_text`/`move_block` on a top-left-overhang crop erase correctly (probe 1) and then draw at R5's known-wrong position. Presumably Task 6/7.
3. **The defect is broader than "CropBox"**: a negative-origin MediaBox with no CropBox triggers it (probe 1b). The wrapper covers it; only the comments (M3, and `at_rotation_zero`'s docstring in `engine/geometry.py`) describe the narrower case.
4. The report's "449 passed" full-suite claim was not re-run here (focused tests only); the two geometry files pass at HEAD (222).
