# Erase without deleting neighbours (P2, P1) — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-09-28-erase-neighbours-design.md`. Its REVISION rulings R1–R12 are **binding**.

**Base:** branch `claude/eager-thompson-5zta3k`, based on master `f881d95`. The suite currently passes with 868 tests.

## Global constraints

- **Existing tests stay unedited.** If one fails, the change is wrong: stop and report it. New tests go in `tests/test_erase_neighbours.py`.
- **Scope (R10):**
  - The clip applies only at the four text erase sites.
  - `replace_image`'s erase and `redact_region` are untouched.
  - Every new refusal is a `RefusedBeforeMutation`, raised before any mutation. Prove it with `fingerprint()` and a spy on the mutator.
- **How claims are checked:** assert output claims on the exported bytes, re-parsed. Check pixels against an "ideal" page: the same page rebuilt without the target. This is the critic's `harness.py` method.
- **Commands:** use `.venv/bin/python` and prefix every test command with `timeout 600`. Test first: each test must fail before its fix. Evidence must come from commands actually run.
- **Mutation runs:** set `PYTHONDONTWRITEBYTECODE=1`, clear `__pycache__`, and pass `-p no:cacheprovider`.
- **Process hygiene (owner's rule):**
  - Stop only the processes you started, by their recorded PID, and verify each is gone.
  - Never use pkill, killall or pattern matching.
  - Keep backups in the scratchpad. Never use git stash.
- **Commit trailer:** from your session's attribution reminder.

## Tasks

### Task 1: the neighbour-aware clip (R1–R5, R8, R10)

**Files:**
- `engine/operations.py`: add a helper that computes the clipped erase rect before any mutation, and route the four text sites through it.
- `tests/test_erase_neighbours.py`

**Review:** Fable, together with Tasks 2–3.

**What the helper does:**
- **R2 (same-line neighbours):** identify them with the origin rule; for a hand-built block, match the page span by its bbox.
- **Other overlapping neighbours:** decide whether each is above or below by its centre, then clip `y0` or `y1` to that neighbour's bbox edge.
- **R3 (minimum height):** if the clipped height is below 15% of the target's, refuse.
- **R4 (direction):** refuse non-horizontal text whose band overlaps another line.
- **R5 (Type3):** keep the full rect for Type3 targets.
- **R8 (the target's own rules):** before the clipped erase, run a first pass over the full rect with `text=1, graphics=1, images=0, fill=False`.

**Red tests (R11 fixtures):**
- **Pitch sweep:** paragraphs at pitches 18, 16.5, 15, 14.4, 13, 12 and 11. Cover `delete_block`, `replace_text` on the widen path and on the box path, and `move_block`'s source, each on the middle line, the first line and the last line.
- **Same-line pair:** a bold label followed by body text at tight leading.
- **Superscripts and subscripts:** the target's own superscript, and a neighbour's subscript.
- **Target's underline:** at tight leading, it is removed.
- **Floor refusal:** a case that falls below the 15% floor is refused.
- **Other cases:** vertical text is refused; a Type3 target takes the full rect.
- **Exported checks:** the neighbours are present in the exported text, and no pixels are damaged versus the ideal page.

**Mutations:** each must fail a named test:
- the above-clip removed;
- the below-clip removed;
- the same-line rule removed (the two `replace_text` same-line tests from the existing suite must fail);
- the floor removed;
- R4 removed;
- R5 removed;
- R8 removed.

### Task 2: layout rules and the bleed margin (R6, R7)

**Files:**
- `engine/operations.py`: the same helper.
- the new test file.

**What to add:**
- **R6:** geometric ink-top and ink-bottom from `fitz.Font.glyph_bbox`. If that is unavailable, use 0.75·size and 0.25·size.
- **Which rules count:** a rule that extends beyond the target, or starts left of it, and whose stroke lies wholly outside the ink band.
- **R7:** clip 0.5pt short of the stroke. This includes rules that sit outside the rect but within 0.5pt of it.

**Red tests:**
- the owner's form at 14pt and at 18pt: the box border must be unbroken in a pixel diff;
- a bordered table row;
- a rule that crosses the ink zone keeps today's behaviour.

**Mutations:** each must fail a named test:
- the 0.5pt margin set to 0.25;
- the within-0.5pt-outside rule removed;
- the ink-band test replaced with the old 15% band.

### Task 3: image-backed targets (R9)

**Files:**
- `engine/operations.py`
- the new test file

**What to do:** when an image overlaps the target's band, do two passes:
1. the clipped rect with `text=0`;
2. the full rect with `text=1, images=2, graphics=0` and the fill.

**Red test:** a synthetic 300 dpi scan with a `render_mode=3` OCR layer at pitch 13. No neighbouring OCR words may be lost, and none of the target's ink may be left. Build it with the critic's `n3_scan.py` construction, inside the test file.

**Mutation:** collapse the two passes into one (option (a)). The test must fail.

### Task 4: documentation

**Files:**
- `README.md`: add a note, for `delete_block`, `replace_text` and `move_block`, that neighbouring lines are preserved at any leading. State the R12 limitations and the R4 and R5 refusals and fallbacks.
- `docs/superpowers/records/2026-09-26-page-operations/audit.md`: add the new erase rows.

## Final review (Fable)

- **Mutation sweep:** re-run every mutation listed above.
- **Pixel and export checks:** run them on all the fixtures and on the real scans.
- **Edits:** confirm that no existing test was edited.
