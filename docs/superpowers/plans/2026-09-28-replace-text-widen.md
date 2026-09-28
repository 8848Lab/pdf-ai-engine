# replace_text: widen before shrinking, keep the baseline (and C21) — Implementation Plan

> **For agentic workers:** execute this task by task. Tests are written red first, and every claim is backed by an executed command. Steps use checkbox (`- [ ]`) syntax.

**Goal:**
- A longer replacement uses free space to its right before it shrinks.
- It is drawn as one line on the original baseline, in the original colour.
- A replacement that cannot fit is refused before anything is erased.
- The background sampler ignores samples that fall off the canvas (C21).

**Spec:** `docs/superpowers/specs/2026-09-28-replace-text-widen-design.md`. Its "REVISION after the critique" section (D1–D3, R1–R15) is **binding** over the original text.

**Base:** `9403c05`, on branch `claude/eager-thompson-5zta3k`. The full suite is 733 passed.

## Global constraints

- **Existing tests stay unedited**, with one exception: the tests named in D1. Each of those edits is listed in the ledger with its before and after, and a reviewer checks it. Any other existing test that fails means the change is wrong.
- New tests go in a new file, `tests/test_replace_widen.py`.
- **Scope:**
  - Only `replace_text` changes behaviour. `move_block`, `insert_block` and `_draw_shrink_to_fit` keep their current behaviour.
  - Merge A's gate order and Merge B's `RefusedBeforeMutation` rules hold, as amended by R11.
- Assert "nothing changed" with `fingerprint()` from `tests/test_page_geometry.py`. Assert output claims on exported bytes, re-parsed.
- Run everything with `.venv/bin/python` from the repo root, and prefix every test command with `timeout 600`.
- **Process hygiene (owner's rule).**
  - Stop every process you start by the PID you recorded when you started it (`cmd & echo $! > pidfile`, then `kill $(cat pidfile)`), and verify it is gone.
  - Never use `pkill`, `killall` or any pattern match.
  - Never stop a process you did not start.
  - Remove only the worktrees you created.
  - Report stale processes; do not stop them.
- **Backups** go in the scratchpad. Never use `git stash`.
- **Commit trailer:** the attribution your session reminder gives, with this session's link.

## Tasks

### Task 1: C21, off-canvas background samples (W7, R14)

**Files:**
- `engine/operations.py`: `_sample_background_color`
- `tests/test_replace_widen.py`

**Review:** Opus.

- **Red test.** Use the critic's page-frame corner fixture: `docs/superpowers/records/2026-09-28-replace-text-widen/probes/critique/probe_w7.py`, cases 7 and 8.
  - A 300×200 page with a printed frame along the top and right edges, and `"Wide value"` at (285, 12).
  - The old sampler returns grey 0.498 on a white page, and a wrong blue on a light-blue page.
  - With C21 it must return the true background colour.
  - Build the fixture inside the test file.
- **Fix.** Record whether each sample was on the canvas before clamping. When some samples are on the canvas and some are off, take the median of the on-canvas samples only. When none are on the canvas, keep using the clamped set.
- **Mutations.** Each must fail the red test:
  - drop the on-canvas preference;
  - invert the on-canvas test.

### Task 2: `TextBlock` gains `origin`, `direction` and `color` (W1, W5, D3), with no behaviour change

**Files:**
- `engine/document.py`
- `engine/parser.py`
- `tests/test_replace_widen.py`

**Review:** Opus.

- **Fields.** All three default to `None`, so existing constructors keep working:
  - `origin: tuple[float, float] | None = None`
  - `direction: tuple[float, float] | None = None`, taken from the line's `dir`
  - `color: tuple[float, float, float] | None = None`, as RGB floats from the span's sRGB int
- **Red test.** Parse a fixture with red text at a known origin, on a skewed or rotated line, and assert all three fields.
- **Also check** that the web layer's block summaries are unaffected. `get_blocks_summary` lists explicit keys, so it should be.

### Task 3: the right limit (W2, R3–R8)

**Files:**
- `engine/operations.py`: a new pure helper
- `tests/test_replace_widen.py`

**Review:** Opus.

- **The helper.**
  - Signature: `_right_limit(page, target_bbox, baseline, size) -> float`.
  - It is read-only and calls no mutator.
  - It collects obstacles from `get_text("dict")` spans, `get_image_info()`, `get_drawings()` (with rects split into their edges), `page.widgets()` and `page.annots()`.
- **Rules to apply:**
  - **R3:** an obstacle is anything with `x1 > target.x1` in the vertical band, and its limit is `max(x0, target.x1) - gap`.
  - **R4:** widgets and annotations are obstacles.
  - **R5:** an image in the band means no widening.
  - **R6:** horizontal rules under 1pt tall are ignored, and an underline bounds the limit at its own x1.
  - **R7:** the paragraph column edge applies only when there are at least 2 aligned neighbours whose x1 agree within 10%.
  - **R8:** a right-aligned target does not widen.
  - **W2.3:** the page margin, floored at 18pt.
- **Red tests.** One per rule, each built from the critic's fixtures in `probe_w2.py`, `probe_w4.py` and `scenarios.py`:
  - a text neighbour 180pt away;
  - a neighbour starting 1.5pt left of the target's x1 (expect no widening);
  - a table's vertical rule;
  - a cell rectangle, where only its right edge counts;
  - an underline;
  - dotted leaders (a pinned limitation);
  - an empty AcroForm field;
  - a full-page scan image (expect no widening);
  - the stacked form at a 22pt pitch (widens to the box edge less the gap);
  - a heading over a shorter line (not capped);
  - a real paragraph (capped at the column edge);
  - a right-aligned amount (no widening);
  - a cropped page;
  - a page rotated to 90, 180 and 270.
- **Mutations.** Remove each rule in turn; each removal must fail a named test.

### Task 4: the new `replace_text` path (W1, W3, R1, R2/D2, R9, R11, R13, D3), and the D1 test edits

**Files:**
- `engine/operations.py`: `replace_text`
- `tests/test_replace_widen.py`
- the D1 tests

**Review: Fable**, because the erase and redraw touch neighbouring content.

- **Order of operations in `replace_text`:**
  1. Validate, then apply Merge A's gate. Both are unchanged.
  2. Collapse line breaks to a space (D2).
  3. Resolve the font (unchanged).
  4. Decide the path:
     - the **new path** when `origin` is present, `direction` is within 1e-3 of (1,0), and R1's sanity gate passes;
     - otherwise today's box path, with only D2 and D3 applied.
  5. On the new path, compute the limit, then work out the size:
     - at the original size if the text fits;
     - otherwise the exact size `size * w_avail / w_need`;
     - if that size is below the 50% floor, raise `RefusedBeforeMutation` **before erasing**. Word the message like today's "does not fit" message, and add that nothing was changed.
  6. Erase exactly as today: the target bbox plus the precision pad.
  7. Draw one line at the origin with `insert_textbox`, using R9's rect, in the original colour (black when the colour is `None`).
  8. A draw failure after the erase stays a plain `ValueError`.
- **Verify R9.** Every new-path draw must read back as **one span**, with its origin equal to the original origin within 0.01pt. If `insert_textbox` cannot guarantee that, switch to `insert_text`, record why, and then the two spy tests fall under D1.
- **Red tests:**
  - The owner's form (V2): "Jonathan Lee" draws at 14pt as one span on baseline 100.0.
  - The very long value is refused with the fingerprint unchanged.
  - The paragraph line keeps its baseline.
  - A newline collapses to a space.
  - Red text stays red.
  - y-mirrored, scaled `Tm`, `Tz`, Type3 and a 1° skew all take today's path, following the critic's `probe_w1.py` and `probe_w5.py`.
  - Rotations 0/90/180/270, plus Merge A's contained crop: the text lands at the original origin.
  - Merge B's B1 guard test still holds, with its "replace no fit" case now a refusal.
- **D1 edits.** List each one in the task report as before/after:
  - `test_replace_text_raises_when_text_does_not_fit_even_shrunk`
  - `test_replace_text_reports_an_unexpected_drawing_failure_as_a_valueerror` (possibly unchanged under R9)
  - `test_refused_before_mutation_is_raised_exactly_when_nothing_changed[replace draw raises]` (possibly unchanged under R9)
  - `test_a_failed_replace_leaves_state_consistent_with_the_real_document`
  - `test_a_failure_after_a_mutation_still_refreshes_the_ids`, which needs a different post-mutation failure. For example, monkeypatch the draw to raise after the erase.
- **Mutations.** Each must fail a named test:
  - the widen step removed;
  - the exact shrink replaced by the old 0.9 loop;
  - the refusal moved after the erase;
  - the R1 gate removed;
  - the direction tolerance removed;
  - the newline collapse removed;
  - the colour dropped;
  - the baseline taken from `bbox.y0`.

### Task 5: documentation

**Files:**
- `README.md`: the `replace_text` entry. State the widening, the baseline, the colour, the refusal before any erase, and the known limitations: right-to-left text, dotted leaders, scans and scaled text all fall back to today's behaviour.
- `docs/superpowers/records/2026-09-26-page-operations/audit.md`: update the drawing-call row for `replace_text`, if the primitive or its rect changed.

**Review:** Opus.

## Final review (Fable)

- Re-run every mutation named above; none may survive.
- Check exported bytes on the critic's scenario fixtures and on the real scans (`scratchpad/fetch/`).
- A widened draw must never cover any neighbouring span, image, widget or rule.
- Confirm that only the D1 tests were edited, each as ledgered.
