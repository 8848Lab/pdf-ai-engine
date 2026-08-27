from pathlib import Path

import pymupdf as fitz

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


def test_export_produces_a_full_rewrite_not_an_incremental_save():
    # Exactly one %%EOF proves a single-generation, full rewrite. An
    # incremental save appends a new trailer/%%EOF while leaving prior
    # generations (including any pre-redaction content) physically present
    # in the file -- which would be a real security regression for a
    # redaction library. See the comment above export()'s tobytes() call.
    pdf_bytes = (FIXTURES / "simple_text.pdf").read_bytes()
    handle = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = handle[0]
    hits = page.search_for("REDACT-ME-12345")
    assert hits
    page.add_redact_annot(tuple(hits[0]), fill=(0, 0, 0))
    page.apply_redactions(images=2, graphics=1, text=0)

    exported_bytes = export(handle)

    assert exported_bytes.count(b"%%EOF") == 1
    handle.close()
