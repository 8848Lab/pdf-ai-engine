# Resuming Merge A (page geometry correctness)

State: Tasks 1–6 are complete and reviewed. **Task 7 is next.**

## What to read

- **Plan:** `docs/superpowers/plans/2026-09-26-page-geometry-correctness.md`, including its two REVISION sections at the end.
- **Spec:** `docs/superpowers/specs/2026-09-26-page-operations-design.md`.
- **Ledger:** `sdd/progress.md`. It is the recovery map, and it holds every ruling (S1–S5, C1–C23). Trust it, together with `git log`.
- **Task briefs:** `sdd/task-7-brief.md` and `sdd/task-8-brief.md`. Both are already extracted and current.
- **Reviewer attack scripts:** `probes/fable-reviewer/` (Task 2) and `probes/fable-t5/` (Task 5). They contain absolute Windows scratch paths, so fix those before running them.

## Environment differences on a Linux cloud session

- **Python path:** the briefs use `./.venv/Scripts/python.exe`, which is the Windows path. On Linux, use `.venv/bin/python`.
- **Setup:** `python -m venv .venv && .venv/bin/pip install -e ".[test,webui,ai]"`.
- **Baseline:** the full suite is 470 passed at 7b6506d.

## Build setup (owner's standing choice)

- The coordinator runs subagent-driven development.
- Sonnet implementers:
  - Fix rounds 1–3 resume the same implementer.
  - Round 4 and later go to a fresh Opus implementer.
- Reviewers:
  - Opus for routine tasks.
  - **Fable for Task 7** (privacy: when redaction is refused).
  - **Fable for the final whole-branch review.**
- Every finding is fixed, Minors included.
- Tests are red first. Evidence is an executed mutation, not reasoning.

## Parked for the final review

These are listed in the ledger:

- **C17:** `drawing_refusal` and page load can raise `IndexError` or `FzErrorFormat`. Callers need to turn that into a refusal instead of a 500.
- **C21:** a clamped off-canvas background sample can read a glyph pixel on rects that straddle the page edge.
- **Task 2 re-review 4:** cosmetic notes.

## Merge B notes

- `parse()` writes an explicit page-level `/Rotate` on load, so a parent-level rotate after parse is a no-op.

## Queued after Merge A (owner-approved)

- `replace_text` should widen rightward into free space before shrinking, and keep the baseline.
- See the ledger's last entries.

## Not pushed

- `master` is still local-only, ahead of origin.
- This branch contains master's unpushed merges.
