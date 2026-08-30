# Multi-Provider AI Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the AI instruction layer (currently Anthropic-only) with a generic OpenAI-compatible provider (covers Ollama's OpenAI-compat shim, LM Studio, llama.cpp server, vLLM, and real OpenAI-compatible clouds) and a native Ollama provider, selected via an explicit `provider` field — no auto-detection.

**Architecture:** Restructure `webui/ai.py` into a `webui/ai/` package. The tool-calling loop's internal message history keeps Anthropic's existing shape as the canonical format (Approach A from the design discussion); each new provider translates at its own boundary — canonical messages/tools in, a canonical-shaped `Response` out — so `loop.py` never changes based on which provider it's talking to.

**Tech Stack:** Python, `anthropic` SDK (unchanged), `openai` SDK (new), `ollama` SDK (new). All three ship together under one broadened `ai` extras group; each provider module soft-imports its own SDK so a caller who never selects that provider never needs it installed.

**Spec:** `docs/superpowers/specs/2026-08-29-multi-provider-ai-layer-design.md`

## Global Constraints

- `provider` is a required field on `POST /api/ai-instruct` — no default. Valid values: `"anthropic"`, `"openai_compatible"`, `"ollama"`.
- `model` keeps its `"claude-opus-5"` default only for `anthropic`; it is required (no default, clean 400 if missing) for `openai_compatible` and `ollama`, since there's no way to guess a local/generic model name.
- `api_key`: required for `anthropic` (request → `ANTHROPIC_API_KEY` env → 400, unchanged from before); optional for `openai_compatible` (request → `OPENAI_API_KEY` env → a placeholder string, never an error); unused for `ollama` (field accepted, ignored).
- No API key of any kind is ever logged, written to disk, or stored in `webui/session.py`'s module-level state.
- The `ai` extras group grows to include `openai` and `ollama`, still fully separate from `webui`'s own extras group.
- No real network calls in the automated test suite — every provider's SDK client is mocked in every automated test. The one deliberate exception (same carve-out as last session's Anthropic verification): the final manual-verification task may make a real call to a locally-reachable Ollama server (free, no billing concern) and, opportunistically, to real OpenAI if `OPENAI_API_KEY` happens to already be set.
- No engine changes — `engine/` stays untouched by this plan.
- No provider auto-detection, no plugin/registration system beyond the three providers built into `providers/__init__.py`'s `PROVIDERS` registry.
- The internal canonical message/response format stays Anthropic-shaped (Approach A) — not a fully neutral format. `tools.py` (`TOOLS`, `SYSTEM_PROMPT`, `_execute_tool`) is untouched by this plan beyond moving to its new file location in Task 1.

---

## Task 1: Restructure `webui/ai.py` into a package (zero behavior change)

**Files:**
- Create: `webui/ai/__init__.py`, `webui/ai/loop.py`, `webui/ai/tools.py`, `webui/ai/providers/__init__.py`, `webui/ai/providers/anthropic.py`
- Delete: `webui/ai.py`
- Modify: `tests/test_ai.py` (import paths and patch targets only — no test logic changes)

**Interfaces:**
- Produces: `webui.ai.run_instruction(instruction, api_key, base_url=None, model="claude-opus-5") -> str` (unchanged signature from before this plan), `webui.ai.resolve_api_key(request_key) -> str` (unchanged signature), `webui.ai.providers.anthropic.make_client(api_key, base_url)`, `webui.ai.providers.anthropic.send(client, system, tools, messages, model, max_tokens)`.
- Consumes: `webui.session` (unchanged).

This task is a pure move — every one of the 93 existing tests must still pass, with only import paths and the `patch(...)` target string changed. No behavior, no new functionality. This isolates "did the refactor break anything" from every later task's real new behavior.

- [ ] **Step 1: Create `webui/ai/tools.py`**

```python
"""Tool schemas the model is given, and the function that actually executes
one tool call against the live session. Provider-agnostic -- every provider
adapter in providers/ uses this same TOOLS/SYSTEM_PROMPT/_execute_tool,
translated into that provider's own wire format at the provider's own
boundary (see providers/__init__.py).
"""
from webui import session

SYSTEM_PROMPT = (
    "You are editing a PDF document through two tools: redact_block (permanently "
    "remove a block's content) and replace_block (replace a block's text with new "
    "text, preserving layout as much as the engine allows). You will be given the "
    "current list of text blocks in the document and an instruction. Find the "
    "block(s) the instruction refers to and call the appropriate tool(s). Only "
    "touch blocks that are actually relevant to the instruction -- if nothing in "
    "the block list matches what the instruction is asking for, say so in your "
    "final response instead of guessing or acting on an unrelated block. Block ids "
    "are reassigned after every edit -- only the most recently shown block list is "
    "valid, so never reuse an id from earlier in the conversation."
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


def _execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool call against the live session. Returns (result_text,
    is_error) -- is_error becomes the tool_result block's is_error flag, so
    the model sees the same failure a human clicking the UI would see and
    can react to it (retry a different block, explain it in the final
    summary) rather than the loop crashing.
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

- [ ] **Step 2: Create `webui/ai/providers/__init__.py`**

```python
"""Provider adapters for the AI instruction layer. Each providers/<name>.py
module implements a common interface -- make_client(api_key, base_url),
send(client, system, tools, messages, model, max_tokens) -> Response,
resolve_key(request_key) -> str | None, plus DEFAULT_MODEL/DEFAULT_BASE_URL
constants (None means "no default, required"). See the design spec's
"Provider interface" section.

As of this file, only providers/anthropic.py exists -- the PROVIDERS
registry and the generic resolve_api_key() dispatcher are added once a
second provider does, in a later task.
"""
```

- [ ] **Step 3: Create `webui/ai/providers/anthropic.py`**

```python
"""The Anthropic provider adapter: today's client.messages.create() call,
moved here unchanged from the pre-package webui/ai.py. See the design
spec's "Provider specifics" section.

Note: this file is named anthropic.py and does `import anthropic` (the
third-party SDK) inside it -- Python's absolute-import semantics mean this
always refers to the installed SDK, never to this file itself, so there is
no actual collision, just a same-name coincidence worth flagging for
whoever reads this next.

The SDK import is soft: a developer who only installed
`pip install -e ".[test,webui]"` must still be able to import this whole
package (providers/__init__.py imports this module to build its registry
in a later task) -- only actually calling make_client()/send() needs the
SDK to be present.
"""
import os

try:
    import anthropic
except ImportError:
    anthropic = None

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_BASE_URL = None  # None -> let the SDK use its own default (api.anthropic.com)


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


def make_client(api_key, base_url):
    if anthropic is None:
        raise ValueError(
            "the AI instruction layer needs the ai extras group -- pip install -e '.[ai]'"
        )
    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        return anthropic.Anthropic(**client_kwargs)
    except Exception as exc:
        # Not just anthropic.APIError -- e.g. a malformed base_url raises
        # httpx's InvalidURL during client construction, which is not an
        # APIError subclass at all. Broad catch mirrors webui/main.py's own
        # upload-handler idiom: an external library can throw various
        # things, they all become a clean ValueError here.
        raise ValueError(f"Anthropic API error: {exc}") from exc


def send(client, system, tools, messages, model, max_tokens):
    """One turn. Returns the raw anthropic.Message -- its .content/
    .stop_reason shape is exactly what webui/ai/loop.py's run_instruction()
    already expects, so no translation is needed for this provider.
    """
    try:
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            messages=messages,
        )
    except Exception as exc:
        raise ValueError(f"Anthropic API error: {exc}") from exc
```

- [ ] **Step 4: Create `webui/ai/loop.py`**

```python
"""The tool-calling loop: run_instruction() is the only thing webui/main.py
calls into this package. As of this file, this module talks directly to
providers/anthropic.py -- a later task replaces this with a generic
provider lookup once a second provider exists.
"""
import json

from webui import session
from webui.ai.providers import anthropic as _anthropic
from webui.ai.tools import SYSTEM_PROMPT, TOOLS, _execute_tool

MAX_TOOL_ROUNDS = 10
DEFAULT_MAX_TOKENS = 16000


def run_instruction(
    instruction: str,
    api_key: str,
    base_url: str | None = None,
    model: str = "claude-opus-5",
) -> str:
    """Run the tool-calling loop for one instruction against the current
    session document. Returns the final summary text. Raises ValueError for
    an empty instruction, a missing `ai` extras install, no document loaded,
    or any failure from the Anthropic SDK/network -- every error path out of
    this function is a clean ValueError, for the route handler in
    webui/main.py to map straight to a 400.
    """
    if not instruction.strip():
        raise ValueError("instruction must be non-empty")

    # Fail fast, before any API call is made, if nothing is loaded -- without
    # this, get_blocks_summary() below silently returns [] and we'd burn a
    # real API call before get_pages_summary() (only reached at the very end)
    # ever gets a chance to raise this same LookupError.
    session.get_handle()

    block_list = json.dumps(session.get_blocks_summary())
    messages = [
        {
            "role": "user",
            "content": f"Current blocks in the document:\n{block_list}\n\nInstruction: {instruction}",
        }
    ]

    client = _anthropic.make_client(api_key, base_url)

    for _ in range(MAX_TOOL_ROUNDS):
        response = _anthropic.send(client, SYSTEM_PROMPT, TOOLS, messages, model, DEFAULT_MAX_TOKENS)

        if response.stop_reason == "tool_use":
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
            # Block ids churn on every mutation (see webui/session.py's
            # monotonic registry rebuild), and the ids the model was
            # originally given may already be dead. Re-send the current
            # list in the same message as the tool results so the model's
            # next turn always has a valid set of ids to work from.
            tool_results.append(
                {
                    "type": "text",
                    "text": (
                        "Current blocks in the document (ids may have changed after "
                        f"the edit(s) above):\n{json.dumps(session.get_blocks_summary())}"
                    ),
                }
            )
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "end_turn":
            return "".join(block.text for block in response.content if block.type == "text")

        # Some other stop reason (e.g. max_tokens, refusal) -- not a clean
        # finish, so don't silently join possibly-empty content into "".
        return (
            f"the model stopped early ({response.stop_reason}) before finishing -- "
            "try a simpler or more specific instruction"
        )

    return (
        "reached the step limit before finishing -- the instruction may be "
        "incompletely handled; check the block list below for what actually changed"
    )
```

- [ ] **Step 5: Create `webui/ai/__init__.py`**

```python
"""Public surface of the AI instruction layer -- resolve_api_key() and
run_instruction() are what webui/main.py calls. See loop.py, tools.py, and
providers/ for the implementation; this package replaces the single-file
webui/ai.py module now that a second provider (beyond Anthropic) makes a
package layout worth the file count. See the design spec's "Architecture"
section.
"""
from webui.ai.loop import run_instruction
from webui.ai.providers.anthropic import resolve_api_key

__all__ = ["run_instruction", "resolve_api_key"]
```

- [ ] **Step 6: Delete `webui/ai.py`**

`webui/ai.py` and `webui/ai/` cannot coexist as the same importable name — delete the old file now that its content lives in the new package.

- [ ] **Step 7: Update `tests/test_ai.py`'s imports and patch targets**

Change the top of the file (everything through the `FIXTURES` line) from:

```python
from webui import ai, session  # noqa: E402
```

to:

```python
from webui import session  # noqa: E402
from webui.ai import resolve_api_key, run_instruction  # noqa: E402
from webui.ai.loop import MAX_TOOL_ROUNDS  # noqa: E402
from webui.ai.tools import _execute_tool  # noqa: E402
```

Then, throughout the rest of the file:
- Replace every `ai.resolve_api_key(...)` call with `resolve_api_key(...)`.
- Replace every `ai._execute_tool(...)` call with `_execute_tool(...)`.
- Replace every `ai.run_instruction(...)` call with `run_instruction(...)`.
- Replace `ai.MAX_TOOL_ROUNDS` with `MAX_TOOL_ROUNDS`.
- Replace every `patch("webui.ai.anthropic.Anthropic")` with
  `patch("webui.ai.providers.anthropic.anthropic.Anthropic")`.

No other change to any test's logic, assertions, or docstrings.

- [ ] **Step 8: Update `tests/test_webui.py`'s patch targets**

Every `patch("webui.ai.anthropic.Anthropic")` in this file (there are three,
in the `test_ai_instruct_*` tests) becomes
`patch("webui.ai.providers.anthropic.anthropic.Anthropic")`. No other
change — `webui.main`'s `from webui import ai` import and its
`ai.resolve_api_key(...)`/`ai.run_instruction(...)` call sites in
`webui/main.py` are untouched by this task (they still resolve correctly
against the new package's `__init__.py` re-exports).

- [ ] **Step 9: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all 93 tests still pass, byte-for-byte the same set as before this task — this task changed zero behavior.

- [ ] **Step 10: Commit**

```bash
git add webui/ai.py webui/ai/ tests/test_ai.py tests/test_webui.py
git commit -m "refactor: split webui/ai.py into a package ahead of multi-provider support"
```

---

## Task 2: Provider registry, OpenAI-compatible provider, and route wiring

**Files:**
- Modify: `webui/ai/providers/__init__.py`, `webui/ai/providers/anthropic.py`, `webui/ai/loop.py`, `webui/main.py`, `pyproject.toml`, `tests/test_ai.py`, `tests/test_webui.py`
- Create: `webui/ai/providers/openai_compatible.py`, `tests/test_ai_provider_openai_compatible.py`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces: `webui.ai.providers.PROVIDERS: dict[str, module]`, `webui.ai.providers.resolve_api_key(provider, request_key) -> str | None`, `webui.ai.providers.Response`/`TextBlock`/`ToolUseBlock` dataclasses, `webui.ai.loop.run_instruction(instruction, provider, api_key, base_url=None, model=None) -> str` (signature change from Task 1 — `provider` is now a required second positional argument, `api_key` becomes `str | None`, `model` becomes `str | None` with per-provider defaulting). `webui.ai.providers.openai_compatible.{make_client, send, resolve_key, DEFAULT_MODEL, DEFAULT_BASE_URL}`.

This task changes `run_instruction`'s signature, so it must also update the one real caller (`webui/main.py`'s route) and every existing test call site in the same task — leaving any of them on the old signature would break the full suite.

- [ ] **Step 1: Verify the `openai` SDK's actual current shape before writing translation code**

Before finalizing Step 4 below, install the SDK (`./.venv/Scripts/python.exe -m pip install "openai>=1.0"` inside this worktree's venv, ahead of adding it to `pyproject.toml` properly in Step 7) and confirm, against the actually-installed version:
- The exact constructor: `openai.OpenAI(api_key=..., base_url=...)`.
- The exact chat-completions call shape: `client.chat.completions.create(model=..., messages=..., tools=..., max_tokens=..., parallel_tool_calls=...)` — in particular, whether `max_tokens` is still accepted directly for standard chat models, or whether the installed version wants `max_completion_tokens` instead (this has been in flux across OpenAI API versions).
- The response shape: `response.choices[0].message.content`, `response.choices[0].message.tool_calls` (each with `.id`, `.function.name`, `.function.arguments` as a JSON string), `response.choices[0].finish_reason`.
- The exception hierarchy: confirm `openai.APIError` (or whatever the real common base class is named) actually covers `AuthenticationError`/`APIConnectionError`/`APIStatusError` the way `anthropic.APIError` did — though per this plan's error-handling approach (broad `except Exception`, not enumerating specific SDK exception classes), this is informational rather than something the code branches on.

If any of these differ from what Step 4's code below assumes, adjust Step 4's code accordingly and note the discrepancy in your report — this mirrors the same verify-before-finalizing step the original AI-layer plan used for `anthropic.APIError`.

- [ ] **Step 2: Write `webui/ai/providers/__init__.py`'s registry and shared response types**

Replace the Task-1 placeholder content of `webui/ai/providers/__init__.py` entirely with:

```python
"""Shared provider interface -- the Response/TextBlock/ToolUseBlock shape
every provider's send() returns, and the PROVIDERS registry every provider
module registers into. See the design spec's "Provider interface" section.

Each providers/<name>.py module exposes:
  - DEFAULT_MODEL: str | None (None means "no default, model is required")
  - DEFAULT_BASE_URL: str | None (None means "no default, required" or "let
    the SDK use its own built-in default" -- see that provider's own
    comment for which)
  - resolve_key(request_key: str | None) -> str | None
  - make_client(api_key, base_url) -> opaque client object
  - send(client, system, tools, messages, model, max_tokens) -> Response
"""
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class Response:
    content: list
    stop_reason: str


# These class definitions MUST come before this import, not after: both
# submodules below do `from webui.ai.providers import Response, TextBlock,
# ToolUseBlock` -- since Python registers this package's module object in
# sys.modules before executing this file's body, that import succeeds only
# if TextBlock/ToolUseBlock/Response already exist as attributes on this
# (still-executing) module by the time the submodule import below runs.
# Reordering this would reintroduce a circular ImportError.
from webui.ai.providers import anthropic, openai_compatible  # noqa: E402


PROVIDERS = {
    "anthropic": anthropic,
    "openai_compatible": openai_compatible,
}


def resolve_api_key(provider: str, request_key: str | None) -> str | None:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} -- must be one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider].resolve_key(request_key)
```

- [ ] **Step 3: Rewrite `webui/ai/providers/anthropic.py`'s key-resolution function name and add default constants**

In `webui/ai/providers/anthropic.py`: rename `resolve_api_key` to `resolve_key` (same body, same behavior — just the name, to match the shared interface every provider module now follows). `DEFAULT_MODEL`/`DEFAULT_BASE_URL` already exist from Task 1 (`"claude-opus-5"` and `None`) — no change needed to those two lines.

- [ ] **Step 4: Create `webui/ai/providers/openai_compatible.py`**

```python
"""The generic OpenAI-compatible provider adapter -- covers any server that
speaks OpenAI's chat-completions + tool-calling wire format at some
base_url: Ollama's own OpenAI-compat shim, LM Studio, llama.cpp server,
vLLM, and real OpenAI-compatible clouds. See the design spec's "Provider
specifics" section.

The `openai` SDK import is soft, same pattern as providers/anthropic.py.
"""
import json
import os

try:
    import openai
except ImportError:
    openai = None

from webui.ai.providers import Response, TextBlock, ToolUseBlock

DEFAULT_MODEL = None  # no sensible default -- local/generic model names vary too widely to guess
DEFAULT_BASE_URL = None  # no sensible default -- there's no one "the" OpenAI-compatible server


def resolve_key(request_key: str | None) -> str | None:
    """Unlike Anthropic, a missing key is not an error here -- many servers
    behind this wire format don't check auth at all. Falls back to
    OPENAI_API_KEY if set, otherwise returns None -- make_client() below
    substitutes a placeholder, since the SDK's constructor still wants a
    non-empty string even when the server will ignore it.
    """
    if request_key:
        return request_key
    return os.environ.get("OPENAI_API_KEY")


def _translate_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
                "strict": t.get("strict", False),
            },
        }
        for t in tools
    ]


def _translate_messages(messages: list[dict]) -> list[dict]:
    """Flatten our canonical Anthropic-shaped message history into OpenAI's
    flat messages format. Called fresh on every send() -- the canonical
    history keeps growing across rounds, and this API is stateless per-call
    like Anthropic's, so translation isn't incremental.
    """
    openai_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            # Assistant content is a list of canonical Response blocks
            # (TextBlock/ToolUseBlock instances, or the real anthropic.Message
            # content if this history started life via the anthropic
            # provider -- both expose the same .type/.text/.id/.name/.input
            # attributes) -- attribute access, not dict access.
            text = "".join(b.text for b in content if b.type == "text") or None
            tool_calls = [
                {
                    "id": b.id,
                    "type": "function",
                    "function": {"name": b.name, "arguments": json.dumps(b.input)},
                }
                for b in content
                if b.type == "tool_use"
            ]
            entry = {"role": "assistant", "content": text}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            openai_messages.append(entry)
            continue
        # role == "user" with block content: tool_result blocks plus a
        # trailing text block with the refreshed block list, appended by
        # loop.py -- these are plain dicts (loop.py's own construction),
        # not objects, so dict access here.
        for block in content:
            if block["type"] == "tool_result":
                prefix = "ERROR: " if block["is_error"] else ""
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": prefix + block["content"],
                    }
                )
            elif block["type"] == "text":
                openai_messages.append({"role": "user", "content": block["text"]})
    return openai_messages


def _translate_response(completion) -> Response:
    choice = completion.choices[0]
    message = choice.message
    content = []
    if message.content:
        content.append(TextBlock(text=message.content))
    for tool_call in message.tool_calls or []:
        content.append(
            ToolUseBlock(
                id=tool_call.id,
                name=tool_call.function.name,
                input=json.loads(tool_call.function.arguments),
            )
        )
    stop_reason = {"tool_calls": "tool_use", "stop": "end_turn"}.get(
        choice.finish_reason, choice.finish_reason
    )
    return Response(content=content, stop_reason=stop_reason)


def make_client(api_key, base_url):
    if openai is None:
        raise ValueError(
            "the AI instruction layer's OpenAI-compatible provider needs the ai "
            "extras group -- pip install -e '.[ai]'"
        )
    if not base_url:
        raise ValueError("base_url is required for the openai_compatible provider")
    try:
        return openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url)
    except Exception as exc:
        raise ValueError(f"OpenAI-compatible provider error: {exc}") from exc


def send(client, system, tools, messages, model, max_tokens):
    try:
        completion = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + _translate_messages(messages),
            tools=_translate_tools(tools),
            parallel_tool_calls=False,
        )
        return _translate_response(completion)
    except Exception as exc:
        raise ValueError(f"OpenAI-compatible provider error: {exc}") from exc
```

Adjust this code to match whatever Step 1's verification actually found, if it differs.

- [ ] **Step 5: Update `webui/ai/loop.py` to be fully provider-agnostic**

Replace the whole file:

```python
"""The tool-calling loop: run_instruction() is the only thing webui/main.py
calls into this package. Fully provider-agnostic -- it looks up the given
provider name in providers.PROVIDERS and calls that module's
make_client()/send(), never touching any provider-specific detail itself.
"""
import json

from webui import session
from webui.ai.providers import PROVIDERS
from webui.ai.tools import SYSTEM_PROMPT, TOOLS, _execute_tool

MAX_TOOL_ROUNDS = 10
DEFAULT_MAX_TOKENS = 16000


def run_instruction(
    instruction: str,
    provider: str,
    api_key: str | None,
    base_url: str | None = None,
    model: str | None = None,
) -> str:
    """Run the tool-calling loop for one instruction against the current
    session document, against the given provider. Returns the final summary
    text. Raises ValueError for an empty instruction, an unknown provider
    name, a missing extras install for the chosen provider, a missing
    required model/base_url, no document loaded, or any failure from that
    provider's SDK/network -- every error path out of this function is a
    clean ValueError, for the route handler in webui/main.py to map straight
    to a 400.
    """
    if not instruction.strip():
        raise ValueError("instruction must be non-empty")

    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} -- must be one of {sorted(PROVIDERS)}")
    provider_module = PROVIDERS[provider]

    if model is None:
        model = provider_module.DEFAULT_MODEL
        if model is None:
            raise ValueError(f"model is required for provider {provider!r}")

    if base_url is None:
        base_url = provider_module.DEFAULT_BASE_URL

    # Fail fast, before any API call is made, if nothing is loaded -- without
    # this, get_blocks_summary() below silently returns [] and we'd burn a
    # real API call before get_pages_summary() (only reached at the very end)
    # ever gets a chance to raise this same LookupError.
    session.get_handle()

    block_list = json.dumps(session.get_blocks_summary())
    messages = [
        {
            "role": "user",
            "content": f"Current blocks in the document:\n{block_list}\n\nInstruction: {instruction}",
        }
    ]

    client = provider_module.make_client(api_key, base_url)

    for _ in range(MAX_TOOL_ROUNDS):
        response = provider_module.send(client, SYSTEM_PROMPT, TOOLS, messages, model, DEFAULT_MAX_TOKENS)

        if response.stop_reason == "tool_use":
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
            tool_results.append(
                {
                    "type": "text",
                    "text": (
                        "Current blocks in the document (ids may have changed after "
                        f"the edit(s) above):\n{json.dumps(session.get_blocks_summary())}"
                    ),
                }
            )
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "end_turn":
            return "".join(block.text for block in response.content if block.type == "text")

        return (
            f"the model stopped early ({response.stop_reason}) before finishing -- "
            "try a simpler or more specific instruction"
        )

    return (
        "reached the step limit before finishing -- the instruction may be "
        "incompletely handled; check the block list below for what actually changed"
    )
```

- [ ] **Step 6: Update `webui/ai/__init__.py` to re-export the new dispatcher**

```python
"""Public surface of the AI instruction layer -- resolve_api_key() and
run_instruction() are what webui/main.py calls. See loop.py, tools.py, and
providers/ for the implementation.
"""
from webui.ai.loop import run_instruction
from webui.ai.providers import resolve_api_key

__all__ = ["run_instruction", "resolve_api_key"]
```

- [ ] **Step 7: Add `openai` to `pyproject.toml`'s `ai` extras group**

```toml
ai = [
    "anthropic>=1.0",
    "openai>=1.0",
]
```

Reinstall: `./.venv/Scripts/python.exe -m pip install -e ".[test,webui,ai]"`.

- [ ] **Step 8: Update `webui/main.py`'s request model and route**

Change:

```python
class AIInstructRequest(BaseModel):
    instruction: str
    api_key: str | None = None
    base_url: str | None = None
    model: str = "claude-opus-5"


@app.post("/api/ai-instruct")
def ai_instruct(body: AIInstructRequest) -> dict:
    # Plain `def`, not `async def`: FastAPI runs sync route handlers in a
    # threadpool automatically, which keeps this (synchronous, blocking)
    # Anthropic API call from blocking the whole event loop during a request.
    resolved_key = ai.resolve_api_key(body.api_key)
    summary = ai.run_instruction(body.instruction, resolved_key, body.base_url, body.model)
    return {
        "summary": summary,
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
    }
```

to:

```python
class AIInstructRequest(BaseModel):
    instruction: str
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/api/ai-instruct")
def ai_instruct(body: AIInstructRequest) -> dict:
    # Plain `def`, not `async def`: FastAPI runs sync route handlers in a
    # threadpool automatically, which keeps this (synchronous, blocking) AI
    # provider call from blocking the whole event loop during a request.
    resolved_key = ai.resolve_api_key(body.provider, body.api_key)
    summary = ai.run_instruction(body.instruction, body.provider, resolved_key, body.base_url, body.model)
    return {
        "summary": summary,
        "pages": session.get_pages_summary(),
        "blocks": session.get_blocks_summary(),
    }
```

`provider` has no default (unlike `model`/`base_url`/`api_key`) — a request that omits it gets Pydantic's own clean 422 validation error, forcing an explicit choice rather than silently landing on Anthropic.

- [ ] **Step 9: Update `tests/test_ai.py`'s `run_instruction`/`resolve_api_key` call sites for the new signature**

Every `run_instruction("...", api_key="fake-key", ...)` call becomes
`run_instruction("...", provider="anthropic", api_key="fake-key", ...)`.
Every `resolve_api_key("request-key")`/`resolve_api_key(None)`/`resolve_api_key("")`
call becomes `resolve_api_key("anthropic", "request-key")` /
`resolve_api_key("anthropic", None)` / `resolve_api_key("anthropic", "")`.
The import line `from webui.ai import resolve_api_key, run_instruction`
(added in Task 1) stays the same — only call sites change. No other
change to any test's assertions or docstrings.

- [ ] **Step 10: Update `tests/test_webui.py`'s ai-instruct request bodies**

Every JSON body posted to `/api/ai-instruct` in this file's `test_ai_instruct_*`
tests gains `"provider": "anthropic"` alongside its existing fields (e.g.
`{"instruction": "redact the secret code", "provider": "anthropic", "api_key": "fake-key"}`).
No other change to those tests.

- [ ] **Step 11: Write `tests/test_ai_provider_openai_compatible.py`**

```python
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
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all tests pass (the existing 93 with updated signatures, plus the new ones in `tests/test_ai_provider_openai_compatible.py`). Note the exact new count in your report.

- [ ] **Step 13: Commit**

```bash
git add webui/ai/ webui/main.py pyproject.toml tests/test_ai.py tests/test_webui.py tests/test_ai_provider_openai_compatible.py
git commit -m "feat: add a generic OpenAI-compatible AI provider and provider dispatch"
```

---

## Task 3: Ollama provider

**Files:**
- Modify: `webui/ai/providers/__init__.py`, `pyproject.toml`
- Create: `webui/ai/providers/ollama.py`, `tests/test_ai_provider_ollama.py`

**Interfaces:**
- Consumes: `webui.ai.providers.{Response, TextBlock, ToolUseBlock}`, the `PROVIDERS` registry (Task 2).
- Produces: `webui.ai.providers.ollama.{make_client, send, resolve_key, DEFAULT_MODEL, DEFAULT_BASE_URL}`; registers `"ollama"` into `PROVIDERS`.

- [ ] **Step 1: Verify the `ollama` package's actual current shape before writing translation code**

Install it first (`./.venv/Scripts/python.exe -m pip install "ollama>=0.3"` inside this worktree's venv, ahead of Step 4's proper `pyproject.toml` addition) and confirm against the installed version:
- The client constructor: `ollama.Client(host=base_url)`.
- The chat call shape: `client.chat(model=..., messages=..., tools=...)` — confirm the parameter name for `tools` is actually `tools` and that it accepts the same `{"type": "function", "function": {...}}` shape used for OpenAI (Ollama has adopted this convention, but confirm against the installed version's behavior/type stubs rather than assuming).
- **The response shape** — this is the part flagged as genuinely uncertain in the design spec: is the return value a dict (`response["message"]["content"]`, `response["message"].get("tool_calls")`) or a typed object (`response.message.content`, `response.message.tool_calls`)? Does each tool_call in the response carry any kind of `id`/correlation field, or none at all? Does the SDK or the API expose any "disable parallel tool calls" control, or is that purely a property of which local model is running (in which case there is nothing to set, and the loop's `disable_parallel_tool_use`-equivalent step from Task 2's Anthropic/OpenAI providers has no Ollama counterpart)?
- **How to bound output length.** Ollama's chat API doesn't take a direct `max_tokens` kwarg the way Anthropic/OpenAI do — generation limits go through an `options` dict, commonly `options={"num_predict": ...}`. Confirm the actual current parameter name and pass `max_tokens` through that way in Step 2's `send()`, rather than silently accepting the parameter and never using it (which is what the code below does as written — a placeholder for you to fix, not the intended final behavior).

Write Step 2's code to match what you actually find. If Ollama's tool_calls carry no id, keep the synthesized-id approach shown below (never sent back over the wire, used only for our own internal bookkeeping matching tool_results to the tool_use blocks that spawned them). If your installed version's response is dict-shaped rather than attribute-shaped (or vice versa), adjust the translation code's access style accordingly. Note what you found in your report.

- [ ] **Step 2: Create `webui/ai/providers/ollama.py`**

```python
"""The native Ollama provider adapter -- /api/chat, not the OpenAI-compat
shim (per the design spec's explicit choice to build both a generic
OpenAI-compatible adapter and a native Ollama one). Ollama has no auth
concept for a local instance, so resolve_key() ignores its input entirely.

The `ollama` SDK import is soft, same pattern as the other two providers.
"""
try:
    import ollama
except ImportError:
    ollama = None

from webui.ai.providers import Response, TextBlock, ToolUseBlock

DEFAULT_MODEL = None  # no sensible default -- depends what's been `ollama pull`ed locally
DEFAULT_BASE_URL = "http://localhost:11434"  # Ollama's default port, native API (not the /v1 shim)


def resolve_key(request_key: str | None) -> str | None:
    """Ollama has no auth concept for a local instance -- the key field is
    accepted (for symmetry with the other providers' request shape) but
    never actually used.
    """
    return request_key


def _translate_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _translate_messages(messages: list[dict]) -> list[dict]:
    """Flatten our canonical Anthropic-shaped message history into Ollama's
    flat messages format -- mirrors providers/openai_compatible.py's
    translation, adjusted for whatever Step 1's verification found. Called
    fresh on every send(), same reasoning as the OpenAI-compatible provider.
    """
    ollama_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            ollama_messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(b.text for b in content if b.type == "text") or None
            tool_calls = [
                {"function": {"name": b.name, "arguments": b.input}}
                for b in content
                if b.type == "tool_use"
            ]
            entry = {"role": "assistant", "content": text}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            ollama_messages.append(entry)
            continue
        for block in content:
            if block["type"] == "tool_result":
                prefix = "ERROR: " if block["is_error"] else ""
                ollama_messages.append({"role": "tool", "content": prefix + block["content"]})
            elif block["type"] == "text":
                ollama_messages.append({"role": "user", "content": block["text"]})
    return ollama_messages


def _translate_response(raw: dict) -> Response:
    message = raw["message"]
    content = []
    if message.get("content"):
        content.append(TextBlock(text=message["content"]))
    tool_calls = message.get("tool_calls") or []
    for i, tool_call in enumerate(tool_calls):
        # Ollama's native tool_calls may not carry a correlatable id the way
        # OpenAI/Anthropic do -- synthesize one for our own internal
        # bookkeeping (matching tool_results back to the call that spawned
        # them within our own message history). Never sent back over the
        # wire -- see _translate_messages above, which doesn't echo any id
        # back in the "tool" role message. Adjust if Step 1 found otherwise.
        content.append(
            ToolUseBlock(
                id=f"ollama_call_{i}",
                name=tool_call["function"]["name"],
                input=tool_call["function"]["arguments"],
            )
        )
    stop_reason = "tool_use" if tool_calls else "end_turn"
    return Response(content=content, stop_reason=stop_reason)


def make_client(api_key, base_url):
    if ollama is None:
        raise ValueError(
            "the AI instruction layer's Ollama provider needs the ai extras group -- "
            "pip install -e '.[ai]'"
        )
    try:
        return ollama.Client(host=base_url)
    except Exception as exc:
        raise ValueError(f"Ollama provider error: {exc}") from exc


def send(client, system, tools, messages, model, max_tokens):
    try:
        raw = client.chat(
            model=model,
            messages=[{"role": "system", "content": system}] + _translate_messages(messages),
            tools=_translate_tools(tools),
            # Ollama takes generation-length limits through `options`, not a
            # direct max_tokens kwarg -- `num_predict` is the commonly
            # documented key for this as of recent versions. Confirm this
            # against Step 1's findings and correct the key name if it's
            # changed.
            options={"num_predict": max_tokens},
        )
        return _translate_response(raw)
    except Exception as exc:
        raise ValueError(f"Ollama provider error: {exc}") from exc
```

Adjust this code to match whatever Step 1's verification actually found, if it differs from what's shown here — note any adjustment in your report.

- [ ] **Step 3: Register `ollama` in the `PROVIDERS` registry**

In `webui/ai/providers/__init__.py`, change:

```python
from webui.ai.providers import anthropic, openai_compatible
```

to:

```python
from webui.ai.providers import anthropic, ollama, openai_compatible
```

and:

```python
PROVIDERS = {
    "anthropic": anthropic,
    "openai_compatible": openai_compatible,
}
```

to:

```python
PROVIDERS = {
    "anthropic": anthropic,
    "openai_compatible": openai_compatible,
    "ollama": ollama,
}
```

- [ ] **Step 4: Add `ollama` to `pyproject.toml`'s `ai` extras group**

```toml
ai = [
    "anthropic>=1.0",
    "openai>=1.0",
    "ollama>=0.3",
]
```

Reinstall: `./.venv/Scripts/python.exe -m pip install -e ".[test,webui,ai]"`.

- [ ] **Step 5: Write `tests/test_ai_provider_ollama.py`**

Mirror the structure of `tests/test_ai_provider_openai_compatible.py` from
Task 2, adapted for Ollama's actual verified response shape from Step 1.
At minimum:

```python
"""Tests for webui/ai/providers/ollama.py's translation layer and the
run_instruction() loop driven through it. Mocked -- no real network call.
"""
from pathlib import Path
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


def test_resolve_key_passes_through_unused():
    assert ollama.resolve_key("anything") == "anything"
    assert ollama.resolve_key(None) is None


def test_translate_response_maps_a_tool_call():
    raw = {
        "message": {
            "content": None,
            "tool_calls": [{"function": {"name": "redact_block", "arguments": {"block_id": 3}}}],
        }
    }

    response = ollama._translate_response(raw)

    assert response.stop_reason == "tool_use"
    assert response.content[0].name == "redact_block"
    assert response.content[0].input == {"block_id": 3}


def test_translate_response_maps_plain_text():
    raw = {"message": {"content": "all done", "tool_calls": []}}

    response = ollama._translate_response(raw)

    assert response.stop_reason == "end_turn"
    assert response.content[0].text == "all done"


def test_run_instruction_executes_a_tool_call_via_ollama():
    _load_simple_text_fixture()
    block_id = next(b["id"] for b in session.get_blocks_summary() if "REDACT-ME-12345" in b["text"])

    tool_call_response = {
        "message": {
            "content": None,
            "tool_calls": [{"function": {"name": "redact_block", "arguments": {"block_id": block_id}}}],
        }
    }
    final_response = {"message": {"content": "Redacted the secret code.", "tool_calls": []}}

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
```

Adjust the mocked `raw`/response shapes here to match Step 1's actual findings if they differ from the dict shape assumed above.

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: all tests pass, including the new Ollama provider tests. Note the exact count.

- [ ] **Step 7: Commit**

```bash
git add webui/ai/providers/ pyproject.toml tests/test_ai_provider_ollama.py
git commit -m "feat: add a native Ollama AI provider"
```

---

## Task 4: Frontend provider selector and README

**Files:**
- Modify: `webui/static/index.html`, `webui/static/app.js`, `README.md`

**Interfaces:**
- Consumes: `POST /api/ai-instruct`'s new `provider` field (Task 2).

- [ ] **Step 1: Add the provider selector to `webui/static/index.html`**

Replace:

```html
  <div>
    <input type="password" id="api-key-input" autocomplete="off" placeholder="Anthropic API key (or leave blank to use the server's ANTHROPIC_API_KEY)" style="width: 24rem;">
  </div>
  <details>
    <summary>Advanced</summary>
    <input type="text" id="base-url-input" placeholder="Custom base URL (optional)">
    <input type="text" id="model-input" placeholder="Model (default: claude-opus-5)">
  </details>
```

with:

```html
  <div>
    <label for="provider-select">Provider:</label>
    <select id="provider-select">
      <option value="anthropic">Anthropic</option>
      <option value="openai_compatible">OpenAI-compatible (Ollama's own shim, LM Studio, vLLM, real OpenAI, ...)</option>
      <option value="ollama">Ollama (native)</option>
    </select>
  </div>
  <div>
    <input type="password" id="api-key-input" autocomplete="off" placeholder="API key (or leave blank to use the server's env var)" style="width: 24rem;">
  </div>
  <details>
    <summary>Advanced</summary>
    <input type="text" id="base-url-input" placeholder="Base URL">
    <input type="text" id="model-input" placeholder="Model">
  </details>
```

- [ ] **Step 2: Wire provider-change field defaults into `webui/static/app.js`**

Add, right after the existing `document.getElementById("download-button").onclick = ...` block and before the `ai-instruct-button` handler:

```javascript
const PROVIDER_DEFAULTS = {
  anthropic: { baseUrlPlaceholder: "Custom base URL (optional)", modelPlaceholder: "Model (default: claude-opus-5)", apiKeyPlaceholder: "Anthropic API key (or leave blank to use the server's ANTHROPIC_API_KEY)" },
  openai_compatible: { baseUrlPlaceholder: "Base URL (required)", modelPlaceholder: "Model (required)", apiKeyPlaceholder: "API key (optional for servers with no auth)" },
  ollama: { baseUrlPlaceholder: "Base URL (default: http://localhost:11434)", modelPlaceholder: "Model (required -- must already be pulled locally)", apiKeyPlaceholder: "Not used by Ollama" },
};

function applyProviderDefaults() {
  const provider = document.getElementById("provider-select").value;
  const defaults = PROVIDER_DEFAULTS[provider];
  document.getElementById("base-url-input").placeholder = defaults.baseUrlPlaceholder;
  document.getElementById("model-input").placeholder = defaults.modelPlaceholder;
  document.getElementById("api-key-input").placeholder = defaults.apiKeyPlaceholder;
}

document.getElementById("provider-select").onchange = applyProviderDefaults;
// Run once immediately, too -- onchange alone never fires for the
// dropdown's own default (first) option on initial page load, which would
// otherwise leave the generic HTML placeholders showing until the user
// actively changes the selection.
applyProviderDefaults();
```

- [ ] **Step 3: Include `provider` in the request body**

In the existing `ai-instruct-button` click handler in `webui/static/app.js`, change:

```javascript
  const body = { instruction };
  if (apiKey) body.api_key = apiKey;
  if (baseUrl) body.base_url = baseUrl;
  if (model) body.model = model;
```

to:

```javascript
  const body = { instruction, provider: document.getElementById("provider-select").value };
  if (apiKey) body.api_key = apiKey;
  if (baseUrl) body.base_url = baseUrl;
  if (model) body.model = model;
```

- [ ] **Step 4: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: unchanged pass count from Task 3 — this task adds no new automated tests.

- [ ] **Step 5: Update the README**

In the existing "## AI instruction layer" section, replace the BYOK
paragraph (currently describing only Anthropic) with a paragraph covering
all three providers: Anthropic (BYOK, `ANTHROPIC_API_KEY` fallback),
OpenAI-compatible (any `base_url`, e.g. Ollama's own OpenAI-compat shim, LM
Studio, vLLM, or real OpenAI/other clouds — key optional, `OPENAI_API_KEY`
fallback), and Ollama (native, `http://localhost:11434` default, no key
needed). Note that `model`/`base_url` are required for the non-Anthropic
providers. Keep the existing "Requires the optional `ai` extras group"
paragraph and install command as-is (it already installs all three SDKs
together).

- [ ] **Step 6: Commit**

```bash
git add webui/static/index.html webui/static/app.js README.md
git commit -m "feat: add a provider selector to the AI instruction frontend"
```

---

## Task 5: Real end-to-end verification

**Files:** none (verification only, no code changes expected unless verification surfaces a real bug).

- [ ] **Step 1: Run the full automated suite**

Run: `./.venv/Scripts/python.exe -m pytest -v`
Expected: 100% passing, pristine output.

- [ ] **Step 2: Check for a reachable local Ollama server**

`curl -s -o /dev/null -w "%{http_code}" http://localhost:11434` (or
equivalent). If it responds, list available models (`curl -s
http://localhost:11434/api/tags`) and pick one that's actually pulled.

**If a local Ollama server is reachable:** run the webui server
(`./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8000`),
upload `tests/fixtures/mixed.pdf`, POST to `/api/ai-instruct` with
`provider: "ollama"`, the model you found, and an instruction that clearly
targets one of the fixture's known blocks. Confirm: a 200 response, a
sensible summary, and the target block actually gone from
`/api/state` afterward. This is a genuine real round-trip — no billing
concern since Ollama is local and free, unlike the Anthropic verification
in the original AI-layer plan.

**If no local Ollama server is reachable:** say so honestly in your report,
and instead verify the clean-error path: POST to `/api/ai-instruct` with
`provider: "ollama"` and a `model` value, and confirm the connection
failure surfaces as a clean 400 (not a 500/stack trace) — this at least
proves the error-handling path for "server not running" is clean, even
without a real successful round-trip.

- [ ] **Step 3: Opportunistically verify `openai_compatible` if a real key is available**

Check for `OPENAI_API_KEY` in the environment. If set, and if you're
willing to spend the (small) real cost, POST to `/api/ai-instruct` with
`provider: "openai_compatible"`, `base_url: "https://api.openai.com/v1"`,
a real OpenAI model name (e.g. `gpt-4o-mini`), and no `api_key` (letting it
fall back to the environment variable) — confirm a real round-trip works
end-to-end through the OpenAI-compatible translation layer specifically (as
opposed to Ollama, which exercises the same code path but is a different
concrete server). If no key is available, or you'd rather not spend real
money without the user's explicit go-ahead, skip this and say so honestly
— the mocked tests from Task 2 already cover this provider's translation
correctness; this step is a nice-to-have, not required.

- [ ] **Step 4: Verify the `anthropic` provider still works end-to-end**

Same "no real key available" fallback path as the original AI-layer plan's
own final verification: submit a deliberately-fake Anthropic key via
`provider: "anthropic"` and confirm the resulting `AuthenticationError`
still surfaces as a clean 400 (proving Task 1/2's restructuring didn't
regress the one provider that was already fully working before this plan).

- [ ] **Step 5: Report**

Write a short report to
`docs/superpowers/plans/2026-08-29-multi-provider-ai-layer-verification.md`
covering: which of the three providers got a genuine real round-trip versus
only the clean-error-path check, and why (reachability/cost), plus the
final automated-suite pass count. Commit it.

```bash
git add docs/superpowers/plans/2026-08-29-multi-provider-ai-layer-verification.md
git commit -m "docs: multi-provider AI layer real-verification report"
```

---

## Final Verification

After all 5 tasks:

1. Full suite: `./.venv/Scripts/python.exe -m pytest -v` — 100% passing.
2. Confirm `engine/` and `webui/session.py` are completely untouched by this plan: `git diff <plan-start-commit>..HEAD -- engine/ webui/session.py` should be empty.
3. Confirm the base install and `webui`-only install both still work without any provider SDK: in a scratch venv, `pip install -e .` and `pip install -e ".[test,webui]"` should both leave `webui.main` importable (mirrors the check the original AI-layer plan's final review added after Critical #1).
4. Grep for hardcoded provider assumptions that should have become generic: `grep -rn "claude-opus-5" webui/ai/ webui/main.py` (the logic layer only -- `webui/static/app.js`'s `PROVIDER_DEFAULTS` legitimately shows this as a user-facing placeholder hint, that's not a code smell) should show it only as `providers/anthropic.py`'s `DEFAULT_MODEL`, nowhere else.
5. Grep for stored keys: `grep -rn "OPENAI_API_KEY\|ANTHROPIC_API_KEY" --include=*.py .` should show only the two providers' own `resolve_key`/`resolve_api_key` environment reads, never a write to a file or session state.
