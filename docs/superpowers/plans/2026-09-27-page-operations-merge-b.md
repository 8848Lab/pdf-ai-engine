# Page Operations (Merge B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the five page operations (delete, move, rotate, insert blank, duplicate) through the engine, session, API, AI tools and UI, and stop a refused operation from reissuing every block and image id.

**Architecture:**
- **Engine.**
  - A new `engine/pages.py` holds the five operations. It is a sibling of `operations.py`, because these take no rect and change the document's shape.
  - A new `engine/errors.py` holds `RefusedBeforeMutation`, a `ValueError` subclass raised only by checks that run before the first mutation.
  - `operations.py`'s six pre-mutation refusal sites raise it: `_validate_target` and the geometry gate.
- **Session.** `webui/session.py` skips its registry refresh for that type. Otherwise the web and AI layers follow the established shapes.

**Tech stack:** Python 3.11+, PyMuPDF 1.28.2 (declared `pymupdf>=1.24,<2`), FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-page-operations-design.md`. Read the "Merge B — page operations" section, then REVISION 1's rulings R6–R10, which are binding over it. Merge A has landed on `master` (`a7debea`).

## Global constraints

- **Existing tests must pass unedited.** The count is 524 at `a7debea`. If one fails, the change is wrong, not the test. All new tests go in new files: `tests/test_pages.py`, `tests/test_webui_pages.py` and `tests/test_ai_pages.py`.
- **Every validation failure in `engine/pages.py` raises `RefusedBeforeMutation` before any mutation**, with a message that names the problem and says "Nothing was changed."
- **"Nothing was changed" is asserted on `fingerprint()`** (from `tests/test_page_geometry.py`), never on exported bytes. PyMuPDF regenerates the trailer `/ID` on every save.
- **Claims about output are asserted on exported bytes, re-parsed.**
- **Scope boundaries:**
  - No operation's existing signature changes.
  - `engine/export.py` and `engine/geometry.py` are not touched.
- **Run from the repo root** with `.venv/bin/python` (Linux) or `./.venv/Scripts/python.exe` (Windows). Prefix every test command with `timeout 600`. `pytest` alone collects only `tests/`.
- **Backups:** use a copy in the scratchpad, never `git stash`.
- **Commit trailer, exactly:**
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_014vSh7XebS1vQxW3TyaoENs
  ```

## The staged implementation

The coordinator wrote and executed the whole of Merge B in a scratch worktree before writing this plan. The result is committed at `docs/superpowers/records/2026-09-27-page-operations-merge-b/staged/`:
- `merge-b-staged.diff` is the complete change against `a7debea`;
- the five new files are also there in full, under the same paths.

Measured on the staged tree:
- **Full suite:** 641 passed, which is 524 plus 117 new.
- **UI:** a Playwright run drove every page control in Chromium and found no console errors (B7).

Each task below names the exact part of the staged change it applies. The implementer's job is to:
- apply that part test-first, showing the red run before the code;
- re-measure every claim;
- run the named mutations;
- report any disagreement with this plan rather than smoothing it over.

The staged code is the reference, not an oracle. A reviewer finding in it is fixed like any other.

## Plan-level rulings

**B1 — `RefusedBeforeMutation`, and the session skips the refresh on it.**
- This is the owner-approved follow-up from Merge A's final review (Task 7's parked item: a refused operation reissued every id).
- It subclasses `ValueError`, so every existing handler and test keeps working. Two things raise it:
  - the six raise sites in `_validate_target` and `_refuse_unsupported_drawing`, which all run before any mutation in every one of the six targeted operations (confirmed against Merge A's audit);
  - `engine/pages.py`'s validation.
- Every other `ValueError` stays a plain `ValueError`, and the session still refreshes after it. That includes the "erased, then did not fit" failures.
- Cost if wrong: an id kept valid after a real mutation. Task 4's tests pin both sides.

**B2 — `insert_page` bounds each given dimension to 1–14,400pt and rejects non-finite values and booleans.**
- 14,400pt is the PDF specification's largest page side, far inside Merge A's 2^18 bound.
- 1pt matches Merge A's smallest visible side, so an inserted page is never one the drawing gate would refuse.

**B3 — `rotate_page` must validate before calling PyMuPDF.**
- Verified: `set_rotation(45)` silently stores 0. Without the check, "rotate 45" would silently become "reset to upright".
- `set_rotation` normalises -90, 450 and 360 by itself. The engine does not repeat that (a staged `% 360` survived its mutation). The normalisation test pins PyMuPDF's behaviour instead.

**B4 — Where the pages summary goes in what the model receives (R10/E3).**
- In the first message it goes **after** the instruction. In each later round it is a text block placed **before** the blocks list, which stays the last block.
- Why: the existing AI tests parse the blocks list by its position, and they must pass unedited.
- Verified: all three providers pass every text block through as its own user message.

**B5 — A no-op `move_page` is a success, so it still reissues ids.**
- R9 asks for stale-id behaviour to be verified, not changed. A test pins this, with a comment saying it is pinned, not endorsed.

**B6 — `get_pages_summary()` gains `rotation`, read from the live handle.**
- The parser's `Page` dataclass is not changed. `Page.width` and `Page.height` stay display dimensions, per spec.

**B7 — The UI is verified in a real browser.**
- The task's report includes a Playwright run that clicks each page control and lists the page labels after each click, plus a screenshot.
- Chromium is at `/opt/pw-browsers/chromium`, and global `playwright` is at `$(npm root -g)/playwright`. Do not run `playwright install`.

## Verified by the coordinator on PyMuPDF 1.28.2

These probes are in the session scratchpad and summarised here.
- **F5 (final-index move):** the formula passes all 16 (src, final) pairs.
- **F4 (duplicate independence):** redacting the copy made by `copy_page` also empties the original in the exported bytes (`['', '', 'P1']`). With `fullcopy_page` the original survives (`['P0', '', 'P1']`).
- **R7 (duplicating the last page):** `fullcopy_page(0, 1)` on a one-page document raises "bad page number(s)".
- **R6 (inserted page size):** `new_page` without a size gives A4 whatever the neighbour's size.
- **Rendered sizes:** a rotation-90 neighbour's display rect is 842×595 for A4, and a cropped neighbour's is its crop.
- **Links:**
  - A link follows its target page through a move.
  - Deleting a link's target removes the link.
  - A duplicated self-link still targets page 0 (R8).
- **Deleting to zero pages:** PyMuPDF allows it, but `tobytes()` then raises "cannot save with zero pages".

## File structure

| File | Change |
|---|---|
| `engine/errors.py` | **New.** `RefusedBeforeMutation`. |
| `engine/pages.py` | **New.** `delete_page`, `move_page`, `rotate_page`, `insert_page`, `duplicate_page`. |
| `engine/operations.py` | Six `raise ValueError(` → `raise RefusedBeforeMutation(` in `_validate_target` and `_refuse_unsupported_drawing`, plus the import and two `Raises:` lines. |
| `webui/session.py` | Five wrappers; `except RefusedBeforeMutation: raise` in `_registry_refreshed`; `rotation` in `get_pages_summary()`. |
| `webui/main.py` | Four request models; five `POST /api/pages/...` routes. |
| `webui/ai/tools.py` | `PAGE_INDEX` schema fragment; five tools (6 → 11); system prompt; five `_execute_tool` branches. |
| `webui/ai/loop.py` | `_pages_text()`; the pages summary in the first message and in every round. |
| `webui/static/app.js`, `styles.css` | `renderPageControls()`; `.page-controls` styling. |
| `tests/test_pages.py`, `tests/test_webui_pages.py`, `tests/test_ai_pages.py` | **New.** |
| `README.md` | The operations list gains the five page operations. |

---

### Task 1: `RefusedBeforeMutation`, and `delete_page` / `move_page` / `rotate_page`

**Files:**
- Create `engine/errors.py` and `engine/pages.py`. `engine/pages.py` gets the module docstring, the constants, `_check_page_index`, `delete_page`, `move_page` and `rotate_page`, all as staged.
- Create `tests/test_pages.py`, with the header and the move, delete and rotate sections as staged.

**Review:** Opus.

- [ ] **Step 1 (red).** Add the test file sections. Run `timeout 600 .venv/bin/python -m pytest tests/test_pages.py -q`. Expected: a collection error (`ModuleNotFoundError: engine.errors`). Paste it.
- [ ] **Step 2 (green).** Add `engine/errors.py` and the three operations. Expected: every test in those sections passes. Report the count.
- [ ] **Step 3 (mutations).** Apply each change to a scratchpad backup, then restore. Each must fail at least one named test:
  - `move_page`'s `to_index + 1` → `to_index`: 3 fail.
  - The only-page guard disabled: 1 fails.
  - `rotation % 90 != 0` → `False`: 4 fail.
- [ ] **Step 4.** Run the full suite (expect 524 plus this task's new tests, all passing), then commit: `feat: add delete_page, move_page and rotate_page`.

### Task 2: `insert_page`

**Files:**
- `engine/pages.py`: `_side` and `insert_page`, as staged.
- `tests/test_pages.py`: the insert section.

**Review:** Opus.

- [ ] **Step 1 (red).** Run the insert tests; they fail on `ImportError: insert_page`.
- [ ] **Step 2 (green).** Add the code. Run the insert section and the full suite.
- [ ] **Step 3 (mutations).** Each must fail at least one named test:
  - `new_page` without `width`/`height`: 6 fail.
  - Width defaulting from the neighbour's height: 4 fail.
  - The height check removed: 2 fail.
- [ ] **Step 4.** Commit: `feat: add insert_page, sized from its neighbour`.

### Task 3: `duplicate_page`, and the link pins

**Files:**
- `engine/pages.py`: `duplicate_page`.
- `tests/test_pages.py`: the duplicate and links sections.

**Review: Fable** (spec F4 is a data-loss hazard).

- [ ] **Step 1 (red).** Run the duplicate and link tests; they fail on `ImportError: duplicate_page`.
- [ ] **Step 2 (green).** Add the code, then run the tests.
- [ ] **Step 3 (mutations).** Each must fail at least one named test:
  - `fullcopy_page` → `copy_page`: 2 fail. These must be the two `test_redacting_the_duplicate_leaves_the_original_intact_in_the_exported_bytes` cases.
  - `-1 if page_index == last else page_index + 1` → `page_index + 1`: 4 fail.
- [ ] **Step 4.** Commit: `feat: add duplicate_page as an independent copy; pin link behaviour`.

### Task 4: Refusals keep ids (B1)

**Files:**
- `engine/operations.py`: the import, the six raise sites, and two `Raises:` lines.
- `webui/session.py`: the `_registry_refreshed` change and its docstring paragraph, only.
- `tests/test_pages.py`: the "existing operations" section.
- `tests/test_webui_pages.py`: create it with its header plus these tests only:
  - `test_a_refused_block_operation_keeps_every_id_valid`
  - `test_a_failure_after_a_mutation_still_refreshes_the_ids`
  - `test_a_geometry_gate_refusal_keeps_every_id_valid`

**Review:** Opus.

- [ ] **Step 1 (red).** Expected:
  - the "existing operations" tests fail with `DID NOT RAISE RefusedBeforeMutation`, since a plain `ValueError` is raised;
  - the two keeps-ids tests fail on the state comparison;
  - `test_a_failure_after_a_mutation_still_refreshes_the_ids` passes already, and is kept as a guard.
- [ ] **Step 2 (green).** Apply the changes.
- [ ] **Step 3 (mutations).**
  - Convert each of the six raise sites back to `ValueError` in turn. Each must fail a named test; the staged tree measured 1, 1, 1, 2, 1 and 2 failures.
  - Remove the session's `except RefusedBeforeMutation: raise`. The keeps-ids tests must fail.
- [ ] **Step 4.** Run the full suite with the existing 524 unedited, then commit: `feat: a refusal before any mutation keeps every block and image id valid`.

### Task 5: Session wrappers, pages summary, API routes

**Files:**
- `webui/session.py`: the five page wrappers and `rotation`.
- `webui/main.py`: the models and routes.
- `tests/test_webui_pages.py`: the remaining tests.

**Review:** Opus.

- [ ] **Step 1 (red).** The route tests fail with 404 or 405, and the summary test fails on the missing `rotation`.
- [ ] **Step 2 (green).** Apply the changes. The cross-merge test (`test_a_page_rotated_through_the_api_accepts_every_block_operation_on_a_low_block`) must pass.
- [ ] **Step 3.** Run the full suite and commit: `feat: page operations in the session and under /api/pages/`.

### Task 6: AI tools and the pages summary for the model

**Files:**
- `webui/ai/tools.py` and `webui/ai/loop.py`, as staged.
- `tests/test_ai_pages.py`.

**Review:** Opus.

- [ ] **Step 1 (red).** Expected: the tool-count, schema and description tests fail; `_execute_tool` returns "unknown tool"; the pages-summary test fails.
- [ ] **Step 2 (green).** Apply the changes. `tests/test_ai.py` and both provider test files must pass unedited.
- [ ] **Step 3 (mutations).** Remove the per-round pages block, then remove the first-message pages text. Each must fail `test_the_model_is_shown_the_pages_first_and_after_every_round`.
- [ ] **Step 4.** Commit: `feat: page tools for the AI layer, and the pages summary in its context`.

### Task 7: UI, README, and the browser check

**Files:**
- `webui/static/app.js` and `styles.css`, as staged.
- `README.md`: add the five page operations to `## Operations`, in the existing style. Each gets one line, stating that indices are 0-based, that `move_page` uses final-index semantics, that `rotate_page` is absolute, that `insert_page` defaults to the neighbour's displayed size, and that `duplicate_page` makes an independent copy whose links still point where the original's did.

**Review:** Opus.

- [ ] **Step 1.** Run `node --check webui/static/app.js`.
- [ ] **Step 2 (B7).** Start `uvicorn webui.main:app --port 8765`. Then drive the UI with Playwright:
  1. Upload a three-page labelled PDF and turn on "Show manual editing controls".
  2. Click Rotate right on page 1, Move up on page 3, Duplicate on page 1, Insert blank after on page 2, and Delete page on page 5.
  3. After each click, print the page labels.
  4. Confirm that "Move up" is disabled on page 1, that the error line is empty, and that the browser logged no errors.
  5. Save a screenshot to the scratchpad.

  Put the printed output in the report.
- [ ] **Step 3.** Run the full suite (expect 641), then commit: `feat: per-page controls in the UI; document page operations`.

## Final whole-branch review (Fable)

- **Mutation sweep:** re-run every named mutation above in a scratch copy, plus `copy_page` for F4. There must be no survivor.
- **Exported bytes:** delete, move, rotate, insert and duplicate on the synthetic scan-like pages from Merge A's review and on the fetched real scans (`sandwich.pdf`, `rotated_skew.pdf`), re-parsed from scratch.
  - Page order, text and rotation must be as expected.
  - A redaction on a duplicate must leave the original intact.
- **Tests not weakened:** `git diff a7debea -- tests/` must show only new files.
- **Id behaviour:** check it end to end through `TestClient`, covering a refusal, a success, a no-op move, and a post-mutation failure.
- **AI context:** confirm a blank page is visible to the model.
