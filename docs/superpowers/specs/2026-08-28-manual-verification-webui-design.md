# 8848 PDF — Manual Verification Web UI — Design

## Overview

A minimal local web tool for manually exercising `engine.operations.redact_region`
and `engine.operations.replace_text` against real, arbitrary PDFs — not a
product, not the eventual "Cursor for documents" UI (see the master strategy
document and the two design specs this repo already has for that longer-term
direction). This exists to answer one question by hand: upload a PDF you
didn't author with the engine's own fixture generator, click a piece of text,
redact or replace it, and *see* whether the engine actually behaves the way
its 54 automated tests claim it does — especially against real-world
documents (Word/Docs/LaTeX exports) that exercise paths the engine's own
PyMuPDF-authored fixtures structurally cannot, which is exactly the class of
gap that caught the Critical non-Base-14-font bug in v0.2's final review.

**Why a real web app and not a script:** clicking through is materially
faster than re-running a script with different coordinates for every probe,
and a rendered page image is the only reliable way to confirm a redaction
looks right, not just extracts right.

**Why FastAPI, why outside `engine/`:** `engine/` has never grown an
HTTP/web dependency and this doesn't change that — every prior spec in this
repo states that constraint explicitly, and this UI is the first thing in
the repo that actually needs FastAPI, so it gets its own top-level
directory and its own optional dependency group, not a change to `engine/`
or its core install footprint.

## Non-goals (explicit, this pass)

- Not the product UI. No auth, no multi-user concept, no persistence beyond
  one in-memory session, no deployment story — this runs on `localhost` via
  `uvicorn`, for one person, in one browser tab, and is not meant to survive
  a server restart.
- No click-and-drag region selection. Targets are chosen from the list of
  `TextBlock`s the engine's own `parse()` already produces — this exercises
  the engine's real, designed calling convention (parse → find TextBlock →
  operate) rather than inventing a second, UI-only targeting mechanism.
- No new engine capability. This UI calls `redact_region` and `replace_text`
  exactly as they exist today; it does not add operations, does not work
  around the "no cross-paragraph reflow" or "Base-14 only" limitations, and
  surfacing their `ValueError`s cleanly is itself part of what this tool is
  for.
- No image-based targeting (redacting/replacing an `Image` from the
  `Document` model) — text is the immediate priority; if this tool proves
  useful, image targeting is a small, separate follow-up, not bundled here.

## Architecture

**Language/stack:** Python, FastAPI + `uvicorn` (dev server) for the
backend; a single static HTML page with vanilla JavaScript for the
frontend — no build step, no framework, consistent with keeping this a
fast, disposable verification tool rather than a product investment.

**Package layout:**
```
pdf-ai/
  webui/
    __init__.py
    main.py           # FastAPI app + routes
    session.py         # in-memory session: the current fitz.Document handle
                        # and the current block registry
    static/
      index.html        # the single page
      app.js             # upload / render / click-to-act / download logic
  tests/
    test_webui.py       # FastAPI TestClient tests against real fixtures
  pyproject.toml         # + [project.optional-dependencies] webui group
```

`webui/` depends on `engine/`; `engine/` never imports anything from
`webui/`. This is the same one-directional dependency shape the design
specs for `redact_region`/`replace_text` already assumed a future product
shell would have.

**New dependencies** (added under a `webui` extra, not the base
`pdf-ai-engine` install, so `pip install -e ".[test]"` for pure engine work
stays exactly as light as it is today):
```toml
[project.optional-dependencies]
webui = ["fastapi>=0.110", "uvicorn[standard]>=0.29", "python-multipart>=0.0.9"]
```
(`python-multipart` is FastAPI's own requirement for handling file-upload
form data — confirm the exact minimum version against what's actually
importable once installed, same caution this repo has applied to every
PyMuPDF version assumption so far.)

**Running it:** `./.venv/Scripts/python.exe -m pip install -e ".[webui]"`
then `./.venv/Scripts/python.exe -m uvicorn webui.main:app --reload`,
opened at `http://127.0.0.1:8000`.

## Session and state handling

One module-level, in-process session in `webui/session.py` — no cookies, no
session IDs, no database. Concretely:

```python
_state: dict = {"handle": None, "blocks": []}
```

- `handle`: the live `fitz.Document` returned by `engine.parser.parse()`,
  held across requests exactly the way `redact_region`/`replace_text`
  already expect callers to hold it (both mutate the handle in place; this
  is the intended usage pattern, not a webui-specific hack).
- `blocks`: a flat list built fresh after every upload and after every
  mutation, one entry per `TextBlock` across every page:
  `{"id": int, "page_index": int, "block": TextBlock}`. The `id` is simply
  the entry's position in this list — valid only until the next mutation
  (which rebuilds the list from a fresh `parse()` of the current handle's
  exported state), which is fine since the frontend always re-fetches the
  full block list after every action and never reuses an id across a
  server response boundary.

A single global dict (not thread-local, not request-scoped) is correct
here specifically because this tool is single-user/single-tab by design
(a Non-goal above) — `uvicorn --reload`'s dev server is not meant to
serve concurrent unrelated sessions, and adding session-ID plumbing for a
tool nobody but the operator will ever open twice at once is exactly the
kind of premature complexity this spec's Non-goals exist to rule out.

## API surface

All under `webui/main.py`, all returning JSON except the image and export
endpoints.

**`POST /api/upload`** — multipart file upload (`file: UploadFile`). Reads
the bytes, calls `engine.parser.parse()`, stores the handle and rebuilds
the block registry in session state, returns:
```json
{
  "pages": [
    {"index": 0, "width": 612.0, "height": 792.0}
  ],
  "blocks": [
    {"id": 0, "page_index": 0, "text": "...", "font": "Helvetica", "size": 12.0}
  ]
}
```
(`bbox` is intentionally omitted from the block JSON — the frontend never
needs to know coordinates, it only ever references a block by `id`.)

**`GET /api/page/{page_index}.png`** — renders the CURRENT state of that
page (i.e. reflecting every mutation applied so far this session) via
`handle[page_index].get_pixmap().tobytes("png")` and returns it as
`image/png`. No caching headers — the frontend is responsible for
cache-busting (e.g. appending `?v=<mutation-count>` to the URL) so a
browser doesn't show a stale image after an edit.

**`POST /api/redact`** — body `{"block_id": int}`. Looks up the block's
`page_index` and `block.bbox` from the current registry, calls
`redact_region(handle, page_index, block.bbox)`. On success, rebuilds the
block registry from a fresh `parse()` of the handle's current state and
returns the same shape `/api/upload` returns (fresh `pages`/`blocks`). On
`ValueError` from the engine, returns HTTP 400 with
`{"error": "<the engine's own message>"}` — the engine's error messages are
already written to be actionable (see `redact_region`'s and
`replace_text`'s own docstrings), so this tool passes them through
verbatim rather than wrapping or paraphrasing them.

**`POST /api/replace`** — body `{"block_id": int, "new_text": str}`. Looks
up the block, calls `replace_text(handle, page_index, block, new_text)`.
Same success/error shape as `/api/redact`.

**`GET /api/export`** — calls `engine.export.export(handle)` on the current
session state and returns the bytes with
`Content-Disposition: attachment; filename="edited.pdf"` and
`media_type="application/pdf"`. Returns HTTP 400 with a clear
`{"error": "no document loaded"}` if called before any upload.

**`POST /api/reset`** — clears session state (`handle = None`,
`blocks = []`), for starting over with a different PDF without restarting
the server.

## Frontend

`webui/static/index.html` + `webui/static/app.js`. One page, roughly:

- A file input + "Upload" button, posting to `/api/upload`.
- After upload (and after every subsequent action), the page re-renders:
  one `<img src="/api/page/{i}.png?v={n}">` per page, and beneath each
  page's image, the list of that page's blocks — each showing its text
  snippet, a "Redact" button, and a text input + "Replace" button.
- Clicking Redact/Replace POSTs to the corresponding endpoint, then
  re-renders using the response's fresh `pages`/`blocks` (no separate
  re-fetch needed — the mutation endpoints already return the post-mutation
  state).
- Any `{"error": ...}` response (HTTP 400) is shown as a plain, visible
  message on the page — not swallowed, not just logged to the console,
  since seeing the engine's real error messages surface correctly is
  itself part of what this tool verifies.
- A persistent "Download edited PDF" link/button pointing at
  `/api/export`.
- A "Start over" button posting to `/api/reset`.

No client-side framework, no build tooling — plain `fetch()` calls and
direct DOM manipulation, matching this tool's disposable, verification-only
purpose.

## Testing strategy

Given this tool's own purpose is manual verification, automated tests here
cover the *web layer's* correctness (does it call the engine right, does it
map errors right) — not a re-proof of the engine's own behavior, which
already has 54 tests. Using FastAPI's `TestClient` against real fixture
PDFs already in `tests/fixtures/` (no new fixtures needed for this layer):

1. **Upload round-trip**: POST a real fixture (`simple_text.pdf`) to
   `/api/upload`, assert the response's `blocks` list contains an entry
   whose `text` includes the fixture's known string (`REDACT-ME-12345`).
2. **Redact end-to-end**: upload, find that block's `id` from the upload
   response, POST it to `/api/redact`, then GET `/api/export` and assert
   the exported bytes' extracted text no longer contains
   `REDACT-ME-12345` — i.e. this test goes through the real engine, not a
   mock.
3. **Replace end-to-end**: same shape, POST to `/api/replace` with a
   `new_text`, assert the exported bytes contain the new string and not
   the old one.
4. **Error mapping**: POST an empty `new_text` to `/api/replace` (a case
   `replace_text` itself is documented to reject), assert HTTP 400 and
   that the response body's `error` field is non-empty — proving the
   engine's `ValueError` → HTTP-400 mapping actually fires, not just that
   *a* 400 comes back for some unrelated reason (also assert the original
   text is still present in a subsequent export, proving nothing was
   mutated by the rejected call).
5. **Export before upload**: GET `/api/export` with no prior upload in a
   fresh test session, assert HTTP 400 with a clear error rather than a
   500/crash.
6. **Page image renders**: after upload, GET `/api/page/0.png`, assert
   HTTP 200 and `content-type: image/png` and non-empty bytes.

Each test gets its own fresh `TestClient` (FastAPI's `TestClient` doesn't
share module-level Python state across separate test *processes*, but
since `webui/session.py`'s state is a plain module-level dict, tests
*within the same process* DO share it unless explicitly reset — call
`/api/reset` at the start of every test, or use a pytest fixture that does
so, to keep tests independent regardless of execution order).

## Explicitly out of scope (this pass)

- Click-and-drag / canvas-based region selection.
- Image-block redaction/replacement (text only, this pass).
- Any persistence, auth, multi-session support, or deployment story.
- Any new engine operation or engine capability.
- A "pick from the engine's own test fixtures" convenience — upload only;
  the whole point is exercising the engine against documents it didn't
  author.
