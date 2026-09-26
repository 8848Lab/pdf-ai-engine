# 8848 PDF — Page Operations — Design Brief

**Status:** brief, pending critique. Once critiqued, a "REVISION after the
critique" section is appended with numbered rulings (R1, R2, ...) that are
**binding over the original text below.**

## Intent

Complete phase 1 of the roadmap ("rock-solid editing primitives") by adding
page-level operations: delete, move, rotate, insert blank, duplicate. It
must serve two jobs:

- **Cleaning up a received document** — drop junk pages, fix a sideways
  scan, put pages in the right order before sending it on.
- **Assembling a package** — add blank pages, duplicate repeated form pages.

Same contract as the existing seven operations: validate fully before
mutating, raise `ValueError` naming the problem, never silently no-op, never
produce output that looks right but isn't.

## Why this is two merges, not one

Scoping `rotate_page` surfaced a **pre-existing** coordinate-space defect in
the engine. It already affects any document that arrives with `/Rotate` set
— which is most scanned paper — on all seven existing operations. Adding a
rotate operation merely makes it trivially reachable.

So this ships as two ordered merges, safety piece first:

- **Merge A — rotation correctness.** Fixes the existing engine for rotated
  pages. Standalone, no new features. Reviewed on its own merits as a bug
  fix. Lands before any page operation exists.
- **Merge B — page operations.** The five new operations, their session
  wrappers, API routes, UI and AI tools. Depends on A.

## Verified facts

Every claim below was reproduced on PyMuPDF **1.28.2** (the installed
version; `pyproject.toml` declares `pymupdf>=1.24,<2`, it is **not**
pinned to an exact version). Evidence is in the "Evidence" column.

### F1. The two coordinate spaces

On a page with rotation set, `page.rect` reports the **rotated** (display)
box while `page.get_text()` returns span/block bboxes in the **unrotated**
page space. At rotation 90, `page.rect == (0,0,792,612)` while a span that
reads `(72,87,355,104)` before rotation still reads `(72,87,355,104)` after.

`page.rect * page.derotation_matrix` returns the unrotated box
`(0,0,612,792)` at **every** rotation (0/90/180/270). So does
`page.cropbox` on the test pages, but `cropbox` is the raw PDF box and may
carry a non-zero origin on real files, whereas `page.rect` is normalised to
a `(0,0)` origin — so the derotation form is the one this brief specifies.

### F2. Drawing is already rotation-safe

`page.insert_image` and `page.insert_textbox`, given **unrotated** rects on
a rotation-90 page, land exactly where requested: an image inserted at
`(72,700,136,764)` is reported back at `(72,700,136,764)`, and text inserted
at `(300,700,560,730)` is reported at `(300,700,354,716)` — identical to
rotation 0. `add_redact_annot` + `apply_redactions` likewise remove the
correct text on a rotated page. **Only the checks and the sampling are
broken, not the drawing.** Merge A must therefore not transform any
coordinate passed to a drawing call.

### F3. The five defective sites

| # | Site | Uses rotated `page.rect` as | Effect on a rotated page | Evidence |
|---|---|---|---|---|
| D1 | `operations.py:178` `_validate_target` | intersection bound | Rejects a valid block in the lower part of the original page as "entirely off-page". Every one of the seven operations calls this. | At rotation 90, a block at `(72,687,214,704)` raises `ValueError: does not intersect page 0 (page rect is (0,0,792,612))`; at rotation 0 the same call succeeds. |
| D2 | `operations.py:233-247` `_sample_background_color` | pixmap scale, with **unrotated** sample points fed into a pixmap rendered in **rotated** space | Samples the wrong pixels, so `_clean_erase` fills with the wrong colour — a visible patch. Affects `delete_block`, `replace_text`, `move_block`, `replace_image`. | On `colored_background.pdf` the correct sample is `(178,216,255)`. Rotation 0 returns it. Rotations **90, 180 and 270** all return `(255,255,255)`. |
| D3 | `operations.py:355-356` `_insertion_rect` | growth cap | Loses vertical headroom for blocks below the rotated height, so text shrinks more than needed. **Not** an inverted box — the outer `max(rect.y1, …)` prevents inversion. | Block `y 687..704`: rotation 0 yields insertion box `y1=707`; rotation 90 yields `y1=704` (cap `page.rect.y1=612` loses to the `max`). |
| D4 | `operations.py:761` `move_block` | containment | Rejects a valid in-page destination. Currently **masked by D1**, which rejects first. | Would surface as soon as D1 is fixed. |
| D5 | `operations.py:834` `insert_block` | containment | Rejects a valid in-page bbox. Currently masked by D1. | At rotation 90, `insert_block(bbox=(72,720,400,740))` raises; rotation 0 succeeds. |

`parser.py:106-107` sets `Page.width/height` from the rotated `page.rect`.
Nothing in `engine/` or `webui/` consumes those fields for coordinate math
(verified by grep), so they are **left unchanged** and documented as display
dimensions.

**180 matters separately.** At rotation 180 `page.rect` does not swap
dimensions, so D1/D3/D4/D5 pass there — but D2 still fails, because the
sample points are mirrored. A test matrix covering only 90 and 270 would
miss D2 at 180.

### F4. `copy_page` shares content streams — use `fullcopy_page`

`Document.copy_page(0, -1)` produces a page whose content-stream xrefs are
**identical** to the original's (`[9,10]` and `[9,10]`). Redacting only the
copy then removes the text from the **original** as well, and that survives
export. `Document.fullcopy_page(0, -1)` produces independent streams
(`[6]` vs `[11,12]`); redacting the copy leaves the original intact through
export. **`duplicate_page` must use `fullcopy_page`.** Using `copy_page`
would be silent data loss on the page the operator believed untouched.

### F5. Native `move_page` is not a final-index API

`Document.move_page(src, to)` inserts **before** `to`. On `[P0,P1,P2,P3]`:
`move_page(0, 1)` is a **no-op**; `move_page(0, 2)` yields `P1,P0,P2,P3`;
the last position is reachable only via `to=-1`. A final-index contract —
"after the call, the page is at index `f`" — is implemented as: `f == src`
no-op; `f == last` → `move_page(src, -1)`; `f > src` → `move_page(src, f+1)`;
`f < src` → `move_page(src, f)`. Verified correct on all 16 `(src, f)`
pairs of a four-page document.

## Change surface

### Files written

| Merge | File | Change |
|---|---|---|
| A | `engine/operations.py` | New helper `_unrotated_page_rect(page)`; D1-D5 switched to it; D2's sample points transformed into display space. |
| A | `engine/parser.py` | Docstring only: `Page.width/height` are display dimensions. |
| A | `tests/test_rotation.py` | **New.** The rotation matrix (see Testing). |
| A | `tests/fixtures/generate_fixtures.py` + one new fixture | A rotated fixture set. |
| B | `engine/pages.py` | **New.** The five page operations. |
| B | `webui/session.py` | Five wrappers; page summary gains `rotation`. |
| B | `webui/main.py` | Five routes under `/api/pages/…`. |
| B | `webui/ai/tools.py` | Five tools (6 → 11). |
| B | `webui/static/app.js`, `styles.css`, `index.html` | Per-page controls. |
| B | `tests/test_pages.py` | **New.** |
| B | `tests/test_webui.py`, `tests/test_ai.py` | Route and tool coverage. |
| B | `README.md` | Operations list. |

### Contracts that must NOT change

- **Every existing operation's signature and success-path behaviour on
  unrotated pages.** Merge A is a no-op at rotation 0 by construction; the
  existing 227 tests must pass unchanged, and must not be edited to pass.
- **Drawing calls receive unrotated coordinates** (F2). Merge A transforms
  bounds and sample points only — never a rect handed to `insert_textbox`,
  `insert_image` or `add_redact_annot`.
- **`export()` keeps `garbage=3`; internal refresh keeps using `snapshot()`.**
  `export()`'s garbage pass mutates the live handle; the split between the
  two is load-bearing (metadata-leak and orphan-reclamation guarantees).
- **Block and image ids stay monotonic and are never reused.**
- **`Page.width/height` semantics** (display dimensions).
- **The `move_block` / `insert_block` full-containment rule** — destinations
  must still be fully on-page. Merge A changes *which rect* they are checked
  against, not the rule.

### Overlap with in-flight work

None. `master` is clean at `4732bf5`; no other branch is open.

## Merge A — rotation correctness

- Add `_unrotated_page_rect(page) -> fitz.Rect`, returning
  `page.rect * page.derotation_matrix`. One helper, used at every bound
  site — **not** a per-operation transform, which would scatter the fix
  across seven callers and invite drift.
- **D1, D3, D4, D5:** replace `page.rect` / `destination_page.rect` with the
  helper. Error messages must report the rect actually checked against.
- **D2:** before scaling a sample point into pixmap space, map it from
  unrotated page space into display space with `page.rotation_matrix`.
  The zoom factor itself (`pixmap.width / page.rect.width`) is already
  correct, since both are display-space.
- `_sample_background_color`'s pixmap render and `_clean_erase`'s redaction
  are otherwise unchanged.

## Merge B — page operations

New module `engine/pages.py`. Rationale: `operations.py` is 1,049 lines and
uniformly *"given a page and a target rect, change that region."* Page
operations take no rect and change the document's shape. A sibling module
keeps both coherent; adding them to `operations.py` would push it past
1,300 lines across two abstraction levels. `pages.py` reuses nothing from
`operations.py` except, where needed, the `page_index` range check.

All five raise `ValueError` on invalid input and validate completely before
mutating.

| Operation | Signature | Contract |
|---|---|---|
| `delete_page` | `(handle, page_index)` | Refuses to delete the **last remaining page** — a zero-page PDF is invalid. |
| `move_page` | `(handle, page_index, to_index)` | **Final-index** semantics per F5: after the call the page is at `to_index`. `to_index == page_index` is a valid no-op, not an error. Both indices range-checked. |
| `rotate_page` | `(handle, page_index, rotation)` | **Absolute.** `rotation` must be one of 0/90/180/270 after normalising negatives and multiples of 360 (e.g. `-90 → 270`, `450 → 90`). Anything not a multiple of 90 raises. |
| `insert_page` | `(handle, at_index, width=None, height=None)` | Inserts a blank page that ends at `at_index`; `0 <= at_index <= page_count` (equal to `page_count` appends). Dimensions default to those of the page currently at `at_index`, or the last page when appending — **not** hardcoded Letter. Given dimensions must be positive. |
| `duplicate_page` | `(handle, page_index)` | Inserts an **independent** copy immediately after the source, via `fullcopy_page` (F4). |

**Why absolute rotation.** The driving case is "fix the sideways scan": the
operator — or the model — knows the target orientation, not the current
one. The page summary exposes each page's current `rotation`, so a caller
wanting a relative turn computes it from state.

**Registry interaction.** Page operations shift `page_index` for every block
and image, so they invalidate *all* ids rather than some. The session
already rebuilds both registries after every operation with monotonic ids,
so stale ids raise `LookupError` as intended. No code change; documented.

### Session, API, UI

- `webui/session.py`: five wrappers with the established shape — resolve
  inputs, call the engine op in a `try`, refresh in the `finally` via the
  existing `_registry_refreshed` discipline. `get_pages_summary()` gains
  `rotation`.
- `webui/main.py`: `POST /api/pages/{delete,move,rotate,insert,duplicate}`,
  JSON bodies, returning `_state_payload()`. **`/api/pages/…`, plural** —
  not `/api/page/…`, which already hosts `GET /api/page/{page_index}.png`.
- UI: per-page controls in the existing manual-controls section — delete,
  move up/down, rotate left/right, duplicate, insert blank after. Functional,
  consistent with prior manual controls, not polished.

### AI tools

Five tools: `delete_page`, `move_page`, `rotate_page`, `insert_page`,
`duplicate_page`. Unlike image bytes, a model can fully express these.
Descriptions must state final-index semantics for `move_page` and absolute
semantics for `rotate_page`, and that page indices are **0-based** (the model
will otherwise tend to say "page 1" meaning index 0). Schemas follow the
existing strict-mode convention: optional parameters are nullable and listed
in `required` (`insert_page`'s `width`/`height`).

## Testing

Red-first throughout: every regression test is shown failing on the
pre-merge code before the fix.

### Merge A — the rotation matrix (`tests/test_rotation.py`)

- **All four rotations: 0, 90, 180, 270.** 180 is required — it is the case
  where bound checks pass but sampling fails (F3).
- A block in the **lower portion of the original page** (below the rotated
  height), on each rotation: every one of the seven operations accepts it.
- A block that is **genuinely off-page** is still rejected on each rotation.
- **D2:** on a rotated copy of `colored_background.pdf`, the sampled colour
  is the band colour `(178,216,255)` at every rotation, and a
  `delete_block` leaves the erased region that colour, checked on the
  **exported** bytes re-parsed from scratch, not the live handle.
- **D3:** a replacement of identical text on a low block fits at its
  original size on a rotated page, as it does unrotated.
- **Mutation gate:** revert each of D1-D5 in turn in a scratch copy and
  show a named test fails for each. A site whose revert no test notices is
  a finding.

### Merge B (`tests/test_pages.py`)

- **`move_page`:** the full 16-pair `(src, final)` table on a four-page
  document, asserting final order — not a handful of spot checks.
- **`duplicate_page` independence (F4):** redact on the copy; assert the
  original still yields its text **in the exported bytes**. Then the
  mutation gate: switching to `copy_page` must fail this test.
- **`delete_page`:** refuses the last page; deleting any other page leaves
  the rest in order.
- **`rotate_page`:** normalisation table (`-90→270`, `450→90`, `360→0`);
  non-multiples of 90 raise; rotation survives export.
- **`insert_page`:** default dimensions follow the neighbour, including a
  non-Letter neighbour; append at `page_count`; out-of-range raises.
- Every raise path leaves the document unmodified, asserted on
  `page_count`, page order and content, not merely "it raised".
- Cross-merge: a page rotated with `rotate_page` accepts all seven existing
  operations on a lower-half block — the case Merge A exists to enable.

Every test run uses `timeout 600`. Tests touch no network, database or model.

## Review tiering

- **Merge A: Fable review.** A failure here means a redaction the operator
  asked for is refused on scanned pages, or an erase leaves a visible
  mismatched patch. That is privacy- and correctness-critical.
- **Merge B:** Opus for routine tasks; Fable for `duplicate_page`
  (F4 is a data-loss hazard).
- **Fable final whole-branch review** before each merge.

## Out of scope

- Extracting pages to a new file — that is an export variant, not a
  mutation, and belongs with export.
- Anything multi-document: merging, importing pages from a second PDF.
- Relative rotation as its own operation.
- Page labels and bookmarks/outline repair after reordering or deletion.
  (Internal links are **not** a concern here, verified: a `LINK_GOTO` from
  P0 to P2 still lands on P2 after `move_page(2, 0)`, because links
  reference page objects rather than indices; and deleting a link's target
  page removes the link cleanly instead of leaving it dangling. Merge B
  should pin both behaviours with a test so a future change cannot regress
  them silently.)
- Changing `Page.width/height` semantics.
