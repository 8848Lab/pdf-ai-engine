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
