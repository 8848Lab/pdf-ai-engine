# SDD ledger — plan: docs/superpowers/plans/2026-09-26-page-geometry-correctness.md

Spec: docs/superpowers/specs/2026-09-26-page-operations-design.md (read; REVISIONs 1 and 2 binding)
Repo: D:/Coding/8848 Lab/pdf-ai · branch page-operations · merge-base with master 4732bf5 · plan commit efd26a9
Process: the SQUID build setup adopted by the owner 2026-09-26 (memory: feedback_build_setup).
Coordinator Opus 5.5 · implementers Sonnet · reviewers Opus, or Fable for privacy/data-loss tasks · Fable final review.

## Pre-flight conflict scan

### Cross-task pairs (shared file or interface)

| Pair | Produced → consumed | Finding |
|---|---|---|
| T1 → T2 | `engine/geometry.py` created → appended; `tests/geometry_helpers.py` created → `box_page` appended; `tests/test_geometry.py` created → appended | Clean. T2's drift test reuses T1's `matrix_cases`, `matrix_page` and `reopen`, which T1's test file already imports. |
| T1+T2 → T3 | all geometry names → T3's import block | **Conflict, see Ruling S1.** T3 imports six names but uses only `unrotated_bounds`. |
| T3 → T4..T7 | `build_page`, `block`, `exported`, `fingerprint` | Clean. All defined in T3 before their first use. |
| T4 → T6 | `_centre_pixel` | Clean. Defined in T4, used in T6. |
| T5 → T6 | `CROPS` | Clean. Defined in T5, used in T6. |
| T6 → T7 | `_png`, `BLUE` | Clean. Defined in T6, used in T7. |
| T3 → T6 | T3 imports `replace_image` at the top of the test file; T6 once imported it again | Clean. The coordinator removed T6's duplicate import during plan self-review. |
| T3..T7 | all modify `engine/operations.py` | Clean. The anchors are disjoint regions, and order matters only for T7 (gates after validation lines), none of which T3–T6 touch. |

### Per-task self-consistency

| Task | Finding |
|---|---|
| T1 | Clean. 8 tests; the Step 7 expectation of 235 = 227 + 8 is correct. |
| T2 | Clean. `box_page` added in Step 1, before the tests that use it. |
| T3 | The import block brings in five unused names; see S1. Otherwise clean, and every red-first claim was coordinator-verified. |
| T4 | Clean. Its red-first claims were verified by probe. |
| T5 | Clean. The red/green table was measured on the current engine. |
| T6 | Clean. |
| T7 | Clean. Its gate table covers 7 call sites, including both of move_block's. |
| T8 | Clean. |

## Rulings

Ruling S1: each task imports only the `engine.geometry` names it uses. This contradicts plan Task 3 Step 4, which imports all six up front.
- The task-to-name mapping is:
  - T3: `unrotated_bounds`
  - T4: `to_display_matrix`
  - T5: `at_rotation_zero`
  - T6: reuses `at_rotation_zero`
  - T7: `drawing_refusal`, `TEXT_DRAWING`, `OTHER_DRAWING`
- Why: under the adopted setup every finding is fixed, minors included. An unused import is a predictable review finding and would buy a fix round per task.
- Cost if wrong: none material.

Ruling S2: Minor findings ENTER the fix loop. This overrides the SDD skill's default of deferring minors.
- Why: the owner's adopted setup says "every finding gets fixed before merge, minors included", and the owner's instruction outranks a skill default.
- Cost if wrong: extra fix rounds on cosmetic points.

Ruling S3: review tiering follows the adopted setup, with Opus as the default reviewer.
- Tasks 5 and 7 get **Fable**. Task 5 decides where redaction fill lands; Task 7 decides when redaction is refused. Both are privacy-critical.
- The final whole-branch review is Fable.
- Cost if wrong: under-reviewing a privacy task, or spending Fable time on a mechanical one.

Ruling S4: the Codex brief critique runs over the whole plan once, in parallel with Task 1, instead of blocking before it.
- Why:
  - Task 1 is self-contained.
  - It was verified on 1,024 configurations before the plan was written.
  - The adopted setup says never to wait on Codex.
- Findings are ruled on before the task they affect is dispatched.
- Cost if wrong: a Task 1 finding costs one fix round.

## Progress

Task 1: dispatched (BASE efd26a9) — Sonnet implementer; brief step order amended per hard rule (commit before the mutation check).
Codex plan critique: plan relayed to the SQUID session in 4 parts by a relay subagent (keeps 1,844 lines out of coordinator context); running in parallel with Task 1 per S4.
Task 1: implemented (commits efd26a9..0148cf7). 235 passed; RED ModuleNotFoundError confirmed; mutation (to_display_matrix -> page.rotation_matrix) gave exactly 640 failures; restored clean. Review dispatched (Opus).
Task 1: review (Opus) — Spec ✅, Quality Approved, 0 Critical / 0 Important / 3 Minor. Reviewer mutated in a scratch copy: the banned derotation form gave 1,052 collected failures; removing the swap and the finally broke 4 tests.
Task 1: minor M1 (misleading test name 'draws') — enters the loop under S2; rename.
Task 1: minor M2 (sample point (80,85) only 3pt inside the band edge) — enters the loop under S2. Ruling: move it to (120,70), which has >=12pt margin on every side AND avoids the VISIBLE glyphs. The band centre (85,73) would sample black, so the reviewer's implied fix is wrong. Re-prove on all 1,024 cases, re-run the mutation. Cost if wrong: one test line.
Task 1: minor M3 (unrotated_bounds relies on page.rect being origin-normalised) — Ruling: no change. The reviewer itself concluded nothing to change, and the 1,024-case extent check pins the assumption. Cost if wrong: none; any regression fails the matrix test.
Task 1: fix round 1/5 dispatched to the original implementer (M1, M2).
Codex plan critique: relay complete — 4 parts, file lines 1-428 / 429-1154 / 1155-1528 / 1529-1845, 1,845 lines total sent byte-verbatim (sed-extracted). Awaiting SHIP/REVISE.
Task 1: fix round 1/5 (2 addressed, 0 open — M1 rename, M2 sample point to (120,70); commits 0148cf7..9141394). Scoped re-review (Sonnet): all addressed, no new breakage, engine/geometry.py untouched.
Task 1: re-reviewer out-of-scope note (the comment's top/bottom wording is loose) — Ruling: no change. The wording is CORRECT in PyMuPDF's y-down page coordinates: y=58 is the top edge, so 70 is 12pt from the top and 18pt from the bottom (y=88). The note is mistaken. Cost if wrong: none.
Task 1: complete (commits efd26a9..9141394, review clean after 1 fix round)
Ruling S5 (revises S4): tasks do NOT wait on the Codex plan critique. Any critique finding joins the affected task's review loop, or a fix round if that task has already completed. Why: the critique's ETA is unknown, Task 2's code was prototype-verified, and the adopted setup says never wait on Codex. Cost if wrong: possibly one extra fix round on Task 2.
Task 2: dispatched (BASE 9141394)
Task 2: implemented (commits 9141394..1f3500a), 269 passed (235 + 34 new), RED ImportError confirmed.
Task 2: mutation check found THREE false positives for mediabox.contains(cropbox) — bottom, right, negative-origin-mediabox — where the plan and spec said two. The implementer verified bottom is real: for raw CropBox [0 -60 612 792], PyMuPDF reports cropbox (0,0,612,852) against mediabox (0,0,612,792). Ruling: the code is correct and the test is stronger than claimed; the plan and spec text understate the naive check's failure. Correct the spec's R5/R16 wording ('two valid documents' -> three) in Task 8. Cost if wrong: none; documentation only.
Task 2: review dispatched (Opus).
Task 2: review (Opus) — Spec ✅, Quality NEEDS FIXES. 2 Important (both plan-mandated, both reproduced by the reviewer in scratch), 5 Minor.
Task 2: Ruling I1 (plan-mandated; the coordinator's own prototype defect): FIX. _resolve labelled any resolved indirect non-array as 'other', so an indirect /UserUnit 2 read as 1.0 and was NOT refused (PyMuPDF scaled the page to 1224x1584), and an indirect /Rotate 45 read as 0 with a swapped rect. That is a bypass of the R12/P3 safety gate, and numbers stored as indirect objects are common. Fix: classify the resolved object (int/float/null/array/other) and follow chained references with a cycle guard. Principle binding on all value readers: the gate must AGREE WITH WHAT PYMUPDF ACTUALLY DRAWS, verified by test, not by reading the spec. Cost if wrong: none — the gate becomes strictly more accurate.
Task 2: Ruling I2 (plan-mandated): FIX. _inherited's /Parent walk had no visited set; a cyclic page tree hung >5s in two layouts. Today it is hidden only because _validate_target touches page.rect first, which raises FzErrorFormat — call-order dependent. Denial-of-service for an untrusted-PDF tool. Fix: a visited set; terminate and return None on a repeat. A cyclic tree is treated as 'attribute absent', not refused: MuPDF itself rejects such pages at layout, and terminating is the fix. The FzErrorFormat-surfacing-as-500 question is flagged for the final review. Cost if wrong: a cyclic-tree page could be drawn on as if unset, but MuPDF raises first in practice.
Task 2: minors M1-M5 enter the loop under S2. M1: chained indirection and an indirect null (fixed by the I1 rework). M2: malformed box arrays return None instead of crashing, matching PyMuPDF's defaulting, verified. M3: pin non-numeric /Rotate and /UserUnit defaulting with tests, verified to agree with PyMuPDF. M4: a test pinning rule order 1-before-2 (/Rotate 45 plus /UserUnit 2 must report the rotation). M5: crop_origin_overhangs docstring lists all THREE false positives (bottom, right, negative-origin).
Task 2: Ruling: this fix round's re-review runs on FABLE, not Opus. The fixes close a safety-gate bypass and a DoS, which is security per the adopted setup. Cost if wrong: extra review cost.
Task 2: fix round 1/5 dispatched to the original implementer.

## Codex plan critique: REVISE BRIEF (12 points)

Critic: gpt-6-astra on PyMuPDF 1.28.2 (Linux). It built Tasks 1–2 verbatim: 8 and 42 passed. For Tasks 3–7 it used an excerpt-based harness, so those results are predictions and are re-confirmed on Windows by each task's red-first step.

- C1 (indirect number bypasses the gate): **already in Task 2 fix round 1 as I1.** This is independent convergence with the Opus reviewer. The ancestor case was added as addendum A1.
- C5 (inherited-MediaBox test does not exercise inheritance): added to Task 2 fix round 1 as addendum A2.
- C9 (record mutation results accurately):
  - **Correction.** Task 2's contains()-mutation fails **4** tests, not 3: the bottom/right/negative-origin ids plus the 256-case drift test (60 mismatches). The Task 2 implementer ran only the parametrised test.
  - The 4s timing is machine-specific.
  - Ruling: documentation only; corrected in Task 8.
- C2 (P5's fingerprint omits annotations, resources, streams and other objects):
  - The critic proved an added annotation goes UNDETECTED.
  - Ruling: replace it with a snapshot of every xref object's text and every raw stream, plus page_count. Add a self-test proving the oracle detects an annotation and a resource mutation and is stable on a no-op.
  - Owner: Task 3, which defines fingerprint. The "32 bytes" wording is wrong (one run measured 31); it becomes "the trailer /ID".
  - Cost if wrong: none — a strictly stronger oracle.
- C3 (Task 4 contained-crop integration tests are false greens):
  - The old redaction paints its fill elsewhere, leaving the original band at the asserted centre.
  - The fractional red prediction is also wrong: all four rotations fail on the old engine, not just 0. The old sampler never rotates points, so 90/180/270 fail on D2 as well as on scale.
  - Ruling:
    - Task 4 tests `_sample_background_color` DIRECTLY across plain, contained and oversized pages at all four rotations. That isolates sampling from fill placement.
    - The delete_block integration test is restricted to plain pages, where it is a true red.
    - Fill placement belongs to Task 5. The red table is corrected.
- C4 (Task 5 inherited-rotation test is already green; no spies on the two calls):
  - Ruling: the inherited fixture gets a contained CropBox, so it exercises the defect.
  - Add call spies asserting rotation 0 at BOTH add_redact_annot and apply_redactions.
  - Add an injected exception at each call, asserting rotation is restored.
  - Keep the wrapper around both calls. The critic found only apply_redactions needs it, but R11 wraps both, and the spies pin that.
- C6 (Task 7 completeness):
  - Ruling: bind `destination_page, destination_rect = _validate_target(...)` directly.
  - Add tests for:
    - a plain source moving to an unsupported destination, cross-page;
    - a malformed-rotation replace_image;
    - an inherited malformed rotation through an operation;
    - /UserUnit 0.5 refusals. The critic showed `unit > 1` survives the current tests.
  - The gate positions were confirmed by the coordinator against the real bodies: both move gates precede the source erase at 781, and nothing mutates before it.
  - The `git stash` instruction is removed; use per-file backups.
- C7 (Task 3 straddle red prediction is false):
  - (580,690,640,710) fails D1 at 90 and 270 on the old code.
  - Ruling: correct the table. Add a fixture test asserting post-reload marker origins for each geometry, and assert size and text across ALL replacement spans.
  - Use `pytest.approx(..., abs=0.01, rel=0)`.
- C8 (R14: replace_image erase stage not isolated):
  - Ruling: Task 6 spies on replace_image's own `_clean_erase` call to capture its rect.
  - A second test no-ops `insert_image` so the exported erase fill is visible on its own. It asserts the fill's extent and colour, and that the surroundings are untouched.
  - The insertion test stays separate.
  - Add a supported overhang replacement.
- C10 (recheck_geometry.py tests its own helpers, not the engine):
  - Ruling: it stays as a PyMuPDF baseline. Task 8 adds a production run that imports engine.geometry and records the module path.
- C11 (tolerances):
  - Ruling: add a colour-tolerance helper for drawing colours.
  - Use `rel=0`.
  - Assert across all spans. Document the pixel-interior assumption of the fractional patches.
- C12 (platform):
  - Ruling: the declared shell is Git Bash on Windows, where `timeout` IS GNU coreutils. It has worked for every command this session.
  - Add a guard test asserting `engine` and `tests.geometry_helpers` resolve inside this checkout.
  - Reports save the full pytest output and exit status.
  - Per-file backups replace stash.
Plan revised for C2–C12 (commit 1770621, docs-only; Task 2's staged files untouched). Every Task 3–7 test was run as written against staged engines at each boundary. Measured red/green: T3 20F/48, T4 16F/68, T5 11F/86, T6 6F/106, T7 31F/149. Full suite 418 passed with all fixes. Mutations: D3 revert 4F; R11 wrapper narrowed 3F (spies only); gates 5/6/3/1/4/6/3.
Ruling C13: the C8 erase-isolation test is green at Task 6 start (Task 5 fixes the erase path); measured red on the engine before Task 5. It is kept as a stage pin, not a red-first test — cost if wrong: none, the mutation evidence exists.
Ruling C14: the plan's C8 test compares the band with its own read-back rect, because a CropBox shifts drawing coordinates (found while verifying; the first draft was a false red at contained 0). Cost if wrong: none.
Briefs 3–8 re-extracted after the revision; the task-8 brief was trimmed at "## Final whole-branch review" (coordinator-only content).
Task 2: fix round 1/5 reported DONE (commit 52de01c; 283 passed; RED shown for I1, I2, M2). Review package review-task2-fix1.diff excludes docs commit 1770621. Scoped re-review dispatched on FABLE.
Task 2: re-review (Fable, round 1) — I2, M3, M4, M5, A1 and A2 ADDRESSED. I1, M1 and M2 NOT addressed. Verified bypasses: null or cycle continues the inheritance walk (J); malformed box arrays read as absent (G1, H1, H2, I1–I5, N3); missing-MediaBox letter fallback (I3); int32-truncated /UserUnit 2^32+1; /Rotate 2700000000.0; dangling references raise. Full text in task-2-rereview-1.md. (The reviewer hit a rate limit AFTER delivering its report; the report is complete.)
Ruling C15: replace raw-key parsing with PyMuPDF's interpreted geometry (transformation_matrix, rect, cropbox, mediabox).
- Why: every bypass is a divergence between our parser and MuPDF's. Reading MuPDF's own interpretation agrees by construction.
- Verified by the coordinator against a drift probe: 1,024 matrix cases at 4 units, 0 mismatches; 39 adversarial PDFs, 0 bypasses. The only disagreement is /UserUnit 0, which fails safe: refused, and the page cannot be drawn at all.
- New rule: an "inconsistent boxes" refusal applies to every operation. It covers I5, J-null, crop-outside and a mirrored /UserUnit -1.
- Cost if wrong: an over-refusal on pathological pages. Task 8's README must say redaction is refused on pages whose boxes PyMuPDF lays out inconsistently (the plan's "never refused on an overhang" line needs a qualifier).
Task 2: fix round 2/5 dispatched to the original implementer with task-2-fix2-brief.md. Re-review on FABLE.
Task 2: fix round 2/5 reported DONE (b08c848). 322 passed, 25 skipped, exit 0. RED: 17 failures, including all 10 bypass rows. All 4 mutations bite. Coordinator notes for the re-review: (a) test_the_adversarial_table_categories_apply_to_other_drawing_too duplicates the inline OTHER assertions and skips 25 of 39 cases; (b) raw_object_page is now unused. Scoped re-review dispatched on FABLE.
Task 2: re-review (Fable, round 2) — every round-1 item ADDRESSED. NOT PASSED on two new Important bypasses, both caused by the C15 design (full text in task-2-rereview-2.md):
- page.transformation_matrix is constant at 90/180/270, so /UserUnit -1 plus any valid rotation is allowed and misplaced;
- a sub-point CropBox falls back to the unit rect in MuPDF, but not in page.cropbox.
Plus a float32 magnitude drift at ~1e9pt, and Minors: a docstring, a vacuous assertion in the parent-cycle test, the duplicate test, dead raw_object_page, and the "(1)" message.
Ruling C16: read MuPDF's real transform via mupdf.pdf_page_transform(page._pdf_page(), ...). Require the linear part to be page.rotation's pattern at one positive scale; refuse a visible side under 1pt; refuse coordinates beyond 2^24pt.
- The coordinator verified cand3 (scratchpad/fable-t2/cand3.py): 1,024 matrix cases, 0 mismatches; 39 + 88 adversarial rows, 0 bypasses.
- Cost if wrong: the private-API dependency could break on a PyMuPDF upgrade. It fails closed (every page refused, plain-page tests red), so it cannot fail silently.
Ruling C17: a page tree that loops (kids-loop) raises FzErrorFormat when the page is loaded, before the gate runs. That is outside Merge A's gate. It is parked for the final review: operations and webui need a clear error instead of a 500.
Task 2: fix round 3/5 dispatched to the original implementer (task-2-fix3-brief.md). Re-review on FABLE.
Task 2: fix round 3/5 reported DONE (a8b2406). 349 passed, 0 skipped. Concern 1: mutation 2 (drop the <1 check) broke nothing. The coordinator found row crop-0.995 (text drifts to (200,40.005)) and confirmed by an executed mutation that it is a bypass without the check. Concern 2: .7g still prints '(1)'. Ruling: fix round 4 goes to a fresh Opus implementer (the setup's rule for round 4+) with task-2-fix4-brief.md. The Fable re-review then covers rounds 3 and 4 together.
Task 2: fix round 4/5 DONE (84fc253, fresh Opus). 350 passed, exit 0. crop-0.995 shown red with the <1 check removed. Fable re-review of rounds 3+4 dispatched (review-task2-fix34.diff).
Plan REVISION 2 committed (fe3eca1): Task 8 README text rewritten for C15/C16; task-8 brief re-extracted. Tasks 3-7 re-verified against the new gate (HEAD 84fc253 plus the staged patches): identical counts, 20/16/11/6/31 red and 48/68/86/106/149 green; full suite with all fixes 499 passed.
Task 2: re-review 3 (Fable, rounds 3+4) — every round-2 item ADDRESSED and holding under attack; sub-point check load-bearing (re-executed). NOT PASSED: NB1, an infinite MediaBox plus a repaired xref leaves every rule passing because only mediabox/cropbox are bounded; NB2, 2^24 measured integer positions only, and fractional positions drift 0.3pt there. Two test Minors.
Ruling C18: bound mediabox, cropbox, page.rect and the transform's e/f at 2^18. The coordinator re-ran cand5: 223 rows, 0 bypasses; only rows at 2^20 and above and the infinite-MediaBox attacks change, to "huge". Cost if wrong: refuses pages beyond 92m, far past the PDF spec's 14,400pt page limit.
Ruling C17 (extended): drawing_refusal can raise IndexError (a PyMuPDF bound() bug on infinite pages) or FzErrorFormat (a looping page tree). Callers must treat an exception as a refusal. Parked for the final review.
Task 2: fix round 5/5 (the LAST round) dispatched to a fresh Opus implementer (task-2-fix5-brief.md). After its re-review, any open finding gets adjudicated instead of another round.
Queued (user-approved 2026-09-26), to start after Merge A lands: replace_text widens rightward into free space before shrinking, and keeps the original baseline. Evidence from the live test: the Student Name value shrank 14.04 to 8.29pt (0.9^5); a paragraph line 11.04 to 8.05pt (0.9^3).
Task 2: fix round 5/5 DONE_WITH_CONCERNS (d545d86, fresh Opus). 359 passed, exit 0. RED: 7 exactly as required. Both mutations bite.
Ruling C19: accept the implementer's substitute fractional-test page [261500 0 262112 792], probe at page (511.7, 140.7), drift 0.0031pt. The brief's own example was refused by the brief's own rule; that was a coordinator error. Cost if wrong: none.
Concern 2 (media-sym-2^24 catches neither mutation): noted; each mutation is caught by other rows.
Concern 3: parked under C17 for the final review.
Final Task 2 re-review (Fable) dispatched. Round cap reached: open findings after it are adjudicated, not looped.
Task 2: re-review 4 (Fable, round 5): NB1, NB2, Minor 3 and Minor 4 ADDRESSED and holding under attack. One Minor open: the tests pin the bound only below 2^20.
Ruling C20 (adjudication after the 5-round cap): FIX IN PLACE by the coordinator. It is a test-only, three-line change with no engine change. Coordinator commit adds rows media-2^18 (-) and media-2^18+1 (huge) and the fractional offset 2^19-612. Verified by executed mutation: bound 2^19 now fails 2 tests; bound 300000 fails 1. Full suite green. No further re-review: the change is test-only and its bite is proven by the mutations. Cosmetic out-of-scope notes (message wording on transform-triggered refusals, the _fractional_origin/drift_probe duplication, the double page_transform call) are parked for the final review.
Task 2: complete (commits 9141394..HEAD; security-reviewed across 4 Fable rounds; rulings C15-C20).
Task 3: dispatched (BASE b539129), Sonnet implementer. Review on Opus.
Task 3: implemented (6480eac). Red 20F/28P, green 48, D3-only mutation fails 4, full suite 411 passed. Review dispatched (Opus).
Task 3: review (Opus): Spec ✅. Quality needs fixes, 2 Minor (stale 'page's rect' docstrings in move_block and insert_block). Fix round 1/5 sent to the original implementer, plus executed solo reverts of D1, D4 and D5 as evidence.
Task 3: fix round 1/5 (f03efe7): both docstrings fixed. The coordinator checked the 2-file-hunk docstring diff directly and ruled that a docstring-only change needs no separate re-review. Solo-revert evidence: D1 alone 20F, D4 alone 4F, D5 alone 3F. Every bound fix is guarded on its own.
Task 3: complete (commits b539129..f03efe7, review clean after 1 fix round)
Task 4: dispatched (BASE f03efe7), Sonnet implementer. Review on Opus.
Task 4: implemented (9de0ae3). Red 16F/52P, green 68, full suite 431. Mutation (a) rotation-only revert 15F; (b) scale-only revert 3F. Review dispatched (Opus).
Task 4: review (Opus): Spec ✅, Quality Approved, 0 findings.
Ruling C21: the reviewer's note that clamped off-canvas samples can read a glyph pixel when a rect straddles the page edge predates this merge; Task 4 neither introduced nor widened it. Parked for the final review as "drop off-canvas samples, take the median of the rest". Cost if wrong: a slightly off erase colour on edge-straddling rects.
Task 4: complete (commits f03efe7..9de0ae3, review clean)
Task 5: dispatched (BASE 9de0ae3), Sonnet implementer. Review on FABLE (S3, privacy).
Task 5: implemented (0643677). Red 11F/75P, green 86, full suite 449. Mutation: add_redact_annot moved outside the with fails 3 (spies only); wrapper removed returns the original 11F. Review dispatched (FABLE).
Task 5: review (Fable). Spec ✅. Probes: 96/96 erase cells and 48/48 scan-like cells pass on exported bytes; with the wrapper neutralised, 68 of the 96 misplace the fill. Quality needs fixes:
- I1: the inherited-rotation test never exercises inheritance, because parse() writes a page-level /Rotate on load; a raw-handle test is needed.
- M1: split the combined assertions.
- M2: assert rotation on the export.
- M3: the comments say CropBox only, but a negative-origin MediaBox alone also triggers the defect.
Fix round 1/5 goes to the original implementer; the geometry.py docstring (comment-only) is allowed for M3.
Merge B note (ledger, for the Merge B spec): parse() normalises every page's /Rotate into an explicit page-level key on load, so a parent-level /Rotate change after parse is a silent no-op. A page-level rotate is safe.
Task 5: fix round 1/5 (3c235d0) addressed I1, M1, M2 and M3.
- The coordinator checked the diff: the engine hunks are comment/docstring only, and the test changes are an import, split assertions, a corrected comment, and the reviewer-authored raw-handle test. That test was shown red with the wrapper removed (fill 88pt off). 87 passed, and the full suite has 450.
- Ruling C22: no separate Fable re-review. The test code is the reviewer's own, verified at HEAD by the reviewer and shown red by the implementer, and the engine change is comments only. Cost if wrong: a test-quality nit slips to the final Fable review.
Task 5: complete (commits 9de0ae3..3c235d0)
Task 6: dispatched (BASE 3c235d0), Sonnet implementer. Review on Opus.
Task 6: implemented (7b6506d). Red 6F/101P (the exact six ids), green 107, full suite 470. Removing the wrapper kills exactly those six. Review dispatched (Opus).
Task 6: the Opus review failed on a rate limit (resets 7:50pm Vancouver) before writing anything. Ruling C23: re-run the review on Sonnet, the setup's mid-tier floor for reviewers. The diff is 6.5KB, routine, and not privacy-tier. Cost if wrong: a subtler finding waits for the final Fable review.
Task 6: review (Sonnet, per C23): Spec ✅, Quality Approved, 0 findings. Reviewer independently re-ran red 6F/101P, green 107, full suite 470.
Task 6: complete (commits 3c235d0..7b6506d, review clean)
Paused before Task 7: the user asked about moving to a cloud session to save usage; awaiting their go-ahead to snapshot records and push the branch.
Resumed on a Linux cloud session (2026-09-27). Baseline re-confirmed: 470 passed at 1eea6b0.
Task 7: dispatched (BASE 1eea6b0), Sonnet implementer. Review on FABLE (S3, privacy).
Task 7: implemented (cc206a3). Red 31F/119P (the 31 ids exactly as the brief; +1 passing is the Task 6 extra test, 107 vs 106), green 150, full suite 513, exit 0. Mutation per gate: 5/6/3/1/4/6/3, matching the brief. Coordinator checked the diff: gates sit directly after each validation, destination_page bound from its own _validate_target. Review dispatched (FABLE), package review-1eea6b0..cc206a3.diff.
Task 7: review (Fable). Spec ✅, Quality Approved, 0 Critical / 0 Important / 2 Minor. All claims re-executed (red 31F/119P, green 150, per-gate mutations 5/6/3/1/4/6/3). Attack: 64 cases wrapping every PyMuPDF mutator, zero mutator calls before any refusal; webui.session paths keep the handle fingerprint-identical. M1: the move_block source gate's KIND was unpinned (swapping OTHER->TEXT left 513 passed). M2: Raises wording — "This last case" no longer pointed at the does-not-fit case, and the OTHER ops' docstrings claimed an overhang refusal they never make.
Task 7: parked for the final review (out of scope, predates Merge A): after a REFUSED operation, webui/session._registry_refreshed still re-parses and reissues every block id. Nothing is mutated.
Task 7: fix round 1/5 (0ae8816) to the original implementer. M1: reviewer-authored test added; it passes at HEAD, and the coordinator re-executed the kind swap: 1 failed (exactly that test), 513 passed; restored clean. M2: coordinator checked the diff; every changed line is inside a docstring. Full suite 514, exit 0.
Ruling C24: no separate Fable re-review, following C22's precedent. The test is the reviewer's own, its bite is proven by an executed mutation, and the engine change is docstrings only. Cost if wrong: a wording nit slips to the final Fable review.
Task 7: complete (commits 1eea6b0..0ae8816)
Ruling C25: Task 8's brief text said "page boxes beyond 2^24 points"; C18 lowered the bound to 2^18 (engine/geometry.py _MAX_COORDINATE_PT). README must say 2^18. Cost if wrong: none; documentation matches code.
Task 8: dispatched (BASE fe78a59), Sonnet implementer. Review on Opus.
Task 8: implemented (a6071bf). Recheck SUMMARY matches exactly (Linux, PyMuPDF 1.28.2); test_geometry 136 passed; full suite 514, exit 0. The implementer added one dimension consumer the coordinator's list missed: _sample_background_color's pixmap clamp (coordinate math, correct).
Task 8: coordinator finding F0. audit.md states the Task 2 contains() mutation fails 4 tests and was not re-executed. The coordinator re-executed it at HEAD: 12 failed / 502 passed (5 in test_geometry.py incl. test_the_matrix_agrees_with_pymupdfs_own_drawing; 7 in test_page_geometry.py). Handed to the reviewer; it enters the fix loop. Review dispatched (Opus), package review-fe78a59..a6071bf.diff.
Task 8: review (Opus). Spec ❌, Quality needs fixes: 0 Critical / 3 Important / 8 Minor, all documentation. I1 = F0 confirmed (12F/502P; the 1,024-case matrix test also reports 60 mismatches). I2: the README's "(malformed, or under 1pt)" overstated the refusal; a malformed or sub-point MediaBox that PyMuPDF consistently replaces is not refused. I3: the spec's "Redaction ... is never refused" line and its two-item "Gate order" contradicted the gate. M1-M8: line numbers, the second insert_font row, private-API nuance, rule list, spec wording, README scope clause, measured timing and inlined pytest output, heading numbers.
Task 8: parked for the final review (code, not Task 8): when the private-API call fails closed, every page is refused under the "lays out inconsistently" message, which misleads the operator; exception types other than AttributeError/TypeError propagate out of drawing_refusal (joins C17).
Task 8: fix round 1/5 (72260c2) to the original implementer. Every finding applied; mutation re-executed by the implementer (12F/502P); probe 6.858s; full suite 514, exit 0. Coordinator checked the README and spec diff, and checked the new spec gate order line by line against drawing_refusal (rotation, inconsistent boxes, /UserUnit, 2^18, text-only overhang).
Ruling C26: no separate re-review. The fix is documentation only; the replacement text is the reviewer's own, applied verbatim; the one claim that needed code verification (the gate order) was verified by the coordinator. Cost if wrong: a wording issue slips to the final Fable review.
Task 8: complete (commits fe78a59..72260c2)
Final whole-branch review: dispatched on FABLE (S3), base master (merge-base 4732bf5 on page-operations lineage), per the plan's "Final whole-branch review" section plus the parked items C17, C21, Task 2 re-review-4 cosmetics, Task 7's block-id reissue, and Task 8's private-API message.
Final whole-branch review (Fable): READY TO MERGE. 0 Critical / 0 Important / 4 Minor.
- Mutation sweep: D1-D5, R3, R4, R11 (both forms), all seven gates and both move kinds, plus 17 extra rule mutations. No survivor; gate counts 5/6/3/1/4/6/3 match.
- Scans: archive.org blocked; used pikepdf sandwich.pdf (real OCR scan) and ocrmypdf rotated_skew.pdf (real /Rotate 90, skewed cm) plus synthetic content-stream cm pages x 4 rotations x 4 crops. Exported bytes, re-parsed: 344/356 pass; the 12 are a pre-existing replace_image behaviour on SKEWED placements (old XObject kept but blanked white; no privacy impact). Text ops 96/96 at all rotations on 8 allowed geometries. Zero mutator calls before any refusal.
- Tests not weakened: only three new test files; no pre-existing test line changed.
- R12 wording matches; /api returns 400 with it verbatim.
- Minors: M1 /api/page/{i}.png bare 500 on an infinite-MediaBox page (pre-existing route); M2 upload IndexError message opaque (400, not 500); M3 skewed replace_image keeps a blanked XObject (pre-existing); M4 Task 2 cosmetics.
- Parked-item rulings (reviewer): C17 follow-up, patch tested (wrap gate and page load, except -> ValueError "cannot be laid out"); no 500 reachable from any operation route. C21 follow-up, low priority: 728/728 exact today; median-of-on-canvas patch passes the suite. Task 7 block-id reissue: Merge B (RefusedBeforeMutation subclass). Task 8 private-API message: follow-up, patch tested.
Coordinator: the owner's setup says every finding is fixed before merge, while the reviewer rules these as follow-ups (mostly pre-existing, outside Merge A). Scope decision put to the owner.
Final review fix round (owner-selected 5 items, base 0c1ccb1): C17 (a PyMuPDF exception on page load or in the gate becomes a ValueError refusal, in `engine/operations.py`'s `_validate_target` and `_refuse_unsupported_drawing`), Task 8's parked private-API message (`engine/geometry.py`'s `drawing_refusal` rule 0, before rule 1: "could not be checked... the installed PyMuPDF (`fitz.VersionBind`) does not expose the page transform..."), the Task 2 re-review-4 cosmetics (M4: `page_transform` now computed once per gate call via `layout_orientation`'s new optional `ctm` parameter; `_fractional_origin` deleted from `tests/test_geometry.py` in favor of a `point` parameter on `geometry_helpers.drift_probe`; rule 4's message reworded "page boxes or content placed beyond 262144 points"), M1 (`/api/page/{i}.png` routes a `get_pixmap()` failure through the existing `ValueError`/400 handling instead of a bare 500), and M2 (the upload route catches `IndexError` specifically for a named "PyMuPDF cannot determine a page's size" message instead of the opaque "list index out of range"). All five red-first: 6 new tests, each shown failing against a scratchpad backup of the pre-fix file before the corresponding fix, and passing after. Full suite (`tests/`) 520 passed (514 + 6), exit 0. Mutation sweep, each reverted individually from a scratchpad backup (not git stash) and restored after: gate-wrap revert fails `test_an_exception_computing_the_gate_is_reported_as_cannot_be_laid_out`; load-wrap revert fails `test_an_exception_loading_the_page_is_reported_as_cannot_be_loaded` (the out-of-range test stays green, confirming the range check still runs before the try); private-API message revert fails `test_every_operation_refuses_with_a_clear_message_when_the_private_api_is_missing`; M1 revert fails `test_page_image_returns_a_clean_400_when_pymupdf_cannot_render_the_page`; M2 revert fails `test_upload_reports_a_clear_message_when_pymupdf_raises_indexerror`. `layout_orientation` gained an optional `ctm` parameter (default `None`, same behavior as before when omitted) so `drawing_refusal` computes the transform once; no other public signature changed. README's page-geometry paragraph and audit.md's private-API row updated for the new message and the corrected rule-4 wording; C21, the webui block-id registry and replace_image's skew behaviour untouched, as directed.
Final-review fix round 2 (Fable re-review of dac16d2 PASSED, 0 Critical/0 Important/6 Minor; ruling S2 fixes every Minor except M-6). M-1: README's "first four" corrected to "first five" (rule 0 was added in round 1). M-2: the spec's "Gate order for Merge A" section gained rule 0, matching drawing_refusal. M-3: every stale `operations.py:N` reference in audit.md (off by +23 after round 1's edits) and the one `geometry.py:170` reference re-derived with `grep -n` at this round's HEAD and rewritten as function name plus current line. M-4: reworded the three places that misdescribed exception provenance (geometry.py's drawing_refusal docstring, operations.py's `_refuse_unsupported_drawing` Raises section, audit.md's private-API row) to say what the re-reviewer actually measured: `page_transform` returns a real matrix on a bare infinite-MediaBox page (the `IndexError` comes from `page.rect`/`Page.bound()`); a looping page tree raises at `handle[page_index]` before `drawing_refusal` is ever called; `_validate_target`'s load wrap (which reads `page.rect` right after loading) catches both; the gate wrap is defence in depth with no real file reaching it. Added `test_a_real_looping_page_tree_is_reported_as_cannot_be_loaded` (tests/test_page_geometry.py), a real PDF ported from the reviewer's fresh_process.py KIDS_LOOP construction (a /Pages node whose own /Parent points to itself), no monkeypatching: `engine.parser.parse()` itself loads every page while building its registry, so it hits the same PyMuPDF error first, and the test falls back to a raw `fitz.open` handle in that case; either way `redact_region` raises "cannot be loaded" with `FzErrorFormat` in the message. Shown red (raw `FzErrorFormat` propagating) with the load wrap reverted from a scratchpad backup, green restored. M-5: `page_transform`'s broad `except (AttributeError, TypeError)` was swallowing a caller's own mistake (a non-Page argument) as a false "binding missing" report; replaced with an explicit `getattr(fitz.Page, "_pdf_page", None)`/`getattr(mupdf, "pdf_page_transform", None)` existence check, so only a genuinely missing binding returns None and any other exception (including a bad argument) now propagates for the C17 wrap to handle. Added `test_page_transform_raises_on_a_non_page_argument` (`page_transform(None)` must raise), plus `test_page_transform_fails_closed_when_the_real_binding_is_missing` and `test_page_transform_fails_closed_when_pdf_page_is_missing`, which `monkeypatch.delattr` the real `mupdf.pdf_page_transform`/`fitz.Page._pdf_page` attributes and confirm the rule-0 fail-closed behavior still holds (also verified in a scratch run per the brief). Ruling C27 (M-6, no change): the coordinator's `except Exception` in `_refuse_unsupported_drawing`/`_validate_target` stays broad -- for a privacy tool, refusing on an unforeseen error is safer than a 500, and a programming error inside `drawing_refusal` would still fail the plain-page tests, so it cannot hide. Coordinator item: added `testpaths = ["tests"]` to `[tool.pytest.ini_options]` in pyproject.toml so bare `pytest` no longer collects the leftover `docs/superpowers/records/.../probes/fable-t5/test_mutation_inprocess.py` in-process mutation probe; verified bare `.venv/bin/python -m pytest -q` and `pytest -q tests/` both now collect and pass the same 524 (520 + 4 new tests: the M-4 real-file test plus the three M-5 tests -- one more than the round's 522 estimate, since two of the four go beyond the letter of the brief to pin the real-del fail-closed behavior as a regression test rather than only a scratch check). Exit 0.
