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
