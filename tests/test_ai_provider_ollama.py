"""Tests for webui/ai/providers/ollama.py's translation layer and the
run_instruction() loop driven through it. Mocked -- no real network call.

Soft-imports the `ollama` SDK the same way webui/ai/providers/ollama.py
does, so this file skips cleanly (not a collection failure) when the `ai`
extras group isn't installed.

The `raw` response objects below are `SimpleNamespace` trees, not dicts --
Step 1's verification against the installed `ollama` package (0.6.2)
confirmed `client.chat(...)` returns a typed `ollama.ChatResponse` pydantic
object (attribute access: `raw.message.content`, `raw.message.tool_calls`,
`tool_call.function.name`/`.arguments`), not a plain dict the way the design
spec's placeholder code guessed. SimpleNamespace mirrors that attribute
access the same way tests/test_ai_provider_openai_compatible.py's fakes
mirror the openai SDK's typed objects.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("ollama", reason="tests webui/ai/providers/ollama.py")

from webui import session  # noqa: E402
from webui.ai import run_instruction  # noqa: E402
from webui.ai.providers import ollama  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _load_simple_text_fixture():
    session.load_document((FIXTURES / "simple_text.pdf").read_bytes())


# --- resolve_key ---

def test_resolve_key_passes_through_unused():
    assert ollama.resolve_key("anything") == "anything"
    assert ollama.resolve_key(None) is None


# --- translation ---

def test_translate_tools_wraps_the_schema_in_ollama_function_shape():
    from webui.ai.tools import TOOLS

    translated = ollama._translate_tools(TOOLS)

    assert translated[0]["type"] == "function"
    assert translated[0]["function"]["name"] == "redact_block"
    assert translated[0]["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_translate_response_maps_a_tool_call():
    fake_tool_call = SimpleNamespace(
        function=SimpleNamespace(name="redact_block", arguments={"block_id": 3})
    )
    raw = SimpleNamespace(
        message=SimpleNamespace(content=None, tool_calls=[fake_tool_call])
    )

    response = ollama._translate_response(raw)

    assert response.stop_reason == "tool_use"
    assert response.content[0].type == "tool_use"
    assert response.content[0].name == "redact_block"
    assert response.content[0].input == {"block_id": 3}
    # No id/correlation field exists on Ollama's tool_calls (confirmed in
    # Step 1) -- we synthesize one purely for our own internal bookkeeping.
    assert response.content[0].id == "ollama_call_0"


def test_translate_response_maps_plain_text():
    raw = SimpleNamespace(message=SimpleNamespace(content="all done", tool_calls=None))

    response = ollama._translate_response(raw)

    assert response.stop_reason == "end_turn"
    assert response.content[0].type == "text"
    assert response.content[0].text == "all done"


# --- run_instruction end-to-end through this provider ---

def test_run_instruction_executes_a_tool_call_via_ollama():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    tool_call_response = SimpleNamespace(
        message=SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(name="redact_block", arguments={"block_id": block_id})
                )
            ],
        )
    )
    final_response = SimpleNamespace(
        message=SimpleNamespace(content="Redacted the secret code.", tool_calls=None)
    )

    with patch("webui.ai.providers.ollama.ollama.Client") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.side_effect = [tool_call_response, final_response]

        summary = run_instruction(
            "redact the secret code",
            provider="ollama",
            api_key=None,
            model="llama3.1",
        )

    assert summary == "Redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())
    mock_cls.assert_called_once_with(host="http://localhost:11434")


def test_run_instruction_requires_a_model_for_ollama():
    _load_simple_text_fixture()

    with pytest.raises(ValueError, match="model is required"):
        run_instruction("redact something", provider="ollama", api_key=None, model=None)
