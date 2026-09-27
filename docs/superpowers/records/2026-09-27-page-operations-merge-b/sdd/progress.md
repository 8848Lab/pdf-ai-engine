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

