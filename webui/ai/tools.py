"""Tool schemas the model is given, and the function that actually executes
one tool call against the live session. Provider-agnostic -- every provider
adapter in providers/ uses this same TOOLS/SYSTEM_PROMPT/_execute_tool,
translated into that provider's own wire format at the provider's own
boundary (see providers/__init__.py).
"""
from webui import session

SYSTEM_PROMPT = (
    "You are editing a PDF document through three tools: redact_block (permanently "
    "remove a block's content), replace_block (replace a block's text with new "
    "text, preserving layout as much as the engine allows), and sanitize_document "
    "(remove the whole document's identifying metadata, hidden text, embedded scripts, "
    "and stale thumbnails in one action). You will be given the "
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
    {
        "name": "sanitize_document",
        "description": (
            "Remove identifying metadata (author, creation tool, dates), the separate XMP "
            "metadata stream, hidden or invisible text, embedded JavaScript, and stale page "
            "thumbnails from the whole document. Use this when the instruction asks to strip "
            "metadata, remove identifying information, sanitize, or clean the document as a "
            "whole -- not for redacting a specific block of visible text, which is a "
            "different tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
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
        elif name == "sanitize_document":
            result = session.sanitize_document()
            removed_fields = result["metadata_fields_removed"]
            if not removed_fields and not result["xmp_removed"]:
                return "sanitized the document: no metadata or XMP stream was present to remove", False
            parts = []
            if removed_fields:
                parts.append(f"{len(removed_fields)} metadata field(s) ({', '.join(removed_fields)})")
            if result["xmp_removed"]:
                parts.append("the XMP metadata stream")
            return f"sanitized the document: removed {' and '.join(parts)}", False
        else:
            return f"unknown tool: {name}", True
    except (ValueError, LookupError) as exc:
        return str(exc), True
