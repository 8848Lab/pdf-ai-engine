# 8848 PDF — Layout-Preserving Text Replace v0.2 — Design

## Overview

The second buildable slice of 8848 PDF AI (see the 8848 Lab master strategy
document — this product is the company's current ~60% engineering focus,
and the long-term product direction is "Cursor for documents": a
chat-driven AI layer that reads a document, proposes precise edits, and
applies them via a small set of deterministic tools). v0.1
(`docs/superpowers/specs/2026-08-25-redaction-engine-v0.1-design.md`) built
`redact_region` — real content removal, chosen first specifically because
deletion never needs text reflow. This spec covers the operation v0.1
explicitly deferred as "the hardest, most strategically important problem
for the product overall": replacing a run of text with different text that
may be a different length, and having the surrounding layout absorb that
difference instead of the document simply breaking.

Same headless philosophy as v0.1: no AI, no auth, no UI. The engine stays
a deterministic library of tools; a future AI/chat layer calls into it the
same way an editor's agent calls a small set of well-defined tools — it
does not live inside this engine.

**Why same-line/same-block only, and why that's still the hard part:**
v0.1 was chosen to be narrow (redaction) so it could prove the base
document model and true content-removal mechanics without also solving
layout. This slice is deliberately still narrow in the *other*
direction — it takes on reflow, but bounds it to a single text block, so a
failure here is legible as "reflow doesn't work" rather than tangled up
with multi-page pagination. Cross-paragraph and cross-page cascading
reflow (a real word processor's behavior) is explicitly a later slice.

## Non-goals (explicit, this pass)

- No AI/LLM anything, no auto-detection of what text to replace — the
  caller supplies the exact target (`TextBlock`) and the new text, the
  same way `redact_region` requires an explicit bbox today.
- No cross-paragraph or cross-page cascading reflow. Text that doesn't fit
  its own block raises; it does not push later content down the page.
- No style changes as part of an edit. New text keeps the original
  block's font/size (PyMuPDF's own auto-shrink may reduce the size to
  fit); no per-character styling (can't make half the replacement bold),
  no font-family changes.
- No handling for gradient, patterned, or photographic backgrounds — only
  solid-color regions (see "Background sampling" below for why, and what
  this does and doesn't cover).
- No authentication, no multi-user/multi-tenant concept, no billing.
- No web UI, no file upload endpoint, no storage backend. Input/output
  stay local file paths or in-memory bytes.
- No deployment/hosting story — still a Python library with tests,
  runnable locally.

## Architecture

**Language/stack:** unchanged from v0.1 — Python, PyMuPDF (`pymupdf` on
PyPI, imported as `import pymupdf as fitz`).

**Package layout:**
```
pdf-ai/
  engine/
    document.py       # unchanged — TextBlock already carries bbox/font/size,
                       # exactly what this operation needs as its target
    parser.py          # unchanged
    operations.py       # + replace_text, + _sample_background_color (private)
    export.py          # unchanged
  tests/
    fixtures/
      colored_background.pdf   # new fixture: solid-color box behind text
    test_operations.py         # + replace_text tests
    test_visual_regression.py  # + replace_text end-to-end tests
```

`replace_text` and its private background-sampling helper live in the
existing `operations.py`, not a new file — both are "mutating operations
against a live PyMuPDF handle," the same single responsibility that file
already has, and the helper is small and used by nothing else. No new
top-level module is warranted for one private function.

## Operation

**`replace_text(handle: fitz.Document, page_index: int, target: TextBlock, new_text: str) -> None`**

Takes a `TextBlock` directly rather than a raw bbox — the first operation
to use the `Document`/`TextBlock` projection as a real targeting
interface (mirroring the round-trip test v0.1's final review added:
`parse()` → find a `TextBlock` → act on it → `export()`). A caller (a
future AI layer, or a test) gets the target by calling `parse()` and
locating the `TextBlock` whose `.text` matches what should change; this
operation's job starts once that target is already known.

Validation, mirroring `redact_region`'s existing checks:
1. `page_index` out of range → `ValueError`.
2. `target.bbox`, normalized, empty or non-intersecting with the page →
   `ValueError` (reuses the same normalize/validate logic `redact_region`
   already has for its bbox parameter).
3. `new_text` empty → `ValueError` ("use redact_region to delete without
   replacing").

Mechanism, once validated:
1. **Sample the background color** in a thin margin just outside
   `target.bbox`'s four edges (see "Background sampling" below).
2. **Erase** the old content: the same underlying PyMuPDF redaction
   mechanic `redact_region` uses (`add_redact_annot` + `apply_redactions`
   with the same explicitly-pinned modes), but filled with the sampled
   background color instead of black — this is a private, minimal
   duplication of `redact_region`'s two-call mechanic, not a call to
   `redact_region` itself, since `redact_region`'s whole public contract
   is "visibly blacken" and that contract shouldn't grow a hidden
   fill-color parameter for this unrelated use case.
3. **Draw the new text**: PyMuPDF's `Page.insert_textbox(target.bbox,
   new_text, fontname=target.font, fontsize=target.size, ...)`, using
   PyMuPDF's own word-wrap and auto-shrink (`fontsize=0`-style auto-fit,
   or the closest current-version equivalent — confirm the exact
   parameter against the installed PyMuPDF version before implementing,
   same caution v0.1 applied to `tobytes`/`apply_redactions`).
4. If `insert_textbox` reports it could not fit the text (its own
   documented failure signal — confirm what that looks like on the
   installed version: a raised exception, a non-zero/negative return
   value, or something else) even after auto-shrink and wrap, raise
   `ValueError` rather than allowing silent overflow/clipping.

## Background sampling

**`_sample_background_color(page: fitz.Page, bbox: fitz.Rect) -> tuple[float, float, float]`** (private)

Renders the page (or just the region around `bbox`, whichever is cheaper
and simpler to get right — implementer's call, confirm against the
installed PyMuPDF's pixmap-region API) and samples a handful of points in
a small margin just *outside* `bbox`'s four edges — not inside, since
`bbox` by definition tightly bounds the old text, and inside it means
edge pixels are just as likely to be glyph strokes as background. Sample
at each edge's midpoint, offset outward by a few points so anti-aliasing
at the exact boundary doesn't contaminate the read. Take the **median**
RGB across the samples (not mean — robust against one sample landing on a
stray mark, e.g. a neighboring character's overshoot or a rule line),
convert from the pixmap's 0-255 range to PyMuPDF's 0.0-1.0 fill-color
range, and return it.

This generalizes v1's original "just assume white" idea to any
solid-color background — light-gray form fields, colored highlight or
callout boxes, tinted section headers — without attempting anything
smarter than a color read. It does not, and cannot, handle a gradient,
pattern, or photograph behind the text: sampling a handful of points
returns *a* color, not the real erased pixels, so the erased patch would
look visibly wrong against a non-solid background. This is a real,
inherent limitation of solid-fill erasure (shared by every redaction/edit
tool that works this way, not specific to this implementation) — it is
explicitly out of scope to solve here, and is the actual limitation this
spec's Non-goals section documents, in place of the earlier "white only"
framing.

## Testing strategy

Extends v0.1's three-property proof (visual / content / structural), plus
a new fit-quality category specific to this operation:

1. **Visual**: reuse v0.1's pixel-diff harness, adapted so the target
   region is expected to show new rendered content (not black). New case:
   using the `colored_background.pdf` fixture, confirm the erased-and-redrawn
   region's background stays the sampled color (not white) around the new
   text.
2. **Content**: extracted text contains the *new* string and no longer
   contains the *old* string — both directions checked, same
   `get_text()`-based proof v0.1 used for `redact_region`.
3. **Structural**: document stays valid, page count unchanged, every page
   and text block *outside* the edited one is byte-identical to the
   original — unchanged from v0.1's structural property.
4. **Fit-quality** (new):
   - Same-length replacement: font size and general appearance
     essentially unchanged (spot-check `TextBlock.size` via a fresh
     `parse()` of the exported result, or a visual containment check).
   - Shorter replacement: no leftover artifacts from the old text, no
     obviously-wrong empty gap.
   - Longer-but-fits replacement: proves auto-shrink actually engaged
     (the re-parsed `TextBlock.size` after the edit should be smaller
     than `target.size`).
   - Deliberately-too-long replacement: proves the fail-loudly path
     (`ValueError` raised, and — important, mirroring v0.1's fix-wave
     posture — the document is left byte-identical to before the failed
     call, i.e. a failed `replace_text` must not leave the handle
     partially mutated).

Test fixtures: extend `tests/fixtures/generate_fixtures.py` with one new
fixture, `colored_background.pdf` (a single page, one text run drawn over
a solid, non-white rectangle — e.g. light blue), generated the same
programmatic way the existing four fixtures are, for the same documented,
honest reason (no source of real-world PDFs in this environment).

## Explicitly out of scope (this pass)

- Cross-paragraph/cross-page cascading reflow.
- Any AI/LLM/auto-detection of what to replace.
- Per-character/run styling changes (bold, italic, font-family changes)
  as part of a replace.
- Gradient/patterned/photographic background erasure.
- Auth, multi-tenancy, storage, deployment, or a web/API surface — same
  as v0.1.
- Any operation other than `redact_region` (v0.1) and `replace_text`
  (this spec).
