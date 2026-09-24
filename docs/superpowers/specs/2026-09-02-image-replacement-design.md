# 8848 PDF — Image Replacement — Design

## Overview

Adds a single image-level editing operation, `replace_image`, to advance the
project's phase-1 roadmap ("rock-solid editing primitives" — text
replacement, redaction, sanitize, and delete/move/insert blocks are done;
image replacement and page operations are not). It is the engine's first
operation that manipulates an image rather than a `TextBlock`.

`replace_image` swaps the bitmap of **one placement** of an existing image
for caller-supplied image bytes, scaled to fit inside that placement's
existing rectangle with aspect ratio preserved. It does not move, resize, or
restyle the placement, and it does not touch any other placement of the same
underlying image — even one placed by the same PDF image object (`xref`)
elsewhere on the page.

It extends `engine/operations.py` alongside `redact_region`, `replace_text`,
`sanitize_document`, `delete_block`, `move_block`, and `insert_block`, and is
wired into the webui the same way every prior operation was — with one
deliberate exception: it has **no AI tool** this pass (see "AI tool" below).

## Non-goals (explicit, this pass)

- **No move or resize.** The new image is fit into the target placement's
  existing rectangle, unchanged. Repositioning or resizing an image is a
  separate later operation, mirroring how `move_block` is distinct from the
  content-editing ops.
- **No multi-placement / document-wide replacement.** If the same image
  object (`xref`) is placed in several spots, `replace_image` changes only
  the one placement the caller targeted; the others are left exactly as
  they were. "Replace this logo everywhere" is a phase-6 roadmap item
  ("global edits") and is explicitly not attempted here. This is why the
  operation does **not** use PyMuPDF's native `Page.replace_image(xref)`,
  which is xref-global.
- **No aspect-ratio distortion.** The supplied image is scaled to fit
  entirely within the target rectangle with its own proportions preserved
  (`keep_proportion=True`), centered, with the uncovered margin filled by
  the page's sampled background color. The supplied image is never
  stretched to the box, and never cropped to it.
- **No AI tool.** The AI instruction layer's tools all operate on text the
  model itself produces; the model cannot produce image bytes. `replace_image`
  is a manual-controls-only operation this pass. A future AI tool could take
  a URL or a reference to a pre-uploaded asset, but that is not designed
  here.
- **No orphan-resource cleanup.** When the targeted placement was the only
  placement of its `xref`, the original image object is left in the file,
  unreferenced. This matches how the insert-based text operations already
  behave (they never garbage-collect), and is reclaimed by a later
  `sanitize_document` / export-with-gc pass. Not this operation's job.
- **No change to any existing operation's behavior.** `replace_image` reuses
  `_validate_target` and `_clean_erase` unchanged; it does not modify them.

## Architecture

### Data model: `engine/document.py`

`Image` gains four fields (currently it carries only `bbox`):

```python
@dataclass
class Image:
    bbox: tuple[float, float, float, float]
    xref: int
    width: int          # pixel width of the current image
    height: int         # pixel height of the current image
    placement_count: int # how many times this xref is placed on this page
```

`bbox` remains the placement rectangle in PDF page coordinates. `xref` is
the PDF object number of the image (`0` for an inline image — see below).
`width`/`height` are the current image's pixel dimensions, surfaced so the
UI can show the operator what they are about to replace. `placement_count`
lets the UI warn "this image also appears N times on this page; those
placements will not change".

### Parser: `engine/parser.py`

The image list is built from `pdf_page.get_image_info(xrefs=True)` instead of
the current `get_image_info()`, so each entry carries `xref`. For each
entry:

- `bbox` — `tuple(info["bbox"])`, unchanged.
- `xref` — `info["xref"]`.
- `width` / `height` — `info["width"]` / `info["height"]`.
- `placement_count` — `len(pdf_page.get_image_rects(info["xref"]))` for a
  normal `xref`; `1` when `xref == 0` (an inline image has no queryable
  xref).

Inline images (`xref == 0`) are still listed — the operator should see them
— but `replace_image` rejects them as targets (they are embedded directly in
the content stream with no object to reason about).

If `get_image_info` returns the same `xref` more than once (one entry per
placement), every placement becomes its own `Image` in `page.images`, each
with its own `bbox` and the same `placement_count`. This is what lets the
registry give each placement a distinct id.

### Engine operation: `engine/operations.py`

```python
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB

def replace_image(
    handle: fitz.Document,
    page_index: int,
    target: Image,
    new_image_bytes: bytes,
) -> None:
```

Validation, before any mutation — every failure raises `ValueError` naming
the problem, with nothing modified:

1. `_validate_target(handle, page_index, target.bbox)` — the existing shared
   guard: `page_index` in range, `target.bbox` non-degenerate and not fully
   off-page. Returns `(page, rect)`.
2. `target.xref == 0` → raise: an inline image cannot be targeted.
3. `new_image_bytes` empty → raise.
4. `len(new_image_bytes) > _MAX_IMAGE_BYTES` → raise, naming the cap.
5. `fitz.Pixmap(new_image_bytes)` raises → re-raise as `ValueError`: the
   bytes are not a raster image PyMuPDF can decode (covers PNG, JPEG, and
   the other formats `Pixmap` accepts; rejects SVG, PDF, HTML, garbage).
   The decoded `Pixmap` is not otherwise used — `insert_image` re-decodes
   from the stream — this step is purely an up-front validity gate so a bad
   upload fails before the erase.

Mutation, in order:

1. `_clean_erase(page, rect)` — erase exactly the target placement's
   rectangle, filled with the page's background color sampled just outside
   it. This is the same helper `delete_block` / `move_block` / `replace_text`
   use; it is not modified.
2. `page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)` —
   PyMuPDF scales the new image to fit within `rect` preserving its
   proportions, centered. The letterbox margin (if the aspect ratios
   differ) shows the background color laid down in step 1.

`replace_image` never calls `page.replace_image`, so other placements of
`target.xref` — on this page or any other — are untouched. When
`target.xref` had exactly one placement, its image object is now
unreferenced; it is left in the file (see non-goals).

`replace_image` has exactly one failure mode that mutates and then
raises, and it is the draw itself. All *input* validation — page index,
bbox, inline-image guard, empty/over-cap bytes, and a full trial decode
of the stream — completes before `_clean_erase`, so every one of those
failures leaves the document untouched. `insert_image` is the one step
that can only be attempted after the erase, and it genuinely can raise:
observed on PyMuPDF 1.28.2 as a `ZeroDivisionError` out of its own
`calc_image_matrix` and as an `FzErrorSyntax` out of MuPDF's image
loader. When it does, the placement is left cleanly erased with nothing
drawn over it — the same "clean erase is a well-defined outcome" position
`move_block` and `replace_text` already take for their analogous edge.

Unlike an earlier draft of this spec, that path *is* specially handled:
the `insert_image` call is wrapped so the failure surfaces as the
`ValueError` this operation's contract promises for every other failure,
carrying the original exception's type and message and saying plainly
that the placement was erased. Letting a raw `ZeroDivisionError` or
`FzErrorSyntax` escape meant the web layer's `ValueError`-keyed 400
handlers never saw it and the operator got a bare non-JSON 500.

### Serialization: `export()` vs `snapshot()`

`export()` garbage-collects (`garbage=3`) and that is load-bearing twice
over: it is what physically removes the Info dictionary `scrub()` only
un-references, and it is what reclaims the original bitmap a
`replace_image` orphans when it swaps an xref's only placement. Neither
"removed" thing is actually gone from the file without it.

But on PyMuPDF 1.28.2 `tobytes(garbage=N)` with `N >= 2` compacts and
renumbers the **live** document's object table in place. `export()`
therefore performs its garbage pass on a throwaway reopened copy, never
on the handle it is given, and internal callers that only need a
parseable view of current state (`webui/session.py`'s registry refresh
after every operation) use `snapshot()` — a plain, non-collecting
`tobytes()` — instead. Both guarantees above are unaffected: an object
un-referenced in the original is still un-referenced in the copy.

Without this split, the garbage pass run after one `replace_image` left
the freshly-inserted image holding a dangling `/ColorSpace` reference, so
the **second** `replace_image` in a session destroyed the placement and
produced a document MuPDF could not parse. Any serializer on a path that
keeps editing the same handle must be `snapshot()`.

## API surface (webui)

### `webui/session.py`

The block registry gains a parallel **image registry**. `_state` gains an
`"images"` list; ids are drawn from the **same** `next_block_id` counter as
blocks, so a stale id from the frontend can never resolve to a block when it
meant an image or vice versa. The existing `_refresh_blocks()` is renamed
`_refresh_state()` and rebuilds both lists from the same re-parsed
throwaway `Document`; every current caller (`redact` / `replace` / `delete` /
`move` / `insert` / `sanitize_document`'s `finally`) calls the renamed
function.

- `_build_registries(doc)` replaces `_build_block_registry(doc)`: one pass
  over `doc.pages`, appending `{"id", "page_index", "block"}` entries to the
  block registry and `{"id", "page_index", "image"}` entries to the image
  registry, advancing the shared counter for each.
- `get_image(image_id: int) -> dict` — mirrors `get_block`, raising
  `LookupError` with the same "may be stale after an edit" message.
- `get_images_summary() -> list[dict]` — `[{id, page_index, bbox, width,
  height, placement_count}]`, mirroring `get_blocks_summary()`.
- `replace_image(image_id: int, new_image_bytes: bytes) -> None` — the thin
  wrapper, same shape as `delete` / `move`: resolve the id **outside** the
  `try` (so an unknown id raises before anything happens), call the engine
  operation inside, `_refresh_state()` in `finally`.

### `webui/main.py`

- `POST /api/replace-image` — **multipart/form-data**, not JSON, because the
  payload is binary. `image_id: int = Form(...)`, `file: UploadFile =
  File(...)`, mirroring `/api/upload`'s `UploadFile` handling. Reads the
  upload, calls `session.replace_image(image_id, data)`, returns the
  standard `{pages, blocks, images}` shape.
- `/api/upload` and `/api/state` response bodies gain an `images` array
  next to `blocks` (`session.get_images_summary()`). This is the only change
  to existing endpoints.
- Validation errors surface through the existing `ValueError` /
  `LookupError` → 400 exception handlers. No new error-handling code.

### Frontend (`webui/static/app.js`, `index.html`, `styles.css`)

- `renderState` / `renderPage` consume the new `state.images`. After the
  per-block overlays, `renderPage` adds one overlay element per image whose
  `page_index` matches, positioned over its `bbox` using the same
  page-image-relative coordinate math the block overlays already use.
- Each image overlay carries a caption (`320×80 px · appears 2× on this
  page` when `placement_count > 1`, just `320×80 px` otherwise), an
  `<input type="file" accept="image/*">`, and a **Replace** button. The
  button is wired through the existing `actGuarded` helper to a
  `multipart/form-data` `POST /api/replace-image` (`FormData` with
  `image_id` and the chosen `file`); `actGuarded`'s existing
  double-submit guard and failure-resync behavior apply unchanged.
- The image overlays live inside the existing **"Show manual editing
  controls"** section (like the insert panel), so file inputs stay out of
  the default AI-instruction view.
- Visual treatment is functional, not polished — consistent with how prior
  increments treated the manual controls as secondary to the AI path.

## AI tool

**None this pass.** Every tool in `webui/ai/tools.py` acts on text the model
generates; `replace_image` needs image bytes the model cannot produce.
Adding a degenerate tool now (e.g. one that can only reference an
already-uploaded asset that does not yet exist as a concept) would be
speculative. `SYSTEM_PROMPT`, `TOOLS`, and `_execute_tool` are unchanged.
`webui/ai/` is not touched.

## Testing strategy

Extends the existing deterministic suite the same way every prior increment
did.

### Fixtures (`tests/fixtures/generate_fixtures.py`)

- A single-image PDF: one page, one `insert_image` of a solid-color PNG at a
  known rectangle.
- A same-xref-twice PDF: one page, the **same** image stream placed at two
  non-overlapping rectangles (PyMuPDF reuses the xref when the same
  `stream`/`Pixmap` is inserted twice), so `placement_count == 2` and the
  two placements get distinct registry ids.
- A distinctly-colored replacement PNG (e.g. solid blue where the fixture
  images are solid red) and a non-square replacement PNG (for the
  aspect-ratio test), as helper byte builders.

### Engine-level (`tests/test_operations.py`)

- `replace_image` on the single-image fixture: after the call, sampling a
  pixel at the center of the target rect returns the replacement image's
  color, not the original's.
- `replace_image` on the same-xref-twice fixture, targeting placement 0:
  placement 0's center is the new color; **placement 1's center is
  unchanged** (the original color).
- `replace_image` with a non-square replacement into a square target box:
  the center is the new image's color, and a pixel near a corner of the box
  (outside the centered, aspect-preserved image but inside the box) is the
  page's background color — demonstrating contain + letterbox, not stretch.
- `replace_image` raising, with the document unmodified in each case:
  degenerate `bbox`, fully-off-page `bbox` (both via `_validate_target`);
  `target.xref == 0`; empty `new_image_bytes`; over-cap `new_image_bytes`;
  `new_image_bytes` that `fitz.Pixmap` cannot decode (e.g. `b"not an
  image"`).
- `replace_image` reporting a failed `insert_image` as a `ValueError`
  (not the raw `ZeroDivisionError`/`FzErrorSyntax`), with a message that
  says the placement was erased.
- **Against the exported bytes, not the live handle**: the happy-path
  swap and the placement-isolation case are both asserted after
  `parse(export(handle))`. Plus the regression this increment needed —
  two `replace_image` calls on one handle with an `export()` in between,
  re-parsed, asserting the *second* replacement landed — and its
  route-level twin, two sequential `POST /api/replace-image` calls in one
  session followed by `GET /api/export`. Sampling only the live handle is
  what let both the metadata leak and the second-replacement corruption
  ship.
- A regression check that the full existing `tests/test_operations.py`
  still passes after `_clean_erase` / `_validate_target` are shared into a
  new caller (they are used unchanged, so this should be automatic).

### Webui integration (`tests/test_webui.py`)

- `POST /api/replace-image` multipart round-trip on the single-image
  fixture: 200, response body has `images`, and a follow-up `GET /api/state`
  shows the image list.
- `/api/state` and `/api/upload` now include `images` (assert the key and
  shape).
- The "no document loaded" error path for `/api/replace-image`, matching
  every other route's equivalent test.
- Unknown `image_id` → 400 via the `LookupError` handler.

### Parser / model (`tests/test_parser.py`)

- Parsing the single-image fixture yields one `Image` with the expected
  `xref` (`> 0`), `width`, `height`, and `placement_count == 1`.
- Parsing the same-xref-twice fixture yields two `Image`s with equal `xref`
  and `placement_count == 2`.

## Explicitly out of scope (this pass)

- Moving or resizing an image placement.
- Document-wide / multi-placement image replacement ("replace this logo
  everywhere") — phase-6 global edits.
- Any use of `Page.replace_image` (xref-global by nature).
- An AI tool for image replacement.
- Cleanup of an image object left orphaned when its sole placement is
  replaced.
- Cropping / cover-fit as an option — contain-fit is the only mode.
- Any UI beyond a functional manual-controls extension.
