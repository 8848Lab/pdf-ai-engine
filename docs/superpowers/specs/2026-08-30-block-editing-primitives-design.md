# 8848 PDF — Block Editing Primitives (Delete / Move / Insert) — Design

## Overview

Adds three new block-level editing operations to close the gap identified in
the project's phase-1 roadmap ("rock-solid editing primitives", see the
roadmap: text replacement, redaction, and sanitize are done; delete/move/
insert blocks, image replacement, and page operations are not):

- **`delete_block`** — clean removal of a text block's content, background-
  filled so the page shows no trace, as opposed to `redact_region`'s
  deliberate black-bar "this was removed" signal.
- **`move_block`** — relocate an existing block's own text (at its own font
  and size) to a new position, optionally on a different page.
- **`insert_block`** — draw brand-new text into an empty target region that
  has no corresponding source block.

All three extend `engine/operations.py` alongside `redact_region`,
`replace_text`, and `sanitize_document`, and are wired into the webui and the
AI instruction layer the same way every prior operation was.

## Non-goals (explicit, this pass)

- No resizing as part of `move_block` — it preserves the block's own
  width/height, only relocating position. A future operation can add
  resize/restyle if real demand shows up.
- No automatic font/size inference for `insert_block` beyond the plain
  Helvetica default when `font` is omitted -- no attempt to sample a nearby
  block's style. `size` is always required.
- No shrink-retry for `insert_block` -- the caller chose the size
  deliberately; a poor fit is a caller error to fix (smaller size or bigger
  bbox), not something the engine silently overrides. This differs
  deliberately from `move_block`, which DOES shrink-retry, because
  `move_block` is preserving an *existing* size as a best-effort target the
  same way `replace_text` does, not accepting a fresh explicit choice.
- No change to `redact_region`, `replace_text`, or `sanitize_document`'s
  existing behavior -- the one shared refactor (`_clean_erase`, see
  Architecture) does not change what `replace_text` already does or already
  tests as passing.
- No image-block support in any of the three operations this pass -- all
  three operate on `TextBlock` targets (or, for insert, a target bbox with
  no source block at all). Image replacement is its own later roadmap item.

## Architecture

### Shared refactor: `_clean_erase` and `_draw_shrink_to_fit`

`replace_text` currently inlines two sequences that the new operations also
need. Both are extracted as private helpers with no behavior change --
`replace_text` is rewritten to call them instead of its current inline code,
verified by the existing test suite passing unchanged.

**`_clean_erase(page, rect) -> None`** -- "erase the target rect, sample the
background color just outside it, fill the erased rect with that color":

```python
def _clean_erase(page: fitz.Page, rect: fitz.Rect) -> None:
    fill = _sample_background_color(page, rect)
    _erase_region(page, rect, fill=fill)
```

Used directly by `delete_block`, and by `move_block` for its erase-the-source
step.

**`_draw_shrink_to_fit(page, rect, fontname, font, text, starting_size) -> None`**
-- `replace_text`'s existing shrink-retry loop (try `insert_textbox` at
`starting_size`, step down by `_SHRINK_STEP` until it fits or
`_SHRINK_FLOOR_RATIO * starting_size` is reached, raising `ValueError` naming
the size/floor if nothing fit), with the font-registration step
(`page.insert_font` for a non-Base-14 resolved font) folded in the same way
`replace_text` already orders it -- after the erase, before the draw loop,
so `apply_redactions` never garbage-collects an unreferenced resource. Used
by `replace_text` (unchanged behavior) and by `move_block`'s destination
draw step.

### `delete_block(handle, page_index, target: TextBlock) -> None`

```python
def delete_block(handle: fitz.Document, page_index: int, target: TextBlock) -> None:
    page, rect = _validate_target(handle, page_index, target.bbox)
    _clean_erase(page, rect)
```

No shrink loop, no font resolution -- there is nothing to draw. Raises
`ValueError` only via `_validate_target` (bad `page_index`/degenerate or
off-page `target.bbox`), the same as every other operation's shared
validation.

### `move_block(handle, page_index, target: TextBlock, destination_page_index=None, target_position=None, offset=None) -> None`

```python
def move_block(
    handle: fitz.Document,
    page_index: int,
    target: TextBlock,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
```

Validation, before any mutation:

- Exactly one of `target_position`/`offset` must be given -- both or
  neither raises `ValueError` naming the problem.
- `page_index` (source) validated via `_validate_target` against
  `target.bbox`, as usual.
- `destination_page_index` (defaulting to `page_index` if omitted) validated
  against `handle.page_count` the same way `_validate_target` validates
  `page_index` today.
- The destination bbox is computed (translate `target.bbox` so its top-left
  corner is `target_position`, or by `offset` added to the current top-left
  corner -- width/height unchanged either way) and validated with the same
  degenerate/off-page checks `_validate_target` already applies, against the
  *destination* page's rect.
- Font resolution for the destination draw runs via the existing
  `_select_font(handle, destination_page, target, target.text)` -- reused
  exactly as-is (it already takes a `TextBlock` and the text being drawn;
  passing `target.text` back as `new_text` re-resolves/re-embeds the source
  font onto the destination page, which matters whenever
  `destination_page_index != page_index`). A destination that cannot render
  every character of `target.text` in any tier raises the same `ValueError`
  `_select_font` already raises, before any mutation.

Mutation, in order:

1. `_clean_erase` on the *source* rect.
2. `_draw_shrink_to_fit` on the destination page/rect with the resolved
   font/fontname and `target.text`, starting at `target.size` -- exactly
   `replace_text`'s own shrink-retry behavior, reused rather than
   reimplemented.

If the shrink-retry never fits, `move_block` raises `ValueError` (naming the
destination, same message shape as `replace_text`'s) with the source already
cleanly erased -- the one case, like `replace_text`, where this function
mutates and then fails, by the same deliberate design (erasing at the source
is a clean, well-defined outcome; leaving the original content in an
undefined half-drawn state at the destination would not be).

### `insert_block(handle, page_index, bbox, text, size, font=None) -> None`

```python
def insert_block(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
```

Validation, before any mutation: `text` non-empty (same message style as
`replace_text`'s), `size` positive, `bbox` validated via
`_validate_target`. `font` defaults to `"helvetica"` when omitted. Whatever
name `font` resolves to, only Tiers 2/3 of `_select_font`'s cascade apply --
there is no source block to extract an embedded font from (Tier 1), so a
`font` value that is already a Base-14 name is used as-is (Tier 2), and one
that is not gets the same bold/italic-matched Base-14 substitute
`_base14_style_match` already computes for `replace_text`'s non-Base-14
`target.font` case (e.g. a caller-supplied `"Arial-Bold"` resolves to
`"helvetica-bold"`, not a failed lookup for an embedded resource named
`"Arial-Bold"`, since none exists to find). If even the style-matched Base-14
font can't render every character of `text`, Tier 3 (the bundled
broad-coverage font) is tried before raising -- the same fallback chain
`_select_font` already provides, just entered one tier later since Tier 1
has nothing to offer here.

Mutation: a single `insert_textbox` call at the given `size` via the shared
draw helper *without* the shrink-retry loop -- one attempt, and a negative
return value raises `ValueError` immediately (naming `bbox`, `size`, and
`text`'s length, suggesting a smaller `size` or a larger `bbox`) rather than
silently shrinking. Nothing is erased first (there is no target content to
remove), so a failed attempt leaves the document completely unmodified.

## API surface (webui)

Follows the existing `redact`/`replace` pattern exactly -- `webui/session.py`
gains three thin wrappers using the same `get_block()`/`get_handle()`-
outside-try, mutate-and-`_refresh_blocks()`-inside-`finally` shape:

- `delete(block_id: int) -> None`
- `move(block_id: int, destination_page_index=None, target_position=None, offset=None) -> None`
- `insert(page_index: int, bbox, text: str, size: float, font: str | None = None) -> None`

`webui/main.py` gains matching routes, each returning the standard
`{pages, blocks}` shape every mutating endpoint already returns:

- `POST /api/delete` `{block_id}`
- `POST /api/move` `{block_id, destination_page_index?, target_position?, offset?}`
- `POST /api/insert` `{page_index, bbox, text, size, font?}`

Validation errors surface through the existing `ValueError`/`LookupError` →
400 exception handlers, no new error-handling code needed.

**Frontend:** the existing "Show manual editing controls" section gains a
Delete button alongside each block's Redact/Replace controls, and a small
Move form (destination page, and either a position or an offset). Insert
gets its own small form (page, bbox, text, size, optional font) since it has
no existing block row to attach to. Exact layout is a plan-time decision,
not pinned down further here.

## AI tool

Three new entries in `webui/ai/tools.py`'s `TOOLS`, alongside
`redact_block`/`replace_block`/`sanitize_document`, same `strict: true`
schema style:

```json
{
  "name": "delete_block",
  "description": "Cleanly remove a text block's content with no visible trace left behind (as opposed to redact_block, which leaves a black bar). Use this when the instruction asks to delete or remove something without any replacement and without a visible redaction marker.",
  "input_schema": {
    "type": "object",
    "properties": {
      "block_id": {"type": "integer", "description": "The id of the block to delete, from the block list you were given."}
    },
    "required": ["block_id"],
    "additionalProperties": false
  },
  "strict": true
}
```

```json
{
  "name": "move_block",
  "description": "Relocate an existing text block's own content (unchanged text, font, and size) to a new position, optionally on a different page. Give exactly one of target_position or offset a real value -- pass the other as null, never both non-null.",
  "input_schema": {
    "type": "object",
    "properties": {
      "block_id": {"type": "integer", "description": "The id of the block to move, from the block list you were given."},
      "destination_page_index": {"type": ["integer", "null"], "description": "Page to move the block to, or null to keep it on its current page."},
      "target_position": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[x, y] -- the new top-left corner, in the destination page's own coordinates, or null. Give this OR offset a real value, never both non-null."},
      "offset": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[dx, dy] -- shift relative to the block's current position, or null. Give this OR target_position a real value, never both non-null."}
    },
    "required": ["block_id", "destination_page_index", "target_position", "offset"],
    "additionalProperties": false
  },
  "strict": true
}
```

```json
{
  "name": "insert_block",
  "description": "Draw brand-new text into an empty region of a page -- for adding content that has no existing block to replace. Requires an explicit font size; there is no existing block to infer it from.",
  "input_schema": {
    "type": "object",
    "properties": {
      "page_index": {"type": "integer", "description": "The page to insert into."},
      "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4, "description": "[x0, y0, x1, y1] -- the region to draw the text into."},
      "text": {"type": "string", "description": "The text to insert."},
      "size": {"type": "number", "description": "Font size in points. Choose a size consistent with surrounding text if the instruction implies matching it."},
      "font": {"type": ["string", "null"], "description": "A Base-14 font name (e.g. helvetica, times-roman, courier-bold), or null to default to plain Helvetica."}
    },
    "required": ["page_index", "bbox", "text", "size", "font"],
    "additionalProperties": false
  },
  "strict": true
}
```

**Why every property is listed as `required` with nullable types for the
genuinely-optional ones**, rather than the simpler shape every prior tool in
this codebase uses (only truly-mandatory keys in `required`): OpenAI's
strict function-calling mode -- which the `openai_compatible` provider
passes `strict` straight through to (`webui/ai/providers/openai_compatible.py`'s
`_translate_tools`) -- requires every property in `input_schema` to appear
in `required`; a field that is conceptually optional must instead have a
nullable type (`["type", "null"]`), with the model passing `null` to mean
"not given." `redact_block`/`replace_block`/`sanitize_document`/`delete_block`
never needed this because every one of their properties was already
mandatory. Anthropic and Ollama do not enforce this constraint and tolerate
the nullable-and-required shape fine, so one schema works correctly across
all three providers without per-provider schema variants.

`SYSTEM_PROMPT` is updated to describe all six tools, and to state the
`target_position`-XOR-`offset` rule for `move_block` explicitly (mirroring
how the schema's own descriptions state it) so a model does not need to
infer it. `_execute_tool` gains three branches following the existing
`redact_block`/`replace_block` pattern: resolve the block (for delete/move)
or validate inputs (for insert), call the matching `session` function,
return a short human-readable summary of what happened, relying on the
existing outer `except (ValueError, LookupError)` for error handling -- no
new exception-handling code, consistent with every prior tool.

## Testing strategy

Extends the existing deterministic suite the same way every prior increment
did:

- **Engine-level (`tests/test_operations.py`):** `delete_block` on a fixture
  block, confirming the block's text is gone from `get_text()` and the
  region shows the sampled background color, not black, distinguishing it
  from `redact_region`. `move_block` same-page (position and, separately,
  offset), and cross-page (needs a fixture with at least two pages and a
  target block on page 0 -- `tests/fixtures/multi_page.pdf` already exists
  and has blocks on 3 pages, reusable here), confirming the source is
  cleanly erased and the destination shows the moved text in the same font/
  size. `move_block` raising on both-given and neither-given
  `target_position`/`offset`. `move_block` raising when the destination
  can't fit even at the shrink floor, with the source left cleanly erased
  (mirrors `replace_text`'s existing "doesn't fit" test). `insert_block`
  drawing into an empty region, confirming the new text is extractable
  afterward. `insert_block` raising immediately (no partial draw) when the
  text doesn't fit `bbox` at the given `size` -- no shrink attempted,
  distinguishing it from `move_block`'s shrink-retry. `insert_block` with an
  omitted `font` defaulting to Helvetica. A regression check that
  `replace_text`'s full existing test file still passes unchanged after the
  `_clean_erase`/`_draw_shrink_to_fit` refactor.
- **Webui integration (`tests/test_webui.py`):** `POST /api/delete`,
  `POST /api/move` (same-page and cross-page), `POST /api/insert`, each
  following the existing `redact`/`replace` test pattern (including the "no
  document loaded" error-path tests every prior route has).
- **AI-layer (`tests/test_ai.py`):** the three new tool schemas registered
  correctly (mirroring the existing `sanitize_document`-is-registered
  test), and `_execute_tool` branches for delete/move/insert, including
  `move_block`'s both-given/neither-given error surfaced correctly as a
  tool error.

## Explicitly out of scope (this pass)

- Resizing a block as part of a move.
- Style/font inference for `insert_block` beyond the plain Helvetica
  default.
- Image-block delete/move/insert (separate roadmap item).
- Any UI beyond a functional (not polished) manual-controls extension --
  visual polish is not this pass's goal, consistent with how prior
  increments treated the manual controls as secondary to the AI-instruction
  path.
