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

A local, single-operator tool for exercising `redact_region`/`replace_text`
by hand against a real PDF: upload a file, click a text block, redact or
replace it, and download the result. Not a product -- run it on your own
machine only: no auth, no multi-user concept, and nothing is stored beyond
the one in-process session, which is discarded when the server stops.

FastAPI and uvicorn live in the optional `webui` extras group, so the
engine-only install (`.[test]` above) does not pull them in; the webui tests
skip themselves when they are absent.

```
./.venv/Scripts/python.exe -m pip install -e ".[test,webui]"
./.venv/Scripts/python.exe -m uvicorn webui.main:app --reload
```

## AI instruction layer

An optional page section that turns a natural-language instruction (e.g.
"redact the patient ID") into `redact_region`/`replace_text` calls, decided
by Claude via tool use: it reads the current block list, picks the block(s)
the instruction refers to, and calls the matching tool -- or says so in its
summary if nothing matches, rather than guessing. Three providers are supported:

- **Anthropic**: BYOK with your own API key (paste into the browser field or set
  `ANTHROPIC_API_KEY` on the server and leave blank). Base URL and model are
  optional. The key is never stored -- held only for the duration of one request.
- **OpenAI-compatible**: Any server that speaks the OpenAI API (e.g. Ollama's own
  OpenAI-compat shim, LM Studio, vLLM, real OpenAI, or other clouds). Requires
  base URL and model. API key is optional (some servers have no auth).
- **Ollama (native)**: Direct Ollama protocol. Requires model. Base URL defaults
  to `http://localhost:11434` if not specified. No API key needed.

Requires the optional `ai` extras group on top of `webui`:

```
./.venv/Scripts/python.exe -m pip install -e ".[test,webui,ai]"
```
