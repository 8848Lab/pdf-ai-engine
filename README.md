# pdf-ai-engine

Headless, deterministic PDF redaction engine (v0.1). A Python library, not a
service: parse a PDF into a read-oriented `Document` projection, locate a
region to redact, call `redact_region`, and export the result. No AI/LLM,
no auth, no web UI -- see `docs/superpowers/specs/2026-08-25-redaction-engine-v0.1-design.md`.

## Setup

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[test]"
```

## Test

```
./.venv/Scripts/python.exe -m pytest
```
