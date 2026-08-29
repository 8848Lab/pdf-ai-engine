"""Tests for webui/ai.py's API-key resolution and tool-execution layer.
See tests/test_ai_loop.py (added in a later task) for the tool-calling LOOP
itself, tested against a mocked Anthropic client -- this file's tests never
touch the Anthropic API at all, since resolve_api_key and _execute_tool are
pure Python/session-layer logic with no network dependency.
"""
from pathlib import Path

import pytest

from webui import ai, session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _load_simple_text_fixture():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())


# --- resolve_api_key ---

def test_resolve_api_key_prefers_the_request_supplied_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert ai.resolve_api_key("request-key") == "request-key"


def test_resolve_api_key_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert ai.resolve_api_key(None) == "env-key"


def test_resolve_api_key_raises_when_neither_is_available(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no Anthropic API key available"):
        ai.resolve_api_key(None)


def test_resolve_api_key_treats_an_empty_string_as_no_key_supplied(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no Anthropic API key available"):
        ai.resolve_api_key("")


# --- _execute_tool ---

def test_execute_tool_redact_block_removes_the_target():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    result_text, is_error = ai._execute_tool("redact_block", {"block_id": block_id})

    assert is_error is False
    assert "REDACT-ME-12345" in result_text
    assert not any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())


def test_execute_tool_redact_block_reports_an_unknown_id_as_a_tool_error():
    _load_simple_text_fixture()

    result_text, is_error = ai._execute_tool("redact_block", {"block_id": 999})

    assert is_error is True
    assert "999" in result_text


def test_execute_tool_replace_block_swaps_the_text():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    result_text, is_error = ai._execute_tool(
        "replace_block",
        {"block_id": block_id, "new_text": "Confidential note: the code is NEW-VALUE-99999."},
    )

    assert is_error is False
    blocks = session.get_blocks_summary()
    assert not any("REDACT-ME-12345" in b["text"] for b in blocks)
    assert any("NEW-VALUE-99999" in b["text"] for b in blocks)


def test_execute_tool_replace_block_reports_an_engine_rejection_as_a_tool_error():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    result_text, is_error = ai._execute_tool("replace_block", {"block_id": block_id, "new_text": ""})

    assert is_error is True
    # Confirm nothing was mutated -- the block is still there, found by its
    # text content (not a reused block_id, since a validation-only failure
    # still churns ids via session.replace()'s finally-refresh -- mirrors
    # the equivalent check in tests/test_webui.py for the HTTP endpoint).
    assert any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())


def test_execute_tool_rejects_an_unknown_tool_name():
    _load_simple_text_fixture()

    result_text, is_error = ai._execute_tool("delete_everything", {})

    assert is_error is True
    assert "delete_everything" in result_text
