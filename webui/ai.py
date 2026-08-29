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
