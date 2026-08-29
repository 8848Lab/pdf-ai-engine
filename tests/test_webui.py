"""Tests for the manual-verification FastAPI web layer. Each test resets
session state first, since webui/session.py holds plain module-level state
shared across tests running in the same process -- see the design spec's
"Testing strategy" section.
"""
from pathlib import Path

import pymupdf as fitz
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
