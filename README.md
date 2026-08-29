# pdf-ai-engine

Headless, deterministic PDF redaction and text-replacement engine (v0.2). A
Python library, not a service: parse a PDF into a read-oriented `Document`
projection, locate the region or text block to change, call an operation, and
export the result. No AI/LLM, no auto-detection of what to change, no auth,
no web UI.

## Operations

- `redact_region(handle, page_index, bbox)` (v0.1) -- black out a rectangular
  region and strip its content, so the removed text is unextractable rather
  than merely covered. See
  `docs/superpowers/specs/2026-08-25-redaction-engine-v0.1-design.md`.
- `replace_text(handle, page_index, target, new_text)` (v0.2) -- replace one
  `TextBlock`'s text in place, preserving layout: the replacement is drawn at
  the block's own position and font, word-wrapped and shrunk (to at most 50%
  of the original size) to fit the block's own region. It never reflows
  neighbouring content -- text that cannot fit even at the shrink floor
  raises `ValueError`. Requires the block's font to be one of PyMuPDF's
  built-in Base-14 fonts; embedded/system fonts are not supported. See
  `docs/superpowers/specs/2026-08-28-layout-preserving-text-replace-v0.2-design.md`.

## Setup

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[test]"
```

## Test

```
./.venv/Scripts/python.exe -m pytest
```

## Manual verification web UI

A local, single-user tool for exercising `redact_region`/`replace_text` by
hand against a real PDF: upload a file, click a text block, redact or
replace it, and download the result. Not a product -- no auth, no
persistence beyond one session.

```
pip install -e ".[test,webui]"
python -m uvicorn webui.main:app --reload
```
