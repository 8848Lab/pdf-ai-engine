# replace_text Font Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `replace_text` draw with the block's own real font instead of only ever falling back to a generic Base-14 font — closing the gap a reliability spike found makes it fail on effectively 100% of real-world documents today.

**Architecture:** A three-tier font-resolution cascade inside `engine/operations.py`: (1) the block's own real font, extracted from the source PDF and re-embedded; (2) a Base-14 fallback, style-matched by name; (3) PyMuPDF's own bundled broad-coverage font (`"cjk"`, verified to cover far more than CJK). Every tier is checked for actual glyph coverage of the replacement text before use, closing a silent-character-drop bug the investigation found along the way. `redact_region` is untouched — the same investigation already proved it robust.

**Tech Stack:** Python, PyMuPDF (`pymupdf`) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-replace-text-font-robustness-design.md`

## Global Constraints

- No change to `redact_region`, the shrink-retry loop's sizing logic, background-color sampling, or `_insertion_rect`'s inflation math — only which font gets used changes.
- No new package dependency, no bundled font asset — Tier 3 uses `fitz.Font("cjk")`, which PyMuPDF already ships internally.
- Every tier is checked for glyph coverage of `new_text` (space excluded from the check — real PDF fonts routinely omit an actual space glyph even though it renders fine) before being used to draw. A character missing from every tier's font must never be silently dropped — the existing "fail loudly, nothing modified" contract extends to this.
- Font resolution happens entirely before the erase step, same as every other validation in `replace_text` today — the function's existing guarantee (nothing is erased unless the draw is already known to be possible) must hold for this new step too.
- The existing test `test_replace_text_raises_on_non_base14_font_without_erasing_anything` in `tests/test_operations.py` asserts a premise this plan removes (a non-Base-14 font name always fails) — it must be rewritten, not left in place asserting behavior that no longer exists.
- Font-name matching between `TextBlock.font` (from `page.get_text()`'s span dict) and `page.get_fonts()`'s basename must be normalization-based (strip a 6-uppercase-letter subset-tag prefix, strip whitespace/hyphens/underscores, lowercase), not exact string equality — verified necessary: the two APIs disagree on formatting for the identical font in more than one real case (see Task 1).

---

## Task 1: Font-resolution helper functions

**Files:**
- Modify: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Produces: `_normalize_font_name(name: str) -> str`, `_extract_target_font(handle: fitz.Document, page: fitz.Page, target_font: str) -> tuple[int, bytes] | None`, `_missing_glyphs(font: fitz.Font, text: str) -> list[str]`, `_base14_style_match(font_name: str) -> str`, `_bundled_fallback_font() -> fitz.Font`. All pure/near-pure helpers, independently testable without a full `replace_text` call.
- Consumes: `fitz` (PyMuPDF), already imported in `engine/operations.py`.

These five helpers are the building blocks Task 2 wires into `replace_text` itself. None of them mutate a document.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_operations.py` (add `from engine.operations import (..., _normalize_font_name, _extract_target_font, _missing_glyphs, _base14_style_match, _bundled_fallback_font)` to the existing import line from `engine.operations`):

```python
def test_normalize_font_name_strips_subset_tag_and_matches_across_formats():
    # Real case, confirmed against an actual IRS Form 1040: the subset tag
    # only appears in page.get_fonts()'s basename, never in the span's own
    # reported font name.
    assert _normalize_font_name("PIMSLO+HelveticaNeueLTStd-Roman") == \
        _normalize_font_name("HelveticaNeueLTStd-Roman")
    # Real case, confirmed by embedding a font via page.insert_font() and
    # reading it back: get_text()'s span reports 'NimbusSans-Regular' (no
    # spaces) while get_fonts()'s basename reports 'Nimbus Sans Regular'
    # (with spaces) for the identical resource.
    assert _normalize_font_name("NimbusSans-Regular") == \
        _normalize_font_name("Nimbus Sans Regular")
    # Genuinely different fonts must not collide.
    assert _normalize_font_name("Arial-Bold") != _normalize_font_name("Arial-Italic")


def test_missing_glyphs_excludes_space_and_reports_real_gaps():
    helv = fitz.Font("helvetica")
    # Ordinary Latin text: nothing missing, including the space itself.
    assert _missing_glyphs(helv, "Hello World 123") == []
    # A Private Use Area codepoint is guaranteed unassigned by any real font.
    pua_char = chr(0xE000)
    assert _missing_glyphs(helv, f"test{pua_char}") == [pua_char]


def test_missing_glyphs_deduplicates_in_first_occurrence_order():
    helv = fitz.Font("helvetica")
    a, b = chr(0xE000), chr(0xE001)  # two distinct, unassigned Private Use Area codepoints

    missing = _missing_glyphs(helv, f"{a}{b}{a}{b}")

    assert missing == [a, b]


def test_base14_style_match_picks_bold_and_italic_variants():
    assert _base14_style_match("HelveticaNeueLTStd-Bold") == "helvetica-bold"
    assert _base14_style_match("SomeFont-Italic") == "helvetica-oblique"
    assert _base14_style_match("SomeFont-BoldOblique") == "helvetica-boldoblique"
    assert _base14_style_match("SomeFont-Regular") == "helvetica"


def test_bundled_fallback_font_covers_latin_cyrillic_greek_cjk_and_symbols():
    # Pins the reliability-spike finding this whole plan is built on: despite
    # the reserved name "cjk", this font is not CJK-only.
    font = _bundled_fallback_font()
    test_strings = {
        "latin": "ABCXYZabcxyz0123456789",
        "punctuation": "@#%&*()[]{}!?.,;:\"'/\\-_+=<>",
        "cyrillic": "абвгдЖЗИК",
        "greek": "αβγδΩΦΨ",
        "cjk": "中文日本語한국어",
        "currency": "$€£¥©®°",
    }
    for label, chars in test_strings.items():
        assert _missing_glyphs(font, chars) == [], f"{label} should be fully covered"


def test_extract_target_font_resolves_a_real_embedded_font():
    # Build a fixture with a genuinely embedded, custom-named font -- the
    # same construction pattern used by Task 2's new fixture (see that
    # task for why this specific pattern was chosen: embedding a Base-14
    # font's own buffer under a fake alias forces a real font-name-format
    # mismatch between get_text()'s span and get_fonts()'s basename,
    # exercising the exact normalization this helper exists for).
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page.insert_font(fontname="CustomCorporateFont", fontbuffer=helv.buffer)
    page.insert_text((72, 100), "target text", fontsize=12, fontname="CustomCorporateFont")
    data = doc.tobytes()
    doc.close()

    handle = fitz.open(stream=data, filetype="pdf")
    page = handle[0]
    span_font_name = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]["font"]

    resolved = _extract_target_font(handle, page, span_font_name)

    assert resolved is not None
    xref, buffer = resolved
    assert isinstance(xref, int)
    assert len(buffer) > 0
    # The extracted buffer must actually be usable as a font.
    font = fitz.Font(fontbuffer=buffer)
    assert font.has_glyph(ord("A"))
    handle.close()


def test_extract_target_font_returns_none_for_a_non_embedded_base14_reference():
    # simple_text.pdf's text is drawn via plain insert_text() with no
    # explicit fontname -- PyMuPDF references "Helvetica" by name only,
    # never embeds it (confirmed: page.get_fonts() reports ext='n/a' and
    # extract_font() returns an empty buffer for it). This must fall
    # through cleanly, not crash or return an unusable "font".
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    resolved = _extract_target_font(handle, page, "Helvetica")

    assert resolved is None
    handle.close()


def test_extract_target_font_returns_none_for_a_font_name_with_no_match_at_all():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    resolved = _extract_target_font(handle, page, "SomeFontThatDoesNotExistAnywhere")

    assert resolved is None
    handle.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k "normalize_font_name or missing_glyphs or base14_style_match or bundled_fallback_font or extract_target_font" -v`
Expected: FAIL — `ImportError` (the helpers don't exist yet).

- [ ] **Step 3: Write the implementation**

Add to `engine/operations.py`, after the existing imports (add `import re` alongside the existing `import pymupdf as fitz`) and before `_validate_target`:

```python
_SUBSET_TAG_RE = re.compile(r"^[A-Z]{6}\+")


def _normalize_font_name(name: str) -> str:
    """Normalize a font name for matching a TextBlock.font string (from
    page.get_text()'s span dict) against a page.get_fonts() basename for
    the SAME underlying font resource.

    The two APIs do not always agree on formatting for identical fonts --
    verified empirically: a font embedded via page.insert_font() and later
    read back reports 'NimbusSans-Regular' via get_text()'s span but
    'Nimbus Sans Regular' (with spaces) via get_fonts()'s basename. Real
    third-party-authored PDFs add their own wrinkle: a subset tag (exactly
    6 uppercase letters + '+', e.g. 'PIMSLO+HelveticaNeueLTStd-Roman' --
    confirmed against a real IRS tax form) that only appears in
    get_fonts()'s basename, never in the span's own font name.

    Stripping the subset tag, removing whitespace/hyphens/underscores, and
    lowercasing collapses both wrinkles: 'HelveticaNeueLTStd-Roman' and
    'PIMSLO+HelveticaNeueLTStd-Roman' both normalize to
    'helveticaneueltstdroman'; 'NimbusSans-Regular' and 'Nimbus Sans
    Regular' both normalize to 'nimbussansregular'.
    """
    name = _SUBSET_TAG_RE.sub("", name)
    return re.sub(r"[\s\-_]", "", name).lower()


def _extract_target_font(
    handle: fitz.Document, page: fitz.Page, target_font: str
) -> tuple[int, bytes] | None:
    """Best-effort: find target_font's real embedded font resource on
    `page` (matched via _normalize_font_name against page.get_fonts()'s
    basenames) and return its (xref, raw bytes), or None if no matching
    resource exists, the match is not actually embedded (a Base-14 font
    referenced by name only reports an empty buffer here -- confirmed:
    page.get_fonts() shows ext='n/a' for it and extract_font() returns
    b''), or anything else about extraction fails.

    Never raises: this is Tier 1 of a fallback cascade (see _select_font),
    and any failure here must fall through to Tier 2, not abort the whole
    operation.
    """
    try:
        normalized_target = _normalize_font_name(target_font)
        for font_info in page.get_fonts(full=True):
            if _normalize_font_name(font_info[3]) == normalized_target:
                xref = font_info[0]
                result = handle.extract_font(xref)
                buffer = result[3] if len(result) > 3 else None
                if buffer:
                    return xref, buffer
                return None
        return None
    except Exception:
        return None


def _missing_glyphs(font: fitz.Font, text: str) -> list[str]:
    """Characters in `text` (excluding space) that `font` has no glyph
    for, in first-occurrence order with duplicates removed.

    Space is excluded deliberately: real PDF fonts routinely omit an
    actual glyph for it (word spacing is handled by positioning, not a
    drawn glyph) even though insert_textbox renders it correctly
    regardless -- verified empirically against every font tested in this
    project, including PyMuPDF's own Base-14 set; including it here would
    report a false "missing" character for essentially every real font.
    """
    seen: list[str] = []
    for ch in text:
        if ch == " " or ch in seen:
            continue
        if not font.has_glyph(ord(ch)):
            seen.append(ch)
    return seen


def _base14_style_match(font_name: str) -> str:
    """Pick a reasonable generic Base-14 substitute for font_name, using a
    simple bold/italic heuristic on the name itself so a styled font at
    least keeps its styling rather than always falling back to plain
    Helvetica.

    Only used when font_name is NOT already a Base-14 name (callers check
    that first) and Tier 1's real embedded font could not be resolved or
    could not cover the needed text -- see _select_font.
    """
    lowered = font_name.lower()
    is_bold = "bold" in lowered
    is_italic = "italic" in lowered or "oblique" in lowered
    if is_bold and is_italic:
        return "helvetica-boldoblique"
    if is_bold:
        return "helvetica-bold"
    if is_italic:
        return "helvetica-oblique"
    return "helvetica"


def _bundled_fallback_font() -> fitz.Font:
    """PyMuPDF's own bundled broad-coverage font (reserved name 'cjk') --
    the final fallback tier. Despite the name, verified in this project's
    own testing to cover Latin, Cyrillic, Greek, CJK, and common
    currency/punctuation symbols with zero gaps -- not CJK-only.
    """
    return fitz.Font("cjk")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k "normalize_font_name or missing_glyphs or base14_style_match or bundled_fallback_font or extract_target_font" -v`
Expected: all 8 new tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (118 existing + 8 new = 126).

- [ ] **Step 6: Commit**

```bash
git add engine/operations.py tests/test_operations.py
git commit -m "feat: add font-resolution helpers for replace_text's fallback cascade"
```

---

## Task 2: Wire the cascade into replace_text

**Files:**
- Modify: `engine/operations.py`, `tests/test_operations.py`, `tests/fixtures/generate_fixtures.py`
- Create: `tests/fixtures/embedded_custom_font.pdf` (generated, checked in — same convention as every other fixture in this repo)

**Interfaces:**
- Consumes: all five helpers from Task 1.
- Produces: `_select_font(handle: fitz.Document, page: fitz.Page, target: TextBlock, new_text: str) -> tuple[str, fitz.Font]`. `_insertion_rect`'s signature changes from `(page, rect, font_name: str, size)` to `(page, rect, font: fitz.Font, size)` — it now takes a resolved font object directly instead of building one from a Base-14 name internally.
- `replace_text`'s public signature and `Raises: ValueError` contract are unchanged in shape (still `ValueError` for every failure case), but the specific condition "target.font is not Base-14" is replaced by "no tier's font covers every character new_text needs."

- [ ] **Step 1: Generate the new fixture**

Add to `tests/fixtures/generate_fixtures.py` (following the existing `make_*` function convention in that file):

```python
def make_embedded_custom_font() -> None:
    """A block whose font is genuinely embedded under a name that is
    neither a Base-14 name nor (after normalization) matches one -- the
    fixture Task 2's Tier-1-succeeds test needs. Embeds Base-14
    Helvetica's own font data under a fake alias, which both makes it a
    real embedded resource (not a name-only reference, unlike every other
    fixture in this file) and reproduces a real formatting mismatch this
    project found between how page.get_text() and page.get_fonts() report
    the same font (see _normalize_font_name's docstring in operations.py).
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    helv = fitz.Font("helvetica")
    page.insert_font(fontname="CustomCorporateFont", fontbuffer=helv.buffer)
    page.insert_text(
        (72, 100),
        "Embedded custom font target EMBEDDED-FONT-TARGET-555.",
        fontsize=12,
        fontname="CustomCorporateFont",
    )
    doc.save(FIXTURES_DIR / "embedded_custom_font.pdf")
    doc.close()
```

Add `make_embedded_custom_font()` to the `if __name__ == "__main__":` block's list of calls (alongside the existing `make_simple_text()` etc.), then run:

`./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py`

Confirm `tests/fixtures/embedded_custom_font.pdf` was created.

- [ ] **Step 2: Write the failing tests**

Add `_select_font` and `_insertion_rect`'s new signature to the existing `from engine.operations import (...)` line in `tests/test_operations.py`.

Replace the existing `test_replace_text_raises_on_non_base14_font_without_erasing_anything` test (its premise — any non-Base-14 font name always fails — no longer holds) with:

```python
def test_replace_text_falls_back_to_base14_when_font_is_not_embedded_anywhere():
    # "Calibri" is not embedded anywhere in this fixture (simple_text.pdf's
    # text is drawn via plain insert_text(), never insert_font()) and is
    # not a Base-14 name itself -- Tier 1 correctly finds no match and
    # falls through, Tier 2's style-match ("Calibri" has no bold/italic in
    # its name) resolves to plain "helvetica", which covers ordinary text.
    # This directly replaces the pre-cascade behavior, where any
    # non-Base-14 name failed outright.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    non_base14 = replace(target, font="Calibri")

    replace_text(handle, page_index=0, target=non_base14, new_text="Replaced via fallback.")

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    assert "Replaced via fallback." in remaining_text
    handle.close()


def test_replace_text_uses_the_blocks_own_real_font_when_embedded():
    # Proves Tier 1 actually activated, not just that the overall call
    # succeeded (Tier 2's style-match fallback would also succeed here,
    # since "CustomCorporateFont" has no bold/italic in its name -- the
    # meaningful assertion is that the DRAWN text's re-parsed font is NOT
    # a Base-14 name, which only happens if Tier 1's real embedded font
    # was actually used).
    pdf_bytes = (FIXTURES / "embedded_custom_font.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "EMBEDDED-FONT-TARGET-555" in b.text)

    replace_text(handle, page_index=0, target=target, new_text="TIER1-CONFIRMED-ACTIVE")

    remaining_text = page.get_text()
    assert "EMBEDDED-FONT-TARGET-555" not in remaining_text
    assert "TIER1-CONFIRMED-ACTIVE" in remaining_text

    new_span_font = None
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if "TIER1-CONFIRMED-ACTIVE" in span["text"]:
                    new_span_font = span["font"]
    assert new_span_font is not None, "could not find the replacement text's span"
    assert new_span_font.lower() not in fitz.Base14_fontdict, (
        f"expected the block's own real font to be used, but the drawn text's "
        f"font is a Base-14 name ({new_span_font!r}) -- Tier 1 did not activate"
    )
    handle.close()


def test_replace_text_cascades_to_the_bundled_fallback_for_a_cjk_character():
    # target.font ("Calibri") is not embedded (same as the fallback test
    # above, so Tier 1 falls through) and Tier 2's Base-14 Helvetica has no
    # CJK coverage -- only Tier 3's bundled broad-coverage font can render
    # this, proving the cascade actually reaches its last tier rather than
    # stopping at Tier 2.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    non_base14 = replace(target, font="Calibri")

    replace_text(handle, page_index=0, target=non_base14, new_text="中文 CJK test")

    remaining_text = page.get_text()
    assert "中文" in remaining_text, (
        f"expected the CJK characters to render via the Tier 3 fallback, got: {remaining_text!r}"
    )
    handle.close()


def test_replace_text_raises_naming_the_missing_character_when_no_tier_covers_it():
    # A Private Use Area codepoint is guaranteed unassigned by any real
    # font, including PyMuPDF's own bundled broad-coverage Tier 3 font
    # (pinned by test_bundled_fallback_font_covers_... in Task 1 -- this
    # test relies on that font genuinely not covering it, not on a mock).
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = handle[0]
    target = next(b for b in doc.pages[0].text_blocks if "REDACT-ME-12345" in b.text)
    pua_char = chr(0xE000)  # Private Use Area -- confirmed unassigned in both
    # fitz.Font("helvetica") and fitz.Font("cjk") via has_glyph(0xE000) == 0.

    with pytest.raises(ValueError) as excinfo:
        replace_text(handle, page_index=0, target=target, new_text=f"test{pua_char}")

    assert pua_char in str(excinfo.value)
    # Nothing was modified -- the original text must still be there.
    assert "REDACT-ME-12345" in page.get_text()
    handle.close()
```

Update `test_insertion_rect_inflates_the_bbox_but_never_past_the_page_edge` (the existing test) to pass a `fitz.Font` object instead of a string, matching `_insertion_rect`'s new signature — change:

```python
    interior = _insertion_rect(page, fitz.Rect(72.0, 100.0, 300.0, 116.5), "Helvetica", 12.0)
```

and

```python
    at_edge = _insertion_rect(page, fitz.Rect(400.0, 780.0, 612.0, 792.0), "Helvetica", 12.0)
```

to:

```python
    helv = fitz.Font("helvetica")
    interior = _insertion_rect(page, fitz.Rect(72.0, 100.0, 300.0, 116.5), helv, 12.0)
```

and

```python
    at_edge = _insertion_rect(page, fitz.Rect(400.0, 780.0, 612.0, 792.0), helv, 12.0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: the 4 new tests and the updated `test_insertion_rect_...` FAIL (the new tests with `AttributeError`/`TypeError` since `_select_font` doesn't exist yet and `_insertion_rect` still expects a string; several pre-existing `replace_text` tests may also now fail once you reach Step 5 if `_insertion_rect`'s signature changes without `replace_text` being updated to match — this is expected mid-step, resolved by Step 5).

- [ ] **Step 4: Update `_insertion_rect`'s signature**

In `engine/operations.py`, change:

```python
def _insertion_rect(
    page: fitz.Page, rect: fitz.Rect, font_name: str, size: float
) -> fitz.Rect:
```

to:

```python
def _insertion_rect(
    page: fitz.Page, rect: fitz.Rect, font: fitz.Font, size: float
) -> fitz.Rect:
```

and change the docstring's opening line and the body's font lookup — replace:

```python
    font = _base14_font(font_name)
    line_height_factor = font.ascender - font.descender
```

with:

```python
    line_height_factor = font.ascender - font.descender
```

(the parameter is already the `fitz.Font` the caller resolved — no lookup needed here anymore). Update the docstring's first line from "one line of `size`pt text in `font_name`" to "one line of `size`pt text in `font`" and its "Why this is needed" paragraph's reference to a font *name* to reference the font object instead — read the existing docstring in full and adjust only the parts that describe `font_name` as a string; the geometry explanation itself (the `lheight * lines - descender * fontsize` rule, the descender-inflation reasoning, the page-edge clamping) is unchanged and must be kept verbatim.

- [ ] **Step 5: Add `_select_font` and wire it into `replace_text`**

Add this function to `engine/operations.py`, after `_bundled_fallback_font` (from Task 1) and before `redact_region`:

```python
_FALLBACK_FONT_ALIAS = "repl-fallback-broad"


def _select_font(
    handle: fitz.Document, page: fitz.Page, target: TextBlock, new_text: str
) -> tuple[str, fitz.Font]:
    """Resolve the best-available font to draw new_text into target's
    region with, trying three tiers in order and returning the first
    whose glyph set covers every character new_text needs (space
    excluded -- see _missing_glyphs):

    1. target's own real font, extracted from the source document and
       re-embedded on `page` -- the closest visual match to the original
       document, and what makes this succeed on the vast majority of
       real-world text. See the design spec's reliability spike: both a
       real IRS Form 1040 and a real arXiv paper use exclusively embedded,
       non-Base-14 fonts (100% and 99% of blocks respectively), and this
       tier resolves and draws both correctly.
    2. A Base-14 fallback: target.font itself if it already IS a Base-14
       name, otherwise a bold/italic-matched generic substitute (see
       _base14_style_match).
    3. PyMuPDF's bundled 'cjk' font -- not just for CJK despite the name;
       verified in this project's own testing to cover Latin, Cyrillic,
       Greek, CJK, and common symbols/currency/punctuation with zero gaps.
       The true last resort: reached only when neither tier above covers
       every character new_text needs.

    Returns (fontname, font) where `fontname` is ready to pass directly to
    page.insert_textbox(fontname=...) -- already embedded on `page` if it
    needed to be -- and `font` is the matching fitz.Font, for
    _insertion_rect's metrics lookup.

    Raises:
        ValueError: no tier's font covers every character new_text needs.
        Names the specific unrenderable character(s). Called before any
        page mutation, same as every other check in replace_text -- this
        can never fire after the target has been erased.
    """
    # Tier 1: the block's own real font.
    resolved = _extract_target_font(handle, page, target.font)
    if resolved is not None:
        xref, embedded_bytes = resolved
        try:
            embedded_font = fitz.Font(fontbuffer=embedded_bytes)
        except Exception:
            embedded_font = None
        if embedded_font is not None and not _missing_glyphs(embedded_font, new_text):
            alias = f"repl-embedded-{xref}"
            page.insert_font(fontname=alias, fontbuffer=embedded_bytes)
            return alias, embedded_font

    # Tier 2: Base-14, either target.font itself or a style-matched generic.
    base14_key = target.font.lower()
    if base14_key not in fitz.Base14_fontdict:
        base14_key = _base14_style_match(target.font)
    base14_font = _base14_font(base14_key)
    if not _missing_glyphs(base14_font, new_text):
        return base14_key, base14_font

    # Tier 3: PyMuPDF's own bundled broad-coverage font, the last resort.
    fallback_font = _bundled_fallback_font()
    missing = _missing_glyphs(fallback_font, new_text)
    if not missing:
        page.insert_font(fontname=_FALLBACK_FONT_ALIAS, fontbuffer=fallback_font.buffer)
        return _FALLBACK_FONT_ALIAS, fallback_font

    raise ValueError(
        f"new_text contains character(s) {missing!r} that no available font "
        f"can render -- tried the block's own font ({target.font!r}), a "
        f"Base-14 fallback, and PyMuPDF's bundled broad-coverage font. "
        f"Nothing has been modified."
    )
```

Now update `replace_text` itself. Replace this block (the old flat Base-14 validation):

```python
    base14_key = target.font.lower()
    if base14_key not in fitz.Base14_fontdict:
        raise ValueError(
            f"target.font {target.font!r} is not one of PyMuPDF's built-in "
            f"Base-14 fonts ({', '.join(sorted(fitz.Base14_fontdict))}). "
            f"replace_text draws replacement text with a built-in font only; "
            f"it cannot load the embedded or system font this block actually "
            f"uses. Nothing has been modified."
        )
    if target.size <= 0:
```

with:

```python
    if target.size <= 0:
```

(the `target.size` check moves up to replace the removed block's position — everything else about it is unchanged), then find the section that currently reads:

```python
    # ---- geometry ----
    # Font metrics are safe to look up now that the name is known Base-14.
    try:
        insert_rect = _insertion_rect(page, rect, target.font, target.size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad
```

and replace it with:

```python
    # ---- font resolution ----
    # Resolves the block's own real font (extracted from the source PDF
    # and re-embedded), falling back through Base-14 and finally PyMuPDF's
    # bundled broad-coverage font -- see _select_font's docstring. Raises
    # ValueError before any mutation if no tier covers new_text.
    resolved_fontname, resolved_font = _select_font(handle, page, target, new_text)

    # ---- geometry ----
    try:
        insert_rect = _insertion_rect(page, rect, resolved_font, target.size)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad
```

Finally, in the shrink-retry loop, change:

```python
            remaining_space = page.insert_textbox(
                insert_rect,
                new_text,
                fontname=target.font,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
```

to:

```python
            remaining_space = page.insert_textbox(
                insert_rect,
                new_text,
                fontname=resolved_fontname,
                fontsize=fontsize,
                color=(0, 0, 0),
            )
```

Update `replace_text`'s docstring: the `Raises: ValueError` entry currently reading "target.font is not one of PyMuPDF's built-in Base-14 fonts (replace_text draws with built-in fonts only -- it has no way to load an embedded or system font file)" must be replaced with something reflecting the new cascade, e.g. "no available font (the block's own real font, a Base-14 fallback, or PyMuPDF's bundled broad-coverage font) can render every character in new_text — see _select_font". Leave every other `Raises` entry and the rest of the docstring's extensive documentation of the shrink-retry loop, the erase/insert rect distinction, and the PyMuPDF 1.28.2 investigation findings exactly as-is — none of that changed.

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: all tests pass, including the 4 new cascade tests and the updated `test_insertion_rect_...` and `test_replace_text_falls_back_to_base14_when_font_is_not_embedded_anywhere` tests.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing. Note the exact count in your report (126 from Task 1; this task replaces 1 existing test 1-for-1 with `test_replace_text_falls_back_to_base14_when_font_is_not_embedded_anywhere` and adds 3 genuinely new tests, net +3 = 129).

- [ ] **Step 8: Commit**

```bash
git add engine/operations.py tests/test_operations.py tests/fixtures/generate_fixtures.py tests/fixtures/embedded_custom_font.pdf
git commit -m "feat: wire the three-tier font cascade into replace_text"
```

---

## Task 3: Real-document verification and documentation

**Files:**
- Modify: `README.md` (if it documents `replace_text`'s font constraint — check first)

**Interfaces:** none — verification and docs only, no new code.

- [ ] **Step 1: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: 100% passing, pristine output.

- [ ] **Step 2: Real-document verification**

Download the same two real PDFs the original reliability spike used (a real IRS Form 1040 and a real arXiv paper — any similarly-real, non-network-fixture PDF with embedded non-Base-14 fonts works if these specific ones are unavailable):

```bash
curl -sL -o /tmp/irs_form1040.pdf "https://www.irs.gov/pub/irs-pdf/f1040.pdf"
curl -sL -o /tmp/arxiv_paper.pdf "https://arxiv.org/pdf/1706.03762"
```

For each, parse it with the engine, pick a handful of real text blocks (not just the first one), and call `replace_text` on each with a short replacement string, confirming:
- No `ValueError` is raised for ordinary replacement text (proving Tier 1 or Tier 2 succeeds where the pre-fix code would have raised "not Base-14" on effectively every block).
- The exported document opens cleanly and the replacement text is genuinely present when re-extracted.

This is manual verification, not part of the automated suite (same "no network calls in the automated suite" rule this project has followed throughout) — a short ad-hoc script is fine, it does not need to be committed.

- [ ] **Step 3: Check the README**

Read `README.md`'s description of `replace_text` (currently states: "Requires the block's font to be one of PyMuPDF's built-in Base-14 fonts; embedded/system fonts are not supported."). This is no longer accurate. Replace it with a short, accurate description of the new behavior: it now draws with the block's own real font when possible, falling back through a Base-14 substitute and finally a broad-coverage font, and only fails if literally no available font can render the replacement text's characters.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update replace_text's font-support description"
```

---

## Final Verification

After all 3 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — 100% passing.
2. Confirm `redact_region`, `_validate_target`, `_erase_region`, `_sample_background_color`, the shrink-retry loop's sizing constants (`_SHRINK_STEP`, `_SHRINK_FLOOR_RATIO`, `_WIDTH_PRECISION_PAD_PT`), and `webui/`/`engine/parser.py`/`engine/document.py` are completely untouched by this plan: `git diff <plan-start-commit>..HEAD -- webui/ engine/parser.py engine/document.py` should be empty, and `git diff <plan-start-commit>..HEAD -- engine/operations.py` should show only the changes this plan describes.
3. Re-run Task 3 Step 2's real-document verification one more time as a final sanity check.
