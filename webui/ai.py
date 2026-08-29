"""Turns a natural-language instruction into calls against the engine's
redact_region/replace_text operations, via Claude's tool-use API. See the
design spec's "Tools exposed to Claude" and "The instruction loop" sections.

BYOK: the caller supplies its own Anthropic API key per request (falling
back to the ANTHROPIC_API_KEY environment variable if none is supplied). No
key is ever stored in webui/session.py's module-level state -- it lives
only for the duration of one call to run_instruction() (added in a later
task; this file currently has the key resolution and tool layer only).
"""
import json
import os

import anthropic

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
