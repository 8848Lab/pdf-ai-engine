# Block Editing Primitives (Delete / Move / Insert) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `delete_block`, `move_block`, and `insert_block` to the engine, wired into the webui and the AI instruction layer, closing out the remaining phase-1 "rock-solid editing primitives" roadmap items alongside the already-shipped `redact_region`/`replace_text`/`sanitize_document`.

**Architecture:** Three new functions in `engine/operations.py`, built on two helpers extracted (with no behavior change) from `replace_text`'s existing erase/draw logic. `delete_block` is a clean background-fill erase (no black box, unlike `redact_region`). `move_block` erases the source and redraws the same text/font/size at a new position, same-page or cross-page. `insert_block` draws brand-new text into an empty region with no source block, no shrink-retry. Each gets a `webui/session.py` wrapper, a `webui/main.py` route, and an AI tool entry, mirroring every prior operation's exact pattern.

**Tech Stack:** Python, PyMuPDF (`pymupdf` as `fitz`) 1.28.2, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-block-editing-primitives-design.md`

## Global Constraints

- No change to `redact_region`, `replace_text`'s (or `sanitize_document`'s) *behavior* -- the `_clean_erase`/`_draw_shrink_to_fit` refactor of `replace_text`'s internals must leave its existing test suite passing unchanged.
- `delete_block` never draws a black box -- background-fill only, distinguishing it from `redact_region`.
- `move_block` requires exactly one of `target_position`/`offset` -- both or neither raises `ValueError` before any mutation.
- `insert_block` requires an explicit `size` (never optional); `font` defaults to `"helvetica"` when omitted. No shrink-retry -- a poor fit raises `ValueError` immediately with nothing drawn.
- Every operation's contract: every check that can run without touching the page runs first; the only operation allowed to mutate and then raise is `move_block` (mirroring `replace_text`'s existing "doesn't fit" contract) -- `delete_block` and `insert_block` never mutate before a later check could still fail.
- No image-block support in this pass -- all three operations target `TextBlock`s (or, for insert, an empty bbox with no source block).

---

### Task 1: Shared refactor + `delete_block`

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Produces: `_clean_erase(page: fitz.Page, rect: fitz.Rect) -> None`, `delete_block(handle: fitz.Document, page_index: int, target: TextBlock) -> None`.
- `replace_text`'s public signature and behavior are unchanged -- only its internals are refactored to call `_clean_erase`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_operations.py` (add `delete_block` to the existing `from engine.operations import (...)` block, alphabetically):

```python
def test_delete_block_removes_text_and_fills_with_background_not_black():
    # colored_background.pdf's block sits over a light-blue (0.7, 0.85, 1.0)
    # rect, drawn specifically so a wrong fill (e.g. black, which is what
    # redact_region draws) is trivially distinguishable from a correct clean
    # erase. Verified empirically: the fixture's real fill pixel is
    # (178, 216, 255).
    pdf_bytes = (FIXTURES / "colored_background.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REPLACE-ME-SHORT" in b.text)

    delete_block(handle, page_index=0, target=target)

    assert "REPLACE-ME-SHORT" not in page.get_text()

    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width
    cx = int((target.bbox[0] + target.bbox[2]) / 2 * zoom)
    cy = int((target.bbox[1] + target.bbox[3]) / 2 * zoom)
    pixel = pixmap.pixel(cx, cy)
    assert pixel[0] > 100 and pixel[1] > 100 and pixel[2] > 100, (
        f"expected the erased region to show the sampled light-blue "
        f"background, got pixel {pixel} -- looks like a black box instead"
    )
    handle.close()


def test_delete_block_raises_on_degenerate_bbox_and_does_not_mutate():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    original_text = page.get_text()
    target = replace(doc.pages[0].text_blocks[0], bbox=(100.0, 100.0, 100.0, 200.0))

    with pytest.raises(ValueError):
        delete_block(handle, page_index=0, target=target)

    assert page.get_text() == original_text
    handle.close()


def test_delete_block_raises_on_page_index_out_of_range():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].text_blocks[0]

    with pytest.raises(ValueError):
        delete_block(handle, page_index=handle.page_count, target=target)

    handle.close()
```

(`replace` here is `dataclasses.replace`, already imported at the top of this file as `from dataclasses import replace`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k delete_block -v`
Expected: FAIL with `ImportError: cannot import name 'delete_block'`.

- [ ] **Step 3: Refactor `replace_text`'s internals (no behavior change)**

In `engine/operations.py`, add these two private helpers directly after `_sample_background_color` (which both depend on) and before the `# Shrink-retry loop tuning` comment block:

```python
def _clean_erase(page: fitz.Page, rect: fitz.Rect) -> None:
    """Erase rect and fill it with the page's own sampled background color,
    leaving no visible trace. Shared by replace_text's erase step,
    delete_block, and move_block's erase-the-source step. See
    _sample_background_color for the sampling method and its solid-color-
    background limitation.
    """
    fill = _sample_background_color(page, rect)
    _erase_region(page, rect, fill=fill)
```

Directly after `_insertion_rect` (which it depends on for its docstring's cross-reference, though it does not call it), add:

```python
def _draw_shrink_to_fit(
    page: fitz.Page,
    insert_rect: fitz.Rect,
    resolved_fontname: str,
    resolved_font: fitz.Font,
    text: str,
    starting_size: float,
    context_bbox: fitz.Rect,
) -> None:
    """Register resolved_font on page if it is not a Base-14 name, then draw
    text into insert_rect starting at starting_size, retrying at
    _SHRINK_STEP-smaller sizes down to _SHRINK_FLOOR_RATIO * starting_size
    until it fits. Shared by replace_text and move_block's destination draw
    step -- this is replace_text's original inline shrink-retry loop,
    extracted with no behavior change.

    Registration happens here, not earlier, for the same reason
    replace_text's original inline code registered it here:
    apply_redactions (already run by the caller before this is called)
    garbage-collects a page-registered font resource not yet referenced by
    any content stream, so registering any earlier would risk losing it.

    context_bbox is the caller's own pre-inflation target region, used only
    in the ValueError message on failure (naming the region the caller
    actually asked about, not this function's inflated drawing box) --
    replace_text passes target.bbox, move_block passes the destination bbox
    before _insertion_rect's inflation.

    Raises:
        ValueError: text does not fit insert_rect at any attempted size
            down to the shrink floor. Names context_bbox, the smallest size
            actually attempted, and the floor.
    """
    if resolved_fontname not in fitz.Base14_fontdict:
        page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)

    fontsize = starting_size
    floor = starting_size * _SHRINK_FLOOR_RATIO
    smallest_attempted = fontsize
    remaining_space = -1.0
    while fontsize >= floor:
        smallest_attempted = fontsize
        try:
            remaining_space = page.insert_textbox(
                insert_rect,
                text,
                fontname=resolved_fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            raise ValueError(
                f"failed to draw text into region {tuple(insert_rect)} at "
                f"{fontsize:.2f}pt: {type(exc).__name__}: {exc}"
            ) from exc
        if remaining_space >= 0:
            return
        fontsize *= _SHRINK_STEP

    raise ValueError(
        f"text ({len(text)} chars) does not fit within the target region "
        f"{tuple(context_bbox)} at any attempted size down to "
        f"{smallest_attempted:.2f}pt (the shrink floor is {floor:.2f}pt, "
        f"50% of the original {starting_size}pt)"
    )
```

Now find this EXACT block in `replace_text` (it runs from the `erase_rect =` line to the function's closing `raise ValueError` -- the whole "erase, register font, shrink-retry loop, raise if nothing fit" tail of the function):

```python
    erase_rect = fitz.Rect(rect.x0, rect.y0, insert_rect.x1, rect.y1)

    # Sample around what is actually erased, not around the drawing box:
    # _sample_background_color reads a thin margin just *outside* the rect
    # it is given, so passing the taller insert_rect would probe points
    # that are neither erased nor representative of the erased region's
    # own surroundings.
    fill = _sample_background_color(page, erase_rect)

    # Erased once, up front. A failed insert_textbox attempt below draws
    # nothing at all (see the docstring's Step 1 findings), so there is
    # never partial content from a larger-fontsize attempt for a smaller
    # retry to stack on top of: one erase is enough to keep every attempt
    # starting from a clean, background-colored rect.
    _erase_region(page, erase_rect, fill=fill)

    # _select_font deliberately does NOT register a Tier 1/Tier 3 font on
    # `page` itself (Tier 2 is a Base-14 name, needing no page resource at
    # all either way) -- registering it before the erase above would be
    # pure wasted work: confirmed empirically on PyMuPDF 1.28.2,
    # apply_redactions (just run above) garbage-collects page resources not
    # yet referenced by any content stream, and a font registered but not
    # yet drawn with is exactly that. So this is the ONLY place a Tier 1/
    # Tier 3 font actually gets embedded on `page`, using the same alias
    # and buffer _select_font resolved (fitz.Font.buffer round-trips the
    # original bytes for both a fontbuffer-constructed Font and the bundled
    # 'cjk' font) for the draw loop below.
    if resolved_fontname not in fitz.Base14_fontdict:
        page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)

    fontsize = target.size
    floor = target.size * _SHRINK_FLOOR_RATIO
    smallest_attempted = fontsize
    remaining_space = -1.0
    while fontsize >= floor:
        smallest_attempted = fontsize
        try:
            remaining_space = page.insert_textbox(
                insert_rect,
                new_text,
                fontname=resolved_fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            # Defense in depth. Every failure mode known on PyMuPDF 1.28.2
            # is already excluded by the validation above, and a "doesn't
            # fit" outcome is a negative return value rather than an
            # exception. Anything that still escapes here is unanticipated
            # -- re-raise it as the ValueError this function's contract
            # promises so callers never see a bare Exception.
            raise ValueError(
                f"failed to draw new_text into the target block's region "
                f"{tuple(insert_rect)} at {fontsize:.2f}pt: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if remaining_space >= 0:
            break
        fontsize *= _SHRINK_STEP

    if remaining_space < 0:
        # erase_rect is still cleanly erased -- confirmed above that a
        # failed insert_textbox call never draws partial content, so there
        # is nothing left to clean up before raising.
        #
        # The message names the caller's own target.bbox, not the internal
        # inflated/erased rects: those are this function's private geometry
        # and would read as unrelated to what the caller actually passed.
        raise ValueError(
            f"new_text ({len(new_text)} chars) does not fit within the target "
            f"block's region {tuple(target.bbox)} at any attempted size down to "
            f"{smallest_attempted:.2f}pt (the shrink floor is "
            f"{floor:.2f}pt, 50% of the original {target.size}pt) -- "
            f"replace_text does not cascade reflow into neighboring content; "
            f"shorten the text or use a different operation"
        )
```

Replace that whole block with:

```python
    erase_rect = fitz.Rect(rect.x0, rect.y0, insert_rect.x1, rect.y1)

    # Sample around what is actually erased, not around the drawing box:
    # _sample_background_color reads a thin margin just *outside* the rect
    # it is given, so passing the taller insert_rect would probe points
    # that are neither erased nor representative of the erased region's
    # own surroundings.
    _clean_erase(page, erase_rect)

    # _select_font deliberately does NOT register a Tier 1/Tier 3 font on
    # `page` itself -- see _select_font's docstring and _draw_shrink_to_fit's
    # own registration-ordering comment for why that registration is
    # deferred to here.
    _draw_shrink_to_fit(
        page, insert_rect, resolved_fontname, resolved_font, new_text,
        target.size, context_bbox=target.bbox,
    )
```

`_draw_shrink_to_fit` fully replaces the deleted block, including both its `ValueError` cases (the `insert_textbox` exception case and the "doesn't fit even shrunk" case) -- nothing from the deleted block needs to survive elsewhere.

This step touches only `replace_text`'s internals -- its signature, its docstring's contract, and every check before the erase step (everything above the `erase_rect = ...` line) are unchanged. `_SHRINK_STEP`, `_SHRINK_FLOOR_RATIO`, `_erase_region`, `_sample_background_color`, `_insertion_rect` all stay exactly as they are; `_clean_erase`/`_draw_shrink_to_fit` are the only new code, and they call those unchanged helpers rather than duplicating their logic.

- [ ] **Step 4: Run the FULL existing suite to confirm zero regressions**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: every pre-existing test still passes -- this refactor must not change any observable behavior of `replace_text`. If anything in `test_replace_text_*` fails, the refactor introduced a real behavior change and must be fixed before continuing; do not adjust the test to match new behavior.

- [ ] **Step 5: Add `delete_block`**

Directly after `replace_text`'s closing line (before `get_metadata_summary`), add:

```python
def delete_block(handle: fitz.Document, page_index: int, target: TextBlock) -> None:
    """Cleanly remove target's content from the page, filling the erased
    region with the page's own sampled background color -- no visible
    trace, unlike redact_region's deliberate black bar. See the design
    spec's "Architecture" section for why this is a distinct operation
    rather than a block-id-based wrapper around redact_region.

    Raises:
        ValueError: see _validate_target.
    """
    page, rect = _validate_target(handle, page_index, target.bbox)
    _clean_erase(page, rect)
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k delete_block -v`
Expected: all 3 new tests PASS.

- [ ] **Step 7: Run the full suite again**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (baseline + 3 new).

- [ ] **Step 8: Commit**

```bash
git add engine/operations.py tests/test_operations.py
git commit -m "refactor: extract _clean_erase/_draw_shrink_to_fit from replace_text; add delete_block"
```

---

### Task 2: `move_block`

**Files:**
- Modify: `engine/operations.py`
- Modify: `tests/fixtures/generate_fixtures.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: `_clean_erase`, `_draw_shrink_to_fit`, `_validate_target`, `_select_font`, `_insertion_rect` (Task 1 and pre-existing).
- Produces: `move_block(handle, page_index, target, destination_page_index=None, target_position=None, offset=None) -> None`.

- [ ] **Step 1: Add the cross-page fixture**

In `tests/fixtures/generate_fixtures.py`, add (after `make_embedded_custom_font`, before the `if __name__ == "__main__":` block):

```python
def make_move_target() -> None:
    """Two pages: page 0 has a block whose font is genuinely embedded under
    an alias that is NOT a Base-14 name; page 1 has no fonts embedded at
    all. move_block's cross-page fixture -- proves a cross-page move
    gracefully falls back to a Base-14 substitute (Tier 2 of _select_font)
    when the destination page does not already have the source's font,
    rather than crashing. Verified empirically: Tier 1 is genuinely tried
    against the destination page and genuinely fails to find a match here,
    exercising the real fallback path rather than assuming it.
    """
    doc = fitz.open()
    page0 = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page0.insert_font(fontname="MoveTargetFont", fontbuffer=helv.buffer)
    page0.insert_text(
        (72, 100),
        "Move target block MOVE-ME-777.",
        fontsize=12,
        fontname="MoveTargetFont",
    )
    doc.new_page(width=612, height=792)  # page 1: intentionally blank
    doc.save(FIXTURES_DIR / "move_target.pdf")
    doc.close()
```

Add `make_move_target()` to the `if __name__ == "__main__":` block's call sequence (after `make_embedded_custom_font()`).

- [ ] **Step 2: Run the generator and verify the new fixture exists**

Run: `./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py`
Expected: `tests/fixtures/move_target.pdf` is created; every previously-existing fixture file is regenerated identically (confirm with `git status` -- only `move_target.pdf` should show as new; if any existing fixture shows as modified, something about the generator script changed unintentionally and must be investigated before continuing).

- [ ] **Step 3: Write the failing tests**

Add to `tests/test_operations.py` (add `move_block` to the `from engine.operations import (...)` block; add `import dataclasses` is not needed, `replace` is already imported from `dataclasses`):

```python
def test_move_block_same_page_to_an_absolute_position():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    move_block(handle, page_index=0, target=target, target_position=(72.0, 400.0))

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" in remaining_text

    moved_y = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "REDACT-ME-12345" in span["text"]:
                    moved_y = span["bbox"][1]
    assert moved_y is not None
    assert abs(moved_y - 400.0) < 5.0, f"expected the moved block near y=400, got y={moved_y}"
    handle.close()


def test_move_block_same_page_by_a_relative_offset():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    original_y = target.bbox[1]

    move_block(handle, page_index=0, target=target, offset=(0.0, 200.0))

    moved_y = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "REDACT-ME-12345" in span["text"]:
                    moved_y = span["bbox"][1]
    assert moved_y is not None
    assert abs(moved_y - (original_y + 200.0)) < 5.0
    handle.close()


def test_move_block_raises_when_both_target_position_and_offset_given():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].text_blocks[0]
    original_text = handle[0].get_text()

    with pytest.raises(ValueError):
        move_block(
            handle, page_index=0, target=target,
            target_position=(72.0, 400.0), offset=(0.0, 10.0),
        )

    assert handle[0].get_text() == original_text
    handle.close()


def test_move_block_raises_when_neither_target_position_nor_offset_given():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].text_blocks[0]
    original_text = handle[0].get_text()

    with pytest.raises(ValueError):
        move_block(handle, page_index=0, target=target)

    assert handle[0].get_text() == original_text
    handle.close()


def test_move_block_same_page_preserves_the_exact_embedded_font():
    # Same-page move: Tier 1 of _select_font must find the block's own
    # embedded font resource, since it's still on the very same page it was
    # extracted from -- proving move_block preserves the exact original
    # font, not just a Base-14 substitute, whenever the source font is
    # actually available at the destination.
    pdf_bytes = (FIXTURES / "embedded_custom_font.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "EMBEDDED-FONT-TARGET-555" in b.text)

    move_block(handle, page_index=0, target=target, target_position=(72.0, 400.0))

    new_font = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "EMBEDDED-FONT-TARGET-555" in span["text"]:
                    new_font = span["font"]
    assert new_font is not None
    assert "repl-embedded" in new_font, (
        f"expected the moved text to use the re-embedded original font "
        f"(alias contains 'repl-embedded'), got {new_font!r}"
    )
    handle.close()


def test_move_block_cross_page_falls_back_gracefully_when_the_font_is_not_on_the_destination():
    pdf_bytes = (FIXTURES / "move_target.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    source_page = handle[0]
    destination_page = handle[1]
    target = next(b for b in doc.pages[0].text_blocks if "MOVE-ME-777" in b.text)
    assert "MOVE-ME-777" not in destination_page.get_text()

    move_block(
        handle, page_index=0, target=target,
        destination_page_index=1, target_position=(72.0, 200.0),
    )

    assert "MOVE-ME-777" not in source_page.get_text()
    assert "MOVE-ME-777" in destination_page.get_text()
    handle.close()


def test_move_block_raises_on_destination_page_index_out_of_range():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    target = doc.pages[0].text_blocks[0]

    with pytest.raises(ValueError):
        move_block(
            handle, page_index=0, target=target,
            destination_page_index=handle.page_count, target_position=(72.0, 400.0),
        )

    handle.close()


def test_move_block_raises_when_destination_does_not_fit_even_shrunk_and_leaves_source_erased():
    # Verified empirically: an artificially narrowed target bbox (width
    # only, height preserved) reliably fails to fit the same text even at
    # the 50% shrink floor, since move_block preserves the target's own
    # (here, deliberately tiny) width/height at the destination.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    narrow_target = replace(target, bbox=(target.bbox[0], target.bbox[1], target.bbox[0] + 20.0, target.bbox[3]))

    with pytest.raises(ValueError):
        move_block(handle, page_index=0, target=narrow_target, target_position=(72.0, 400.0))

    assert "REDACT-ME-12345" not in page.get_text()
    handle.close()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k move_block -v`
Expected: FAIL with `ImportError: cannot import name 'move_block'`.

- [ ] **Step 5: Implement `move_block`**

Directly after `delete_block`, add:

```python
def move_block(
    handle: fitz.Document,
    page_index: int,
    target: TextBlock,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    """Relocate target's own text, at its own font and size, to a new
    position -- same page by default, or a different page via
    destination_page_index. Exactly one of target_position (the new
    top-left corner) or offset (a (dx, dy) shift from the current
    position) must be given; width/height are preserved from target.bbox
    unchanged, only the position moves.

    Font resolution for the destination draw reuses _select_font exactly
    as replace_text does, called against the DESTINATION page: Tier 1
    (the block's own embedded font) succeeds whenever that font resource
    is genuinely present on the destination page -- always true for a
    same-page move, and true for a cross-page move only if the
    destination happens to already share the resource -- and gracefully
    falls through to Tier 2/3 otherwise, exactly like replace_text's own
    fallback. See the design spec's "Architecture" section.

    Raises:
        ValueError: exactly one of target_position/offset was not given;
            page_index or destination_page_index out of range;
            target.bbox or the computed destination bbox is degenerate or
            fully off-page (see _validate_target); no available font can
            render target.text at the destination (see _select_font); or
            target.text does not fit the destination even after shrinking
            to 50% of target.size -- move_block does not cascade reflow,
            same as replace_text. This last case is the sole one that
            raises AFTER erasing the source: the source is left cleanly
            erased, by design, mirroring replace_text's own contract for
            its equivalent failure case.
    """
    if (target_position is None) == (offset is None):
        raise ValueError(
            "exactly one of target_position or offset must be given "
            f"(target_position={target_position!r}, offset={offset!r}). "
            "Nothing has been modified."
        )

    source_page, source_rect = _validate_target(handle, page_index, target.bbox)

    dest_index = destination_page_index if destination_page_index is not None else page_index
    if dest_index < 0 or dest_index >= handle.page_count:
        raise ValueError(
            f"destination_page_index {dest_index} is out of range for a document "
            f"with {handle.page_count} page(s); must be 0 <= destination_page_index "
            f"< {handle.page_count}. Nothing has been modified."
        )
    destination_page = handle[dest_index]

    width = source_rect.x1 - source_rect.x0
    height = source_rect.y1 - source_rect.y0
    if target_position is not None:
        new_x0, new_y0 = target_position
    else:
        new_x0, new_y0 = source_rect.x0 + offset[0], source_rect.y0 + offset[1]
    destination_bbox = (new_x0, new_y0, new_x0 + width, new_y0 + height)
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)

    # ---- font resolution, before any mutation ----
    resolved_fontname, resolved_font = _select_font(handle, destination_page, target, target.text)

    try:
        insert_rect = _insertion_rect(destination_page, destination_rect, resolved_font, target.size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
        raise ValueError(
            f"failed to compute the insertion box for destination "
            f"{tuple(destination_rect)} in {target.font!r} at {target.size}pt: "
            f"{type(exc).__name__}: {exc}. Nothing has been modified."
        ) from exc

    # ---- mutation: erase source, then draw at the destination ----
    _clean_erase(source_page, source_rect)
    _draw_shrink_to_fit(
        destination_page, insert_rect, resolved_fontname, resolved_font,
        target.text, target.size, context_bbox=destination_rect,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k move_block -v`
Expected: all 8 new tests PASS.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (Task 1's total + 8 new).

- [ ] **Step 8: Commit**

```bash
git add engine/operations.py tests/fixtures/generate_fixtures.py tests/fixtures/move_target.pdf tests/test_operations.py
git commit -m "feat: add move_block (same-page and cross-page)"
```

---

### Task 3: `insert_block`

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: `_validate_target`, `_select_font`'s Tier 2/3 building blocks (`_base14_font`, `_base14_style_match`, `_bundled_fallback_font`, `_missing_glyphs`), `_draw_shrink_to_fit` -- but calls it in a single-attempt way, not via its own retry (see Step 5).
- Produces: `insert_block(handle, page_index, bbox, text, size, font=None) -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_operations.py` (add `insert_block` to the `from engine.operations import (...)` block):

```python
def test_insert_block_draws_new_text_with_default_font():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    assert "INSERTED-NEW-TEXT-999" not in page.get_text()

    insert_block(handle, page_index=0, bbox=(72.0, 300.0, 400.0, 320.0), text="INSERTED-NEW-TEXT-999", size=12.0)

    assert "INSERTED-NEW-TEXT-999" in page.get_text()
    handle.close()


def test_insert_block_with_an_explicit_base14_font():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]

    insert_block(
        handle, page_index=0, bbox=(72.0, 300.0, 400.0, 320.0),
        text="INSERTED-COURIER-TEXT", size=12.0, font="courier-bold",
    )

    new_font = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "INSERTED-COURIER-TEXT" in span["text"]:
                    new_font = span["font"]
    assert new_font is not None
    assert "courier" in new_font.lower() or "Courier" in new_font
    handle.close()


def test_insert_block_raises_immediately_when_text_does_not_fit_with_no_partial_draw():
    # Verified empirically: a too-long string in a tiny bbox returns a large
    # negative remaining_space from insert_textbox and draws nothing at all --
    # insert_block must not shrink-retry (the caller chose size deliberately)
    # and must not leave a partial draw behind.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    too_long = "This text is way too long to fit in a tiny twenty point wide box."

    with pytest.raises(ValueError):
        insert_block(handle, page_index=0, bbox=(72.0, 300.0, 92.0, 316.0), text=too_long, size=12.0)

    assert "way too long" not in page.get_text()
    handle.close()


def test_insert_block_raises_on_empty_text():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    with pytest.raises(ValueError):
        insert_block(handle, page_index=0, bbox=(72.0, 300.0, 400.0, 320.0), text="", size=12.0)

    handle.close()


def test_insert_block_raises_on_non_positive_size():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    with pytest.raises(ValueError):
        insert_block(handle, page_index=0, bbox=(72.0, 300.0, 400.0, 320.0), text="hello", size=0.0)

    handle.close()


def test_insert_block_raises_on_degenerate_bbox():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)

    with pytest.raises(ValueError):
        insert_block(handle, page_index=0, bbox=(100.0, 100.0, 100.0, 200.0), text="hello", size=12.0)

    handle.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k insert_block -v`
Expected: FAIL with `ImportError: cannot import name 'insert_block'`.

- [ ] **Step 3: Implement `insert_block`**

Directly after `move_block`, add:

```python
def insert_block(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
    """Draw brand-new text into an empty region of a page -- for adding
    content that has no existing block to replace. Unlike replace_text/
    move_block, there is no shrink-retry: size is an explicit, deliberate
    choice, and a poor fit is a caller error to fix (a smaller size or a
    larger bbox), not something this function silently overrides.

    Font resolution: font defaults to "helvetica" when omitted. Only
    Tiers 2/3 of _select_font's cascade apply -- there is no source block
    to extract an embedded font from (Tier 1). A font value that is
    already a Base-14 name is used as-is; one that is not gets the same
    bold/italic-matched Base-14 substitute _base14_style_match already
    computes for replace_text's non-Base-14 target.font case (e.g. a
    caller-supplied "Arial-Bold" resolves to "helvetica-bold", not a
    failed lookup for an embedded resource of that name, since none
    exists to find). If even the style-matched Base-14 font can't render
    every character of text, the bundled broad-coverage font (Tier 3) is
    tried before raising.

    Raises:
        ValueError: text is empty; size is not positive; bbox is
            degenerate or fully off-page (see _validate_target); no
            available font (a Base-14 name/style match, or the bundled
            broad-coverage font) can render every character of text; or
            text does not fit bbox at size -- named explicitly, since no
            shrink is attempted. Nothing is ever drawn before this
            function's validation completes, so a raise always leaves the
            document completely unmodified.
    """
    if not text:
        raise ValueError("text must be non-empty -- nothing to insert")

    page, rect = _validate_target(handle, page_index, bbox)

    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")

    # ---- font resolution: Tier 2/3 only, no source block for Tier 1 ----
    font_key = (font or "helvetica").lower()
    if font_key not in fitz.Base14_fontdict:
        font_key = _base14_style_match(font_key)
    base14_font = _base14_font(font_key)
    if not _missing_glyphs(base14_font, text):
        resolved_fontname, resolved_font = font_key, base14_font
    else:
        fallback_font = _bundled_fallback_font()
        missing = _missing_glyphs(fallback_font, text)
        if missing:
            missing_display = ", ".join(f"{c} (U+{ord(c):04X})" for c in missing)
            raise ValueError(
                f"text contains character(s) that no available font can render: "
                f"{missing_display} -- tried {font_key!r} and PyMuPDF's bundled "
                f"broad-coverage font. Nothing has been modified."
            )
        resolved_fontname, resolved_font = _FALLBACK_FONT_ALIAS, fallback_font

    try:
        insert_rect = _insertion_rect(page, rect, resolved_font, size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, same defense as replace_text
        raise ValueError(
            f"failed to compute the insertion box for bbox {tuple(bbox)} in "
            f"{font_key!r} at {size}pt: {type(exc).__name__}: {exc}. "
            f"Nothing has been modified."
        ) from exc

    # ---- single attempt, no shrink-retry -- size was an explicit choice ----
    if resolved_fontname not in fitz.Base14_fontdict:
        page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
    remaining_space = page.insert_textbox(
        insert_rect, text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0),
    )
    if remaining_space < 0:
        raise ValueError(
            f"text ({len(text)} chars) does not fit within bbox {tuple(bbox)} "
            f"at {size}pt -- insert_block does not shrink to fit; choose a "
            f"smaller size or a larger bbox"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k insert_block -v`
Expected: all 6 new tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (Task 2's total + 6 new).

- [ ] **Step 6: Commit**

```bash
git add engine/operations.py tests/test_operations.py
git commit -m "feat: add insert_block"
```

---

### Task 4: webui wiring

**Files:**
- Modify: `webui/session.py`
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `delete_block`, `move_block`, `insert_block` (Tasks 1-3).
- Produces: `session.delete(block_id)`, `session.move(block_id, destination_page_index=None, target_position=None, offset=None)`, `session.insert(page_index, bbox, text, size, font=None)`; routes `POST /api/delete`, `POST /api/move`, `POST /api/insert`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webui.py` (read the file's existing imports/fixtures/helpers first -- e.g. its `client`, `_upload_simple_text()`-style helper, and `_reset_session` autouse fixture -- and match its exact conventions):

```python
def test_delete_removes_a_block_with_no_black_box():
    body = _upload_simple_text()
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post("/api/delete", json={"block_id": block_id})

    assert response.status_code == 200
    data = response.json()
    assert not any("REDACT-ME-12345" in b["text"] for b in data["blocks"])


def test_delete_returns_a_clean_error_with_an_unknown_block_id():
    _upload_simple_text()

    response = client.post("/api/delete", json={"block_id": 999999})

    assert response.status_code == 400
    assert response.json()["error"]


def test_move_relocates_a_block_to_an_absolute_position():
    body = _upload_simple_text()
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post(
        "/api/move", json={"block_id": block_id, "target_position": [72.0, 400.0]},
    )

    assert response.status_code == 200
    data = response.json()
    assert any("REDACT-ME-12345" in b["text"] for b in data["blocks"])


def test_move_relocates_a_block_by_an_offset():
    body = _upload_simple_text()
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post(
        "/api/move", json={"block_id": block_id, "offset": [0.0, 200.0]},
    )

    assert response.status_code == 200
    data = response.json()
    assert any("REDACT-ME-12345" in b["text"] for b in data["blocks"])


def test_move_returns_a_clean_error_when_both_target_position_and_offset_given():
    body = _upload_simple_text()
    block_id = body["blocks"][0]["id"]

    response = client.post(
        "/api/move",
        json={"block_id": block_id, "target_position": [72.0, 400.0], "offset": [0.0, 10.0]},
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_insert_draws_new_text_into_an_empty_region():
    _upload_simple_text()

    response = client.post(
        "/api/insert",
        json={"page_index": 0, "bbox": [72.0, 300.0, 400.0, 320.0], "text": "NEW-INSERTED-TEXT", "size": 12.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert any("NEW-INSERTED-TEXT" in b["text"] for b in data["blocks"])


def test_insert_returns_a_clean_error_when_text_does_not_fit():
    _upload_simple_text()
    too_long = "This text is way too long to fit in a tiny twenty point wide box."

    response = client.post(
        "/api/insert",
        json={"page_index": 0, "bbox": [72.0, 300.0, 92.0, 316.0], "text": too_long, "size": 12.0},
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_delete_move_insert_return_a_clean_error_with_no_document_loaded():
    for url, body in [
        ("/api/delete", {"block_id": 0}),
        ("/api/move", {"block_id": 0, "target_position": [0.0, 0.0]}),
        ("/api/insert", {"page_index": 0, "bbox": [0.0, 0.0, 10.0, 10.0], "text": "x", "size": 12.0}),
    ]:
        response = client.post(url, json=body)
        assert response.status_code == 400
        assert response.json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "delete or move or insert" -v`
Expected: FAIL with 404 Not Found on the new routes (they don't exist yet).

- [ ] **Step 3: Wire `webui/session.py`**

Change the import block at the top from:

```python
from engine.document import Document
from engine.export import export
from engine.operations import get_metadata_summary as _get_metadata_summary
from engine.operations import redact_region, replace_text
from engine.operations import sanitize_document as _sanitize_document
from engine.parser import parse
```

to:

```python
from engine.document import Document
from engine.export import export
from engine.operations import delete_block, insert_block, move_block
from engine.operations import get_metadata_summary as _get_metadata_summary
from engine.operations import redact_region, replace_text
from engine.operations import sanitize_document as _sanitize_document
from engine.parser import parse
```

Add these three functions directly after `replace(block_id, new_text)` (before `sanitize_document`):

```python
def delete(block_id: int) -> None:
    entry = get_block(block_id)
    try:
        delete_block(get_handle(), entry["page_index"], entry["block"])
    finally:
        _refresh_blocks()


def move(
    block_id: int,
    destination_page_index: int | None = None,
    target_position: tuple[float, float] | None = None,
    offset: tuple[float, float] | None = None,
) -> None:
    entry = get_block(block_id)
    try:
        move_block(
            get_handle(),
            entry["page_index"],
            entry["block"],
            destination_page_index=destination_page_index,
            target_position=target_position,
            offset=offset,
        )
    finally:
        _refresh_blocks()


def insert(
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    font: str | None = None,
) -> None:
    handle = get_handle()
    try:
        insert_block(handle, page_index, bbox, text, size, font=font)
    finally:
        _refresh_blocks()
```

(`insert` checks `get_handle()` outside the try, exactly like `redact`/`replace`/`delete`/`move` check via `get_block()` -- there is no block to look up for an insert, but the same "don't refresh a registry for a document that was never loaded" reasoning applies.)

- [ ] **Step 4: Wire `webui/main.py`**

Add these three request models directly after `ReplaceRequest`:

```python
class DeleteRequest(BaseModel):
    block_id: int


class MoveRequest(BaseModel):
    block_id: int
    destination_page_index: int | None = None
    target_position: tuple[float, float] | None = None
    offset: tuple[float, float] | None = None


class InsertRequest(BaseModel):
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    size: float
    font: str | None = None
```

Add these three routes directly after `/api/replace` (before `/api/export`):

```python
@app.post("/api/delete")
async def delete(body: DeleteRequest) -> dict:
    session.delete(body.block_id)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.post("/api/move")
async def move(body: MoveRequest) -> dict:
    session.move(
        body.block_id,
        destination_page_index=body.destination_page_index,
        target_position=body.target_position,
        offset=body.offset,
    )
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.post("/api/insert")
async def insert(body: InsertRequest) -> dict:
    session.insert(body.page_index, body.bbox, body.text, body.size, font=body.font)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "delete or move or insert" -v`
Expected: all 8 new tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (Task 3's total + 8 new).

- [ ] **Step 7: Commit**

```bash
git add webui/session.py webui/main.py tests/test_webui.py
git commit -m "feat: add POST /api/delete, /api/move, /api/insert"
```

---

### Task 5: AI tool wiring

**Files:**
- Modify: `webui/ai/tools.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `session.delete`, `session.move`, `session.insert` (Task 4).
- Produces: `delete_block`, `move_block`, `insert_block` entries in `TOOLS`; three new `_execute_tool` branches.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ai.py` (matching the file's existing `session`/`_execute_tool`/`FIXTURES` import and fixture-loading conventions):

```python
def test_delete_block_tool_is_registered():
    from webui.ai.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "delete_block")
    assert tool["input_schema"]["required"] == ["block_id"]
    assert tool["strict"] is True


def test_move_block_tool_is_registered_with_nullable_optional_fields():
    # OpenAI's strict function-calling mode requires every property to
    # appear in "required" -- a genuinely optional field is expressed as a
    # nullable type instead of being omitted from "required" (the model
    # passes null to mean "not given"). Anthropic and Ollama both tolerate
    # this shape fine (neither enforces OpenAI's strict-mode constraint),
    # so one schema shape works correctly for all three providers -- see
    # the design spec's "AI tool" section.
    from webui.ai.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "move_block")
    properties = tool["input_schema"]["properties"]
    assert set(tool["input_schema"]["required"]) == set(properties.keys())
    assert "null" in properties["target_position"]["type"]
    assert "null" in properties["offset"]["type"]
    assert "null" in properties["destination_page_index"]["type"]
    assert tool["strict"] is True


def test_insert_block_tool_is_registered_with_nullable_font():
    from webui.ai.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "insert_block")
    properties = tool["input_schema"]["properties"]
    assert set(tool["input_schema"]["required"]) == set(properties.keys())
    assert "null" in properties["font"]["type"]
    assert tool["strict"] is True


def test_execute_tool_delete_block_removes_the_block():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    result_text, is_error = _execute_tool("delete_block", {"block_id": block_id})

    assert is_error is False
    assert not any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())


def test_execute_tool_move_block_relocates_the_block():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    result_text, is_error = _execute_tool(
        "move_block", {"block_id": block_id, "target_position": [72.0, 400.0]},
    )

    assert is_error is False
    assert any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())


def test_execute_tool_move_block_reports_an_error_when_both_position_and_offset_given():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())
    block_id = session.get_blocks_summary()[0]["id"]

    result_text, is_error = _execute_tool(
        "move_block",
        {"block_id": block_id, "target_position": [72.0, 400.0], "offset": [0.0, 10.0]},
    )

    assert is_error is True


def test_execute_tool_insert_block_draws_new_text():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())

    result_text, is_error = _execute_tool(
        "insert_block",
        {"page_index": 0, "bbox": [72.0, 300.0, 400.0, 320.0], "text": "NEW-INSERTED-TEXT", "size": 12.0},
    )

    assert is_error is False
    assert any("NEW-INSERTED-TEXT" in b["text"] for b in session.get_blocks_summary())


def test_execute_tool_delete_move_insert_report_a_missing_document_as_a_tool_error():
    session.reset()

    for name, args in [
        ("delete_block", {"block_id": 0}),
        ("move_block", {"block_id": 0, "target_position": [0.0, 0.0]}),
        ("insert_block", {"page_index": 0, "bbox": [0.0, 0.0, 10.0, 10.0], "text": "x", "size": 12.0}),
    ]:
        result_text, is_error = _execute_tool(name, args)
        assert is_error is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -k "delete_block or move_block or insert_block" -v`
Expected: FAIL -- the registration tests fail with `StopIteration` (no such tool in `TOOLS`), the execution tests get `("unknown tool: ...", True)`.

- [ ] **Step 3: Add the tool schemas and `SYSTEM_PROMPT` update**

**Before writing these schemas, note why `move_block` and `insert_block`
list every property in `required` (with nullable types for the
genuinely-optional ones), unlike every prior tool in this file:** OpenAI's
strict function-calling mode -- which `webui/ai/providers/openai_compatible.py`'s
`_translate_tools` passes `strict` straight through to -- requires every
property to appear in `required`; a conceptually-optional field must
instead have a nullable type (`["type", "null"]`), with the model passing
`null` to mean "not given." Anthropic and Ollama tolerate this shape fine
(neither enforces OpenAI's constraint), so this one schema shape is
correct for all three providers. Do not "simplify" these two schemas back
to the plainer optional-properties shape `redact_block`/`replace_block`/
`delete_block` use -- that shape would 400-error against real OpenAI (or
any strict-mode-enforcing OpenAI-compatible server) the first time a model
tries to omit `target_position`/`offset`/`font`. See the design spec's "AI
tool" section for the full rationale.

In `webui/ai/tools.py`, replace `SYSTEM_PROMPT` with:

```python
SYSTEM_PROMPT = (
    "You are editing a PDF document through six tools: redact_block (permanently "
    "remove a block's content, leaving a black bar), replace_block (replace a "
    "block's text with new text, preserving layout as much as the engine allows), "
    "delete_block (cleanly remove a block's content with no visible trace, unlike "
    "redact_block), move_block (relocate an existing block's own text, font, and "
    "size to a new position, optionally on a different page -- give exactly one "
    "of target_position or offset, never both), insert_block (draw brand-new text "
    "into an empty region that has no existing block -- requires an explicit font "
    "size, since there is no existing block to infer it from), and "
    "sanitize_document (remove the whole document's identifying metadata, hidden "
    "text, embedded scripts, and stale thumbnails in one action). You will be "
    "given the current list of text blocks in the document and an instruction. "
    "Find the block(s) the instruction refers to and call the appropriate "
    "tool(s). Only touch blocks that are actually relevant to the instruction -- "
    "if nothing in the block list matches what the instruction is asking for, "
    "say so in your final response instead of guessing or acting on an unrelated "
    "block. Block ids are reassigned after every edit -- only the most recently "
    "shown block list is valid, so never reuse an id from earlier in the "
    "conversation."
)
```

Add these three entries to `TOOLS`, after `replace_block` and before `sanitize_document`:

```python
    {
        "name": "delete_block",
        "description": (
            "Cleanly remove a text block's content with no visible trace left behind "
            "(as opposed to redact_block, which leaves a black bar). Use this when the "
            "instruction asks to delete or remove something without any replacement "
            "and without a visible redaction marker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to delete, from the block list you were given.",
                }
            },
            "required": ["block_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "move_block",
        "description": (
            "Relocate an existing text block's own content (unchanged text, font, "
            "and size) to a new position, optionally on a different page. Give "
            "exactly one of target_position or offset a real value -- pass the "
            "other as null, never both non-null."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to move, from the block list you were given.",
                },
                "destination_page_index": {
                    "type": ["integer", "null"],
                    "description": "Page to move the block to, or null to keep it on its current page.",
                },
                "target_position": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[x, y] -- the new top-left corner, in the destination page's own coordinates, or null. Give this OR offset a real value, never both non-null.",
                },
                "offset": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[dx, dy] -- shift relative to the block's current position, or null. Give this OR target_position a real value, never both non-null.",
                },
            },
            "required": ["block_id", "destination_page_index", "target_position", "offset"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "insert_block",
        "description": (
            "Draw brand-new text into an empty region of a page -- for adding "
            "content that has no existing block to replace. Requires an explicit "
            "font size; there is no existing block to infer it from."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "description": "The page to insert into."},
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "[x0, y0, x1, y1] -- the region to draw the text into.",
                },
                "text": {"type": "string", "description": "The text to insert."},
                "size": {
                    "type": "number",
                    "description": "Font size in points. Choose a size consistent with surrounding text if the instruction implies matching it.",
                },
                "font": {
                    "type": ["string", "null"],
                    "description": "A Base-14 font name (e.g. helvetica, times-roman, courier-bold), or null to default to plain Helvetica.",
                },
            },
            "required": ["page_index", "bbox", "text", "size", "font"],
            "additionalProperties": False,
        },
        "strict": True,
    },
```

- [ ] **Step 4: Add the `_execute_tool` branches**

Add these three branches to `_execute_tool`, after the `replace_block` branch and before the `sanitize_document` branch:

```python
        elif name == "delete_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            session.delete(block_id)
            return f"deleted block {block_id}: {original_text!r} (no visible trace left)", False
        elif name == "move_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            target_position = tool_input.get("target_position")
            offset = tool_input.get("offset")
            session.move(
                block_id,
                destination_page_index=tool_input.get("destination_page_index"),
                target_position=tuple(target_position) if target_position else None,
                offset=tuple(offset) if offset else None,
            )
            return f"moved block {block_id} ({original_text!r})", False
        elif name == "insert_block":
            session.insert(
                tool_input["page_index"],
                tuple(tool_input["bbox"]),
                tool_input["text"],
                tool_input["size"],
                font=tool_input.get("font"),
            )
            return f"inserted new text {tool_input['text']!r} on page {tool_input['page_index']}", False
```

The existing outer `try: ... except (ValueError, LookupError) as exc: return str(exc), True` already wraps this whole if/elif chain -- no new exception handling needed. In particular, `move_block`'s "exactly one of target_position/offset" `ValueError` (e.g. when a model supplies both, or neither beyond `block_id`) is caught here automatically, consistent with every other validation error in this file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -k "delete_block or move_block or insert_block" -v`
Expected: all 8 new tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (Task 4's total + 8 new).

- [ ] **Step 7: Commit**

```bash
git add webui/ai/tools.py tests/test_ai.py
git commit -m "feat: add delete_block, move_block, insert_block as AI tools"
```

---

### Task 6: Frontend, README, and real verification

**Files:**
- Modify: `webui/static/index.html`, `webui/static/app.js`, `webui/static/styles.css`, `README.md`

**Interfaces:** none new -- wires the Task 4/5 endpoints into the existing manual-controls UI.

- [ ] **Step 1: Extend each block row with Delete and Move controls in `webui/static/app.js`**

In `render(state)`'s per-block loop, directly after the existing `replaceButton` is appended to `blockDiv` (and before `pageDiv.appendChild(blockDiv)`), add:

```javascript
      const deleteButton = document.createElement("button");
      deleteButton.textContent = "Delete";
      blockDiv.appendChild(deleteButton);

      const moveXInput = document.createElement("input");
      moveXInput.type = "number";
      moveXInput.className = "coord-input";
      moveXInput.placeholder = "x";
      blockDiv.appendChild(moveXInput);

      const moveYInput = document.createElement("input");
      moveYInput.type = "number";
      moveYInput.className = "coord-input";
      moveYInput.placeholder = "y";
      blockDiv.appendChild(moveYInput);

      const moveButton = document.createElement("button");
      moveButton.textContent = "Move";
      blockDiv.appendChild(moveButton);
```

Update the existing `buttonsForBlock` array and add the two new `.onclick` handlers, replacing:

```javascript
      const buttonsForBlock = [redactButton, replaceButton];
      redactButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/redact", { block_id: block.id });
      replaceButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/replace", {
          block_id: block.id,
          new_text: replaceInput.value,
        });
```

with:

```javascript
      const buttonsForBlock = [redactButton, replaceButton, deleteButton, moveButton];
      redactButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/redact", { block_id: block.id });
      replaceButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/replace", {
          block_id: block.id,
          new_text: replaceInput.value,
        });
      deleteButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/delete", { block_id: block.id });
      moveButton.onclick = () =>
        actGuarded(buttonsForBlock, "/api/move", {
          block_id: block.id,
          target_position: [parseFloat(moveXInput.value), parseFloat(moveYInput.value)],
        });
```

(The manual Move control always does a same-page absolute move -- `destination_page_index` omitted. Cross-page move is fully available through the AI instruction layer, per the design spec's non-goal on UI polish; this keeps the manual control simple.)

- [ ] **Step 2: Add the Insert panel to `webui/static/index.html`**

Add, directly after the `manual-toggle-row` div and before `<div id="pages"></div>`:

```html
  <section class="instruct-panel manual-only" id="insert-panel">
    <div class="provider-row">
      <span class="provider-label">Insert new text</span>
    </div>
    <div class="insert-grid">
      <input type="number" id="insert-page-input" placeholder="page" min="0">
      <input type="number" id="insert-x0-input" placeholder="x0">
      <input type="number" id="insert-y0-input" placeholder="y0">
      <input type="number" id="insert-x1-input" placeholder="x1">
      <input type="number" id="insert-y1-input" placeholder="y1">
      <input type="number" id="insert-size-input" placeholder="size (pt)">
      <input type="text" id="insert-font-input" placeholder="font (optional, e.g. helvetica)">
      <input type="text" id="insert-text-input" placeholder="text to insert">
      <button class="secondary-button" id="insert-button" type="button" disabled>Insert</button>
    </div>
  </section>
```

- [ ] **Step 3: Wire the Insert panel and gate it on `hasDocument` in `webui/static/app.js`**

Update `setHasDocument` from:

```javascript
function setHasDocument(value) {
  hasDocument = value;
  document.getElementById("download-button").disabled = !value;
  document.getElementById("ai-instruct-button").disabled = !value;
  document.getElementById("sanitize-button").disabled = !value;
}
```

to:

```javascript
function setHasDocument(value) {
  hasDocument = value;
  document.getElementById("download-button").disabled = !value;
  document.getElementById("ai-instruct-button").disabled = !value;
  document.getElementById("sanitize-button").disabled = !value;
  document.getElementById("insert-button").disabled = !value;
}
```

Add, near the end of the file (after the `sanitize-button` handler):

```javascript
document.getElementById("insert-button").onclick = async () => {
  const button = document.getElementById("insert-button");
  const page_index = parseInt(document.getElementById("insert-page-input").value, 10);
  const bbox = [
    parseFloat(document.getElementById("insert-x0-input").value),
    parseFloat(document.getElementById("insert-y0-input").value),
    parseFloat(document.getElementById("insert-x1-input").value),
    parseFloat(document.getElementById("insert-y1-input").value),
  ];
  const size = parseFloat(document.getElementById("insert-size-input").value);
  const font = document.getElementById("insert-font-input").value;
  const text = document.getElementById("insert-text-input").value;

  const body = { page_index, bbox, text, size };
  if (font) body.font = font;

  button.disabled = true;
  try {
    await act("/api/insert", body);
  } finally {
    button.disabled = false;
  }
};
```

- [ ] **Step 4: Add CSS for the new controls in `webui/static/styles.css`**

Add, near the existing `.block-controls` rules:

```css
.coord-input {
  min-width: 55px;
}

.manual-only {
  display: none;
}

body[data-manual-controls="true"] .manual-only {
  display: block;
}

.insert-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.insert-grid input {
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: 12.5px;
}

.insert-grid button {
  grid-column: 1 / -1;
}
```

- [ ] **Step 5: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: unchanged pass count from Task 5 -- this task adds no new automated tests.

- [ ] **Step 6: Smoke-test the wiring with `TestClient`**

Following `tests/test_webui.py`'s existing pattern, confirm via a throwaway script (not necessarily committed) that `GET /` now contains `insert-button`, `insert-panel`, and that a block row's rendered controls include the new Delete/Move markup once a document is loaded and `/api/state` is fetched (or simply re-confirm Task 4's own webui tests, which already exercise the underlying routes this task's HTML/JS call). Do not attempt a live browser walkthrough here -- that is a separate, controller-level verification step outside this task's scope, mirroring how the document-sanitize plan's equivalent task split the work.

- [ ] **Step 7: Update the README**

Add a short section (matching the existing terse style, near the "Document sanitize" section) describing the three new operations:

```markdown
## Block editing: delete, move, insert

Three more block-level operations alongside redaction and replacement:

- `delete_block` -- cleanly removes a block's content with no visible
  trace (background-filled, unlike `redact_region`'s deliberate black bar).
- `move_block` -- relocates an existing block's own text, font, and size
  to a new position, same page or a different page.
- `insert_block` -- draws brand-new text into an empty region that has no
  existing block. Always requires an explicit font size; `font` defaults
  to Helvetica if omitted.

All three are available as manual controls in the web UI (delete/move
appear alongside each block's existing Redact/Replace controls; insert has
its own small form) and as AI instruction-layer tools
(`delete_block`/`move_block`/`insert_block`), following the same pattern
as every other operation in this project.
```

- [ ] **Step 8: Commit**

```bash
git add webui/static/index.html webui/static/app.js webui/static/styles.css README.md
git commit -m "feat: add delete/move/insert UI controls and AI tool documentation"
```

---

## Final Verification

After all 6 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` -- all passing. Baseline before this plan is 148 (confirmed on master); Tasks 1-5 add 3+8+6+8+8 = 33 new tests, for an expected total of 181.
2. Confirm `redact_region` and `sanitize_document` are completely untouched by this plan, and `replace_text`'s *public contract* (signature, docstring's Raises list, every existing test) is unchanged even though its internals were refactored: `git diff <plan-start-commit>..HEAD -- engine/operations.py` should show `redact_region`/`sanitize_document`/`get_metadata_summary` with zero changes, `replace_text`'s body restructured but its existing tests all still green, and three wholly new functions (`delete_block`, `move_block`, `insert_block`) plus the two new private helpers.
3. Confirm the new operations are reachable exactly the way every prior operation is: `grep -rn "delete_block\|move_block\|insert_block" webui/session.py webui/main.py webui/ai/tools.py` should show each used consistently (session wrapper, route, and AI tool branch) with no other, unexpected call site.
4. A controller-level live browser walkthrough (not part of any task's own scope): upload a document, use each new manual control (Delete, Move, Insert) and confirm the page re-renders correctly; try an AI instruction that should trigger each new tool (e.g. "delete the phone number", "move the confidential note to the bottom of the page", "insert a footer that says Draft -- Not for Distribution") against a real local model, and confirm the tool is actually called with a sensible result -- mirroring how the document-sanitize and font-robustness plans were both verified live, not just via the automated suite.
