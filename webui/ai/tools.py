"""Tool schemas the model is given, and the function that actually executes
one tool call against the live session. Provider-agnostic -- every provider
adapter in providers/ uses this same TOOLS/SYSTEM_PROMPT/_execute_tool,
translated into that provider's own wire format at the provider's own
boundary (see providers/__init__.py).
"""
from webui import session

SYSTEM_PROMPT = (
    "You are editing a PDF document through six tools: redact_block (permanently "
    "remove a block's content, leaving a black bar), replace_block (replace a "
    "block's text with new text, preserving layout as much as the engine allows), "
    "delete_block (cleanly remove a block's content with no visible trace, unlike "
    "redact_block), move_block (relocate an existing block's own text, font, and "
    "size to a new position, optionally on a different page -- give exactly one "
    "of target_position or offset, never both), insert_block (draw brand-new text "
    "into an empty region that has no existing block -- requires an explicit font "
    "size, since there is no existing block to infer it from), and "
    "sanitize_document (remove the whole document's identifying metadata, hidden "
    "text, embedded scripts, and stale thumbnails in one action). You will be "
    "given the current list of text blocks in the document and an instruction. "
    "Find the block(s) the instruction refers to and call the appropriate "
    "tool(s). Only touch blocks that are actually relevant to the instruction -- "
    "if nothing in the block list matches what the instruction is asking for, "
    "say so in your final response instead of guessing or acting on an unrelated "
    "block. Block ids are reassigned after every edit -- only the most recently "
    "shown block list is valid, so never reuse an id from earlier in the "
    "conversation."
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
        "name": "delete_block",
        "description": (
            "Cleanly remove a text block's content with no visible trace left behind "
            "(as opposed to redact_block, which leaves a black bar). Use this when the "
            "instruction asks to delete or remove something without any replacement "
            "and without a visible redaction marker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to delete, from the block list you were given.",
                }
            },
            "required": ["block_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "move_block",
        "description": (
            "Relocate an existing text block's own content (unchanged text, font, "
            "and size) to a new position, optionally on a different page. Give "
            "exactly one of target_position or offset a real value -- pass the "
            "other as null, never both non-null."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "integer",
                    "description": "The id of the block to move, from the block list you were given.",
                },
                "destination_page_index": {
                    "type": ["integer", "null"],
                    "description": "Page to move the block to, or null to keep it on its current page.",
                },
                "target_position": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[x, y] -- the new top-left corner, in the destination page's own coordinates, or null. Give this OR offset a real value, never both non-null.",
                },
                "offset": {
                    "type": ["array", "null"],
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[dx, dy] -- shift relative to the block's current position, or null. Give this OR target_position a real value, never both non-null.",
                },
            },
            "required": ["block_id", "destination_page_index", "target_position", "offset"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "insert_block",
        "description": (
            "Draw brand-new text into an empty region of a page -- for adding "
            "content that has no existing block to replace. Requires an explicit "
            "font size; there is no existing block to infer it from."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_index": {"type": "integer", "description": "The page to insert into."},
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "[x0, y0, x1, y1] -- the region to draw the text into.",
                },
                "text": {"type": "string", "description": "The text to insert."},
                "size": {
                    "type": "number",
                    "description": "Font size in points. Choose a size consistent with surrounding text if the instruction implies matching it.",
                },
                "font": {
                    "type": ["string", "null"],
                    "description": "A Base-14 font name (e.g. helvetica, times-roman, courier-bold), or null to default to plain Helvetica.",
                },
            },
            "required": ["page_index", "bbox", "text", "size", "font"],
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
        elif name == "delete_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            session.delete(block_id)
            return f"deleted block {block_id}: {original_text!r} (no visible trace left)", False
        elif name == "move_block":
            block_id = tool_input["block_id"]
            entry = session.get_block(block_id)
            original_text = entry["block"].text
            target_position = tool_input.get("target_position")
            offset = tool_input.get("offset")
            session.move(
                block_id,
                destination_page_index=tool_input.get("destination_page_index"),
                target_position=tuple(target_position) if target_position else None,
                offset=tuple(offset) if offset else None,
            )
            return f"moved block {block_id} ({original_text!r})", False
        elif name == "insert_block":
            session.insert(
                tool_input["page_index"],
                tuple(tool_input["bbox"]),
                tool_input["text"],
                tool_input["size"],
                font=tool_input.get("font"),
            )
            return f"inserted new text {tool_input['text']!r} on page {tool_input['page_index']}", False
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
