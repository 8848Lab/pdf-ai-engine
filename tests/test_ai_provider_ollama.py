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
import json
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
        message=SimpleNamespace(content=None, tool_calls=[fake_tool_call]),
        done_reason="tool_calls",
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
    raw = SimpleNamespace(message=SimpleNamespace(content="all done", tool_calls=None), done_reason="stop")

    response = ollama._translate_response(raw)

    assert response.stop_reason == "end_turn"
    assert response.content[0].type == "text"
    assert response.content[0].text == "all done"


def test_translate_response_maps_a_non_stop_done_reason_through_unchanged():
    # done_reason="length" -- send()'s options={"num_predict": max_tokens}
    # truncating generation is a realistic outcome, and it must not be
    # silently reported as a clean "end_turn".
    raw = SimpleNamespace(message=SimpleNamespace(content="partial...", tool_calls=None), done_reason="length")

    response = ollama._translate_response(raw)

    assert response.stop_reason == "length"


def test_translate_messages_includes_the_matching_tool_name_on_tool_results():
    from webui.ai.providers import ToolUseBlock

    messages = [
        {"role": "user", "content": "do something"},
        {
            "role": "assistant",
            "content": [ToolUseBlock(id="call_1", name="redact_block", input={"block_id": 3})],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "redacted", "is_error": False}
            ],
        },
    ]

    translated = ollama._translate_messages(messages)

    tool_message = next(m for m in translated if m["role"] == "tool")
    assert tool_message["tool_name"] == "redact_block"


def test_translate_messages_correlates_multiple_parallel_tool_calls_by_name():
    from webui.ai.providers import ToolUseBlock

    messages = [
        {"role": "user", "content": "do two things"},
        {
            "role": "assistant",
            "content": [
                ToolUseBlock(id="call_1", name="redact_block", input={"block_id": 1}),
                ToolUseBlock(id="call_2", name="replace_block", input={"block_id": 2, "new_text": "x"}),
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_2", "content": "replaced", "is_error": False},
                {"type": "tool_result", "tool_use_id": "call_1", "content": "redacted", "is_error": False},
            ],
        },
    ]

    translated = ollama._translate_messages(messages)

    tool_messages = [m for m in translated if m["role"] == "tool"]
    assert tool_messages[0]["tool_name"] == "replace_block"
    assert tool_messages[0]["content"] == "replaced"
    assert tool_messages[1]["tool_name"] == "redact_block"
    assert tool_messages[1]["content"] == "redacted"


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
        ),
        done_reason="tool_calls",
    )
    final_response = SimpleNamespace(
        message=SimpleNamespace(content="Redacted the secret code.", tool_calls=None),
        done_reason="stop",
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


def test_run_instruction_wraps_a_sdk_exception_as_a_value_error():
    _load_simple_text_fixture()

    with patch("webui.ai.providers.ollama.ollama.Client") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.side_effect = Exception("boom")

        with pytest.raises(ValueError, match="boom"):
            run_instruction("redact something", provider="ollama", api_key=None, model="llama3.1")


# --- wire-shape-aware multi-round test --------------------------------------
#
# Mirrors tests/test_ai.py's _blocks_from_last_sent_message /
# test_run_instruction_loops_across_multiple_tool_rounds: the fake "model"
# reads the refreshed block-id list out of what was actually SENT to the
# mocked client on the previous call (this provider's own translated wire
# format), not out of webui/session.py's live state.


def _blocks_from_last_sent_message(kwargs):
    """Parse the block-id list out of the last message in the Ollama-shaped
    `messages` kwarg actually sent to client.chat(...). Both loop.py's
    round-1 initial user message and every later round's trailing "current
    blocks" text block translate (via ollama._translate_messages) to a
    plain-string "user" role message as the LAST entry in the list -- so one
    parse handles both.
    """
    last_content = kwargs["messages"][-1]["content"]
    assert isinstance(last_content, str)
    if "\n\nInstruction:" in last_content:
        json_text = last_content.split(":\n", 1)[1].split("\n\nInstruction:")[0]
    else:
        json_text = last_content.split(":\n", 1)[1]
    return json.loads(json_text)


def _ollama_tool_call_response(name, arguments):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))],
        ),
        done_reason="tool_calls",
    )


def _ollama_text_response(text):
    return SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None), done_reason="stop")


def test_run_instruction_loops_across_multiple_tool_rounds_via_ollama():
    _load_simple_text_fixture()
    call_count = 0

    def scripted_responses(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        remaining = _blocks_from_last_sent_message(kwargs)
        if remaining:
            block_id = remaining[0]["id"]
            return _ollama_tool_call_response("redact_block", {"block_id": block_id})
        return _ollama_text_response("Redacted both lines.")

    with patch("webui.ai.providers.ollama.ollama.Client") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.side_effect = scripted_responses

        summary = run_instruction(
            "redact everything", provider="ollama", api_key=None, model="llama3.1"
        )

    assert summary == "Redacted both lines."
    assert session.get_blocks_summary() == []
    assert mock_client.chat.call_count == 3


def test_run_instruction_sends_the_matching_tool_name_for_each_parallel_tool_call():
    # Ollama has no parallel-tool-call suppression, so a single round can
    # legitimately contain multiple tool calls -- confirm each tool-result
    # message sent back on the NEXT call carries the tool_name that actually
    # matches the call it answers, not just present-but-wrong.
    _load_simple_text_fixture()
    blocks = session.get_blocks_summary()
    id_a, id_b = blocks[0]["id"], blocks[1]["id"]

    two_tool_call_response = SimpleNamespace(
        message=SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(function=SimpleNamespace(name="redact_block", arguments={"block_id": id_a})),
                SimpleNamespace(function=SimpleNamespace(name="redact_block", arguments={"block_id": id_b})),
            ],
        ),
        done_reason="tool_calls",
    )
    final_response = _ollama_text_response("Redacted both.")

    with patch("webui.ai.providers.ollama.ollama.Client") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.chat.side_effect = [two_tool_call_response, final_response]

        run_instruction("redact everything", provider="ollama", api_key=None, model="llama3.1")

    second_call_kwargs = mock_client.chat.call_args_list[1].kwargs
    tool_messages = [m for m in second_call_kwargs["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 2
    assert all(m["tool_name"] == "redact_block" for m in tool_messages)
