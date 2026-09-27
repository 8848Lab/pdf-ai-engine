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

---

## REVISION after the critique

**This revision is binding over everything above.** Where a ruling here contradicts the
original text, the ruling wins.

The critic was Codex `gpt-6-astra`. Its verdict was **REVISE BRIEF**, with six points.
It ran its own probes offline on PyMuPDF 1.28.2. The coordinator re-ran every point on
the Windows target, and **all six reproduced exactly**. The coordinator's own follow-up
probes then found one defect the critique did not cover (R5).

### Rulings

**R1 — Merge A becomes "page geometry correctness".**

- It absorbs critique points 1–3 and R5. They are one concern: mapping correctly
  between PyMuPDF's coordinate spaces.
- Several of these defects are in code already merged to master, including
  `replace_image`, shipped 2026-09-24. So Merge A fixes shipped behaviour; it is
  not just groundwork for rotate.
- Merge A stays a single merge with one Fable review, but is planned as several
  tasks.

**R2 — One helper pair replaces the brief's single helper.**

The brief's `page.rect * page.derotation_matrix` is **withdrawn**. On a CropBox that
extends past the MediaBox, it returns `(0,88,612,880)` at rotation 90 and rejects
visible text (critique point 2, reproduced).

It is replaced by two helpers:

- `_unrotated_bounds(page)` returns `Rect(0, 0, W, H)`, where `(W, H)` are the display
  width and height, **un-swapped** at rotations 90 and 270.
- `_to_display_matrix(page)` returns `Matrix(page.rotation)`, followed by the
  translation that moves the rotated image of `_unrotated_bounds(page)` to the origin.

The coordinator verified the pair on 16 configurations: four page types (ordinary,
contained crop, oversized crop, fractional size) at each of 0/90/180/270.

- Every bound check accepts visible text.
- Every sample reads the correct `(178,216,255)`.
- The matrix is **identical** to `page.rotation_matrix` in every configuration except
  the oversized CropBox, which is exactly where the library matrix is wrong.

So this is a strict correction, not a behaviour change for ordinary pages.

F1's wording is also corrected. `page.cropbox` is returned in PyMuPDF's own coordinates,
not as the raw PDF box: the raw box `[-40 -60 660 820]` reads back as `(-40,-28,660,852)`.

**R3 — Sampling stops inferring scale from raster size.**

Critique point 3 reproduced. A `100.1 × 800.1` page renders to `101 × 801` pixels, so
the current `zoom = pixmap.width / page.rect.width` gives `1.008991`. At rotation 0, the
samples land on the wrong pixels.

The new sampling procedure:

1. Render with `page.get_pixmap()`. Its default matrix is the identity: one pixel per
   point.
2. Map each sample point through `_to_display_matrix(page)`.
3. Subtract the pixmap's origin (`pix.x`, `pix.y`), then clamp.

There is **no zoom factor at all**. Two claims in the brief are withdrawn: "keep the
zoom, it is already correct", and that D2 "switches to the unrotated-bounds helper".
Sampling is a raster mapping, so it uses the display matrix.

**The contract is amended.** "Merge A is a no-op at rotation 0" is replaced by **"no
behaviour change wherever current behaviour is correct."**

- This deliberately changes rotation-0 results on fractional-size pages, which are
  wrong today.
- Every existing fixture is integer-sized: 612 × 792 renders to exactly 612 × 792, at
  zoom 1.0.
- So all 227 existing tests must still pass unedited. If any needs editing, that is a
  finding, not a fix.

**R4 — Image insertion gets its own fix.**

Critique point 1 reproduced. On a page with CropBox `(40,60,580,740)`, `insert_image`
at `(72,500,136,564)` lands at `(32,552,96,616)` at rotations 90, 180 and 270, and the
requested spot renders white. So `replace_image` has been misplacing replacement images
on cropped, rotated pages since it shipped.

- **Fix:** wrap `insert_image` in a temporary `set_rotation(0)`, and restore the
  rotation in a `finally`.
- The coordinator verified this lands correctly at all four rotations, on both offset
  and oversized CropBoxes.
- The brief's ban on changing how drawing calls are *handled* is withdrawn.
- Its ban on transforming the *coordinates* passed to them stands: rects stay
  unrotated.

**R5 — On pages with an oversized CropBox origin, refuse to draw text.**

This was not in the critique. The coordinator found it by extending the probe for
point 1 from an offset CropBox to an oversized one.

**The defect.** When a page's CropBox **top-left corner** lies outside its MediaBox,
`insert_text` and `insert_textbox` both draw shifted by exactly that out-of-bounds
offset. This happens at **every** rotation, **including 0**. Meanwhile `get_text()`
reads in page-rect space, so drawing and reading disagree. Examples:

- raw CropBox `[-40 -60 660 820]` shifts text by `(-40, -28)`;
- raw CropBox `[0 0 612 830]` shifts text by `(0, -38)`.

**The predicate** (raw PDF coordinates): drift occurs **if and only if**
`crop.x0 < media.x0` **or** `crop.y1 > media.y1`. The coordinator verified it on six
cases:

| CropBox overhang | Drifts? |
|---|---|
| Left only | Yes |
| Top only | Yes |
| All four sides | Yes |
| Bottom only | No |
| Right only | No |
| Contained crop | No |

**Do NOT use `page.mediabox.contains(page.cropbox)`.** The coordinator verified that it
gives false positives on three documents that behave correctly: a right-only overhang,
a bottom-only overhang (raw CropBox `[0 -60 612 792]`, which PyMuPDF reports as
`(0, 0, 612, 852)` against a MediaBox of `(0, 0, 612, 792)`), and a MediaBox with a
negative origin (`[-100 -100 512 692]`). It would refuse valid, real documents.
(Corrected during Merge A: Task 2's mutation check found the bottom-only case.)

**The ruling:**

- `replace_text`, `move_block` and `insert_block` raise `ValueError`, before mutating
  anything, when the page they would **draw on** matches the predicate. For
  `move_block`, that is the destination page. The error message names the cause.
- This follows the engine's established contract: refuse, rather than produce output
  that looks right but isn't.
- `redact_region`, `delete_block` and `replace_image` (via R4) **remain allowed** on
  such pages. The coordinator verified that redaction removes the text correctly at
  all four rotations there. **Redaction, the privacy-critical operation, is never
  refused because of a CropBox overhang.** (It is refused on pages with /UserUnit ≠ 1
  (R12), an invalid rotation, boxes PyMuPDF lays out inconsistently, or coordinates
  beyond 2^18pt: rulings C15, C16, C18.)

**Why refuse rather than compensate:**

- Compensating means offsetting every text draw by an amount that differs per edge and
  per rotation.
- That is real engineering for a rare configuration, and the PDF specification already
  resolves it by clipping the CropBox to the MediaBox.
- Compensation can be a later increment if a real document needs it.

**R6 — `insert_page` dimensions are set explicitly.**

Critique point 4 reproduced. Native `new_page` and `insert_page` both produce A4
`(0,0,595,842)` beside a `333 × 444` neighbour, including when appending. They never
inherit the neighbour's size.

- Each missing dimension defaults **independently** to the neighbour's **display**
  width or height. The neighbour is the page currently at `at_index`, or the last page
  when appending.
- The new page has rotation 0, and its dimensions are passed explicitly.
- **Rationale:** display dimensions are what the operator sees. A blank page inserted
  next to a page that is displayed in landscape should also display in landscape.
- **Tests must cover:** a rotated neighbour, a cropped neighbour, and partial
  overrides (width given with height defaulted, and the reverse).

**R7 — `duplicate_page` must handle the last page.**

Critique point 4 reproduced. On a one-page document, `fullcopy_page(0, 1)` raises `bad
page number(s)`.

- The call is specified as `fullcopy_page(src, -1 if src == page_count - 1 else
  src + 1)`.
- **F4 is strengthened.** `copy_page` aliases not only the content streams but **the
  page object itself** (page xrefs `[4, 4]`). Its exported output is
  `['', 'P1', 'P2', 'P3', '']`, against `['P0', 'P1', 'P2', 'P3', '']` for
  `fullcopy_page`.

**R8 — Duplicated pages keep their links' original targets.**

Critique point 6 found that a copied self-link still targets the original page,
index 0.

- "Independent" means independent *editing*, which is what was demonstrated. It does
  not mean navigation is retargeted to the copy.
- This is documented and pinned with a test.
- Retargeting links is out of scope.

**R9 — Claims are scoped to the evidence.**

Critique point 5.

- D1–D5 are **"the identified bounds and sampling defects"**, not a claim that the
  list is complete. R4 and R5 have already shown it is not.
- The implementer **must audit and report on:**
  - every drawing call site in `engine/`;
  - every direct or indirect consumer of page dimensions.
- The coordinator's grep found no code that uses `Page.width` or `Page.height` for
  coordinate math. That finding is **author-reported**, and the audit re-checks it.
- The implementer must verify stale-id behaviour in three cases: a page operation that
  succeeds, one that fails, and a `move_page` that is a no-op.
- The "227 tests pass" figure is **author-reported**. The critic could not see it.

**R10 — The coordinator's own corrections E1–E3 are folded in.**

- **E1.** `_validate_target` is called by **six** operations, not seven:
  `sanitize_document` takes no target. The lower-block test runs over those six.
- **E2.** `_insertion_rect` is also called by `insert_block`, which has no shrink loop.
  On a rotated page, lost headroom makes it **raise** rather than shrink. The test pins
  both behaviours.
- **E3.** The AI loop sends the model only `get_blocks_summary()`, which carries no page
  count, dimensions or rotation. A blank page has no blocks, so the model cannot see it
  at all.
  - **Merge B must add a pages summary (`index`, `width`, `height`, `rotation`) to the
    AI context.**
  - Without it, `rotate_page` and `insert_page` cannot be used through the
    natural-language path.

### What passed the critique and stands unchanged

- **F5's** final-index formula: all 16 `(src, final)` pairs pass.
- **F4's** requirement to use `fullcopy_page`.
- The **link claims**: after export, links survive both a move and a delete.
- Merge B's scope, and its API namespace `/api/pages/…`.
- **The review tiering:**
  - Fable reviews Merge A.
  - Fable reviews `duplicate_page`.
  - Fable does the final whole-branch review.

### Testing added by this revision

**Geometry matrix for Merge A.** Test every combination of five page types (ordinary,
contained crop, offset crop, oversized crop, fractional size) with four rotations (0,
90, 180, 270). In each case, assert that:

- bound checks accept visible content;
- sampling returns the true band colour;
- an erase has the right colour **in the exported bytes, re-parsed from scratch**.

**`replace_image` placement.** Test on offset and oversized crops, at every rotation.
Assert the image's exported bbox, **and** the pixel colours at both the requested
location and the previously shifted location.

**R5 refusal matrix.** Test all six overhang cases against each of the three
text-drawing operations.

- Refusal must match the predicate exactly, with no false positives.
- Include a negative-origin MediaBox regression, so that a future switch to
  `mediabox.contains(cropbox)` fails a test.

**R3 fractional page.** A `100.1 × 800.1` page samples correctly at all four
rotations. That includes rotation 0, which fails today.

**Mutation gate.** Extend the mutation gate to cover R2–R5. Revert each fix in turn, in
a scratch copy, and show that a named test fails for each.

---

## REVISION 2 — after the focused re-check of R2 and R5

**This revision is binding over everything above**, including REVISION 1.

The re-check was run by Codex `gpt-6-astra` on PyMuPDF 1.28.2 across **1,024
configurations**:

- four MediaBox origins, including a fractional one;
- all 16 combinations of CropBox overhang on the left, bottom, right and top;
- rotations 0, 90, 180 and 270;
- `/UserUnit` values 0.5, 1, 1.5 and 2.

Verdict: **REVISE BRIEF**. R2 passed cleanly; R5 has two real problems. The
coordinator re-ran the two decisive claims on the Windows target, and **both
reproduced**.

### Rulings

**R11 — Redaction fill is also misplaced. R5's claim about redaction is withdrawn.**

R5 said redaction was "verified correct at all four rotations". It was not. The
coordinator's check confirmed only that the text disappeared, not where the fill was
painted. That is a single-proxy verification of exactly the kind this project has been
bitten by before.

Re-run on MediaBox `[0 0 612 792]` with CropBox `[-40 -60 660 820]`:

| Rotation | Text removed? | Fill lands on the target? | Where the fill lands |
|---|---|---|---|
| 0 | Yes | Yes | — |
| 90 | Yes | Yes | — |
| 180 | Yes | **No** | `(168,507,251,524)` instead of `(80,507,163,524)` |
| 270 | Yes | **No** | `(168,419,251,436)` |

**What still holds:** the **privacy property**. The text is genuinely removed in every
case.

**What fails:** the **visible result**. The black box paints somewhere else, and it may
visually cover unrelated content that has *not* been removed. That undermines exactly
the "real redaction, not a black box" claim this product is built on.

**Fix:** wrap `add_redact_annot` **and** `apply_redactions` in the same temporary
`set_rotation(0)`, restoring rotation in a `finally`.

- The coordinator confirmed the fill lands on target at all four rotations.
- The critic confirmed it on all 256 unit-1 configurations.
- The fix lives in `_erase_region`, so it covers every caller: `redact_region` directly,
  and every `_clean_erase` caller — `delete_block`, `replace_text`, `move_block` and
  `replace_image`.

**Verification rule, binding from here on:** every redaction and erase test asserts on
**the exported fill rectangle, re-parsed from scratch**, not only on the text being
gone. A test that checks only one of these two is incomplete.

**R12 — Pages with `/UserUnit` ≠ 1 are refused. Draft ruling, pending the owner's decision.**

The problem is independent of any CropBox. On a plain page with `/UserUnit 1.5`, text
drawn at `(100,140)` in size 10 exports at `(150,210)` in size 15. This happens at every
rotation, because PyMuPDF reads in user-unit-scaled space and draws in unscaled space.

- Redaction fills scale too. For example, target `(35,65,95,90)` becomes
  `(35,52.5,125,90)`.
- The rotation-0 workaround does not help.
- The critic found **768 of 768** non-unit cases with wrong fill extents.

**Draft ruling:** every operation that draws text, paints a fill, or inserts an image
raises `ValueError`, before mutating anything, on a page whose `/UserUnit` is not 1.
The error message names the cause.

- That covers all six targeted operations, **including `redact_region`**.
- R2's bounds keep using the scaled `page.rect`. Shrinking the bounds would hide the
  drawing defect, not fix it.
- **Impact is bounded but real.** `/UserUnit` is mainly used for oversized
  engineering drawings. None of the 15 fixtures or the bundled sample carry it.

**Why this ruling is flagged for the owner.** It overturns a promise in R5: *"redaction
is never refused"*. The alternatives are both worse, but that trade-off is a trust and
privacy call, not an engineering one:

- **Allow redaction on these pages.** The text would still be removed, but the fill
  would be mis-sized. It is also untested whether a scaled redaction region removes
  *neighbouring* text, which would be silent data loss.
- **Compensate for the unit.** This is plausible, but the critic tested it for text
  only, not for redaction fills.

**R13 — Compensation for CropBox overhang is simple. R5's stated reason is withdrawn.**

R5 said it refused rather than compensated because compensation "differs per edge and
per rotation". The critic disproved that.

- **The drift is rotation-independent.** It equals
  `(min(crop.x0 - media.x0, 0), min(media.y1 - crop.y1, 0))`.
- **Two fixes passed all 256 unit-1 configurations, after export:**
  - translate both text APIs by the negative of that drift; or
  - temporarily replace the raw CropBox with `MediaBox ∩ CropBox`, draw, then restore.
- The critic also confirmed that **R5's predicate is itself correct**: it matched the
  observed drift in all 256 unit-1 configurations, including shifted and fractional
  origins and every combination of sides.

**Refusal stands, but as a scoped support-policy decision, not a geometric necessity.**
The compensation was proven with Helvetica and default text orientation only. The
engine's own text paths are untested with it:

- its three-tier font cascade, including embedded fonts;
- the shrink-to-fit loop;
- `insert_block`'s no-shrink contract.

Supporting these pages is a candidate for a later increment. The temporary-normalisation
approach is the leading option, since it has the same shape as the rotation-0
workaround.

**R14 — The image workaround is sound, but it proves nothing about other drawing.**

- **R4 stands.** The rotation-0 workaround passed the exported bbox and grey-pixel
  checks in all 1,024 configurations.
- Without the workaround, only 64 of 256 unit-1 image cases landed correctly.
- `draw_rect` is broken the same way, and at unit ≠ 1 even the workaround does not fix
  it. For example, `(80,100,100,120)` becomes `(80,90,110,120)`.
- The rectangles that redaction annotations report differ from the requested ones in
  156 of 256 cases. **Annotation geometry is not evidence that the applied redaction is
  correct.**
- **`replace_image` testing:** test its erase stage and its insert stage *separately*,
  each against exported bytes.
- **The R9 audit of every drawing call site now has a specific target:** any use of
  `draw_rect` or other drawing primitives in `engine/`. It must be reported.

**R15 — R2 stands, with its scope and comparison claims corrected.**

**The 1,024-configuration results:**

- **R2:** zero failures on extent, containment of visible text, off-page rejection and
  colour sampling.
- **`page.rotation_matrix`:** sampled the wrong colour in 640 cases, and differed from
  R2's matrix in 732.

**Corrected claims:**

- R2's claim that the matrix is "identical to `page.rotation_matrix` except on the
  oversized CropBox" is corrected. The two also differ under `/UserUnit`.
- R2's scope is **valid, intersecting boxes**. Malformed or disjoint boxes, and
  arbitrary annotation appearances, were not tested.

**R16 — The detection gates must use boxes resolved from the page tree.**

`/MediaBox` and `/CropBox` are **inheritable** from the page tree, so a direct
`xref_get_key(page.xref, 'CropBox')` returns `null` for an inherited box.

- The coordinator also observed that PyMuPDF's converted `page.mediabox` and
  `page.cropbox` are **not** in one consistent frame when the MediaBox origin is
  negative. For raw MediaBox `[-100 -100 512 692]` with no CropBox, `mediabox` reads
  `(-100,-100,512,692)` but `cropbox` reads `(-100,0,512,792)`.
- **R5's predicate and R12's `/UserUnit` check therefore run on raw PDF values, with
  inheritance resolved.**
- **Tests must include:**
  - an inherited CropBox;
  - an inherited MediaBox;
  - a negative-origin MediaBox.

### Owner's decision on R12 (2026-09-26) — final

The owner ruled **"Refuse with a warning for now, but we're going to build it."** R12 is
therefore **final**, not a draft. It adds two requirements:

- **The refusal must read as a warning to the operator, not as a crash.** The
  `ValueError` message must name the cause in plain language, state that nothing was
  changed, and state that support for this page type is planned. Suggested wording:
  *"Page N uses PDF /UserUnit scaling, which the editor does not support yet, so this
  operation was not applied and nothing was changed. Support is planned."* The existing
  400 handler already surfaces this message verbatim in the UI.
- **`/UserUnit` support is committed future work, not a maybe.** It becomes its own
  increment, to be specced after Merge B. That increment must:
  - scale drawing coordinates by `1/u` and font sizes by `1/u` (the critic's
    `q/u + offset` form passed 1,024 of 1,024 cases for text);
  - establish, with tests, whether a scaled redaction region removes only the
    intended text, before redaction is allowed on these pages;
  - cover the engine's own font cascade and shrink loops, not only Helvetica.

### Gate order for Merge A

Each check runs before any mutation. The first check that fails raises.

0. **Page transform unavailable** (the private binding is missing from the installed
   PyMuPDF): refuse any drawing operation with a message naming the installed version
   (Task 8 parked item, fixed at the final review).
1. **Invalid rotation** (MuPDF's own page transform is not `page.rotation`'s pattern at
   any positive scale, including a negative /UserUnit): refuse any drawing operation
   (C16).
2. **Boxes PyMuPDF lays out inconsistently** (no valid layout, a visible area that is
   empty or under 1pt, or a size that disagrees with `page.rect`): refuse any drawing
   operation (C15, C16).
3. **`/UserUnit` ≠ 1:** refuse any drawing operation (R12).
4. **Coordinates beyond 2^18pt** in mediabox, cropbox, rect or the transform's
   translation: refuse any drawing operation (C18).
5. **CropBox top-left overhang:** refuse text-drawing operations only (R5, rationale per
   R13).
6. **Otherwise:** proceed. Wrap `insert_image` (R4) and the redaction pair (R11) in the
   temporary rotation-0 workaround, and use R2's helpers for bounds and sampling.

All checks read PyMuPDF's interpreted geometry, never raw keys (C15); see
`engine/geometry.py:drawing_refusal`.

### Reference probes

The critic's probe scripts are named for the plan, and the re-check was run with them:

- `recheck_common.py`
- `recheck_fixes.py`
- `recheck_geometry.py` — the 1,024-case R2 matrix
- `recheck_drawing.py`

**The 1,024-configuration matrix is Merge A's regression set.** The implementer ports
it into `tests/test_geometry.py` with fixed parameters.
