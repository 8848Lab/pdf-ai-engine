"""Tests for webui/ai.py: API-key resolution, tool-execution layer, and the
run_instruction() tool-calling loop itself (tested against a mocked
Anthropic client -- resolve_api_key and _execute_tool never touch the
Anthropic API at all, since they're pure Python/session-layer logic with no
network dependency, but the run_instruction() tests below do exercise the
full loop against webui.ai.anthropic.Anthropic, mocked).

webui/ai.py's `anthropic` import is soft (see that module's docstring), so
this whole file is skipped cleanly when the `ai` extras group isn't
installed -- an unconditional import here would otherwise fail at collection
for a developer who only installed `pip install -e ".[test,webui]"`.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("anthropic", reason="webui/ai.py tests need the `ai` extras group installed")

from webui import ai, session  # noqa: E402

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


# --- run_instruction ---

def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _fake_response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_run_instruction_executes_a_single_tool_call_then_returns_the_summary():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    responses = [
        _fake_response([_tool_use_block("call_1", "redact_block", {"block_id": block_id})], "tool_use"),
        _fake_response([_text_block("Done -- redacted the secret code.")], "end_turn"),
    ]

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.side_effect = responses

        summary = ai.run_instruction("redact the secret code", api_key="fake-key")

    assert summary == "Done -- redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in session.get_blocks_summary())
    assert mock_client.messages.create.call_count == 2


def _blocks_from_last_sent_message(messages):
    """Parse the block-id list out of the `messages` argument actually SENT
    to the model on the previous create() call -- i.e. what the real Claude
    would be seeing -- rather than reading webui/session.py's live state.
    Reading live state let the original block-id-goes-stale bug slip through
    a test that looked plausible: a fake "model" that peeks at the session
    directly can always find the current ids even if run_instruction() never
    actually sent them, so it can't catch a regression where the model isn't
    told the ids changed.
    """
    last_content = messages[-1]["content"]
    if isinstance(last_content, str):
        # Round 1's initial user message: "...blocks in the document:\n<json>
        # \n\nInstruction: ...".
        json_text = last_content.split(":\n", 1)[1].split("\n\nInstruction:")[0]
    else:
        # A later round's tool_results message: the last content block is the
        # freshly appended "current blocks" text block.
        text_block = last_content[-1]
        assert text_block["type"] == "text"
        json_text = text_block["text"].split(":\n", 1)[1]
    return json.loads(json_text)


def test_run_instruction_loops_across_multiple_tool_rounds():
    # Block ids churn on every mutation (session.py's monotonic registry
    # rebuild -- see webui/session.py's _build_block_registry), so this
    # cannot script both rounds' block_ids up front: round 2's target id
    # does not exist until round 1's redact has run. The fake "model" instead
    # reads the block ids out of what run_instruction() actually put in the
    # conversation on the previous turn (see _blocks_from_last_sent_message),
    # exactly like the real Claude would have to.
    _load_simple_text_fixture()
    call_count = 0

    def scripted_responses(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        remaining = _blocks_from_last_sent_message(kwargs["messages"])
        if remaining:
            block_id = remaining[0]["id"]
            return _fake_response(
                [_tool_use_block(f"call_{call_count}", "redact_block", {"block_id": block_id})],
                "tool_use",
            )
        return _fake_response([_text_block("Redacted both lines.")], "end_turn")

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.side_effect = scripted_responses

        summary = ai.run_instruction("redact everything", api_key="fake-key")

    assert summary == "Redacted both lines."
    assert session.get_blocks_summary() == []
    assert mock_client.messages.create.call_count == 3


def test_run_instruction_surfaces_a_bad_block_id_as_a_tool_error_not_a_crash():
    _load_simple_text_fixture()

    responses = [
        _fake_response([_tool_use_block("call_1", "redact_block", {"block_id": 999})], "tool_use"),
        _fake_response([_text_block("I could not find that block, so I did nothing.")], "end_turn"),
    ]

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.side_effect = responses

        summary = ai.run_instruction("redact block 999", api_key="fake-key")

    assert "could not find" in summary
    second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    tool_result = second_call_kwargs["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "999" in tool_result["content"]


def test_run_instruction_stops_at_the_round_cap_instead_of_looping_forever():
    _load_simple_text_fixture()
    block_id = session.get_blocks_summary()[0]["id"]

    def always_tool_use(*args, **kwargs):
        return _fake_response(
            [_tool_use_block("call", "redact_block", {"block_id": block_id})], "tool_use"
        )

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.side_effect = always_tool_use

        summary = ai.run_instruction("keep going forever", api_key="fake-key")

    assert "step limit" in summary
    assert mock_client.messages.create.call_count == ai.MAX_TOOL_ROUNDS


def test_run_instruction_rejects_an_empty_instruction_before_any_api_call():
    _load_simple_text_fixture()

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        with pytest.raises(ValueError, match="non-empty"):
            ai.run_instruction("   ", api_key="fake-key")

        mock_anthropic_cls.assert_not_called()


def test_run_instruction_passes_base_url_and_model_through_to_the_client():
    _load_simple_text_fixture()

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.return_value = _fake_response([_text_block("ok")], "end_turn")

        ai.run_instruction(
            "do nothing in particular",
            api_key="fake-key",
            base_url="https://example.test",
            model="claude-sonnet-5",
        )

    mock_anthropic_cls.assert_called_once_with(api_key="fake-key", base_url="https://example.test")
    _, create_kwargs = mock_client.messages.create.call_args
    assert create_kwargs["model"] == "claude-sonnet-5"
