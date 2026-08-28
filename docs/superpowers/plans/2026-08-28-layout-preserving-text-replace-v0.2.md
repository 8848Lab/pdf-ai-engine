# Layout-Preserving Text Replace v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `replace_text`, an operation that replaces a `TextBlock`'s content with different (possibly different-length) text, absorbing the length difference via PyMuPDF's word-wrap/font-shrink within that block's own bbox, and erasing the old content against its real sampled background color rather than assuming white.

**Architecture:** Extends `engine/operations.py` with a new public operation plus two small private helpers shared with the existing `redact_region` (a page/bbox validator and a mark-and-apply eraser), and one new private helper for background-color sampling. No new modules — same single-responsibility file as v0.1.

**Tech Stack:** Python 3.11+, PyMuPDF (`pymupdf`, imported as `import pymupdf as fitz`), pytest. Same as v0.1.

**Spec:** `docs/superpowers/specs/2026-08-28-layout-preserving-text-replace-v0.2-design.md`

## Global Constraints

- No AI/LLM anything, no auto-detection of what text to replace — the caller supplies the exact target (`TextBlock`) and the new text.
- No cross-paragraph or cross-page cascading reflow. Text that doesn't fit its own block raises; it does not push later content down.
- No style changes as part of an edit — new text keeps the original block's font (PyMuPDF's own auto-shrink loop, which this plan implements, may reduce size to fit); no per-character styling, no font-family changes.
- Only solid-color backgrounds are handled by sampling. Gradient/patterned/photographic backgrounds are explicitly out of scope — sampling a handful of points cannot reconstruct them.
- No authentication, no multi-tenancy, no billing, no web UI, no upload endpoint, no storage backend, no deployment story — same as v0.1. `engine/` never grows a FastAPI/HTTP dependency.
- Any operation other than `redact_region` (already shipped) and `replace_text` (this plan) is out of scope.
- `redact_region`'s existing public signature and behavior must not change — the shared internals this plan extracts are private, and `redact_region`'s own test suite must stay green, unmodified, throughout.

---

## Task 1: Extract shared validation/erase helpers (refactor, behavior-preserving)

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py` (no new tests — the existing suite is the safety net for this refactor)

**Interfaces:**
- Produces: `_validate_target(handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]) -> tuple[fitz.Page, fitz.Rect]` and `_erase_region(page: fitz.Page, rect: fitz.Rect, fill: tuple[float, float, float]) -> None` (both private). Consumed by Task 4's `replace_text`.
- Consumes: nothing new — this is a pure internal refactor of `redact_region`'s existing body.

This is a refactor, not new functionality, so the usual "write a failing test first" shape doesn't apply — instead, prove behavior-preservation by running the existing suite unchanged before and after.

- [ ] **Step 1: Run the existing test suite to confirm the current green baseline**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: all existing tests PASS (this is your baseline — the refactor below must not change this).

- [ ] **Step 2: Extract `_validate_target` and `_erase_region`, refactor `redact_region` to use them**

Replace the full contents of `engine/operations.py` with:

```python
"""Mutating operations against a live PyMuPDF document handle.

Supports two operations: redact_region (v0.1, real content removal) and
replace_text (v0.2, layout-preserving text replacement). Both mutate the
handle in place rather than the read-oriented Document dataclasses -- see
the design specs' "Data model" and "Operations" sections for why.
"""
import pymupdf as fitz


def _validate_target(
    handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]
) -> tuple[fitz.Page, fitz.Rect]:
    """Shared page_index/bbox validation for every mutating operation.

    Raises:
        ValueError: page_index out of range, or bbox degenerate (empty/
            zero-area after normalization) or does not intersect the
            target page at all. A bad target is a caller bug -- every
            operation using this helper fails loudly rather than
            silently no-op'ing or producing output that looks right but
            isn't.
    """
    if page_index < 0 or page_index >= handle.page_count:
        raise ValueError(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )

    page = handle[page_index]

    # Normalize handles inverted coordinates (x1<x0 and/or y1<y0) by
    # swapping them into min/max order. It does NOT fix a zero-area or
    # off-page rect -- those are caught explicitly below.
    rect = fitz.Rect(bbox)
    rect.normalize()

    if rect.is_empty:
        raise ValueError(
            f"bbox {tuple(bbox)} is degenerate (zero or negative area after "
            f"normalization: {tuple(rect)}) -- refuses to silently no-op on "
            f"invalid geometry"
        )
    if not rect.intersects(page.rect):
        raise ValueError(
            f"bbox {tuple(bbox)} does not intersect page {page_index} "
            f"(page rect is {tuple(page.rect)}) -- it is entirely off-page"
        )

    return page, rect


def _erase_region(page: fitz.Page, rect: fitz.Rect, fill: tuple[float, float, float]) -> None:
    """Mark and apply a redaction over `rect`, filled with `fill`.

    Shared by redact_region (fill=black, the visible "this was removed"
    signal) and replace_text (fill=the sampled background color, so the
    erase step is invisible once new text is drawn over it). The pinned
    apply_redactions modes matter equally for both callers -- see
    redact_region's own docstring below for why they're hardcoded rather
    than left to PyMuPDF's own defaults.
    """
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)


def redact_region(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> None:
    """Black out and strip content from a rectangular region of one page.

    Note on redaction floor: PyMuPDF removes content by geometric
    intersection with `bbox`, and is generous vertically (a bbox inset
    several points from a text line's true bounds still removes the whole
    line) -- but there is a real floor. A bbox that is technically valid
    (passes the checks below) but too thin/short to meaningfully intersect
    the target glyphs may leave content behind despite still drawing a
    visible black bar over it. Callers should size bboxes to fully cover
    the target content's rendered bounds, not just its nominal coordinates.

    Raises:
        ValueError: see _validate_target.
    """
    page, rect = _validate_target(handle, page_index, bbox)
    _erase_region(page, rect, fill=(0, 0, 0))
```

Note: `apply_redactions`'s pinned modes (`images=2, graphics=1, text=0`) moved into `_erase_region` unchanged — only the call site moved, the values and the comment explaining them are preserved.

- [ ] **Step 3: Run the test suite again to confirm it's still green, byte-for-byte the same results**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: identical pass count and identical test names to Step 1 — this refactor changed no observable behavior.

Run the full suite too, to catch anything outside `test_operations.py` that might import from `engine.operations`:
Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (33 tests, matching the count before this plan started).

- [ ] **Step 4: Commit**

```bash
git add engine/operations.py
git commit -m "refactor: extract shared validation/erase helpers from redact_region"
```

---

## Task 2: New fixture — text over a solid, non-white background

**Files:**
- Modify: `tests/fixtures/generate_fixtures.py`
- Create (generated, then committed as binary): `tests/fixtures/colored_background.pdf`
- Modify: `tests/test_fixtures_exist.py`

**Interfaces:**
- Produces: `tests/fixtures/colored_background.pdf` — a fixed, versioned fixture with one page containing a solid light-blue rectangle behind one line of text containing the known string `REPLACE-ME-SHORT`. Consumed by Task 3's and Task 5's tests.

- [ ] **Step 1: Add the new fixture-generating function**

In `tests/fixtures/generate_fixtures.py`, add (after `make_mixed`):

```python
def make_colored_background() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # A solid, non-white rectangle behind the text run, so
    # _sample_background_color (Task 3) has a genuine non-white
    # background to detect. Draw the rect first, then the text on top.
    # Confirm draw_rect's exact parameter names/behavior against the
    # installed PyMuPDF version before trusting this verbatim -- same
    # caution the design spec applies to insert_textbox/apply_redactions.
    page.draw_rect(fitz.Rect(60, 100, 400, 140), color=None, fill=(0.7, 0.85, 1.0))
    page.insert_text(
        (72, 125),
        "Short text over a light-blue highlight box: REPLACE-ME-SHORT.",
        fontsize=12,
    )
    doc.save(FIXTURES_DIR / "colored_background.pdf")
    doc.close()
```

And add the call to the `if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    make_simple_text()
    make_multi_page()
    make_image_only()
    make_mixed()
    make_colored_background()
    print("Fixtures written to", FIXTURES_DIR)
```

- [ ] **Step 2: Run the generator**

Run: `./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py`
Expected: prints the fixtures directory path; `tests/fixtures/colored_background.pdf` now exists. The other four fixtures are also regenerated in place — confirm they're unchanged (`git diff --stat` after this step should show only `colored_background.pdf` as new; if the other four show as modified, something about the generator or the installed PyMuPDF version changed their output non-deterministically — stop and investigate rather than committing a silent change to fixtures every other task depends on).

- [ ] **Step 3: Extend the fixture smoke test**

In `tests/test_fixtures_exist.py`, add `"colored_background.pdf"` to the `EXPECTED_FILES` list:

```python
EXPECTED_FILES = ["simple_text.pdf", "multi_page.pdf", "image_only.pdf", "mixed.pdf", "colored_background.pdf"]
```

- [ ] **Step 4: Run the smoke test**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fixtures_exist.py -v`
Expected: all tests PASS (the existing tests already iterate `EXPECTED_FILES`, so no new test function is needed — the list extension is the whole change).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/generate_fixtures.py tests/fixtures/colored_background.pdf tests/test_fixtures_exist.py
git commit -m "test: add a colored-background fixture for background-color sampling"
```

---

## Task 3: Background color sampling

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: `tests/fixtures/colored_background.pdf` (Task 2), `tests/fixtures/simple_text.pdf` (existing).
- Produces: `_sample_background_color(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]` (private). Consumed by Task 4's `replace_text`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_operations.py`:

```python
from engine.operations import _sample_background_color  # add to existing import line, or as its own line


def test_sample_background_color_reads_white_on_white_fixture():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    rect = fitz.Rect(hits[0])

    color = _sample_background_color(page, rect)

    # Allow a small tolerance for anti-aliasing near the sample points,
    # not an exact (1.0, 1.0, 1.0) match.
    assert all(c > 0.95 for c in color), f"expected near-white, got {color}"
    handle.close()


def test_sample_background_color_reads_the_real_non_white_background():
    pdf_bytes = (FIXTURES / "colored_background.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REPLACE-ME-SHORT")
    assert hits
    rect = fitz.Rect(hits[0])

    color = _sample_background_color(page, rect)

    # The fixture's rectangle was drawn with fill=(0.7, 0.85, 1.0) -- a
    # light blue. Assert the sample lands close to that, not white and
    # not black, with a tolerance loose enough to absorb anti-aliasing
    # and pixel-rounding but tight enough to prove a real color read
    # happened (not a hardcoded white default).
    r, g, b = color
    assert 0.55 <= r <= 0.85, f"red channel {r} not close to expected 0.7"
    assert 0.70 <= g <= 1.0, f"green channel {g} not close to expected 0.85"
    assert 0.85 <= b <= 1.0, f"blue channel {b} not close to expected 1.0"
    handle.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k sample_background -v`
Expected: FAIL — `ImportError: cannot import name '_sample_background_color'`.

- [ ] **Step 3: Write the implementation**

Add to `engine/operations.py` (after `_erase_region`):

```python
def _median(values: list[int]) -> int:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) // 2
    return ordered[mid]


def _sample_background_color(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """Sample the page's background color in a thin margin just outside
    `rect`'s four edges, returning the median RGB as 0.0-1.0 floats
    suitable for PyMuPDF's `fill=` parameters.

    Samples just outside rect (not inside -- rect tightly bounds the old
    content, so inside pixels are as likely to be glyph strokes as
    background) at each edge's midpoint, offset outward by a few points
    so anti-aliasing at the exact boundary doesn't contaminate the read.
    Median (not mean) per channel is robust against one sample landing on
    a stray mark, e.g. a neighboring character's overshoot or a nearby
    rule line.

    Only correct for a solid-color background -- see the design spec's
    "Background sampling" section for why gradients/patterns/photos are
    explicitly out of scope: sampling a handful of points returns *a*
    color, not the real erased pixels.
    """
    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width

    offset = 3.0  # points, outside each edge -- clears typical anti-aliasing halos
    sample_points_pt = [
        ((rect.x0 + rect.x1) / 2, rect.y0 - offset),  # above the top edge
        ((rect.x0 + rect.x1) / 2, rect.y1 + offset),  # below the bottom edge
        (rect.x0 - offset, (rect.y0 + rect.y1) / 2),  # left of the left edge
        (rect.x1 + offset, (rect.y0 + rect.y1) / 2),  # right of the right edge
    ]

    reds, greens, blues = [], [], []
    for x_pt, y_pt in sample_points_pt:
        x_px = max(0, min(pixmap.width - 1, int(x_pt * zoom)))
        y_px = max(0, min(pixmap.height - 1, int(y_pt * zoom)))
        pixel = pixmap.pixel(x_px, y_px)  # confirm this returns (r, g, b[, a]) 0-255 ints on the installed version
        reds.append(pixel[0])
        greens.append(pixel[1])
        blues.append(pixel[2])

    return (_median(reds) / 255.0, _median(greens) / 255.0, _median(blues) / 255.0)
```

Confirm `Pixmap.pixel(x, y)`'s exact return shape against the installed PyMuPDF version (the comment above flags this) before trusting the `pixel[0]`/`[1]`/`[2]` indexing — adapt if the installed version's API differs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k sample_background -v`
Expected: both tests PASS. If the colored-background test fails because the sampled color is outside the asserted tolerance bands, do not loosen the tolerance to force a pass — first confirm via a throwaway print of the actual sampled value whether the sampling logic has a real bug (e.g., sampling inside `rect` instead of outside, or a wrong zoom calculation) versus the fixture's actual rendered color genuinely differing from its nominal `fill=` value (which can happen due to color-space conversion) — in the latter case, adjust the tolerance bands to match the fixture's *actual* rendered color, not an arbitrarily wide band.

- [ ] **Step 5: Commit**

```bash
git add engine/operations.py tests/test_operations.py
git commit -m "feat: add background color sampling"
```

---

## Task 4: `replace_text` operation

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: `engine.document.TextBlock` (existing), `_validate_target`, `_erase_region` (Task 1), `_sample_background_color` (Task 3).
- Produces: `replace_text(handle: fitz.Document, page_index: int, target: TextBlock, new_text: str) -> None`. Consumed by Task 5.

- [ ] **Step 1: Investigate `Page.insert_textbox`'s real behavior on the installed PyMuPDF version**

Before writing `replace_text`, confirm empirically (a throwaway script or REPL session against a real fixture is fine — do not guess from general PyMuPDF familiarity):

1. What does `insert_textbox(rect, text, fontname=..., fontsize=..., ...)` return when the text fits vs. when it doesn't? (Expected on recent PyMuPDF: a float — the unused vertical space if the text fit, or a negative number indicating the vertical shortfall if it didn't. Confirm this is actually true on the installed version rather than assuming.)
2. Does `insert_textbox` draw partial content onto the page even when the text does NOT fit (i.e., is a "failed" call still a mutating call)? This matters for the shrink-retry loop below: if a failed attempt leaves partial text behind, each retry must re-erase the region first, or successive attempts will visually stack on top of each other.
3. Does `insert_textbox` itself auto-shrink `fontsize` to make text fit, or does it strictly wrap at the *given* fontsize and only report the vertical deficit, leaving font-shrinking to the caller? (This plan assumes the latter — the caller must implement the shrink-retry loop itself. If the installed version's `insert_textbox` behaves differently, e.g. accepts a `fontsize=0` "auto" mode that shrinks internally, note this in your report and adapt Step 3 below accordingly — the goal is auto-shrink actually working, not this specific implementation shape.)

Record what you found in your task report before proceeding.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_operations.py`:

Every test below builds its `target` `TextBlock` via `engine.parser.parse()` and filters `doc.pages[0].text_blocks` by known content, the same pattern already established in `tests/test_visual_regression.py` — not by indexing `get_text("dict")["blocks"][N]`, which is fragile to PyMuPDF's internal block-grouping changing.

```python
from engine.operations import replace_text  # add to existing import line, or as its own line
from engine.document import TextBlock
from engine.parser import parse


def test_replace_text_same_length_replacement():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="Confidential note: the code is CHANGED-NOW-99999.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "CHANGED-NOW-99999" in remaining_text
    handle.close()


def test_replace_text_shorter_replacement():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="Gone.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "Gone." in remaining_text
    handle.close()


def test_replace_text_longer_replacement_shrinks_font_to_fit():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    original_size = target.size

    # Meaningfully longer than the original -- long enough to require
    # either wrapping or shrinking within the same single-line-height bbox.
    longer_text = "Confidential note: the replacement secret access code is now CHANGED-TO-SOMETHING-LONGER-99999-ABCDEF."
    replace_text(handle, page_index=0, target=target, new_text=longer_text)

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "CHANGED-TO-SOMETHING-LONGER-99999-ABCDEF" in remaining_text

    # Confirm auto-shrink actually engaged -- not just that the call
    # succeeded. Re-inspect the live handle's own text-dict for the new
    # span's actual font size, per the design spec's fit-quality
    # requirement: a longer-but-fits replacement's re-parsed size must be
    # smaller than the original.
    new_size = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "CHANGED-TO-SOMETHING-LONGER" in span["text"]:
                    new_size = span["size"]
    assert new_size is not None, "could not find the replacement text's span to check its font size"
    assert new_size < original_size, (
        f"expected font-shrink to engage for a longer replacement, but size stayed "
        f"{new_size} (original was {original_size})"
    )
    handle.close()


def test_replace_text_raises_when_text_does_not_fit_even_shrunk():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    # Several sentences of filler -- unambiguously too much text for one
    # ~16pt-tall, ~274pt-wide single-line bbox even after shrinking to the
    # implementation's floor.
    way_too_long = " ".join(
        [f"This is filler sentence number {i} added to overflow the box." for i in range(15)]
    )

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=target, new_text=way_too_long)

    # The old text must still be gone (the erase step already ran before
    # the fit check), but the region must be left cleanly erased -- not a
    # corrupted partial draw from a failed insert_textbox attempt.
    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    handle.close()


def test_replace_text_raises_on_empty_new_text():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=target, new_text="")

    # An empty-new_text call must reject before mutating anything.
    assert "REDACT-ME-12345" in page.get_text()
    handle.close()


def test_replace_text_reuses_target_validation():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    off_page_target = TextBlock(text="x", bbox=(5000.0, 5000.0, 5100.0, 5100.0), font="helv", size=12.0)

    with pytest.raises(ValueError):
        replace_text(handle, page_index=0, target=off_page_target, new_text="anything")
    handle.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k replace_text -v`
Expected: FAIL — `ImportError: cannot import name 'replace_text'`.

- [ ] **Step 4: Write the implementation**

Add `from engine.document import TextBlock` to `engine/operations.py`'s imports (after `import pymupdf as fitz`, with a blank line separating them) — this is the first thing in the file that needs the `TextBlock` type, so the import belongs here, not earlier.

Add to `engine/operations.py` (after `redact_region`):

```python
def replace_text(
    handle: fitz.Document,
    page_index: int,
    target: TextBlock,
    new_text: str,
) -> None:
    """Replace target's content with new_text, absorbing any length
    difference via PyMuPDF's word-wrap and this function's own font-shrink
    retry loop, all within target's own bbox. See the design spec's
    "Operation" section.

    Raises:
        ValueError: page_index out of range or target.bbox degenerate/
            off-page (same checks redact_region uses, via
            _validate_target); new_text is empty; or new_text does not
            fit within target.bbox even after shrinking to 50% of
            target.size -- replace_text does not cascade reflow into
            neighboring content, it fails loudly instead.
    """
    if not new_text:
        raise ValueError(
            "new_text must be non-empty -- use redact_region to delete without replacing"
        )

    page, rect = _validate_target(handle, page_index, target.bbox)
    fill = _sample_background_color(page, rect)

    fontsize = target.size
    floor = target.size * 0.5
    remaining_space = -1.0
    while fontsize >= floor:
        # Re-erase before every attempt, not just the first: insert_textbox
        # draws as much text as fits even when it reports a deficit (see
        # Step 1's investigation), so a failed attempt at a larger size can
        # leave partial text baked into the page. Re-erasing guarantees
        # every attempt starts from a clean, background-colored rect
        # rather than compounding on a prior partial draw.
        _erase_region(page, rect, fill=fill)
        remaining_space = page.insert_textbox(
            rect,
            new_text,
            fontname=target.font,
            fontsize=fontsize,
            color=(0, 0, 0),
        )
        if remaining_space >= 0:
            break
        fontsize *= 0.9

    if remaining_space < 0:
        _erase_region(page, rect, fill=fill)  # leave a clean erased rect, not a failed partial draw
        raise ValueError(
            f"new_text ({len(new_text)} chars) does not fit within the target "
            f"block's bbox {tuple(rect)} even at {floor:.1f}pt (50% of the "
            f"original {target.size}pt) -- replace_text does not cascade "
            f"reflow into neighboring content; shorten the text or use a "
            f"different operation"
        )
```

Adapt this to whatever Step 1's investigation actually found about `insert_textbox`'s real return semantics and partial-draw behavior on the installed PyMuPDF version — this is a starting point based on commonly-documented PyMuPDF behavior, not a guarantee for every version. If your investigation found different behavior (e.g. an exception instead of a negative return, or no partial draw on failure), adapt the loop's fit-check and the "no partial draw" reasoning accordingly, and note the adaptation in your report.

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k replace_text -v`
Expected: all 6 new tests PASS.

- [ ] **Step 6: Re-export `replace_text` from the package root**

`engine/__init__.py` currently reads:

```python
from engine.document import Document, Image, Page, TextBlock
from engine.export import export
from engine.operations import redact_region
from engine.parser import parse

__all__ = ["Document", "Image", "Page", "TextBlock", "export", "redact_region", "parse"]
```

Update it to also export `replace_text`:

```python
from engine.document import Document, Image, Page, TextBlock
from engine.export import export
from engine.operations import redact_region, replace_text
from engine.parser import parse

__all__ = ["Document", "Image", "Page", "TextBlock", "export", "redact_region", "replace_text", "parse"]
```

Confirm: `./.venv/Scripts/python.exe -c "from engine import replace_text; print(replace_text)"` — should print the function, not raise `ImportError`.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (33 existing + this task's new tests).

- [ ] **Step 8: Commit**

```bash
git add engine/operations.py engine/__init__.py tests/test_operations.py
git commit -m "feat: add replace_text"
```

---

## Task 5: End-to-end proof — visual, content, structural, and fit-quality correctness

**Files:**
- Test: `tests/test_visual_regression.py`

**Interfaces:**
- Consumes: `engine.parser.parse` (existing), `engine.operations.replace_text` (Task 4), `engine.export.export` (existing).
- Produces: no new production code — this task is the integration proof for `replace_text`, extending v0.1's three-property harness with a fit-quality dimension, exactly as v0.1's own Task 6 did for `redact_region`.

- [ ] **Step 1: Write the tests**

Add to `tests/test_visual_regression.py` (append at the end, after the existing `redact_region` round-trip test):

```python
from engine.operations import replace_text


def test_replace_text_only_changes_pixels_inside_the_target_region():
    original_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page = original_handle[0]
    hits = original_page.search_for("REDACT-ME-12345")
    assert hits
    bbox = fitz.Rect(hits[0])

    doc, handle = parse(original_bytes)
    target_block = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    replace_text(handle, page_index=0, target=target_block, new_text="Confidential note: the code is NEW.")
    replaced_bytes = export(handle)
    handle.close()

    replaced_handle = fitz.open(stream=replaced_bytes, filetype="pdf")
    replaced_page = replaced_handle[0]

    ow, oh, original_samples = _pixmap_pixels(original_page)
    rw, rh, replaced_samples = _pixmap_pixels(replaced_page)
    assert (ow, oh) == (rw, rh)

    zoom = original_page.get_pixmap().width / original_page.rect.width
    n_components = len(original_samples) // (ow * oh)

    # Same tolerance-band approach the redact_region visual test uses
    # (see its own comment for the full rationale): a small margin around
    # the exact bbox absorbs PyMuPDF's own redaction-stroke rendering
    # (used internally by _erase_region before the new text is drawn),
    # sampled at pixel centers, not corners.
    TOLERANCE_PT = 1.0
    tolerant_bbox = fitz.Rect(
        bbox.x0 - TOLERANCE_PT, bbox.y0 - TOLERANCE_PT, bbox.x1 + TOLERANCE_PT, bbox.y1 + TOLERANCE_PT
    )

    changed_inside_bbox = False
    changed_outside_bbox = False
    for y in range(oh):
        for x in range(ow):
            idx = (y * ow + x) * n_components
            pixel_original = original_samples[idx : idx + n_components]
            pixel_replaced = replaced_samples[idx : idx + n_components]
            if pixel_original == pixel_replaced:
                continue
            px_pt, py_pt = (x + 0.5) / zoom, (y + 0.5) / zoom
            if bbox.x0 <= px_pt <= bbox.x1 and bbox.y0 <= py_pt <= bbox.y1:
                changed_inside_bbox = True
            elif tolerant_bbox.x0 <= px_pt <= tolerant_bbox.x1 and tolerant_bbox.y0 <= py_pt <= tolerant_bbox.y1:
                continue  # tolerance band -- any change here is acceptable, no directional check needed
                # (unlike redact_region's tolerance band, replace_text's target
                # region ends up with NEW text, not strictly-darker pixels, so
                # a "must get darker" check doesn't apply here -- the visual
                # property this test actually needs is "nothing outside the
                # bbox+tolerance changed", which the two branches above and
                # the assertion below together prove)
            else:
                changed_outside_bbox = True

    assert changed_inside_bbox, "replace_text should visibly change the target region"
    assert not changed_outside_bbox, (
        "replace_text must not touch pixels outside the target region and its "
        "known ~1pt tolerance band"
    )

    original_handle.close()
    replaced_handle.close()


def test_replace_text_preserves_a_colored_background():
    original_bytes = (FIXTURES / "colored_background.pdf").read_bytes()
    doc, handle = parse(original_bytes)
    target_block = next(b for b in doc.pages[0].text_blocks if "REPLACE-ME-SHORT" in b.text)

    replace_text(handle, page_index=0, target=target_block, new_text="New short text.")
    replaced_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=replaced_bytes, filetype="pdf")
    page = reopened[0]
    assert "REPLACE-ME-SHORT" not in page.get_text()
    assert "New short text." in page.get_text()

    # Sample a pixel just outside the (new) text's rendered position but
    # still within the original colored rectangle -- e.g. the rectangle's
    # own corner, far from any glyph -- and confirm it's still the light
    # blue fill, not reset to white.
    pixmap = page.get_pixmap()
    zoom = pixmap.width / page.rect.width
    corner_x_px = int(65 * zoom)  # just inside the rect's left edge (rect starts at x=60)
    corner_y_px = int(105 * zoom)  # just inside the rect's top edge (rect starts at y=100)
    r, g, b = pixmap.pixel(corner_x_px, corner_y_px)[:3]
    assert b > r and b > 200, (
        f"expected the corner to still be light blue (high blue channel), got rgb=({r},{g},{b}) "
        f"-- the colored background was likely reset to white instead of preserved"
    )
    reopened.close()


def test_replace_text_document_projection_round_trip():
    """Mirrors the equivalent redact_region round-trip test: proves a
    future caller can get a target purely from parse()'s Document
    projection (no page.search_for() on the raw handle) and pass it
    straight to replace_text.
    """
    original_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(original_bytes)

    target_block = None
    for block in doc.pages[0].text_blocks:
        if "REDACT-ME-12345" in block.text:
            target_block = block
            break
    assert target_block is not None, "parser must produce a TextBlock containing the secret"

    replace_text(handle, page_index=0, target=target_block, new_text="Replaced via the projection.")
    replaced_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=replaced_bytes, filetype="pdf")
    assert "REDACT-ME-12345" not in reopened[0].get_text()
    assert "Replaced via the projection." in reopened[0].get_text()
    reopened.close()


def test_replace_text_document_stays_valid_and_other_pages_are_untouched():
    original_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page_count = original_handle.page_count
    original_page1_text = original_handle[1].get_text()
    original_page2_text = original_handle[2].get_text()
    original_page1_pixels = _pixmap_pixels(original_handle[1])
    original_page2_pixels = _pixmap_pixels(original_handle[2])

    doc, handle = parse(original_bytes)
    target_block = next(b for b in doc.pages[0].text_blocks if "PAGE-MARK-1" in b.text)
    replace_text(handle, page_index=0, target=target_block, new_text="Different marker text.")
    replaced_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=replaced_bytes, filetype="pdf")
    assert reopened.page_count == original_page_count
    assert reopened[1].get_text() == original_page1_text
    assert reopened[2].get_text() == original_page2_text
    assert _pixmap_pixels(reopened[1]) == original_page1_pixels
    assert _pixmap_pixels(reopened[2]) == original_page2_pixels

    reopened.close()
    original_handle.close()
```

- [ ] **Step 2: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_visual_regression.py -v`
Expected: if Tasks 1-4 are already complete and correct (which they are, since this task depends on them), all new tests should PASS on first run — there is no new production code in this task. If any test fails, that is a real bug in Task 4's `replace_text` (or, less likely, Task 3's sampling) surfaced by this integration proof — diagnose which of the four properties (visual/content/structural/background-preservation) actually broke and why, the same systematic approach v0.1's Task 6 required, rather than adjusting the test to force a pass.

- [ ] **Step 3: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_visual_regression.py
git commit -m "test: add end-to-end visual, content, structural, and fit-quality proof for replace_text"
```

---

## Final Verification

After all 5 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — all passing.
2. Confirm the package root re-exports cleanly: `./.venv/Scripts/python.exe -c "from engine import replace_text, redact_region, parse, export, Document, Page, TextBlock, Image"`.
3. Confirm `engine/` still has no `api/`/`web/`/FastAPI dependency anywhere (`grep -r fastapi engine/ pyproject.toml` should return nothing) — Global Constraints.
4. Confirm `redact_region`'s public signature is unchanged and its full test suite is still green, unmodified from before this plan — Global Constraints.
5. Manually sanity-check one replacement end to end outside the test suite, and actually open the result in a PDF viewer: `./.venv/Scripts/python.exe -c "from engine.parser import parse; from engine.operations import replace_text; from engine.export import export; from pathlib import Path; b=Path('tests/fixtures/simple_text.pdf').read_bytes(); doc,h=parse(b); tb=next(t for t in doc.pages[0].text_blocks if 'REDACT-ME-12345' in t.text); replace_text(h,0,tb,'This text was edited by the AI-native PDF engine.'); Path('/tmp/replaced_sample.pdf').write_bytes(export(h)); h.close(); print('wrote /tmp/replaced_sample.pdf')"` — confirm visually that the new sentence reads naturally in place, with no leftover fragments of the old text and no obviously broken layout.
