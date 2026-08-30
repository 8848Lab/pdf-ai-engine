"""The native Ollama provider adapter -- /api/chat, not the OpenAI-compat
shim (per the design spec's explicit choice to build both a generic
OpenAI-compatible adapter and a native Ollama one). Ollama has no auth
concept for a local instance, so resolve_key() ignores its input entirely.

The `ollama` SDK import is soft, same pattern as the other two providers.

Verified against the installed `ollama` package (0.6.2) before writing this
file, including one live round-trip against a real local Ollama server --
see task-3-report.md for the full transcript. Four things the design spec
flagged as unconfirmed:

  - Response shape: `client.chat(...)` returns a typed `ollama.ChatResponse`
    (a pydantic model), not a plain dict -- attribute access throughout
    (`raw.message.content`, `raw.message.tool_calls`, `tool_call.function
    .name`/`.arguments`), mirroring providers/openai_compatible.py's style
    rather than the brief's dict-access guess. (`ChatResponse` also happens
    to support `[...]` subscripting via a `SubscriptableBaseModel` base
    class, but attribute access is the SDK's own idiomatic style, same as
    the OpenAI/Anthropic SDKs.)
  - Each tool_call carries no id/correlation field at all -- confirmed via
    `ollama._types.Message.ToolCall`'s field list, which is just
    `function: Function`. The synthesized-id approach below is required,
    not optional.
  - There is no "disable parallel tool calls" control anywhere in the SDK --
    `Client.chat()`'s full keyword signature (model, messages, tools,
    stream, think, logprobs, top_logprobs, format, options, keep_alive) has
    no such parameter, unlike Anthropic's `disable_parallel_tool_use` or
    OpenAI's `parallel_tool_calls`. Nothing to set here.
  - Generation-length limit goes through `options={"num_predict": ...}` --
    confirmed both from `ollama._types.Options`'s field list and from a live
    call that honored it.

One more thing worth flagging: `tool_call.function.arguments` arrives
already as a plain `dict`, not a JSON string the way OpenAI's does -- no
`json.loads` needed in _translate_response below.
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
    translation. Called fresh on every send(), same reasoning as the
    OpenAI-compatible provider.
    """
    ollama_messages = []
    # Ollama's own wire shape carries no id/correlation field for tool
    # results (see module docstring), so when a round has more than one
    # tool call the model has no way to tell which result belongs to which
    # call unless we supply the tool's NAME via the SDK's `tool_name` field
    # on the "tool" role message. We look that name up against OUR
    # canonical history's own ids (webui/ai/loop.py always assigns these
    # from ToolUseBlock.id, regardless of which provider produced them) by
    # tracking the immediately-preceding assistant message's tool_use
    # blocks as we iterate.
    pending_tool_names = {}
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            ollama_messages.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(b.text for b in content if b.type == "text") or None
            tool_use_blocks = [b for b in content if b.type == "tool_use"]
            tool_calls = [
                {"function": {"name": b.name, "arguments": b.input}} for b in tool_use_blocks
            ]
            entry = {"role": "assistant", "content": text}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            ollama_messages.append(entry)
            pending_tool_names = {b.id: b.name for b in tool_use_blocks}
            continue
        for block in content:
            if block["type"] == "tool_result":
                prefix = "ERROR: " if block["is_error"] else ""
                tool_name = pending_tool_names.get(block["tool_use_id"])
                ollama_messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": prefix + block["content"],
                    }
                )
            elif block["type"] == "text":
                ollama_messages.append({"role": "user", "content": block["text"]})
    return ollama_messages


def _translate_response(raw) -> Response:
    """`raw` is an `ollama.ChatResponse` -- a typed pydantic object, not a
    dict. See the module docstring for the verification behind this.
    """
    message = raw.message
    content = []
    if message.content:
        content.append(TextBlock(text=message.content))
    tool_calls = message.tool_calls or []
    for i, tool_call in enumerate(tool_calls):
        # Ollama's native tool_calls carry no correlatable id (confirmed --
        # see module docstring) -- synthesize one for our own internal
        # bookkeeping (matching tool_results back to the call that spawned
        # them within our own message history). Never sent back over the
        # wire -- see _translate_messages above, which doesn't echo any id
        # back in the "tool" role message.
        content.append(
            ToolUseBlock(
                id=f"ollama_call_{i}",
                name=tool_call.function.name,
                # Already a plain dict on the wire/SDK -- no json.loads needed
                # here, unlike OpenAI's JSON-string arguments.
                input=tool_call.function.arguments,
            )
        )
    if tool_calls:
        stop_reason = "tool_use"
    else:
        # `raw.done_reason` (confirmed present on the installed SDK's
        # ChatResponse) is Ollama's equivalent of OpenAI's finish_reason --
        # "stop" is the clean-finish value, mirrors
        # providers/openai_compatible.py's finish_reason mapping. Anything
        # else (e.g. "length" from send()'s options={"num_predict": ...}
        # truncating generation) is passed through as-is so loop.py's
        # existing non-tool_use/non-end_turn branch reports the real reason
        # instead of this silently claiming a clean "end_turn".
        stop_reason = "end_turn" if raw.done_reason == "stop" else raw.done_reason
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
            # direct max_tokens kwarg -- `num_predict` confirmed against the
            # installed SDK's ollama._types.Options and via a live call.
            # No parallel-tool-calls control exists in this SDK at all (see
            # module docstring), so there is nothing to set here the way
            # the Anthropic/OpenAI providers set one.
            options={"num_predict": max_tokens},
        )
        return _translate_response(raw)
    except Exception as exc:
        raise ValueError(f"Ollama provider error: {exc}") from exc
