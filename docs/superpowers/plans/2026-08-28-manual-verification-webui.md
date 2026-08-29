# Manual Verification Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal local FastAPI + vanilla-JS web tool for manually exercising `redact_region`/`replace_text` against real, arbitrary PDFs — upload, see the pages, click a text block, redact or replace it, download the result.

**Architecture:** A new top-level `webui/` package (FastAPI backend, single static HTML+JS page) sits entirely outside `engine/` and depends on it one-directionally. A single in-process session (a plain module-level dict) holds the current PyMuPDF document handle and the block registry built from its last parse — no auth, no persistence, no multi-user concept.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn (dev server), vanilla HTML/JS (no build step), pytest + FastAPI's `TestClient` (httpx-based).

**Spec:** `docs/superpowers/specs/2026-08-28-manual-verification-webui-design.md`

## Global Constraints

- `engine/` never imports anything from `webui/`, and this plan never modifies any file under `engine/`. The dependency is one-directional: `webui/` depends on `engine/`.
- No auth, no multi-user concept, no persistence beyond one in-process session, no deployment story. This runs on `localhost` via `uvicorn` for one operator in one browser tab.
- Targets are chosen from the `TextBlock` list `engine.parser.parse()` already produces — no click-and-drag/canvas region selection in this pass.
- No new engine capability, no engine file changes. This UI calls `redact_region`/`replace_text` exactly as they exist today.
- New dependencies (`fastapi`, `uvicorn`, `python-multipart`, `httpx`) live under a `webui` extras group in `pyproject.toml`, never in the base install — `pip install -e ".[test]"` alone (pure engine work) must not pull in FastAPI.
- Image-block redaction/replacement, a "pick from the engine's own fixtures" shortcut, and anything resembling the eventual product shell (see the redaction/text-replace specs) are out of scope for this plan.

---

## Task 1: Scaffolding, session state, and the upload endpoint

**Files:**
- Modify: `pyproject.toml`
- Create: `webui/__init__.py`
- Create: `webui/session.py`
- Create: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `engine.parser.parse`, `engine.export.export`, `engine.operations.redact_region`, `engine.operations.replace_text`, `engine.document.Document`/`TextBlock` (all existing, unchanged).
- Produces: `webui.session.load_document(pdf_bytes: bytes) -> None`, `webui.session.get_handle() -> fitz.Document`, `webui.session.get_block(block_id: int) -> dict`, `webui.session.get_blocks_summary() -> list[dict]`, `webui.session.get_pages_summary() -> list[dict]`, `webui.session.reset() -> None` (all consumed by Tasks 2-4). `webui.main.app` (the FastAPI instance, consumed by every later task and by `tests/test_webui.py`). `POST /api/upload`.

- [ ] **Step 1: Add the `webui` extras group and register the new package**

In `pyproject.toml`, add to `[project.optional-dependencies]` (after the existing `test` block):

```toml
webui = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
]
```

`httpx` is listed here (not under `test`) because FastAPI's `TestClient` (used by `tests/test_webui.py`) requires it, and it is meaningless without the rest of the `webui` stack — installing `webui` is what gets you both the ability to run this tool and the ability to test it. `pip install -e ".[test]"` alone stays exactly as light as it is today for pure engine work.

Change `[tool.setuptools]`'s `packages` line from `packages = ["engine"]` to:

```toml
packages = ["engine", "webui"]
```

- [ ] **Step 2: Install and confirm the versions**

Run: `./.venv/Scripts/python.exe -m pip install -e ".[test,webui]"`
Expected: installs cleanly. Confirm the installed versions actually satisfy the floors above (`pip show fastapi uvicorn python-multipart httpx`) and note any surprises in your report — this repo has a established habit of verifying dependency assumptions rather than trusting version floors blindly.

- [ ] **Step 3: Create the empty package**

Create `webui/__init__.py` (empty file).

- [ ] **Step 4: Write the session module**

Create `webui/session.py`:

```python
"""In-process session state: the current live PyMuPDF document handle and
the block registry built from its last parse.

A single module-level dict, not per-request/per-user state, is correct
here specifically because this tool is single-operator by design (see the
design spec's "Session and state handling" section) -- there is no
concurrent-session concern to design around.
"""
import pymupdf as fitz

from engine.document import Document
from engine.export import export
from engine.operations import redact_region, replace_text
from engine.parser import parse

_state: dict = {"handle": None, "blocks": []}


def load_document(pdf_bytes: bytes) -> None:
    """Parse pdf_bytes, replacing any previously-loaded document."""
    reset()
    doc, handle = parse(pdf_bytes)
    _state["handle"] = handle
    _state["blocks"] = _build_block_registry(doc)


def redact(block_id: int) -> None:
    entry = get_block(block_id)
    redact_region(get_handle(), entry["page_index"], entry["block"].bbox)
    _refresh_blocks()


def replace(block_id: int, new_text: str) -> None:
    entry = get_block(block_id)
    replace_text(get_handle(), entry["page_index"], entry["block"], new_text)
    _refresh_blocks()


def export_current() -> bytes:
    return export(get_handle())


def _refresh_blocks() -> None:
    # Re-derive the Document projection from the handle's CURRENT state via
    # its exported bytes, since parse() is the only way to get a fresh
    # TextBlock list -- the handle itself has no "give me a Document" method.
    # The re-parsed handle this produces is a throwaway: the real handle we
    # keep mutating stays _state["handle"], never this one, which is closed
    # immediately so it doesn't leak across many edits in one session.
    handle = get_handle()
    doc, throwaway_handle = parse(export(handle))
    throwaway_handle.close()
    _state["blocks"] = _build_block_registry(doc)


def _build_block_registry(doc: Document) -> list[dict]:
    registry = []
    for page in doc.pages:
        for block in page.text_blocks:
            registry.append({"id": len(registry), "page_index": page.index, "block": block})
    return registry


def get_handle() -> fitz.Document:
    if _state["handle"] is None:
        raise LookupError("no document loaded -- POST a PDF to /api/upload first")
    return _state["handle"]


def get_block(block_id: int) -> dict:
    for entry in _state["blocks"]:
        if entry["id"] == block_id:
            return entry
    raise LookupError(
        f"no block with id {block_id} in the current document -- it may be stale after an edit"
    )


def get_blocks_summary() -> list[dict]:
    return [
        {
            "id": entry["id"],
            "page_index": entry["page_index"],
            "text": entry["block"].text,
            "font": entry["block"].font,
            "size": entry["block"].size,
        }
        for entry in _state["blocks"]
    ]


def get_pages_summary() -> list[dict]:
    handle = get_handle()
    return [
        {"index": i, "width": handle[i].rect.width, "height": handle[i].rect.height}
        for i in range(handle.page_count)
    ]


def reset() -> None:
    if _state["handle"] is not None:
        _state["handle"].close()
    _state["handle"] = None
    _state["blocks"] = []
```

- [ ] **Step 5: Write the FastAPI app and the upload endpoint**

Create `webui/main.py`:

```python
"""FastAPI app for manually exercising redact_region/replace_text against
real PDFs. See the design spec's "API surface" section -- this is a local
verification tool, not a product: no auth, no persistence beyond one
in-process session.
"""
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from webui import session

app = FastAPI(title="8848 PDF AI -- manual verification tool")


@app.exception_handler(ValueError)
async def _value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(LookupError)
async def _lookup_error_handler(request, exc: LookupError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    pdf_bytes = await file.read()
    try:
        session.load_document(pdf_bytes)
    except Exception as exc:
        # A non-PDF or corrupted upload raises whatever PyMuPDF's own
        # exception type is (fitz.FileDataError, fitz.EmptyFileError, ...).
        # Normalize to ValueError so the handler above returns a clean 400
        # instead of a 500 -- a bad upload is an expected, recoverable user
        # error for this tool, not a server fault.
        raise ValueError(f"could not open the uploaded file as a PDF: {exc}") from exc
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}
```

- [ ] **Step 6: Write the failing test, then make it pass**

Create `tests/test_webui.py`:

```python
"""Tests for the manual-verification FastAPI web layer. Each test resets
session state first, since webui/session.py holds plain module-level state
shared across tests running in the same process -- see the design spec's
"Testing strategy" section.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webui import session
from webui.main import app

FIXTURES = Path(__file__).parent / "fixtures"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def test_upload_returns_the_fixtures_known_text_block():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    assert response.status_code == 200
    body = response.json()
    assert any("REDACT-ME-12345" in block["text"] for block in body["blocks"])
    assert body["pages"][0]["width"] == 612.0
    assert body["pages"][0]["height"] == 792.0


def test_upload_rejects_a_non_pdf_file_cleanly():
    response = client.post(
        "/api/upload", files={"file": ("not-a-pdf.txt", b"this is not a PDF", "text/plain")}
    )

    assert response.status_code == 400
    assert response.json()["error"]
```

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -v`
Expected: this file didn't exist as functional code until this step, so run it now (after writing both `webui/session.py`/`webui/main.py` and this test together) and expect PASS — there's no meaningful "write test first, watch it fail" step here since the implementation and test were specified together; the working check is that both new tests pass against the code above, not that you watched an artificial red state.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (54 existing engine tests + 2 new webui tests = 56).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml webui/__init__.py webui/session.py webui/main.py tests/test_webui.py
git commit -m "feat: scaffold the manual-verification web UI and add the upload endpoint"
```

---

## Task 2: Page image endpoint

**Files:**
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `webui.session.get_handle` (Task 1).
- Produces: `GET /api/page/{page_index}.png`. Consumed by Task 5's frontend.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webui.py`:

```python
def test_page_image_renders_after_upload():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.get("/api/page/0.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0


def test_page_image_rejects_an_out_of_range_page_index():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.get("/api/page/5.png")

    assert response.status_code == 400
    assert response.json()["error"]


def test_page_image_before_upload_returns_a_clear_error():
    response = client.get("/api/page/0.png")

    assert response.status_code == 400
    assert response.json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k page_image -v`
Expected: FAIL — `404 Not Found` (no route registered yet).

- [ ] **Step 3: Write the implementation**

Add to `webui/main.py` (update the `fastapi` import line to include `Response`, and add the new route after `upload`):

```python
from fastapi import FastAPI, File, Response, UploadFile
```

```python
@app.get("/api/page/{page_index}.png")
async def page_image(page_index: int) -> Response:
    handle = session.get_handle()
    if page_index < 0 or page_index >= handle.page_count:
        raise LookupError(
            f"page_index {page_index} is out of range for a document with "
            f"{handle.page_count} page(s); must be 0 <= page_index < {handle.page_count}"
        )
    png_bytes = handle[page_index].get_pixmap().tobytes("png")
    return Response(content=png_bytes, media_type="image/png")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k page_image -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (59 total).

- [ ] **Step 6: Commit**

```bash
git add webui/main.py tests/test_webui.py
git commit -m "feat: add the page-image endpoint"
```

---

## Task 3: Redact and Replace endpoints

**Files:**
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `webui.session.redact`, `webui.session.replace`, `webui.session.get_pages_summary`, `webui.session.get_blocks_summary` (all Task 1).
- Produces: `POST /api/redact`, `POST /api/replace`. Consumed by Task 5's frontend.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webui.py`:

```python
def test_redact_removes_the_targeted_block_from_the_document():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post("/api/redact", json={"block_id": block_id})

    assert response.status_code == 200
    assert not any("REDACT-ME-12345" in b["text"] for b in response.json()["blocks"])


def test_redact_rejects_an_unknown_block_id():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.post("/api/redact", json={"block_id": 999})

    assert response.status_code == 400
    assert response.json()["error"]


def test_replace_swaps_the_targeted_blocks_text():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post(
        "/api/replace",
        json={"block_id": block_id, "new_text": "Confidential note: the code is NEW-VALUE-99999."},
    )

    assert response.status_code == 200
    blocks = response.json()["blocks"]
    assert not any("REDACT-ME-12345" in b["text"] for b in blocks)
    assert any("NEW-VALUE-99999" in b["text"] for b in blocks)


def test_replace_rejects_empty_new_text_without_mutating_anything():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    response = client.post("/api/replace", json={"block_id": block_id, "new_text": ""})

    assert response.status_code == 400
    assert response.json()["error"]

    # Confirm nothing was mutated: the same block_id still targets the
    # original text and can still be redacted successfully.
    redact_response = client.post("/api/redact", json={"block_id": block_id})
    assert redact_response.status_code == 200
    assert not any("REDACT-ME-12345" in b["text"] for b in redact_response.json()["blocks"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "redact or replace" -v`
Expected: FAIL — `404 Not Found` for `/api/redact` and `/api/replace` (routes don't exist yet). (`test_redact_removes_the_targeted_block_from_the_document` and `test_replace_swaps_the_targeted_blocks_text` will collide with the substring `redact`/`replace` matching this task's OWN new test names too — that's fine, that's exactly what you're about to make pass.)

- [ ] **Step 3: Write the implementation**

Add to `webui/main.py` (add a `pydantic` import and two request models, plus the two new routes):

```python
from pydantic import BaseModel


class RedactRequest(BaseModel):
    block_id: int


class ReplaceRequest(BaseModel):
    block_id: int
    new_text: str
```

```python
@app.post("/api/redact")
async def redact(body: RedactRequest) -> dict:
    session.redact(body.block_id)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}


@app.post("/api/replace")
async def replace(body: ReplaceRequest) -> dict:
    session.replace(body.block_id, body.new_text)
    return {"pages": session.get_pages_summary(), "blocks": session.get_blocks_summary()}
```

`pydantic` does not need adding to `pyproject.toml` — it is FastAPI's own required dependency, already installed transitively by `fastapi` in Task 1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "redact or replace" -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (64 total).

- [ ] **Step 6: Commit**

```bash
git add webui/main.py tests/test_webui.py
git commit -m "feat: add the redact and replace endpoints"
```

---

## Task 4: Export and Reset endpoints

**Files:**
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `webui.session.export_current`, `webui.session.reset` (Task 1).
- Produces: `GET /api/export`, `POST /api/reset`. Consumed by Task 5's frontend.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webui.py` (add `import pymupdf as fitz` to the file's existing imports at the top):

```python
def test_export_before_upload_returns_a_clear_error():
    response = client.get("/api/export")

    assert response.status_code == 400
    assert response.json()["error"]


def test_export_reflects_a_prior_redaction():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])
    client.post("/api/redact", json={"block_id": block_id})

    response = client.get("/api/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    exported = fitz.open(stream=response.content, filetype="pdf")
    assert "REDACT-ME-12345" not in exported[0].get_text()
    exported.close()


def test_reset_clears_the_session():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    reset_response = client.post("/api/reset")
    export_response = client.get("/api/export")

    assert reset_response.status_code == 200
    assert export_response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "export or reset" -v`
Expected: FAIL — `404 Not Found` for `/api/export` and `/api/reset`.

- [ ] **Step 3: Write the implementation**

Add to `webui/main.py`:

```python
@app.get("/api/export")
async def export_pdf() -> Response:
    pdf_bytes = session.export_current()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="edited.pdf"'},
    )


@app.post("/api/reset")
async def reset_session() -> dict:
    session.reset()
    return {"status": "ok"}
```

(Named `reset_session`, not `reset`, to avoid shadowing the `webui.session.reset` function this route calls.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "export or reset" -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (67 total).

- [ ] **Step 6: Commit**

```bash
git add webui/main.py tests/test_webui.py
git commit -m "feat: add the export and reset endpoints"
```

---

## Task 5: Frontend page and manual end-to-end verification

**Files:**
- Modify: `webui/main.py`
- Create: `webui/static/index.html`
- Create: `webui/static/app.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: every endpoint from Tasks 1-4 (`/api/upload`, `/api/page/{n}.png`, `/api/redact`, `/api/replace`, `/api/export`, `/api/reset`).
- Produces: `GET /` (serves the page), `GET /static/*` (serves `app.js`). No new Python interfaces for later tasks — this is the last task in the plan.

There is no automated test for this task's frontend code — the design spec's "Testing strategy" section scopes automated tests to the API layer only. This task's verification is Step 4 below: actually running the server and clicking through it.

- [ ] **Step 1: Serve the static page**

Add to `webui/main.py` (near the top, after the existing imports, add the static-serving imports and constant; add the two new routes anywhere after `app = FastAPI(...)`):

```python
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
```

```python
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
```

Note: `StaticFiles(directory=STATIC_DIR)` raises at import time if `STATIC_DIR` doesn't exist yet — do Step 2 (creating `webui/static/index.html` and `webui/static/app.js`) before running anything that imports `webui.main`, including the test suite.

- [ ] **Step 2: Write the frontend page**

Create `webui/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>8848 PDF AI -- manual verification tool</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 900px; }
    .page { margin-bottom: 2rem; border: 1px solid #ccc; padding: 1rem; }
    .page img { max-width: 100%; display: block; margin-bottom: 1rem; }
    .block { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
    .block-text { flex: 1; font-family: monospace; font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #error { color: #b00; font-weight: bold; margin: 1rem 0; min-height: 1.2rem; }
    button { cursor: pointer; }
  </style>
</head>
<body>
  <h1>8848 PDF AI -- manual verification tool</h1>
  <p>Upload a real PDF, pick a text block, redact or replace it, download the result.</p>

  <input type="file" id="file-input" accept="application/pdf">
  <button id="upload-button">Upload</button>
  <button id="reset-button">Start over</button>
  <a href="/api/export"><button>Download edited PDF</button></a>

  <div id="error"></div>
  <div id="pages"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Write the frontend logic**

Create `webui/static/app.js`:

```javascript
let mutationCount = 0;

function showError(message) {
  document.getElementById("error").textContent = message || "";
}

function render(state) {
  showError("");
  mutationCount += 1;
  const pagesDiv = document.getElementById("pages");
  pagesDiv.innerHTML = "";

  for (const page of state.pages) {
    const pageDiv = document.createElement("div");
    pageDiv.className = "page";

    const img = document.createElement("img");
    img.src = `/api/page/${page.index}.png?v=${mutationCount}`;
    pageDiv.appendChild(img);

    const blocksForPage = state.blocks.filter((b) => b.page_index === page.index);
    for (const block of blocksForPage) {
      const blockDiv = document.createElement("div");
      blockDiv.className = "block";

      const textSpan = document.createElement("span");
      textSpan.className = "block-text";
      textSpan.textContent = block.text;
      blockDiv.appendChild(textSpan);

      const redactButton = document.createElement("button");
      redactButton.textContent = "Redact";
      redactButton.onclick = () => act("/api/redact", { block_id: block.id });
      blockDiv.appendChild(redactButton);

      const replaceInput = document.createElement("input");
      replaceInput.type = "text";
      replaceInput.placeholder = "replacement text";
      blockDiv.appendChild(replaceInput);

      const replaceButton = document.createElement("button");
      replaceButton.textContent = "Replace";
      replaceButton.onclick = () =>
        act("/api/replace", { block_id: block.id, new_text: replaceInput.value });
      blockDiv.appendChild(replaceButton);

      pageDiv.appendChild(blockDiv);
    }

    pagesDiv.appendChild(pageDiv);
  }
}

async function act(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    showError(data.error || "request failed");
    return;
  }
  render(data);
}

document.getElementById("upload-button").onclick = async () => {
  const fileInput = document.getElementById("file-input");
  if (!fileInput.files.length) {
    showError("choose a PDF file first");
    return;
  }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  const response = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await response.json();
  if (!response.ok) {
    showError(data.error || "upload failed");
    return;
  }
  render(data);
};

document.getElementById("reset-button").onclick = async () => {
  await fetch("/api/reset", { method: "POST" });
  document.getElementById("pages").innerHTML = "";
  showError("");
};
```

- [ ] **Step 4: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (67 total — this task adds no new automated tests, but confirms nothing in Steps 1-3 broke anything, e.g. `webui.main` still imports cleanly now that `StaticFiles(directory=STATIC_DIR)` has a real directory to point at).

- [ ] **Step 5: Manual end-to-end verification (this is this task's real test)**

Run: `./.venv/Scripts/python.exe -m uvicorn webui.main:app --reload` (from the `pdf-ai` repo root), then open `http://127.0.0.1:8000` in a browser.

Walk through, and confirm each step visually:
1. Upload `tests/fixtures/mixed.pdf` (has both text and an image — a good visual smoke test). Confirm the page image renders and the text-block list appears below it.
2. Click "Redact" on the block containing `PATIENT-0042`. Confirm the page image updates to show a black box where that text was, and the block disappears from the list.
3. Type a replacement string into another block's text input and click "Replace". Confirm the page image updates showing the new text in place, and the block list now shows the new text instead of the old.
4. Try replacing a block with an empty string. Confirm the error message area shows the engine's real error text (not a raw stack trace, not a silent failure).
5. Click "Download edited PDF", open the downloaded file in a real PDF viewer, and confirm both edits are present and correct — the redaction is a real black box with no underlying selectable text, and the replaced text reads naturally.
6. Click "Start over", confirm the page clears, and confirm you can upload a different PDF and it works again.
7. **The point of this whole plan**: find (or create, e.g. by exporting a one-page Word/Google Docs document to PDF) a real, non-PyMuPDF-authored PDF and run through steps 1-5 against it. Note in your report whether it behaved as expected or surfaced anything the engine's own test suite didn't catch — this is genuinely new information, not a formality.

Report the outcome of this walkthrough in your task report, including anything unexpected — this step is not optional busywork, it is the actual point of this plan.

- [ ] **Step 6: Update the README**

Add a short section to `README.md` (matching its existing terse style) mentioning the manual verification tool: what it's for, and the two commands to run it (`pip install -e ".[test,webui]"` then `python -m uvicorn webui.main:app --reload`). Keep it brief — a few lines, not a tutorial.

- [ ] **Step 7: Commit**

```bash
git add webui/main.py webui/static/index.html webui/static/app.js README.md
git commit -m "feat: add the manual-verification frontend page"
```

---

## Final Verification

After all 5 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — all 67 passing.
2. Confirm `engine/` is completely untouched by this plan: `git diff <plan-start-commit>..HEAD -- engine/` should be empty.
3. Confirm the base install still stays light: `pip install -e .` (no extras) in a scratch venv should NOT pull in `fastapi` — `python -c "import fastapi"` should fail in that scratch venv, confirming `webui`'s dependencies are genuinely optional.
4. Re-run Task 5 Step 5's manual walkthrough one more time end to end as a final sanity check, on a real, non-PyMuPDF-authored PDF if you have one handy.
