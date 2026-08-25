# 8848 PDF — Redaction Engine v0.1 — Design

## Overview

First buildable slice of 8848 PDF AI (see the 8848 Lab master strategy
document — this product is the company's current ~60% engineering focus).
The long-term product is AI-driven, layout-preserving PDF editing; this
spec covers only the foundation: a headless, deterministic redaction
engine, with no AI, no auth, and no UI. Matches the master doc's own
"Months 1-2: Document foundation" phase (ingestion, parser, DOM,
deterministic modifications, save/export, visual comparison/testing).

**Why redaction first, and why manual (not auto-detect) first:** redaction
is the narrowest of the doc's listed use cases — it needs no text reflow,
no font-fitting, no layout reconstruction (the hardest, most strategically
important problem for the product overall) — so it proves out the base
document model and true content-removal mechanics without also solving
the harder layout problem at the same time. Auto-detecting *what* to
redact (PII pattern-matching/NER) is deliberately deferred past v0.1: it's
a separate, independent problem (text classification) layered on top of
a region already being redact-able by coordinate, and bundling it in now
would block validating the engine on the AI layer being ready too.

**Why headless, no product shell yet:** the user's own framing — PDF is
the main focus first; auth, UI components, storage, and deployment
infrastructure get reused from Himalaya once there's an actual product to
wrap around the engine, not designed fresh now. Building that shell before
the core redaction mechanism is proven would be solving problems (auth,
billing, hosting) this repo doesn't need answered yet to find out whether
PyMuPDF-based redaction actually holds up.

## Non-goals (explicit, this pass)

- No AI/LLM anything — not even the "detect what to redact" layer.
- No authentication, no multi-user/multi-tenant concept, no billing.
- No web UI. No file upload endpoint, no storage backend (SeaweedFS or
  otherwise) — input/output are local file paths for now.
- No operations beyond `redact_region` — no text rewrite, no page
  deletion, no image replacement. Those come later, once this exact
  pattern (parse → operate → export → verify) is proven for the simplest
  case.
- No deployment/hosting story. This ships as a Python library with tests,
  runnable locally — not a running service.

## Architecture

**Language/stack:** Python, PyMuPDF (`pymupdf` on PyPI, imported as
`fitz`) as the core PDF library — chosen specifically because its
`Page.add_redact_annot()` + `Page.apply_redactions()` API performs real
content-stream removal (deletes the covered text/image data), not a
visual-only overlay. A black rectangle drawn over text with most other
PDF libraries leaves the underlying text fully copy-pasteable/extractable
by script — that would defeat the actual point of this feature for a
compliance-minded buyer, so this API choice is load-bearing, not
incidental.

**Package layout:**
```
pdf-ai/
  engine/
    __init__.py
    document.py       # Document/Page/TextBlock/Image dataclasses
    parser.py         # PDF bytes -> Document (read-only introspection)
    operations.py      # redact_region(doc, page_index, bbox) -> Document
    export.py          # Document + underlying PyMuPDF handle -> PDF bytes
  tests/
    fixtures/           # sample PDFs checked into the repo for test input
    test_parser.py
    test_operations.py
    test_export.py
    test_visual_regression.py
  pyproject.toml
```

No `api/` or `web/` directory yet — deliberately not scaffolded ahead of
need (YAGNI). When the product shell gets built later, it wraps `engine/`
from the outside; `engine/` itself never grows a FastAPI/HTTP dependency.

## Data model

```python
@dataclass
class TextBlock:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1, PDF points
    font: str
    size: float

@dataclass
class Image:
    bbox: tuple[float, float, float, float]
    # raw image bytes/xref handled internally by parser.py; not exposed
    # on this dataclass in v0.1 -- nothing yet needs to read image bytes
    # back out, only know where images are for redaction-region purposes.

@dataclass
class Page:
    index: int
    width: float
    height: float
    text_blocks: list[TextBlock]
    images: list[Image]

@dataclass
class Document:
    pages: list[Page]
```

`Document`/`Page`/`TextBlock`/`Image` are a **read-oriented projection**
for callers to inspect (e.g. to find candidate redaction coordinates) —
they are not themselves mutated in place by `redact_region`. The actual
mutation happens against PyMuPDF's own live document handle, which
`parser.py` also returns (or which `Document` wraps privately) so
`operations.py`/`export.py` can act on the real PDF object model rather
than reconstructing one from the dataclasses. This avoids building a
second, parallel PDF-writing layer in v0.1 — PyMuPDF's own object model
already is the write path; the dataclasses exist for *reading*/
*targeting*, not for *writing*.

## Operations

**`redact_region(handle, page_index: int, bbox: tuple[float, float, float, float]) -> None`**

Mutates the PyMuPDF document handle in place:
1. `page = handle[page_index]`
2. `page.add_redact_annot(bbox, fill=(0, 0, 0))` — marks the region,
   black fill for the visible result.
3. `page.apply_redactions()` — actually removes the underlying
   text/image content within the marked region; this is the step that
   makes it a real redaction rather than an overlay.

Multiple calls (different regions, same or different pages) accumulate;
`apply_redactions()` can be called once per page after all of that page's
regions are marked, or once per `add_redact_annot` call — v0.1 calls it
once per single-region operation for simplicity, batching is a later
optimization if performance ever demands it.

## Export

**`export(handle) -> bytes`** — thin wrapper over PyMuPDF's own
`handle.write()` (technically `tobytes()`/`save()` depending on PyMuPDF's
API surface — confirm the exact current method name against PyMuPDF's
installed version's docs before implementing, don't assume from
training-data familiarity, since PyMuPDF's API has changed across major
versions). Returns raw PDF bytes; the plan's tasks write these to a file
in tests, and (later, out of scope here) an eventual API layer would
stream them back to a caller.

## Testing strategy — this is the actual proof of correctness

Three properties must all hold, and none of them alone is sufficient:

1. **Visual: only the target region changed.** Render the original and
   redacted PDF pages to raster images (PyMuPDF can do this directly via
   `page.get_pixmap()`), diff them pixel-by-pixel. Assert: the redacted
   bbox region differs (now black), every other pixel is identical. A
   naive "did the file change at all" test is not enough — this proves
   *only the intended area* changed, catching accidental damage to
   surrounding content.
2. **Content: the redacted text is actually gone.** Extract text from the
   redacted PDF (`page.get_text()`) and assert the originally-present
   string within that region no longer appears anywhere in the extracted
   text of that page. This is what proves it's a real redaction, not a
   black rectangle sitting on top of extractable text — the single most
   important test in this whole engine, given the reasoning in
   Architecture above.
3. **Structural: the PDF is still a valid, openable document.** Re-parse
   the exported bytes with PyMuPDF and confirm it opens without error,
   has the same page count, and other pages' text/images are byte-for-
   byte or pixel-for-pixel unchanged from the original (not just the
   redacted page — a bug in export/write could theoretically corrupt
   unrelated pages).

Test fixtures: a handful of real, varied sample PDFs checked into
`tests/fixtures/` (a simple single-page text document, a multi-page
document, one with an image, one with mixed text+image on the same page)
— not synthetically generated PDFs with no real-world formatting
quirks, since PyMuPDF's behavior on genuinely varied documents is exactly
what needs proving.

## Explicitly out of scope (this pass)

- Auto-detecting what to redact (PII/NER/pattern-matching) — a
  deliberately separate, later problem (see Overview).
- Any operation other than `redact_region`.
- Any AI/LLM integration at all.
- Auth, multi-tenancy, storage, deployment, or a web/API surface.
- Performance/batching optimization for many-region redaction — v0.1
  proves correctness on realistic small documents, not throughput.
