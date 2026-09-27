# SDD ledger — plan: docs/superpowers/plans/2026-09-27-page-operations-merge-b.md

Spec: docs/superpowers/specs/2026-09-26-page-operations-design.md ("Merge B", REVISION 1 R6–R10 binding).
Repo: /home/user/pdf-ai-engine (Linux cloud session) · branch claude/eager-thompson-5zta3k · base master a7debea (Merge A merged).
Process: the owner's build setup, as in Merge A. Coordinator (this session), Sonnet implementers, Opus reviewers, Fable for Task 3 (duplicate_page, F4 data loss) and the final whole-branch review. Every finding fixed, Minors included (S2 carries over). Tests red first; evidence is executed.

## Pre-plan verification (coordinator)

- Re-verified on PyMuPDF 1.28.2: F5 16/16 pairs; F4 copy_page aliases the page (redacting the copy empties the original in export) and fullcopy_page does not; R7 fullcopy_page(0,1) on one page raises; R6 new_page defaults to A4; rotated/cropped neighbour display rects; links follow moves, vanish with a deleted target, and a duplicated self-link targets the original (R8); zero-page save raises.
- New finding: set_rotation(45) silently stores 0 (plan ruling B3).
- The whole of Merge B was staged and executed in a scratch worktree: 641 passed (524 + 117). Mutations run against it: 8 of 9 engine mutations bite; `% 360` normalisation survived because set_rotation normalises itself, so it was removed (B3). Session/AI mutations bite. The six operations.py refusal sites were each pinned after the coordinator found that converting the gate back to ValueError survived the first draft of the tests. Playwright drove every page control in Chromium, no console errors.
- Codex plan critique: not available in this cloud session (the SQUID relay is on the owner's machine). Substitute: the Fable final review covers the plan's claims by re-running every mutation.

## Rulings

B1–B7: see the plan's "Plan-level rulings".

## Progress

Tasks 1-3: dispatched together to one Sonnet implementer (BASE 5db870c), one commit per task; reviews per commit.
Tasks 1-3: implemented. T1 1862e5b (red ModuleNotFoundError; 49 green; mutations 3/1/4 as planned; suite 573). T2 4393413 (red ImportError; 70 green; mutations 6/4/2; suite 594). T3 98a45db (red ImportError; 82 green; copy_page mutation fails exactly the two redaction-independence cases; last-page mutation 4; suite 606). engine/pages.py identical to the staged reference. Coordinator re-ran the suite: 606 passed. Reviews dispatched: Opus (T1, T2), FABLE (T3).
Task 1 review (Opus): Spec ❌, needs fixes. I1: rotate_page(90*2**40) hangs (PyMuPDF JM_norm_rotation subtracts 360 in a loop), reachable via API/AI once Task 5 lands. Revises ruling B3: `% 360` is required. Minors: no bad-index test for rotate_page; equal invalid move pairs untested; rotation False untested; message casing; errors.py docstring ahead of Task 4; rotation message wording.
Task 2 review (Opus): Spec ✅ (R6 holds for rotated/cropped/negative-origin/fractional/UserUnit neighbours; an inserted page is never gate-refused), needs fixes. I1: insert_page hangs on a zero-page document (handle[-1] with 0 pages loops; parse accepts /Count 0). I2: 10**400 escapes as OverflowError. I3: no test pins which page is the neighbour. Minors: messages for defaulted dimensions, bound-edge tests, at_index True, docstrings.
Task 3 review (Fable): Spec ✅ (independence holds for all six engine ops both directions, shared image/Form XObjects, annotations, content arrays, after garbage=3 and through the session; R7/R8 hold; 10/10 mutations killed), needs fixes. I1: a duplicate of the last page of a /Pages node lands under the NEXT node and inherits its Resources/MediaBox/Rotate, rendering blank at the wrong size. Minors: copy-before-source only caught by accident; shared /Resources dict note; copied widgets not in /AcroForm/Fields note.
Coordinator extension: the same node-boundary defect breaks move_page (move 1->2, 2->0, 3->1, 0->3 on a two-node tree lose text/font/size; scratchpad/move_nodes.py). Ruling B8: pin a page's effective inheritable attributes (Resources, MediaBox, CropBox, Rotate) onto its own dict before move_page or duplicate_page, walking /Parent with a visited set. Cost if wrong: explicit keys equal to inherited values, which render identically.
Tasks 1-3: fix round 1/5 dispatched to the original implementer (all findings plus B8).
