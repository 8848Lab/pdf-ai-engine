"""Merge B's web layer: the /api/pages/... routes, the pages summary, and the
block/image id behaviour around page operations and refusals (spec R9)."""
import pymupdf as fitz
import pytest

pytest.importorskip("fastapi", reason="webui tests need the `webui` extras group installed")

from fastapi.testclient import TestClient  # noqa: E402

from webui import session  # noqa: E402
from webui.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _labelled(count) -> bytes:
    doc = fitz.open()
    for i in range(count):
        doc.new_page(width=612, height=792).insert_text((72, 100), f"P{i}", fontsize=12)
    return doc.tobytes()


def _upload(pdf_bytes) -> dict:
    response = client.post("/api/upload", files={"file": ("doc.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_refused_block_operation_keeps_every_id_valid():
    # R9 case 2, and the Task 7 follow-up: a refusal before any mutation no
    # longer reissues ids, so the operator's next click still works.
    before = _upload(_labelled(1))
    block_id = before["blocks"][0]["id"]
    response = client.post(
        "/api/insert", json={"page_index": 0, "bbox": [900, 900, 950, 950], "text": "x", "size": 12}
    )
    assert response.status_code == 400
    assert client.get("/api/state").json() == before
    assert client.post("/api/redact", json={"block_id": block_id}).status_code == 200


def test_a_failure_after_a_mutation_still_refreshes_the_ids():
    # replace_text erases, then raises when the new text cannot fit. That is
    # a plain ValueError, not a refusal, so the registry must be re-read.
    before = _upload(_labelled(1))
    block_id = before["blocks"][0]["id"]
    response = client.post("/api/replace", json={"block_id": block_id, "new_text": "word " * 400})
    assert response.status_code == 400
    after = client.get("/api/state").json()
    assert block_id not in {b["id"] for b in after["blocks"]}


def test_a_geometry_gate_refusal_keeps_every_id_valid():
    doc = fitz.open(stream=_labelled(1), filetype="pdf")
    doc.xref_set_key(doc[0].xref, "UserUnit", "1.5")
    before = _upload(doc.tobytes())
    response = client.post("/api/redact", json={"block_id": before["blocks"][0]["id"]})
    assert response.status_code == 400
    assert "Support is planned" in response.json()["error"]
    assert client.get("/api/state").json() == before
