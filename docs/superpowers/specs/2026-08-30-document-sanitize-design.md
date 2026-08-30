# 8848 PDF — Document Sanitize — Design

## Overview

Adds a document-wide "sanitize" operation that removes hidden identifying
and potentially-unsafe content a redaction tool should not leave behind:
standard Info-dictionary metadata (Author, Creator, dates), the separate
XMP metadata stream, hidden/invisible text, embedded JavaScript, and stale
page thumbnails. Built on PyMuPDF's own `Document.scrub()` — a
comprehensive, already-available "sanitize" implementation (the library's
own doc string compares it to Adobe Acrobat's Sanitize function) — rather
than hand-rolling a narrower metadata-only version.

**Why this matters for a redaction tool specifically, not just "PDF
hygiene":** two of `scrub()`'s flags catch failure modes that are directly
redaction-relevant, not generic cleanup. Confirmed on a real, public PDF
(the IRS's own Form 1040): its Info dictionary's `author` field is
`"C:DC:TS:CAR:MP"`, an internal IRS organizational/username code, and its
XMP stream separately carries `xmpMM:DocumentID`/`InstanceID` UUIDs the
Info dictionary doesn't even have — this is not a theoretical concern.
`hidden_text` removes text present in a page's content stream but visually
hidden (invisible render mode, or covered by something other than a real
redaction) — the exact failure mode behind real-world "redacted" documents
that were still copy-pasteable underneath a black box. This engine's own
`redact_region` already avoids *creating* that problem; `scrub`'s
`hidden_text` flag catches it if it was already present in the *source*
document, independent of anything this tool did to it. `thumbnails`
matters for the same reason: a cached page-preview thumbnail generated
before an edit can still show pre-redaction content even after the visible
page itself is clean.

## Non-goals (explicit, this pass)

- Not automatic on export or on any other action — this is an explicit,
  opt-in operation the user or the AI instruction layer must deliberately
  invoke, per the user's own directive.
- No field-level or flag-level configurability exposed to the user or the
  AI tool — one fixed, sensible default flag set (see Architecture),
  chosen once, not a settings panel. Keeps both the human UI and the AI
  tool's schema simple (the tool takes no parameters at all).
- No attempt to preview hidden-text/JavaScript/thumbnail counts before
  running sanitize — doing so would require essentially running the scrub
  logic twice (once to detect, once to apply) or reimplementing PyMuPDF's
  internal detection. The read-only preview this spec adds covers only
  what's cheaply inspectable directly (the Info dict's fields and whether
  an XMP stream exists) — the sanitize button's own copy states in plain
  language what else it checks for.
- Does not clear `embedded_files`, `attached_files`, `remove_links`,
  `reset_fields`, or `reset_responses` — `scrub()` supports all of these,
  but each has a legitimate reason a document owner might want to keep it
  (an intentionally attached file, a fillable form's own field values, a
  document's real hyperlinks). Left off by default; not exposed as a
  toggle in this pass either (see the "No field-level configurability"
  point above) — a future pass can revisit if there's real demand.
- No change to `redact_region` or `replace_text` — this is a new, separate
  operation.
- No new package dependency — `Document.scrub()` already ships with
  PyMuPDF, already a hard dependency of this engine.

## Architecture

**`sanitize_document(handle: fitz.Document) -> dict`** in
`engine/operations.py`, alongside `redact_region`/`replace_text`. Calls
`handle.scrub(metadata=True, xml_metadata=True, hidden_text=True,
javascript=True, thumbnails=True, embedded_files=False,
attached_files=False, remove_links=False, reset_fields=False,
reset_responses=False, clean_pages=True, redactions=True,
redact_images=0)`. `clean_pages`/`redactions` stay at their library
defaults (True) — they're `scrub()`'s own page-content sanitation and
finalizing-any-pending-redaction-annotations steps, unrelated to this
spec's five chosen flags and safe to leave as PyMuPDF's own sane defaults.

Before calling `scrub()`, captures a before-snapshot of `handle.metadata`
(the Info dict) and whether `handle.xref_xml_metadata()` is non-zero (XMP
present), so the function can report back what was concretely found and
removed:

```python
{
    "metadata_fields_removed": ["author", "creator", ...],  # non-empty
                                                              # Info-dict
                                                              # keys before
                                                              # the call
    "xmp_removed": True,  # bool -- was there an XMP stream to remove
}
```

Hidden text, JavaScript, and thumbnails are always covered by the fixed
default flags above but not individually counted in this return value —
consistent with the Non-goals section's reasoning for why a live preview
isn't attempted either.

**`get_metadata_summary(handle: fitz.Document) -> dict`**, a read-only
companion, returns the current non-empty Info-dict fields and whether XMP
is present — the same shape of information `sanitize_document`'s
before-snapshot uses internally, exposed separately so the webui can show
it *before* the user decides whether to sanitize.

## API surface (webui)

- `GET /api/metadata` → `get_metadata_summary(handle)`'s result — for a
  small metadata panel in the UI (current Author/Creator/dates/whether XMP
  is present), shown so the opt-in decision is informed rather than blind.
- `POST /api/sanitize` → calls `sanitize_document(handle)`, returns the
  same `{pages, blocks}` shape every other mutating endpoint already
  returns (sanitize doesn't change page images or the text-block registry
  — no visual/structural change — so the existing `render()` frontend
  function needs no new code path), plus the operation's own
  `{"metadata_fields_removed": [...], "xmp_removed": bool}` result merged
  into the response body.

Both new endpoints follow the existing `webui/main.py` pattern exactly:
thin wrappers calling into `webui/session.py`, which calls into the
engine — no new architectural pattern introduced. `session.py`'s
`sanitize_document()` wrapper should follow `redact()`/`replace()`'s own
established `try/finally: _refresh_blocks()` pattern even though sanitize
doesn't touch visible text content — `scrub()` still mutates the
document's underlying PDF object structure, and this codebase's existing
convention is to always reparse after any mutation rather than assume a
particular operation couldn't have shifted anything.

## AI tool

A new tool alongside `redact_block`/`replace_block` in
`webui/ai/tools.py`'s `TOOLS` list:

```json
{
  "name": "sanitize_document",
  "description": "Remove identifying metadata (author, creation tool, dates), the separate XMP metadata stream, hidden/invisible text, embedded JavaScript, and stale page thumbnails from the whole document. Use this when the instruction asks to strip metadata, remove identifying information, sanitize, or clean the document as a whole -- not for redacting a specific block of visible text or an image, which are separate tools.",
  "input_schema": {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  },
  "strict": true
}
```

No parameters — matches the Non-goals section's "no configurability"
decision, and keeps the tool trivially easy for a model to call correctly.
`_execute_tool` (in `webui/ai/tools.py`) gains a new branch calling
`session.sanitize_document()`, returning a result string summarizing what
was found (e.g. `"sanitized the document: removed 4 metadata field(s)
(author, creator, creationDate, modDate) and the XMP metadata stream"`,
or `"sanitized the document: no metadata or XMP stream was present to
remove"` if the before-snapshot was already empty) — mirroring
`redact_block`/`replace_block`'s existing pattern of returning a short,
specific, human-readable description of what actually happened.

## Testing strategy

Extends `engine/`'s existing deterministic test suite:

- A fixture PDF with real Info-dict metadata AND a real XMP stream set
  (built the same way `tests/fixtures/generate_fixtures.py` builds every
  other fixture — `doc.set_metadata({...})` and `doc.set_xml_metadata(...)`
  at generation time).
- `sanitize_document` on that fixture: confirm `handle.metadata`'s
  previously-non-empty fields are empty afterward, confirm
  `handle.xref_xml_metadata() == 0` afterward, confirm the returned dict
  correctly names which fields were removed and that `xmp_removed` is
  `True`.
- `sanitize_document` on a fixture with NO metadata/XMP set at all:
  confirm it doesn't raise, and returns `{"metadata_fields_removed": [],
  "xmp_removed": False}`.
- `get_metadata_summary` on both fixtures above, confirming it reports the
  same information `sanitize_document`'s before-snapshot would have used,
  independently of whether sanitize is ever called.
- A case proving `hidden_text`/`javascript` are genuinely being cleared,
  not just assumed from the flags being set — both verified directly
  against the installed PyMuPDF version while writing this spec, not
  merely asserted:
  - `hidden_text`: a fixture with a `render_mode=3` ("invisible") text
    span alongside ordinary visible text. Confirmed:
    `page.get_text()` extracts BOTH before `scrub()` (proving the
    vulnerability is real — the text is present and copy-pasteable
    despite being invisibly rendered), and only the visible text survives
    after `sanitize_document`.
  - `javascript`: a fixture with a real `/Names /JavaScript` catalog
    entry injected via low-level xref manipulation (`doc.get_new_xref()`
    + `doc.update_object()` for the JS action object, then
    `doc.xref_set_key(doc.pdf_catalog(), "Names", ...)` to link it from
    the document catalog). Confirmed: the JS payload string is present in
    `doc.tobytes()` before `sanitize_document` and genuinely absent after.
- Webui integration tests for `GET /api/metadata` and `POST /api/sanitize`
  following the existing `tests/test_webui.py` pattern exactly.
- AI-layer tests for the new `sanitize_document` tool following the
  existing `tests/test_ai.py`/provider test patterns exactly (mocked, no
  real network call).

## Explicitly out of scope (this pass)

- Automatic/always-on sanitize.
- Field-level or flag-level configurability in the UI or the AI tool.
- `embedded_files`, `attached_files`, `remove_links`, `reset_fields`,
  `reset_responses`.
- Live preview of hidden-text/JavaScript/thumbnail counts before running
  sanitize.
- Any change to `redact_region`, `replace_text`, or the block registry.
