"""Tests for the manual-verification FastAPI web layer. Each test resets
session state first, since webui/session.py holds plain module-level state
shared across tests running in the same process -- see the design spec's
"Testing strategy" section.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf as fitz
import pytest

# FastAPI lives in the optional `webui` extras group, so a developer working
# on the engine alone (`pip install -e ".[test]"`) will not have it. Skip this
# whole module cleanly in that case -- an unconditional import here would
# abort collection for the ENTIRE suite, not just these tests.
pytest.importorskip("fastapi", reason="webui tests need the `webui` extras group installed")

from fastapi.testclient import TestClient  # noqa: E402

from webui import session  # noqa: E402
from webui.main import app  # noqa: E402

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

    # Confirm nothing was mutated: the original text is still there and can
    # still be redacted successfully. Note the block is re-fetched from
    # /api/state rather than reusing block_id -- every failed operation
    # re-derives the registry (so a partially-applied mutation can never
    # leave stale blocks on screen), and block ids are monotonic, so ids
    # issued before the failed call are no longer live.
    state_blocks = client.get("/api/state").json()["blocks"]
    current_id = next(b["id"] for b in state_blocks if "REDACT-ME-12345" in b["text"])

    redact_response = client.post("/api/redact", json={"block_id": current_id})
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


def _upload_simple_text() -> dict:
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        response = client.post(
            "/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")}
        )
    assert response.status_code == 200
    return response.json()


# --- /api/state: the endpoint the frontend re-syncs with -------------------


def test_state_before_upload_returns_a_clear_error():
    response = client.get("/api/state")

    assert response.status_code == 400
    assert response.json()["error"]


def test_state_matches_what_upload_returned():
    body = _upload_simple_text()

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json() == body


# --- Consistency after a failed operation ----------------------------------


def test_a_failed_replace_leaves_state_consistent_with_the_real_document():
    """replace_text's v0.2 contract erases the old content and THEN raises if
    the new text cannot fit even at the shrink floor. The webui must not keep
    showing the erased block as if it were still there."""
    body = _upload_simple_text()
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    # Mirrors test_operations.py's own "does not fit even shrunk" input:
    # far too much text for one ~16pt-tall single-line bbox at any size down
    # to the 50% floor.
    way_too_long = " ".join(
        [f"This is filler sentence number {i} added to overflow the box." for i in range(15)]
    )

    response = client.post("/api/replace", json={"block_id": block_id, "new_text": way_too_long})

    assert response.status_code == 400
    assert response.json()["error"]

    # The erase really happened, so the block must be gone from the state the
    # frontend re-syncs with...
    state = client.get("/api/state").json()
    assert not any("REDACT-ME-12345" in b["text"] for b in state["blocks"])

    # ...and that state must agree with the real exported document, rather
    # than merely being blanked out on its own.
    export_response = client.get("/api/export")
    assert export_response.status_code == 200
    exported = fitz.open(stream=export_response.content, filetype="pdf")
    exported_text = exported[0].get_text()
    assert "REDACT-ME-12345" not in exported_text
    for block in state["blocks"]:
        assert block["text"] in exported_text
    exported.close()

    # The page image is re-rendered from the same mutated handle, so the
    # operator sees the erasure too.
    assert client.get("/api/page/0.png").status_code == 200


# --- Block ids are monotonic, never positionally reassigned -----------------


def test_a_repeated_redact_of_the_same_block_id_is_rejected_not_silently_retargeted():
    """The reviewer's double-click reproduction: two rapid identical redacts.

    With positional block ids the second call resolved to whichever block
    had inherited id 0 after the refresh, so one gesture destroyed TWO
    different blocks and a 2-block fixture went to 0 blocks. Monotonic ids
    make the second call a clean 400.
    """
    body = _upload_simple_text()
    assert len(body["blocks"]) == 2
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    first = client.post("/api/redact", json={"block_id": block_id})
    second = client.post("/api/redact", json={"block_id": block_id})

    assert first.status_code == 200
    assert len(first.json()["blocks"]) == 1

    assert second.status_code == 400
    assert "no block with id" in second.json()["error"]

    # The crux: the surviving block was NOT collateral damage of the
    # second click.
    surviving = client.get("/api/state").json()["blocks"]
    assert len(surviving) == 1
    assert "This is a simple single-page redaction test document." in surviving[0]["text"]


def test_block_ids_are_never_reused_after_a_mutation():
    body = _upload_simple_text()
    original_ids = {b["id"] for b in body["blocks"]}
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])

    after = client.post("/api/redact", json={"block_id": block_id}).json()["blocks"]

    assert original_ids.isdisjoint({b["id"] for b in after})
    assert min(b["id"] for b in after) > max(original_ids)


def test_a_fresh_upload_restarts_block_ids_from_zero():
    first = _upload_simple_text()
    block_id = next(b["id"] for b in first["blocks"] if "REDACT-ME-12345" in b["text"])
    client.post("/api/redact", json={"block_id": block_id})

    second = _upload_simple_text()

    assert [b["id"] for b in second["blocks"]] == [0, 1]


# --- A failed upload must not destroy an in-progress session ---------------


def test_a_failed_upload_preserves_the_in_progress_document_and_its_edits():
    body = _upload_simple_text()
    block_id = next(b["id"] for b in body["blocks"] if "REDACT-ME-12345" in b["text"])
    assert client.post("/api/redact", json={"block_id": block_id}).status_code == 200

    bad = client.post(
        "/api/upload", files={"file": ("not-a-pdf.txt", b"this is not a PDF", "text/plain")}
    )

    assert bad.status_code == 400
    assert bad.json()["error"]

    # The first document is still loaded, still has its redaction, and is
    # still exportable -- the failed upload rolled back to nothing.
    state = client.get("/api/state").json()
    assert len(state["pages"]) == 1
    assert not any("REDACT-ME-12345" in b["text"] for b in state["blocks"])
    assert any("simple single-page redaction test" in b["text"] for b in state["blocks"])

    export_response = client.get("/api/export")
    assert export_response.status_code == 200
    exported = fitz.open(stream=export_response.content, filetype="pdf")
    exported_text = exported[0].get_text()
    assert "REDACT-ME-12345" not in exported_text
    assert "simple single-page redaction test" in exported_text
    exported.close()


def test_a_successful_upload_still_replaces_the_previous_document():
    _upload_simple_text()

    with open(FIXTURES / "multi_page.pdf", "rb") as f:
        response = client.post(
            "/api/upload", files={"file": ("multi_page.pdf", f, "application/pdf")}
        )

    assert response.status_code == 200
    assert len(response.json()["pages"]) == 3
    assert not any("REDACT-ME-12345" in b["text"] for b in response.json()["blocks"])


# --- /api/ai-instruct --------------------------------------------------------
#
# webui/ai.py's `anthropic` import is soft (see that module's docstring), so
# webui.main itself is importable without the `ai` extras group and this
# whole file still collects. But the tests below that `patch
# ("webui.ai.anthropic.Anthropic")` need the real module present to have an
# `Anthropic` attribute to patch -- with `anthropic` absent, `webui.ai.
# anthropic` is None and patching it raises AttributeError, not a clean
# skip. Each such test guards itself with importorskip so a developer who
# only installed `pip install -e ".[test,webui]"` gets a skip here, not a
# failure.


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _fake_response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_ai_instruct_runs_a_tool_call_and_returns_a_summary():
    pytest.importorskip("anthropic", reason="patches webui.ai.providers.anthropic.anthropic.Anthropic")
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    responses = [
        _fake_response([_tool_use_block("call_1", "redact_block", {"block_id": block_id})], "tool_use"),
        _fake_response([_text_block("Redacted the secret code.")], "end_turn"),
    ]

    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_anthropic_cls:
        mock_anthropic_cls.return_value.messages.create.side_effect = responses
        response = client.post(
            "/api/ai-instruct",
            json={"instruction": "redact the secret code", "provider": "anthropic", "api_key": "fake-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in body["blocks"])


def test_ai_instruct_returns_a_clean_error_with_no_api_key_available(monkeypatch):
    pytest.importorskip("anthropic", reason="patches webui.ai.providers.anthropic.anthropic.Anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_anthropic_cls:
        response = client.post(
            "/api/ai-instruct", json={"instruction": "redact something", "provider": "anthropic"}
        )
        mock_anthropic_cls.assert_not_called()

    assert response.status_code == 400
    assert "API key" in response.json()["error"]


def test_ai_instruct_rejects_an_empty_instruction():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.post(
        "/api/ai-instruct", json={"instruction": "  ", "provider": "anthropic", "api_key": "fake-key"}
    )

    assert response.status_code == 400
    assert response.json()["error"]


def test_ai_instruct_uses_the_environment_key_when_none_is_supplied(monkeypatch):
    pytest.importorskip("anthropic", reason="patches webui.ai.providers.anthropic.anthropic.Anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_anthropic_cls:
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_response(
            [_text_block("ok")], "end_turn"
        )
        response = client.post(
            "/api/ai-instruct", json={"instruction": "do nothing", "provider": "anthropic"}
        )

    assert response.status_code == 200
    mock_anthropic_cls.assert_called_once_with(api_key="env-key")


def test_ai_instruct_threads_the_openai_compatible_provider_through_end_to_end():
    pytest.importorskip("openai", reason="patches webui.ai.providers.openai_compatible.openai.OpenAI")
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    tool_call_completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="redact_block", arguments=json.dumps({"block_id": block_id})
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )
    final_completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Redacted the secret code.", tool_calls=None),
                finish_reason="stop",
            )
        ]
    )

    with patch("webui.ai.providers.openai_compatible.openai.OpenAI") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.completions.create.side_effect = [tool_call_completion, final_completion]

        response = client.post(
            "/api/ai-instruct",
            json={
                "instruction": "redact the secret code",
                "provider": "openai_compatible",
                "api_key": "fake-key",
                "base_url": "http://example.test/v1",
                "model": "some-local-model",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in body["blocks"])
