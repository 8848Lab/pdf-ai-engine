# Redaction Engine v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless, deterministic PDF redaction engine — the first buildable slice of 8848 PDF AI — as a Python library with no AI, no auth, and no UI.

**Architecture:** A read-oriented `Document`/`Page`/`TextBlock`/`Image` dataclass projection for callers to find redaction targets, backed by a live PyMuPDF document handle that is the actual read/write path. `parser.py` builds the projection from PDF bytes; `operations.py`'s `redact_region` mutates the handle via PyMuPDF's `add_redact_annot`/`apply_redactions` (real content-stream removal, not a visual overlay); `export.py` serializes the handle back to bytes.

**Tech Stack:** Python 3.11+, PyMuPDF (`pymupdf` on PyPI, imported as `fitz`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-redaction-engine-v0.1-design.md`

## Global Constraints

- No AI/LLM anything — not even a "detect what to redact" layer. This pass is pure mechanism.
- No authentication, no multi-user/multi-tenant concept, no billing.
- No web UI, no file upload endpoint, no storage backend (SeaweedFS or otherwise). Input/output are local file paths or in-memory bytes only.
- No operations beyond `redact_region` — no text rewrite, no page deletion, no image replacement.
- No deployment/hosting story. Ships as a Python library with tests, runnable locally — not a running service.
- `engine/` never grows a FastAPI/HTTP dependency, and no `api/`/`web/` directory gets scaffolded in this plan — YAGNI, per the spec.
- PyMuPDF's `Page.add_redact_annot()` + `Page.apply_redactions()` is load-bearing: it must perform real content-stream removal, not a visual-only overlay. Verify this is genuinely what's happening (Task 4's tests exist specifically to prove it) rather than assuming the API name is enough.
- Auto-detecting *what* to redact (PII/NER/pattern-matching) is explicitly out of scope for this plan.

---

## Task 1: Project scaffolding, dependencies, and test fixtures

**Files:**
- Create: `pyproject.toml`
- Create: `engine/__init__.py`
- Create: `.gitignore`
- Create: `tests/fixtures/generate_fixtures.py`
- Create (generated, then committed as binary): `tests/fixtures/simple_text.pdf`, `tests/fixtures/multi_page.pdf`, `tests/fixtures/image_only.pdf`, `tests/fixtures/mixed.pdf`
- Test: `tests/test_fixtures_exist.py`

**Interfaces:**
- Produces: the `engine` Python package (importable as `import engine`, `from engine.document import ...` etc. once later tasks populate it), and four fixed, versioned PDF fixture files every later test task reads by name and by known text content (`REDACT-ME-12345` in `simple_text.pdf`; `PAGE-MARK-1`/`PAGE-MARK-2`/`PAGE-MARK-3` in `multi_page.pdf`, one per page; one image with a non-empty bbox in `image_only.pdf`; both `PATIENT-0042` text and one image in `mixed.pdf`). Later tasks must not regenerate or edit these files — they are fixed test input.

**Judgment call carried from planning:** the design spec asks for "real, varied sample PDFs... not synthetically generated PDFs with no real-world formatting quirks." This environment has no source of genuinely real-world third-party PDFs to check in. This task instead generates real, valid PDF files (not mocks — actual files PyMuPDF writes and any PDF reader can open) with varied, realistic structure (single-page, multi-page, image-only, mixed text+image) using PyMuPDF's own writing API. This is a pragmatic substitute, not the spec's ideal — swapping in genuinely sourced real-world PDFs later is a drop-in file replacement (same filenames, same known-text-content contract) if that's ever wanted.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "pdf-ai-engine"
version = "0.1.0"
description = "8848 PDF AI -- headless, deterministic PDF redaction engine (v0.1)"
requires-python = ">=3.11"
dependencies = [
    "pymupdf>=1.24",
]

[project.optional-dependencies]
test = [
    "pytest>=8",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["engine"]
```

- [ ] **Step 2: Create the empty package**

Create `engine/__init__.py` (empty file — later tasks populate `engine/document.py`, `engine/parser.py`, `engine/operations.py`, `engine/export.py`, but nothing needs re-exporting from `__init__.py` in v0.1).

- [ ] **Step 3: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
```

- [ ] **Step 4: Create the venv and install**

Run (from the repo root, `pdf-ai/`):
```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -e ".[test]"
```
Expected: installs cleanly, `pymupdf` and `pytest` present. Confirm the installed PyMuPDF's exact API surface before later tasks rely on it — run `./.venv/Scripts/python.exe -c "import fitz; print(fitz.__version__ if hasattr(fitz, '__version__') else fitz.VersionBind)"` and note the version in your task report, since the spec explicitly flags PyMuPDF's API as having changed across major versions (e.g. `Document.tobytes()` vs older `Document.write()`).

- [ ] **Step 5: Write the fixture generator**

Create `tests/fixtures/generate_fixtures.py`:

```python
"""One-time fixture generator. Run manually:
    ./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py

Produces the PDF files this test suite checks into tests/fixtures/ and reads
as fixed, versioned input. Not run as part of the test suite itself -- the
generated files are checked into git, so tests never depend on this script
existing or on PyMuPDF's page.insert_text/insert_image behavior at test
time, only on the fixed files it already produced.
"""
import fitz
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def _red_square_png(size: int = 64) -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, size, size))
    pixmap.set_rect(pixmap.irect, (200, 30, 30))
    return pixmap.tobytes("png")


def make_simple_text() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 100),
        "This is a simple single-page redaction test document.",
        fontsize=12,
    )
    page.insert_text(
        (72, 130),
        "Confidential note: the secret code is REDACT-ME-12345.",
        fontsize=12,
    )
    doc.save(FIXTURES_DIR / "simple_text.pdf")
    doc.close()


def make_multi_page() -> None:
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"This is page {i + 1} of a 3-page test document.", fontsize=12)
        page.insert_text((72, 130), f"Unique marker for page {i + 1}: PAGE-MARK-{i + 1}.", fontsize=12)
    doc.save(FIXTURES_DIR / "multi_page.pdf")
    doc.close()


def make_image_only() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(fitz.Rect(72, 100, 136, 164), stream=_red_square_png())
    doc.save(FIXTURES_DIR / "image_only.pdf")
    doc.close()


def make_mixed() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Mixed-content document with text and an embedded image below.", fontsize=12)
    page.insert_text((72, 130), "Sensitive figure caption: Subject ID PATIENT-0042.", fontsize=12)
    page.insert_image(fitz.Rect(72, 150, 136, 214), stream=_red_square_png())
    doc.save(FIXTURES_DIR / "mixed.pdf")
    doc.close()


if __name__ == "__main__":
    make_simple_text()
    make_multi_page()
    make_image_only()
    make_mixed()
    print("Fixtures written to", FIXTURES_DIR)
```

- [ ] **Step 6: Run the generator**

Run: `./.venv/Scripts/python.exe tests/fixtures/generate_fixtures.py`
Expected: prints the fixtures directory path; `tests/fixtures/simple_text.pdf`, `multi_page.pdf`, `image_only.pdf`, `mixed.pdf` now exist on disk.

- [ ] **Step 7: Write the smoke test**

Create `tests/test_fixtures_exist.py`:

```python
from pathlib import Path

import fitz

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_FILES = ["simple_text.pdf", "multi_page.pdf", "image_only.pdf", "mixed.pdf"]


def test_all_fixture_files_exist_and_are_nonempty():
    for name in EXPECTED_FILES:
        path = FIXTURES / name
        assert path.exists(), f"missing fixture: {name}"
        assert path.stat().st_size > 0, f"empty fixture: {name}"


def test_all_fixture_files_are_openable_pdfs():
    for name in EXPECTED_FILES:
        handle = fitz.open(FIXTURES / name)
        assert handle.page_count > 0
        handle.close()


def test_multi_page_fixture_has_three_pages():
    handle = fitz.open(FIXTURES / "multi_page.pdf")
    assert handle.page_count == 3
    handle.close()
```

- [ ] **Step 8: Run the smoke test**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fixtures_exist.py -v`
Expected: all 3 tests PASS. This proves the toolchain (venv, PyMuPDF install, fixture generation) works end to end before any engine code is written.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml engine/__init__.py .gitignore tests/fixtures/generate_fixtures.py tests/fixtures/simple_text.pdf tests/fixtures/multi_page.pdf tests/fixtures/image_only.pdf tests/fixtures/mixed.pdf tests/test_fixtures_exist.py
git commit -m "chore: scaffold the engine package and generate test fixtures"
```

---

## Task 2: Document data model

**Files:**
- Create: `engine/document.py`
- Test: `tests/test_document.py`

**Interfaces:**
- Consumes: nothing (pure data model, no dependencies beyond stdlib `dataclasses`).
- Produces: `TextBlock(text: str, bbox: tuple[float, float, float, float], font: str, size: float)`, `Image(bbox: tuple[float, float, float, float])`, `Page(index: int, width: float, height: float, text_blocks: list[TextBlock] = [], images: list[Image] = [])`, `Document(pages: list[Page] = [])`. Consumed by Tasks 3-6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_document.py`:

```python
from engine.document import Document, Image, Page, TextBlock


def test_text_block_holds_its_fields():
    block = TextBlock(text="hello", bbox=(0.0, 0.0, 10.0, 5.0), font="Helvetica", size=12.0)
    assert block.text == "hello"
    assert block.bbox == (0.0, 0.0, 10.0, 5.0)
    assert block.font == "Helvetica"
    assert block.size == 12.0


def test_image_holds_its_bbox():
    image = Image(bbox=(0.0, 0.0, 64.0, 64.0))
    assert image.bbox == (0.0, 0.0, 64.0, 64.0)


def test_page_defaults_to_empty_lists():
    page = Page(index=0, width=612.0, height=792.0)
    assert page.text_blocks == []
    assert page.images == []


def test_page_holds_provided_lists():
    block = TextBlock(text="x", bbox=(0.0, 0.0, 1.0, 1.0), font="Helvetica", size=10.0)
    image = Image(bbox=(0.0, 0.0, 1.0, 1.0))
    page = Page(index=0, width=612.0, height=792.0, text_blocks=[block], images=[image])
    assert page.text_blocks == [block]
    assert page.images == [image]


def test_document_holds_pages_in_order():
    page0 = Page(index=0, width=612.0, height=792.0)
    page1 = Page(index=1, width=612.0, height=792.0)
    doc = Document(pages=[page0, page1])
    assert doc.pages == [page0, page1]
    assert doc.pages[1].index == 1


def test_document_defaults_to_empty_pages():
    doc = Document()
    assert doc.pages == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_document.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.document'`.

- [ ] **Step 3: Write the implementation**

Create `engine/document.py`:

```python
"""Read-oriented projection of a PDF's structure.

Document/Page/TextBlock/Image exist for callers to inspect a PDF and find
redaction-target coordinates. They are not the write path -- operations.py
mutates the live PyMuPDF document handle directly. See the design spec's
"Data model" section.
"""
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float


@dataclass
class Image:
    bbox: tuple[float, float, float, float]


@dataclass
class Page:
    index: int
    width: float
    height: float
    text_blocks: list[TextBlock] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)


@dataclass
class Document:
    pages: list[Page] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_document.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/document.py tests/test_document.py
git commit -m "feat: add the Document/Page/TextBlock/Image data model"
```

---

## Task 3: Parser — PDF bytes to Document

**Files:**
- Create: `engine/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `engine.document.Document`, `Page`, `TextBlock`, `Image` (Task 2). `fitz.open(stream=..., filetype="pdf")`, `Page.get_text("dict")`, `Page.get_image_info()`, `Page.rect` (PyMuPDF).
- Produces: `parse(pdf_bytes: bytes) -> tuple[Document, fitz.Document]`. The returned `fitz.Document` handle is consumed by Tasks 4 and 5 — it is the live, mutable document the redaction operation acts on and export serializes; the `Document` dataclass returned alongside it is for callers to find target coordinates only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_parser.py`:

```python
from pathlib import Path

from engine.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_simple_text_document():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.index == 0
    all_text = " ".join(block.text for block in page.text_blocks)
    assert "REDACT-ME-12345" in all_text
    handle.close()


def test_parses_multi_page_document_preserving_order():
    pdf_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    assert len(doc.pages) == 3
    for i, page in enumerate(doc.pages):
        assert page.index == i
        all_text = " ".join(block.text for block in page.text_blocks)
        assert f"PAGE-MARK-{i + 1}" in all_text
    handle.close()


def test_parses_image_bbox_from_image_only_document():
    pdf_bytes = (FIXTURES / "image_only.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert len(page.images) == 1
    x0, y0, x1, y1 = page.images[0].bbox
    assert x1 > x0
    assert y1 > y0
    handle.close()


def test_parses_mixed_text_and_image_document():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert len(page.images) == 1
    all_text = " ".join(block.text for block in page.text_blocks)
    assert "PATIENT-0042" in all_text
    handle.close()


def test_page_dimensions_are_populated():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    doc, handle = parse(pdf_bytes)
    page = doc.pages[0]
    assert page.width == 612.0
    assert page.height == 792.0
    handle.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.parser'`.

- [ ] **Step 3: Write the implementation**

Create `engine/parser.py`:

```python
"""PDF bytes -> Document: read-only introspection.

Returns both the read-oriented Document projection (for callers to find
redaction-target coordinates) and the live PyMuPDF handle the same bytes
were opened into, since operations.py/export.py mutate and read from that
handle directly rather than a second write path. See the design spec's
"Data model" section for why.
"""
import fitz

from engine.document import Document, Image, Page, TextBlock


def parse(pdf_bytes: bytes) -> tuple[Document, fitz.Document]:
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page_index in range(handle.page_count):
        pdf_page = handle[page_index]

        text_blocks = []
        for block in pdf_page.get_text("dict")["blocks"]:
            if block["type"] != 0:  # 0 = text block, 1 = image block
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text_blocks.append(
                        TextBlock(
                            text=span["text"],
                            bbox=tuple(span["bbox"]),
                            font=span["font"],
                            size=span["size"],
                        )
                    )

        images = [Image(bbox=tuple(info["bbox"])) for info in pdf_page.get_image_info()]

        pages.append(
            Page(
                index=page_index,
                width=pdf_page.rect.width,
                height=pdf_page.rect.height,
                text_blocks=text_blocks,
                images=images,
            )
        )
    return Document(pages=pages), handle
```

Verify `Page.get_text("dict")`'s block/line/span key names (`"type"`, `"lines"`, `"spans"`, `"bbox"`, `"font"`, `"size"`, `"text"`) and `Page.get_image_info()`'s `"bbox"` key against the PyMuPDF version installed in Task 1, Step 4 before trusting this code verbatim — these have been stable across recent PyMuPDF versions but the spec's own caution about API drift applies here too.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_parser.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/parser.py tests/test_parser.py
git commit -m "feat: add the PDF-bytes-to-Document parser"
```

---

## Task 4: Redaction operation

**Files:**
- Create: `engine/operations.py`
- Test: `tests/test_operations.py`

**Interfaces:**
- Consumes: a live `fitz.Document` handle, as produced by `engine.parser.parse` (Task 3). `Page.add_redact_annot()`, `Page.apply_redactions()`, `Page.search_for()` (PyMuPDF).
- Produces: `redact_region(handle: fitz.Document, page_index: int, bbox: tuple[float, float, float, float]) -> None`. Mutates `handle` in place. Consumed by Task 6 (and by Task 5's own tests, which redact before exporting).

- [ ] **Step 1: Write the failing test**

Create `tests/test_operations.py`:

```python
from pathlib import Path

import fitz

from engine.operations import redact_region

FIXTURES = Path(__file__).parent / "fixtures"


def test_redact_region_removes_text_from_extraction():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    # Locate the sensitive string's bbox via PyMuPDF's own search, so this
    # test doesn't hardcode coordinates that would silently drift if the
    # fixture's text position ever changes.
    hits = page.search_for("REDACT-ME-12345")
    assert hits, "fixture must contain the sensitive string for this test to mean anything"

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    remaining_text = page.get_text()
    assert "REDACT-ME-12345" not in remaining_text
    handle.close()


def test_redact_region_only_affects_the_targeted_page():
    pdf_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page0 = handle[0]
    hits = page0.search_for("PAGE-MARK-1")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    assert "PAGE-MARK-1" not in page0.get_text()
    assert "PAGE-MARK-2" in handle[1].get_text()
    assert "PAGE-MARK-3" in handle[2].get_text()
    handle.close()


def test_redact_region_accumulates_across_multiple_calls_on_same_page():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]

    caption_hits = page.search_for("PATIENT-0042")
    assert caption_hits
    redact_region(handle, page_index=0, bbox=tuple(caption_hits[0]))

    intro_hits = page.search_for("Mixed-content document")
    assert intro_hits
    redact_region(handle, page_index=0, bbox=tuple(intro_hits[0]))

    remaining_text = page.get_text()
    assert "PATIENT-0042" not in remaining_text
    assert "Mixed-content document" not in remaining_text
    handle.close()


def test_redact_region_leaves_unrelated_text_on_the_same_page_intact():
    pdf_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("PATIENT-0042")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))

    assert "Mixed-content document with text and an embedded image below." in page.get_text()
    handle.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.operations'`.

- [ ] **Step 3: Write the implementation**

Create `engine/operations.py`:

```python
"""Mutating operations against a live PyMuPDF document handle.

v0.1 supports exactly one operation: redact_region. It mutates the handle
in place rather than the read-oriented Document dataclasses -- see the
design spec's "Data model" and "Operations" sections for why.
"""
import fitz


def redact_region(
    handle: fitz.Document,
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> None:
    page = handle[page_index]
    page.add_redact_annot(bbox, fill=(0, 0, 0))
    page.apply_redactions()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_operations.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/operations.py tests/test_operations.py
git commit -m "feat: add redact_region"
```

---

## Task 5: Export — handle to PDF bytes

**Files:**
- Create: `engine/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: a live `fitz.Document` handle (Task 3's `parse` return, optionally mutated by Task 4's `redact_region`). `Document.tobytes()` (PyMuPDF) — verify this exact method name against the installed version (Step 3 below) before trusting it; the spec calls out `write()`/`tobytes()`/`save()` as having varied across PyMuPDF versions.
- Produces: `export(handle: fitz.Document) -> bytes`. Consumed by Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_export.py`:

```python
from pathlib import Path

import fitz

from engine.export import export

FIXTURES = Path(__file__).parent / "fixtures"


def test_export_round_trips_to_a_valid_pdf():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    exported_bytes = export(handle)

    reopened = fitz.open(stream=exported_bytes, filetype="pdf")
    assert reopened.page_count == handle.page_count
    assert "REDACT-ME-12345" in reopened[0].get_text()
    reopened.close()
    handle.close()


def test_export_reflects_redaction_applied_before_export():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    page.add_redact_annot(tuple(hits[0]), fill=(0, 0, 0))
    page.apply_redactions()

    exported_bytes = export(handle)

    reopened = fitz.open(stream=exported_bytes, filetype="pdf")
    assert "REDACT-ME-12345" not in reopened[0].get_text()
    reopened.close()
    handle.close()


def test_export_returns_nonempty_bytes():
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")

    exported_bytes = export(handle)

    assert isinstance(exported_bytes, bytes)
    assert len(exported_bytes) > 0
    handle.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.export'`.

- [ ] **Step 3: Confirm the export method name, then write the implementation**

Run: `./.venv/Scripts/python.exe -c "import fitz; print([m for m in dir(fitz.Document) if 'byte' in m.lower() or m in ('save', 'write')])"`
Expected output includes `tobytes` (current PyMuPDF API for in-memory export). If it does not, use whichever method that check actually reveals instead, and note the discrepancy in your task report.

Create `engine/export.py`:

```python
"""Document handle -> PDF bytes."""
import fitz


def export(handle: fitz.Document) -> bytes:
    return handle.tobytes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_export.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/export.py tests/test_export.py
git commit -m "feat: add export"
```

---

## Task 6: End-to-end proof — visual, content, and structural correctness

**Files:**
- Test: `tests/test_visual_regression.py`

**Interfaces:**
- Consumes: `engine.parser.parse` (Task 3), `engine.operations.redact_region` (Task 4), `engine.export.export` (Task 5). No new production code — this task is the integration proof the design spec's "Testing strategy" section calls "the actual proof of correctness," combining all three prior tasks' pieces into one pipeline and checking three independent properties.

- [ ] **Step 1: Write the failing test**

Create `tests/test_visual_regression.py`:

```python
"""End-to-end proof that redact_region -> export produces a PDF satisfying
all three properties the design spec requires: visual (only the target
region's pixels changed), content (redacted text is unextractable, not
just visually covered), and structural (the document stays valid and
untouched pages are byte-for-byte unchanged). No single property alone is
sufficient proof -- see the spec's "Testing strategy" section.
"""
from pathlib import Path

import fitz

from engine.export import export
from engine.operations import redact_region
from engine.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def _pixmap_pixels(page: fitz.Page) -> tuple[int, int, bytes]:
    pixmap = page.get_pixmap()
    return pixmap.width, pixmap.height, pixmap.samples


def test_redaction_only_changes_pixels_inside_the_target_region():
    original_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page = original_handle[0]
    hits = original_page.search_for("REDACT-ME-12345")
    assert hits
    bbox = fitz.Rect(hits[0])

    _, handle = parse(original_bytes)
    redact_region(handle, page_index=0, bbox=tuple(bbox))
    redacted_bytes = export(handle)
    handle.close()

    redacted_handle = fitz.open(stream=redacted_bytes, filetype="pdf")
    redacted_page = redacted_handle[0]

    ow, oh, original_samples = _pixmap_pixels(original_page)
    rw, rh, redacted_samples = _pixmap_pixels(redacted_page)
    assert (ow, oh) == (rw, rh)

    zoom = original_page.get_pixmap().width / original_page.rect.width
    n_components = len(original_samples) // (ow * oh)

    changed_inside_bbox = False
    changed_outside_bbox = False
    for y in range(oh):
        for x in range(ow):
            idx = (y * ow + x) * n_components
            pixel_original = original_samples[idx : idx + n_components]
            pixel_redacted = redacted_samples[idx : idx + n_components]
            if pixel_original == pixel_redacted:
                continue
            px_pt, py_pt = x / zoom, y / zoom
            if bbox.x0 <= px_pt <= bbox.x1 and bbox.y0 <= py_pt <= bbox.y1:
                changed_inside_bbox = True
            else:
                changed_outside_bbox = True

    assert changed_inside_bbox, "redaction should visibly change the target region"
    assert not changed_outside_bbox, "redaction must not touch pixels outside the target region"

    original_handle.close()
    redacted_handle.close()


def test_redacted_text_is_unextractable_not_just_visually_covered():
    original_bytes = (FIXTURES / "mixed.pdf").read_bytes()
    _, handle = parse(original_bytes)
    page = handle[0]
    hits = page.search_for("PATIENT-0042")
    assert hits

    redact_region(handle, page_index=0, bbox=tuple(hits[0]))
    redacted_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=redacted_bytes, filetype="pdf")
    assert "PATIENT-0042" not in reopened[0].get_text()
    reopened.close()


def test_redacted_document_stays_valid_and_other_pages_are_untouched():
    original_bytes = (FIXTURES / "multi_page.pdf").read_bytes()
    original_handle = fitz.open(stream=original_bytes, filetype="pdf")
    original_page_count = original_handle.page_count
    original_page1_text = original_handle[1].get_text()
    original_page2_text = original_handle[2].get_text()
    original_page1_pixels = _pixmap_pixels(original_handle[1])
    original_page2_pixels = _pixmap_pixels(original_handle[2])

    _, handle = parse(original_bytes)
    page0 = handle[0]
    hits = page0.search_for("PAGE-MARK-1")
    assert hits
    redact_region(handle, page_index=0, bbox=tuple(hits[0]))
    redacted_bytes = export(handle)
    handle.close()

    reopened = fitz.open(stream=redacted_bytes, filetype="pdf")
    assert reopened.page_count == original_page_count
    assert reopened[1].get_text() == original_page1_text
    assert reopened[2].get_text() == original_page2_text
    assert _pixmap_pixels(reopened[1]) == original_page1_pixels
    assert _pixmap_pixels(reopened[2]) == original_page2_pixels

    reopened.close()
    original_handle.close()
```

- [ ] **Step 2: Run test to verify it fails for the right reason**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_visual_regression.py -v`
Expected: if Tasks 1-5 are already complete (which they are, since this task depends on them), this should PASS immediately rather than fail — there is no new production code in this task. If any of the three tests fails, that is a real bug in Tasks 3-5's implementation surfaced by this integration proof, not an expected-red state: stop and diagnose which of the three properties (visual/content/structural) actually broke and why, rather than treating it as a normal TDD red step.

- [ ] **Step 3: Confirm all tests pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_visual_regression.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all tests across every file (fixtures smoke test, document, parser, operations, export, visual regression) PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_visual_regression.py
git commit -m "test: add end-to-end visual, content, and structural redaction proof"
```

---

## Final Verification

After all 6 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — all passing.
2. Confirm `engine/` has no `api/`/`web/`/FastAPI dependency anywhere (`grep -r fastapi engine/ pyproject.toml` should return nothing) — Global Constraints.
3. Confirm no operation beyond `redact_region` exists in `engine/operations.py` — Global Constraints.
4. Manually sanity-check one redaction end to end outside the test suite: `./.venv/Scripts/python.exe -c "from engine.parser import parse; from engine.operations import redact_region; from engine.export import export; from pathlib import Path; b=Path('tests/fixtures/simple_text.pdf').read_bytes(); doc,h=parse(b); hits=h[0].search_for('REDACT-ME-12345'); redact_region(h,0,tuple(hits[0])); Path('/tmp/redacted_sample.pdf').write_bytes(export(h)); h.close(); print('wrote /tmp/redacted_sample.pdf')"` — open the resulting file in a real PDF viewer and visually confirm the redaction renders as a black box with no underlying text selectable.
