"""Tests for webui/ai/providers/openai_compatible.py's translation layer
and the run_instruction() loop driven through it. Mocked -- no real network
call, same rule as tests/test_ai.py's Anthropic tests.

Soft-imports the `openai` SDK the same way webui/ai/providers/
openai_compatible.py does, so this file skips cleanly (not a collection
failure) when the `ai` extras group isn't installed.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("openai", reason="tests webui/ai/providers/openai_compatible.py")

from webui import session  # noqa: E402
from webui.ai import run_instruction  # noqa: E402
from webui.ai.providers import openai_compatible  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _load_simple_text_fixture():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())


# --- resolve_key ---

def test_resolve_key_prefers_the_request_supplied_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert openai_compatible.resolve_key("request-key") == "request-key"


def test_resolve_key_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert openai_compatible.resolve_key(None) == "env-key"


def test_resolve_key_returns_none_when_neither_is_available_not_an_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert openai_compatible.resolve_key(None) is None


# --- translation ---

def test_translate_tools_wraps_the_schema_in_openai_function_shape():
    from webui.ai.tools import TOOLS

    translated = openai_compatible._translate_tools(TOOLS)

    assert translated[0]["type"] == "function"
    assert translated[0]["function"]["name"] == "redact_block"
    assert translated[0]["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_translate_response_maps_a_tool_call_and_finish_reason():
    fake_tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="redact_block", arguments=json.dumps({"block_id": 3})),
    )
    fake_completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[fake_tool_call]),
                finish_reason="tool_calls",
            )
        ]
    )

    response = openai_compatible._translate_response(fake_completion)

    assert response.stop_reason == "tool_use"
    assert response.content[0].type == "tool_use"
    assert response.content[0].name == "redact_block"
    assert response.content[0].input == {"block_id": 3}


def test_translate_response_maps_plain_text_and_stop():
    fake_completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="all done", tool_calls=None),
                finish_reason="stop",
            )
        ]
    )

    response = openai_compatible._translate_response(fake_completion)

    assert response.stop_reason == "end_turn"
    assert response.content[0].type == "text"
    assert response.content[0].text == "all done"


# --- make_client / send error handling ---

def test_make_client_requires_a_base_url():
    with pytest.raises(ValueError, match="base_url is required"):
        openai_compatible.make_client(api_key="fake", base_url=None)


def test_make_client_uses_a_placeholder_when_no_key_is_given():
    with patch("webui.ai.providers.openai_compatible.openai.OpenAI") as mock_cls:
        openai_compatible.make_client(api_key=None, base_url="http://example.test/v1")

    mock_cls.assert_called_once_with(api_key="not-needed", base_url="http://example.test/v1")


# --- run_instruction end-to-end through this provider ---

def test_run_instruction_executes_a_tool_call_via_openai_compatible():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

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

        summary = run_instruction(
            "redact the secret code",
            provider="openai_compatible",
            api_key="fake-key",
            base_url="http://example.test/v1",
            model="some-local-model",
        )

    assert summary == "Redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())


def test_run_instruction_requires_a_model_for_openai_compatible():
    _load_simple_text_fixture()

    with pytest.raises(ValueError, match="model is required"):
        run_instruction(
            "redact something",
            provider="openai_compatible",
            api_key="fake-key",
            base_url="http://example.test/v1",
            model=None,
        )
