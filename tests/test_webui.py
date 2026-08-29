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
