# Document Sanitize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, opt-in "sanitize document" operation that removes identifying metadata (Info dictionary + XMP), hidden/invisible text, embedded JavaScript, and stale page thumbnails — exposed through the webui, and as a new AI tool.

**Architecture:** One new engine operation (`sanitize_document`, built on PyMuPDF's own `Document.scrub()`) plus a read-only companion (`get_metadata_summary`), wired through the same three layers every prior feature in this project has used: `engine/operations.py` → `webui/session.py`/`webui/main.py` → `webui/ai/tools.py`. No automatic trigger anywhere — always explicit.

**Tech Stack:** Python, PyMuPDF (`Document.scrub()`, already a hard dependency — no new package).

**Spec:** `docs/superpowers/specs/2026-08-30-document-sanitize-design.md`

## Global Constraints

- `sanitize_document` uses a fixed, non-configurable flag set:
  `metadata=True, xml_metadata=True, hidden_text=True, javascript=True,
  thumbnails=True, embedded_files=False, attached_files=False,
  remove_links=False, reset_fields=False, reset_responses=False,
  clean_pages=True, redactions=True, redact_images=0`. Never exposed as
  configurable to the user or the AI tool.
- Nothing in this plan runs sanitize automatically — every trigger (the
  webui button, the AI tool) is an explicit, deliberate action.
- No change to `redact_region` or `replace_text`.
- No new package dependency.
- `session.py`'s `sanitize_document()` wrapper follows `redact()`/
  `replace()`'s existing `try/finally: _refresh_blocks()` pattern, even
  though sanitize doesn't touch visible text content — `scrub()` still
  mutates the document's underlying PDF object structure, and this
  codebase's established convention is to always reparse after any
  mutation.
- The new AI tool takes no parameters (whole-document, not block-targeted)
  — matches `redact_block`/`replace_block`'s existing schema style.

---

## Task 1: Engine operations

**Files:**
- Modify: `engine/operations.py`, `tests/fixtures/generate_fixtures.py`
- Create: `tests/fixtures/sanitize_target.pdf`, `tests/fixtures/no_metadata.pdf`
- Test: `tests/test_operations.py`

**Interfaces:**
- Produces: `get_metadata_summary(handle: fitz.Document) -> dict` (returns `{"fields": {...}, "xmp_present": bool}`), `sanitize_document(handle: fitz.Document) -> dict` (returns `{"metadata_fields_removed": [...], "xmp_removed": bool}`).
- Consumes: `fitz` (PyMuPDF), already imported in `engine/operations.py`.

- [ ] **Step 1: Add the two new fixtures**

Add to `tests/fixtures/generate_fixtures.py` (following the file's existing `make_*` function convention):

```python
def make_sanitize_target() -> None:
    """A single fixture carrying every kind of content sanitize_document
    should remove: Info-dict metadata, an XMP stream, invisible
    (render_mode=3) text, and a real embedded JavaScript action -- plus
    ordinary visible text that must survive. One fixture, not several,
    since sanitize_document exercises all of these together.

    The invisible-text and JavaScript constructions were both verified
    directly against the installed PyMuPDF version while writing this
    plan's design spec (docs/superpowers/specs/2026-08-30-document-
    sanitize-design.md's Testing strategy section) -- render_mode=3 text
    is genuinely extractable via get_text() before scrub and genuinely
    gone after; the low-level /Names /JavaScript catalog injection below
    genuinely produces bytes scrub(javascript=True) removes.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Visible text that must survive: KEEP-ME-VISIBLE.", fontsize=12)
    page.insert_text((72, 130), "INVISIBLE-HIDDEN-TEXT-777", fontsize=12, render_mode=3)

    doc.set_metadata(
        {
            "title": "Confidential Report",
            "author": "Jane Doe",
            "subject": "Internal review",
            "keywords": "secret,internal",
            "creator": "Acme Word Processor",
            "producer": "Acme PDF Engine",
            "creationDate": "D:20260101120000",
            "modDate": "D:20260102120000",
        }
    )
    doc.set_xml_metadata(
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:creator><rdf:Seq><rdf:li>Jane Doe</rdf:li></rdf:Seq></dc:creator>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
    )

    js_xref = doc.get_new_xref()
    doc.update_object(js_xref, '<< /S /JavaScript /JS (app.alert("EMBEDDED-JS-PAYLOAD");) >>')
    names_xref = doc.get_new_xref()
    doc.update_object(names_xref, f"<< /Names [ (EmbeddedJS) {js_xref} 0 R ] >>")
    doc.xref_set_key(doc.pdf_catalog(), "Names", f"<< /JavaScript {names_xref} 0 R >>")

    doc.save(FIXTURES_DIR / "sanitize_target.pdf")
    doc.close()


def make_no_metadata() -> None:
    """A fixture with no metadata/XMP set at all -- confirmed empirically
    that a freshly-created, saved PyMuPDF document has every metadata
    field blank and no XMP stream by default, so this needs no special
    construction beyond just not calling set_metadata()/set_xml_metadata().
    sanitize_document must not raise on it and must correctly report
    nothing was found.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Plain document with no metadata to scrub.", fontsize=12)
    doc.save(FIXTURES_DIR / "no_metadata.pdf")
    doc.close()
```

Add both new functions to the `if __name__ == "__main__":` block's call list, then run:

`./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py`

Confirm both new fixture files were created.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_operations.py` (add `get_metadata_summary` and `sanitize_document` to the existing `from engine.operations import (...)` block, keeping it alphabetized like the rest of that import list):

```python
def test_get_metadata_summary_reports_the_real_fields_and_xmp_presence():
    pdf_bytes = (FIXTURES / "sanitize_target.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    result = get_metadata_summary(handle)

    assert result["fields"]["author"] == "Jane Doe"
    assert result["fields"]["title"] == "Confidential Report"
    assert "format" not in result["fields"], "format is not user-set metadata, must be excluded"
    assert result["xmp_present"] is True
    handle.close()


def test_get_metadata_summary_reports_nothing_on_a_clean_document():
    pdf_bytes = (FIXTURES / "no_metadata.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    result = get_metadata_summary(handle)

    assert result["fields"] == {}
    assert result["xmp_present"] is False
    handle.close()


def test_sanitize_document_removes_metadata_and_xmp_and_reports_what_was_found():
    pdf_bytes = (FIXTURES / "sanitize_target.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    result = sanitize_document(handle)

    assert result["xmp_removed"] is True
    assert set(result["metadata_fields_removed"]) == {
        "title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate",
    }
    after = get_metadata_summary(handle)
    assert after["fields"] == {}
    assert after["xmp_present"] is False
    handle.close()


def test_sanitize_document_removes_hidden_text_but_keeps_visible_text():
    pdf_bytes = (FIXTURES / "sanitize_target.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    before_text = page.get_text()
    assert "INVISIBLE-HIDDEN-TEXT-777" in before_text, (
        "fixture must genuinely expose the hidden text before sanitizing, proving it was a real "
        "vulnerability and not already absent"
    )

    sanitize_document(handle)

    after_text = page.get_text()
    assert "INVISIBLE-HIDDEN-TEXT-777" not in after_text
    assert "KEEP-ME-VISIBLE" in after_text
    handle.close()


def test_sanitize_document_removes_embedded_javascript():
    pdf_bytes = (FIXTURES / "sanitize_target.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert b"EMBEDDED-JS-PAYLOAD" in pdf_bytes, (
        "fixture must genuinely carry the JS payload for this test to mean anything"
    )

    sanitize_document(handle)

    out = handle.tobytes()
    assert b"EMBEDDED-JS-PAYLOAD" not in out
    handle.close()


def test_sanitize_document_does_not_raise_and_reports_nothing_found_on_a_clean_document():
    pdf_bytes = (FIXTURES / "no_metadata.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    result = sanitize_document(handle)

    assert result == {"metadata_fields_removed": [], "xmp_removed": False}
    handle.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k "metadata_summary or sanitize_document" -v`
Expected: FAIL — `ImportError` (the functions don't exist yet).

- [ ] **Step 4: Write the implementation**

Add to `engine/operations.py`, after `replace_text` (at the end of the file):

```python
def get_metadata_summary(handle: fitz.Document) -> dict:
    """The document's current Info-dictionary fields (non-empty only) and
    whether a separate XMP metadata stream is present. Read-only -- makes
    no change to the document. See sanitize_document for removing what
    this reports.

    'format', 'encryption', and 'trapped' are excluded from `fields`: they
    are not user-set identifying data (format is always populated, e.g.
    "PDF 1.7"; encryption/trapped are structural/empty in practice) --
    verified on a freshly-created PyMuPDF document that every OTHER field
    is blank by default, so this exclusion list is exactly the three keys
    that would otherwise always appear regardless of what the document
    author actually set.
    """
    fields = {
        k: v for k, v in handle.metadata.items() if v and k not in ("format", "encryption", "trapped")
    }
    return {
        "fields": fields,
        "xmp_present": handle.xref_xml_metadata() != 0,
    }


def sanitize_document(handle: fitz.Document) -> dict:
    """Remove identifying metadata (Info dictionary + XMP stream), hidden/
    invisible text, embedded JavaScript, and stale page thumbnails from the
    whole document, via PyMuPDF's own Document.scrub(). See the design
    spec's "Architecture" section for why these five flags specifically,
    not scrub()'s full flag set (embedded_files/attached_files/
    remove_links/reset_fields/reset_responses are left off -- each has a
    legitimate reason a document owner might want to keep it).

    Returns a summary of what was concretely found and removed: which
    Info-dictionary fields were non-empty before the call, and whether an
    XMP stream existed. Hidden text/JavaScript/thumbnails are always
    covered by the fixed flags below but not individually counted here --
    a live preview of those would require essentially running scrub twice
    (once to detect, once to apply), which this operation deliberately
    does not attempt.
    """
    before = get_metadata_summary(handle)
    handle.scrub(
        attached_files=False,
        clean_pages=True,
        embedded_files=False,
        hidden_text=True,
        javascript=True,
        metadata=True,
        redactions=True,
        redact_images=0,
        remove_links=False,
        reset_fields=False,
        reset_responses=False,
        thumbnails=True,
        xml_metadata=True,
    )
    return {
        "metadata_fields_removed": sorted(before["fields"]),
        "xmp_removed": before["xmp_present"],
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -k "metadata_summary or sanitize_document" -v`
Expected: all 6 new tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (133 existing + 6 new = 139).

- [ ] **Step 7: Commit**

```bash
git add engine/operations.py tests/test_operations.py tests/fixtures/generate_fixtures.py tests/fixtures/sanitize_target.pdf tests/fixtures/no_metadata.pdf
git commit -m "feat: add sanitize_document and get_metadata_summary engine operations"
```

---

## Task 2: webui wiring

**Files:**
- Modify: `webui/session.py`, `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `engine.operations.sanitize_document`, `engine.operations.get_metadata_summary` (Task 1).
- Produces: `session.sanitize_document() -> dict`, `session.get_metadata_summary() -> dict`. New routes `GET /api/metadata` and `POST /api/sanitize`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webui.py` (near the other endpoint tests, following the file's existing patterns exactly — `client.post(...)`/`client.get(...)`, `FIXTURES` fixture files, the `_reset_session` autouse fixture already in this file):

```python
def test_get_metadata_reports_the_current_documents_fields():
    with open(FIXTURES / "sanitize_target.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("sanitize_target.pdf", f, "application/pdf")})

    response = client.get("/api/metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["author"] == "Jane Doe"
    assert body["xmp_present"] is True


def test_get_metadata_returns_a_clean_error_with_no_document_loaded():
    response = client.get("/api/metadata")

    assert response.status_code == 400
    assert response.json()["error"]


def test_sanitize_removes_metadata_and_returns_pages_and_blocks():
    with open(FIXTURES / "sanitize_target.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("sanitize_target.pdf", f, "application/pdf")})

    response = client.post("/api/sanitize")

    assert response.status_code == 200
    body = response.json()
    assert body["xmp_removed"] is True
    assert "author" in body["metadata_fields_removed"]
    assert "pages" in body
    assert "blocks" in body

    follow_up = client.get("/api/metadata")
    assert follow_up.json()["fields"] == {}
    assert follow_up.json()["xmp_present"] is False


def test_sanitize_returns_a_clean_error_with_no_document_loaded():
    response = client.post("/api/sanitize")

    assert response.status_code == 400
    assert response.json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "metadata or sanitize" -v`
Expected: FAIL — `404 Not Found` (the routes don't exist yet).

- [ ] **Step 3: Write the implementation**

In `webui/session.py`, add `sanitize_document, get_metadata_summary` to the existing `from engine.operations import redact_region, replace_text` import line, then add these two functions after the existing `replace()` function:

```python
def sanitize_document() -> dict:
    handle = get_handle()
    try:
        result = _sanitize_document(handle)
    finally:
        # scrub() mutates the document's underlying PDF object structure
        # even though it never touches visible text content -- the block
        # registry is re-derived unconditionally, same as redact()/
        # replace() above, rather than assuming this particular operation
        # couldn't have shifted anything.
        _refresh_blocks()
    return result


def get_metadata_summary() -> dict:
    return _get_metadata_summary(get_handle())
```

Since `engine.operations` already exports functions named `sanitize_document`/`get_metadata_summary` and this file wants its own same-named wrappers, import the engine functions under aliases instead of adding to the existing combined import line. The file's top-of-file import block goes from:

```python
import pymupdf as fitz

from engine.document import Document
from engine.export import export
from engine.operations import redact_region, replace_text
from engine.parser import parse
```

to:

```python
import pymupdf as fitz

from engine.document import Document
from engine.export import export
from engine.operations import get_metadata_summary as _get_metadata_summary
from engine.operations import redact_region, replace_text
from engine.operations import sanitize_document as _sanitize_document
from engine.parser import parse
```

(The three `engine.operations` import lines replace the single original one, positioned alphabetically among the block's other lines exactly as shown — `get_metadata_summary` sorts before `redact_region`, `sanitize_document` sorts after.)

In `webui/main.py`, add these two routes after the existing `/api/reset` route and before the `AIInstructRequest` class:

```python
@app.get("/api/metadata")
async def metadata() -> dict:
    return session.get_metadata_summary()


@app.post("/api/sanitize")
async def sanitize() -> dict:
    result = session.sanitize_document()
    return {
        **result,
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k "metadata or sanitize" -v`
Expected: all 4 new tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (139 from Task 1 + 4 new = 143).

- [ ] **Step 6: Commit**

```bash
git add webui/session.py webui/main.py tests/test_webui.py
git commit -m "feat: add GET /api/metadata and POST /api/sanitize"
```

---

## Task 3: AI tool

**Files:**
- Modify: `webui/ai/tools.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `session.sanitize_document()` (Task 2).
- Produces: a new `sanitize_document` entry in `TOOLS`; a new branch in `_execute_tool`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ai.py`:

```python
def test_execute_tool_sanitize_document_removes_metadata_and_reports_what_was_found():
    session.load_document((FIXTURES / "sanitize_target.pdf").read_bytes())

    result_text, is_error = _execute_tool("sanitize_document", {})

    assert is_error is False
    assert "metadata" in result_text.lower()
    assert "xmp" in result_text.lower()
    assert session.get_metadata_summary()["fields"] == {}
    assert session.get_metadata_summary()["xmp_present"] is False


def test_execute_tool_sanitize_document_reports_nothing_found_on_a_clean_document():
    session.load_document((FIXTURES / "no_metadata.pdf").read_bytes())

    result_text, is_error = _execute_tool("sanitize_document", {})

    assert is_error is False
    assert "no metadata" in result_text.lower() or "nothing" in result_text.lower()


def test_execute_tool_sanitize_document_reports_a_missing_document_as_a_tool_error():
    session.reset()

    result_text, is_error = _execute_tool("sanitize_document", {})

    assert is_error is True
```

Also add a small assertion somewhere near the existing `TOOLS`-referencing tests (or as a new standalone test) confirming the new tool is present and well-formed:

```python
def test_sanitize_document_tool_is_registered_with_no_required_parameters():
    from webui.ai.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "sanitize_document")
    assert tool["input_schema"]["properties"] == {}
    assert tool["input_schema"].get("required", []) == []
    assert tool["strict"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -k "sanitize" -v`
Expected: FAIL — `sanitize_document` returns `"unknown tool: sanitize_document", True` instead of succeeding (the tool doesn't exist in `TOOLS`/`_execute_tool` yet).

- [ ] **Step 3: Write the implementation**

In `webui/ai/tools.py`, add a third entry to the `TOOLS` list (after `replace_block`):

```python
    {
        "name": "sanitize_document",
        "description": (
            "Remove identifying metadata (author, creation tool, dates), the separate XMP "
            "metadata stream, hidden or invisible text, embedded JavaScript, and stale page "
            "thumbnails from the whole document. Use this when the instruction asks to strip "
            "metadata, remove identifying information, sanitize, or clean the document as a "
            "whole -- not for redacting a specific block of visible text, which is a "
            "different tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    },
```

Update `SYSTEM_PROMPT` to mention the third tool — change the opening sentence from "You are editing a PDF document through two tools: redact_block ... and replace_block ..." to "You are editing a PDF document through three tools: redact_block ..., replace_block ..., and sanitize_document (remove the whole document's identifying metadata, hidden text, embedded scripts, and stale thumbnails in one action)."

Add a new branch to `_execute_tool`, alongside the existing `redact_block`/`replace_block` branches:

```python
        elif name == "sanitize_document":
            result = session.sanitize_document()
            removed_fields = result["metadata_fields_removed"]
            if not removed_fields and not result["xmp_removed"]:
                return "sanitized the document: no metadata or XMP stream was present to remove", False
            parts = []
            if removed_fields:
                parts.append(f"{len(removed_fields)} metadata field(s) ({', '.join(removed_fields)})")
            if result["xmp_removed"]:
                parts.append("the XMP metadata stream")
            return f"sanitized the document: removed {' and '.join(parts)}", False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -k "sanitize" -v`
Expected: all 4 new tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (143 from Task 2 + 4 new = 147).

- [ ] **Step 6: Commit**

```bash
git add webui/ai/tools.py tests/test_ai.py
git commit -m "feat: add sanitize_document as an AI tool"
```

---

## Task 4: Frontend, README, and real verification

**Files:**
- Modify: `webui/static/index.html`, `webui/static/app.js`, `README.md`

**Interfaces:** none new — wires the Task 2/3 endpoints into the existing UI.

- [ ] **Step 1: Add a metadata panel and sanitize button to `webui/static/index.html`**

Add, after the existing upload zone section and before the AI instruction panel:

```html
  <section class="instruct-panel" id="metadata-panel">
    <div class="provider-row">
      <span class="provider-label">Document metadata</span>
    </div>
    <div id="metadata-summary" class="mono" style="font-size: 12.5px; color: var(--muted); white-space: pre-wrap;"></div>
    <div style="margin-top: 12px;">
      <button class="secondary-button" id="sanitize-button" type="button" disabled>Sanitize document</button>
    </div>
  </section>
```

- [ ] **Step 2: Wire it up in `webui/static/app.js`**

Add a function to fetch and render the metadata summary:

```javascript
async function refreshMetadata() {
  const summaryDiv = document.getElementById("metadata-summary");
  const response = await fetch("/api/metadata");
  if (!response.ok) {
    summaryDiv.textContent = "No document loaded.";
    return;
  }
  const data = await response.json();
  const fieldLines = Object.entries(data.fields).map(([key, value]) => `${key}: ${value}`);
  const lines = [
    ...fieldLines,
    data.xmp_present ? "XMP metadata stream: present" : "XMP metadata stream: none",
  ];
  summaryDiv.textContent = fieldLines.length || data.xmp_present
    ? lines.join("\n")
    : "No metadata or XMP stream found.";
}

document.getElementById("sanitize-button").onclick = async () => {
  const button = document.getElementById("sanitize-button");
  button.disabled = true;
  try {
    const response = await fetch("/api/sanitize", { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      await refreshState();
      showError(data.error || "sanitize failed");
      return;
    }
    render(data);
    await refreshMetadata();
  } finally {
    button.disabled = false;
  }
};
```

Update `setHasDocument` to also gate the new button, matching the existing pattern for `download-button`/`ai-instruct-button`:

```javascript
function setHasDocument(value) {
  hasDocument = value;
  document.getElementById("download-button").disabled = !value;
  document.getElementById("ai-instruct-button").disabled = !value;
  document.getElementById("sanitize-button").disabled = !value;
}
```

Call `refreshMetadata()` at the end of the existing `render(state)` function (after `setHasDocument(...)`), so the metadata panel updates automatically every time the document changes for any reason (upload, redact, replace, AI instruction, sanitize) — matching how the rest of the page already re-syncs from a single `render()` call.

- [ ] **Step 3: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: unchanged pass count from Task 3 (147) — this task adds no new automated tests.

- [ ] **Step 4: Real verification**

Run the server (`./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8000`), open it in a browser, upload `tests/fixtures/sanitize_target.pdf` (or the bundled `webui/static/sample-document.pdf`, which also carries whatever default metadata PyMuPDF's export step attaches — check what the metadata panel shows for it specifically, since it's the document a real visitor is most likely to try this on). Confirm the metadata panel shows real field values, click "Sanitize document," and confirm: the panel updates to show no fields/no XMP, and (for `sanitize_target.pdf` specifically) the page image still shows "KEEP-ME-VISIBLE" text — proving the visible content survived while the hidden content didn't. Also try the AI instruction box with something like "strip the metadata from this document" against a real or fake key (matching the fallback pattern established in every prior AI-layer verification task) and confirm the `sanitize_document` tool gets called with a sensible summary.

- [ ] **Step 5: Update the README**

Add a short section (matching the existing terse style, near the AI instruction layer section) describing the sanitize feature: what it removes (metadata, XMP, hidden text, embedded JavaScript, stale thumbnails), that it's opt-in only (never automatic), and that it's available both as a button and as something the AI instruction layer can do when asked.

- [ ] **Step 6: Commit**

```bash
git add webui/static/index.html webui/static/app.js README.md
git commit -m "feat: add a document-sanitize UI and wire it into the AI instruction layer"
```

---

## Final Verification

After all 4 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — 147 passing.
2. Confirm `redact_region` and `replace_text` are completely untouched by this plan: `git diff <plan-start-commit>..HEAD -- engine/operations.py` should show only additions (`get_metadata_summary`, `sanitize_document`), no changes to existing functions.
3. Confirm nothing in this plan runs sanitize automatically: `grep -rn "sanitize_document\|scrub(" webui/session.py webui/main.py` should show it only invoked from the explicit `POST /api/sanitize` route and the AI tool's `_execute_tool` branch — never from `load_document`, `redact`, `replace`, or any other existing function.
4. Re-run Task 4 Step 4's verification one more time as a final sanity check.
