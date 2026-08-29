# AI Instruction Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the manual-verification web UI a natural-language instruction box, backed by a Claude tool-calling loop that turns an instruction into `redact_region`/`replace_text` calls against whatever PDF is loaded in the current session — bring-your-own-key, no server-side credential.

**Architecture:** A new `webui/ai.py` module: tool definitions wrapping the existing `webui/session.py` mutation functions, a bounded manual tool-calling loop (not the SDK's beta Tool Runner — this is one bounded server-side call per instruction, not a long interactive session), and BYOK key resolution. One new endpoint (`POST /api/ai-instruct`) and one new frontend section reuse everything the manual-verification UI already built (the block registry, the `{pages, blocks}` response shape, the existing render/error-handling JS).

**Tech Stack:** Python, the `anthropic` SDK, model `claude-opus-5` by default (overridable per request). `pytest` + `unittest.mock` for the tool-calling loop (no real API calls in the test suite — see Global Constraints).

**Spec:** `docs/superpowers/specs/2026-08-29-ai-instruction-layer-design.md`

## Global Constraints

- No multi-turn chat memory across instructions — each instruction is a fresh loop with the current block list as its only context.
- No auto-detection/NER layer — Claude reads the block list itself.
- No real multi-provider abstraction — BYOK covers an Anthropic API key and an optional `base_url` override, nothing more.
- No persistence of API keys, conversation history, or instructions anywhere. Keys live in the browser only for the tab's lifetime (a JS variable/form field, never `localStorage`) and are never written to disk, logged, or stored in `webui/session.py`'s module-level state.
- No image-block instructions — text operations only.
- No engine file changes — `engine/` stays untouched by this plan, same as the manual-verification UI plan before it.
- New dependency (`anthropic`) lives under its own `ai` extras group in `pyproject.toml`, separate from `webui`'s extras — installing the manual-verification UI's click-through controls must not require installing the AI layer's dependency.
- No test in this plan makes a real network call to the Anthropic API — `client.messages.create` is mocked via `unittest.mock.patch` for every automated test. Real API verification happens once, manually, in the final task.
- The instruction loop is capped at a fixed number of tool-call rounds (`MAX_TOOL_ROUNDS = 10`) — it must fail loudly with a clear summary rather than loop forever if the model keeps calling tools without ending its turn.

---

## Task 1: AI module scaffolding — API key resolution, tool definitions, tool execution

**Files:**
- Modify: `pyproject.toml`
- Create: `webui/ai.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `webui.session.get_block`, `webui.session.get_blocks_summary`, `webui.session.redact`, `webui.session.replace` (all existing, unchanged).
- Produces: `resolve_api_key(request_key: str | None) -> str`, `TOOLS: list[dict]`, `SYSTEM_PROMPT: str`, `_execute_tool(name: str, tool_input: dict) -> tuple[str, bool]` (private, returns `(result_text, is_error)`). Consumed by Task 2's `run_instruction`.

This task's tests never touch the Anthropic API at all — API key resolution and tool execution are pure Python/session-layer logic.

- [ ] **Step 1: Add the `ai` extras group**

In `pyproject.toml`, add to `[project.optional-dependencies]` (after the existing `webui` block):

```toml
ai = [
    "anthropic>=1.0",
]
```

- [ ] **Step 2: Install and confirm the version**

Run: `./.venv/Scripts/python.exe -m pip install -e ".[test,webui,ai]"`
Expected: installs cleanly. Run `./.venv/Scripts/python.exe -c "import anthropic; print(anthropic.__version__)"` and note the actual installed version in your report.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_ai.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webui.ai'`.

- [ ] **Step 5: Write the implementation**

Create `webui/ai.py`:

```python
"""Turns a natural-language instruction into calls against the engine's
redact_region/replace_text operations, via Claude's tool-use API. See the
design spec's "Tools exposed to Claude" and "The instruction loop" sections.

BYOK: the caller supplies its own Anthropic API key per request (falling
back to the ANTHROPIC_API_KEY environment variable if none is supplied). No
key is ever stored in webui/session.py's module-level state -- it lives
only for the duration of one call to run_instruction() (added in a later
task; this file currently has the key resolution and tool layer only).
"""
import os

from webui import session

MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT = (
    "You are editing a PDF document through two tools: redact_block (permanently "
    "remove a block's content) and replace_block (replace a block's text with new "
    "text, preserving layout as much as the engine allows). You will be given the "
    "current list of text blocks in the document and an instruction. Find the "
    "block(s) the instruction refers to and call the appropriate tool(s). Only "
    "touch blocks that are actually relevant to the instruction -- if nothing in "
    "the block list matches what the instruction is asking for, say so in your "
    "final response instead of guessing or acting on an unrelated block."
)

TOOLS = [
    {
        "name": "redact_block",
        "description": (
            "Permanently remove the content of one text block from the document. "
            "Use this when the instruction asks to delete, remove, black out, or "
            "redact something, with no replacement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to redact, from the block list you were given.",
                }
            },
            "required": ["block_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "replace_block",
        "description": (
            "Replace one text block's content with new text, preserving its "
            "layout/font size as much as the engine allows. Use this when the "
            "instruction asks to change, fix, reword, or correct something (as "
            "opposed to deleting it)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to replace, from the block list you were given.",
                },
                "new_text": {
                    "type": "string",
                    "description": "The full replacement text for this block.",
                },
            },
            "required": ["block_id", "new_text"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def resolve_api_key(request_key: str | None) -> str:
    """The request-supplied key always wins; otherwise fall back to the
    ANTHROPIC_API_KEY environment variable. Raises ValueError (mapped to a
    clean 400 by webui/main.py's existing handler) if neither is available,
    before any Anthropic client is constructed.
    """
    if request_key:
        return request_key
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    raise ValueError("no Anthropic API key available -- supply one or set ANTHROPIC_API_KEY")


def _execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool call against the live session. Returns (result_text,
    is_error) -- is_error becomes the tool_result block's is_error flag, so
    Claude sees the same failure a human clicking the UI would see and can
    react to it (retry a different block, explain it in the final summary)
    rather than the loop crashing.
    """
    try:
        if name == "redact_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            session.redact(block_id)
            return f"redacted block {block_id}: {original_text!r}", False
        elif name == "replace_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            session.replace(block_id, tool_input["new_text"])
            return (
                f"replaced block {block_id} ({original_text!r}) with {tool_input['new_text']!r}",
                False,
            )
        else:
            return f"unknown tool: {name}", True
    except (ValueError, LookupError) as exc:
        return str(exc), True
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (74 existing + 9 new = 83).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml webui/ai.py tests/test_ai.py
git commit -m "feat: add API key resolution and tool execution for the AI instruction layer"
```

---

## Task 2: The instruction loop

**Files:**
- Modify: `webui/ai.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `resolve_api_key`, `TOOLS`, `SYSTEM_PROMPT`, `_execute_tool` (Task 1), `webui.session.get_blocks_summary` (existing).
- Produces: `run_instruction(instruction: str, api_key: str, base_url: str | None = None, model: str = "claude-opus-5") -> str`. Consumed by Task 3's `/api/ai-instruct` endpoint.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ai.py` (add `import json` and `from types import SimpleNamespace` and `from unittest.mock import patch` to the file's imports):

```python
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


def test_run_instruction_loops_across_multiple_tool_rounds():
    _load_simple_text_fixture()
    blocks = session.get_blocks_summary()
    first_id = blocks[0]["id"]
    second_id = blocks[1]["id"]

    responses = [
        _fake_response([_tool_use_block("call_1", "redact_block", {"block_id": first_id})], "tool_use"),
        _fake_response([_tool_use_block("call_2", "redact_block", {"block_id": second_id})], "tool_use"),
        _fake_response([_text_block("Redacted both lines.")], "end_turn"),
    ]

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.side_effect = responses

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -k run_instruction -v`
Expected: FAIL — `AttributeError: module 'webui.ai' has no attribute 'run_instruction'`.

- [ ] **Step 3: Write the implementation**

Add `import anthropic` and `import json` to the top of `webui/ai.py` (after the existing `import os`), and add this function at the end of the file:

```python
def run_instruction(
    instruction: str,
    api_key: str,
    base_url: str | None = None,
    model: str = "claude-opus-5",
) -> str:
    """Run the tool-calling loop for one instruction against the current
    session document. Returns the final summary text. Raises ValueError for
    an empty instruction, checked before any API call; otherwise propagates
    whatever anthropic.* exception the API call raises, for the route
    handler in webui/main.py to catch and map to a clean 400.
    """
    if not instruction.strip():
        raise ValueError("instruction must be non-empty")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)

    block_list = json.dumps(session.get_blocks_summary())
    messages = [
        {
            "role": "user",
            "content": f"Current blocks in the document:\n{block_list}\n\nInstruction: {instruction}",
        }
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result_text, is_error = _execute_tool(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return (
        "reached the step limit before finishing -- the instruction may be "
        "incompletely handled; check the block list below for what actually changed"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_ai.py -v`
Expected: all 16 tests PASS (9 from Task 1 + 7 new).

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (90 total).

- [ ] **Step 6: Commit**

```bash
git add webui/ai.py tests/test_ai.py
git commit -m "feat: add the AI instruction tool-calling loop"
```

---

## Task 3: `POST /api/ai-instruct` endpoint

**Files:**
- Modify: `webui/main.py`
- Test: `tests/test_webui.py`

**Interfaces:**
- Consumes: `webui.ai.resolve_api_key`, `webui.ai.run_instruction` (Task 1/2), `webui.session.get_pages_summary`, `webui.session.get_blocks_summary` (existing).
- Produces: `POST /api/ai-instruct`. Consumed by Task 4's frontend.

- [ ] **Step 1: Confirm the Anthropic SDK's exception hierarchy**

Before writing the exception-mapping code below, confirm against the actually-installed `anthropic` package that `anthropic.APIError` is the correct common base class for `AuthenticationError`, `RateLimitError`, `APIStatusError`, and `APIConnectionError` — e.g. `./.venv/Scripts/python.exe -c "import anthropic; print(anthropic.AuthenticationError.__mro__)"`. If the base class has a different name on the installed version, use that name instead everywhere `anthropic.APIError` appears below, and note the discrepancy in your report.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_webui.py` (add `from unittest.mock import patch` and `from types import SimpleNamespace` to the file's existing imports if not already present from a prior task):

```python
def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _fake_response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_ai_instruct_runs_a_tool_call_and_returns_a_summary():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        upload_response = client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})
    block_id = next(b["id"] for b in upload_response.json()["blocks"] if "REDACT-ME-12345" in b["text"])

    responses = [
        _fake_response([_tool_use_block("call_1", "redact_block", {"block_id": block_id})], "tool_use"),
        _fake_response([_text_block("Redacted the secret code.")], "end_turn"),
    ]

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_anthropic_cls.return_value.messages.create.side_effect = responses
        response = client.post(
            "/api/ai-instruct",
            json={"instruction": "redact the secret code", "api_key": "fake-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Redacted the secret code."
    assert not any("REDACT-ME-12345" in b["text"] for b in body["blocks"])


def test_ai_instruct_returns_a_clean_error_with_no_api_key_available(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.post("/api/ai-instruct", json={"instruction": "redact something"})

    assert response.status_code == 400
    assert "API key" in response.json()["error"]


def test_ai_instruct_rejects_an_empty_instruction():
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    response = client.post("/api/ai-instruct", json={"instruction": "  ", "api_key": "fake-key"})

    assert response.status_code == 400
    assert response.json()["error"]


def test_ai_instruct_uses_the_environment_key_when_none_is_supplied(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    with open(FIXTURES / "simple_text.pdf", "rb") as f:
        client.post("/api/upload", files={"file": ("simple_text.pdf", f, "application/pdf")})

    with patch("webui.ai.anthropic.Anthropic") as mock_anthropic_cls:
        mock_anthropic_cls.return_value.messages.create.return_value = _fake_response(
            [_text_block("ok")], "end_turn"
        )
        response = client.post("/api/ai-instruct", json={"instruction": "do nothing"})

    assert response.status_code == 200
    mock_anthropic_cls.assert_called_once_with(api_key="env-key")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k ai_instruct -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Add `import anthropic` to `webui/main.py`'s imports (after the existing `fastapi`/`pydantic` imports), add `from webui import ai` to the `from webui import session` line's block (as its own line), and add this request model and route:

```python
class AIInstructRequest(BaseModel):
    instruction: str
    api_key: str | None = None
    base_url: str | None = None
    model: str = "claude-opus-5"


@app.post("/api/ai-instruct")
async def ai_instruct(body: AIInstructRequest) -> dict:
    resolved_key = ai.resolve_api_key(body.api_key)
    try:
        summary = ai.run_instruction(body.instruction, resolved_key, body.base_url, body.model)
    except anthropic.APIError as exc:
        raise ValueError(f"Anthropic API error: {exc}") from exc
    return {
        "summary": summary,
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
    }
```

(Use whatever base class name Step 1 actually confirmed, if different from `anthropic.APIError`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_webui.py -k ai_instruct -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (94 total).

- [ ] **Step 7: Commit**

```bash
git add webui/main.py tests/test_webui.py
git commit -m "feat: add the /api/ai-instruct endpoint"
```

---

## Task 4: Frontend, README, and real end-to-end verification

**Files:**
- Modify: `webui/static/index.html`
- Modify: `webui/static/app.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: `POST /api/ai-instruct` (Task 3).
- Produces: no new interfaces for later tasks — this is the last task in the plan.

There is no automated test for this task's frontend code, matching the same scoping decision the manual-verification UI plan made for its own frontend. This task's real verification is Step 3 below: actually running the server and trying it, with a real API key if one is available.

- [ ] **Step 1: Add the AI instruction section to the page**

Add to `webui/static/index.html`, after the existing `download-button` line and before the `<div id="error">` line:

```html
  <hr>
  <h2>AI instruction (optional)</h2>
  <p>
    Give a natural-language instruction and Claude will decide which block(s)
    to redact or replace. Requires your own Anthropic API key -- it stays in
    this browser tab only, sent to this server per-request, never stored.
  </p>
  <div>
    <input type="password" id="api-key-input" placeholder="Anthropic API key (or leave blank to use the server's ANTHROPIC_API_KEY)" style="width: 24rem;">
  </div>
  <details>
    <summary>Advanced</summary>
    <input type="text" id="base-url-input" placeholder="Custom base URL (optional)">
    <input type="text" id="model-input" placeholder="Model (default: claude-opus-5)">
  </details>
  <div>
    <input type="text" id="instruction-input" placeholder="e.g. redact the patient's name" style="width: 24rem;">
    <button id="ai-instruct-button">Run</button>
  </div>
  <div id="ai-summary"></div>
```

- [ ] **Step 2: Wire it up**

Add to `webui/static/app.js` (at the end of the file):

```javascript
document.getElementById("ai-instruct-button").onclick = async () => {
  const button = document.getElementById("ai-instruct-button");
  const instruction = document.getElementById("instruction-input").value;
  const apiKey = document.getElementById("api-key-input").value;
  const baseUrl = document.getElementById("base-url-input").value;
  const model = document.getElementById("model-input").value;

  const body = { instruction };
  if (apiKey) body.api_key = apiKey;
  if (baseUrl) body.base_url = baseUrl;
  if (model) body.model = model;

  button.disabled = true;
  document.getElementById("ai-summary").textContent = "";
  try {
    const response = await fetch("/api/ai-instruct", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      await refreshState();
      showError(data.error || "AI instruction failed");
      return;
    }
    document.getElementById("ai-summary").textContent = data.summary;
    render(data);
  } finally {
    button.disabled = false;
  }
};
```

- [ ] **Step 3: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all passing (94 total — this task adds no new automated tests, but confirms nothing in Steps 1-2 broke anything).

- [ ] **Step 4: Real end-to-end verification**

First, check whether a real Anthropic API key is available in your environment: `echo $ANTHROPIC_API_KEY` (or check via whatever credential-check mechanism your environment provides). Two paths:

**If a real key is available:** run the server (`./.venv/Scripts/python.exe -m uvicorn webui.main:app --reload`), open it in a browser, upload `tests/fixtures/mixed.pdf`, leave the API key field blank (so it falls back to the environment variable) or paste the key, type an instruction that clearly targets one of the fixture's known blocks (e.g. "redact the patient ID" — the fixture contains `PATIENT-0042`), click Run, and confirm: the summary text appears, the correct block is actually gone from the page image and block list, and the exported PDF (via the existing Download button) reflects the change. Also try a deliberately-impossible instruction (e.g. "delete the signature block" when no such block exists) and confirm Claude's summary says it found nothing matching, rather than acting on an unrelated block.

**If no real key is available:** say so honestly in your report. Do the next-best verification: run the server, open it in a browser, submit an instruction with an obviously-fake API key (e.g. `sk-ant-fake`), and confirm the request is built correctly (check the browser's network tab or server logs for the actual POST body) and that the resulting `AuthenticationError` surfaces as a clean, readable error in the UI rather than a raw stack trace or a silent failure. This proves the wiring is correct even without a working key.

Report the outcome of whichever path you took — this step is not optional busywork, it is the actual point of this task, same as the manual-verification UI plan's own final-task verification step.

- [ ] **Step 5: Update the README**

Add a short section to `README.md` (matching its existing terse style) describing the AI instruction layer: what it does, that it requires `pip install -e ".[ai]"` (in addition to `webui`) and either an `ANTHROPIC_API_KEY` environment variable or pasting a key into the browser field, and that no key is ever stored server-side.

- [ ] **Step 6: Commit**

```bash
git add webui/static/index.html webui/static/app.js README.md
git commit -m "feat: add the AI instruction frontend"
```

---

## Final Verification

After all 4 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — all 94 passing.
2. Confirm `engine/` is completely untouched by this plan: `git diff <plan-start-commit>..HEAD -- engine/` should be empty.
3. Confirm the base install and the `webui`-only install both stay unaffected: `pip install -e .` (no extras) and `pip install -e ".[test,webui]"` (no `ai`) should both leave `import anthropic` failing in a scratch venv, confirming the `ai` extras group is genuinely optional on top of `webui`, the same way `webui` is optional on top of the base engine.
4. Grep for anything resembling a stored API key anywhere in the repo (`grep -rn "ANTHROPIC_API_KEY" --include=*.py .` should show only the environment-variable read in `webui/ai.py`, never a hardcoded value or a write to a file/session dict).
5. Re-run Task 4 Step 4's verification one more time as a final sanity check.
