"""Tool schemas the model is given, and the function that actually executes
one tool call against the live session. Provider-agnostic -- every provider
adapter in providers/ uses this same TOOLS/SYSTEM_PROMPT/_execute_tool,
translated into that provider's own wire format at the provider's own
boundary (see providers/__init__.py).
"""
from webui import session

PAGE_INDEX = {
    "type": "integer",
    "description": "0-based index of the page, from the page list you were given (the first page is 0).",
}

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
    {
        "name": "delete_page",
        "description": (
            "Delete one whole page. Refused for the only page of the document. Every "
            "later page moves up by one index."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"page_index": PAGE_INDEX},
            "required": ["page_index"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "move_page",
        "description": (
            "Move one page so that, AFTER the move, it is at to_index (final-index "
            "semantics; both 0-based). Every other page keeps its relative order. "
            "Example: in a 4-page document, moving page_index 0 to to_index 3 makes it "
            "the last page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_index": PAGE_INDEX,
                "to_index": {
                    "type": "integer",
                    "description": "0-based index the page must end up at.",
                },
            },
            "required": ["page_index", "to_index"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "rotate_page",
        "description": (
            "Set a page's rotation to an ABSOLUTE value: 0, 90, 180 or 270 degrees "
            "clockwise. This replaces the current rotation; it does not add to it. To "
            "turn a page a further 90 degrees, read its current rotation from the page "
            "list and pass current + 90. Use this to fix a sideways or upside-down scan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_index": PAGE_INDEX,
                "rotation": {
                    "type": "integer",
                    "description": "The page's new absolute rotation: 0, 90, 180 or 270.",
                },
            },
            "required": ["page_index", "rotation"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "insert_page",
        "description": (
            "Insert a blank page so that, after the insert, it is at at_index "
            "(0-based; at_index equal to the page count appends at the end). Width and "
            "height default to the displayed size of the page currently at at_index, "
            "or of the last page when appending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "at_index": {
                    "type": "integer",
                    "description": "0-based index the new blank page will have.",
                },
                "width": {
                    "type": ["number", "null"],
                    "description": "Width in points (1 to 14400), or null to match the neighbouring page.",
                },
                "height": {
                    "type": ["number", "null"],
                    "description": "Height in points (1 to 14400), or null to match the neighbouring page.",
                },
            },
            "required": ["at_index", "width", "height"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "duplicate_page",
        "description": (
            "Insert an independent copy of a page immediately after it. Later edits "
            "to either page do not affect the other."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"page_index": PAGE_INDEX},
            "required": ["page_index"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

# M3: derived from len(TOOLS) rather than spelled out, so the prompt can
# never drift out of sync with the actual tool count.
SYSTEM_PROMPT = (
    f"You are editing a PDF document through {len(TOOLS)} tools: redact_block (permanently "
    "remove a block's content, leaving a black bar), replace_block (replace a "
    "block's text with new text, preserving layout as much as the engine allows), "
    "delete_block (cleanly remove a block's content with no visible trace, unlike "
    "redact_block), move_block (relocate an existing block's own text, font, and "
    "size to a new position, optionally on a different page -- give exactly one "
    "of target_position or offset, never both), insert_block (draw brand-new text "
    "into an empty region that has no existing block -- requires an explicit font "
    "size, since there is no existing block to infer it from), "
    "sanitize_document (remove the whole document's identifying metadata, hidden "
    "text, embedded scripts, and stale thumbnails in one action), and five page "
    "tools: delete_page, move_page, rotate_page, insert_page and duplicate_page. "
    "Page indices are 0-BASED everywhere: the first page is index 0, so when the "
    "instruction says 'page 1' it means index 0. You will be given the current "
    "list of text blocks and the current list of pages in the document, and an "
    "instruction. "
    "Find the block(s) or page(s) the instruction refers to and call the "
    "appropriate tool(s). Only touch blocks or pages that are actually relevant "
    "to the instruction -- if nothing in the block or page list matches what the "
    "instruction is asking for, say so in your final response instead of "
    "guessing or acting on an unrelated block or page. Block ids are reassigned "
    "after every edit, and page indices shift after any page is deleted, moved, "
    "inserted or duplicated -- only the most recently shown block and page lists "
    "are valid, so never reuse an id or index from earlier in the conversation."
)


def _execute_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run one tool call against the live session. Returns (result_text,
    is_error) -- is_error becomes the tool_result block's is_error flag, so
    the model sees the same failure a human clicking the UI would see and
    can react to it (retry a different block, explain it in the final
    summary) rather than the loop crashing.
    """
    # M1: a malformed tool call (not a JSON object at all) is a clean tool
    # error, not a 500 -- ollama/other providers are not guaranteed to
    # always hand back a dict.
    if not isinstance(tool_input, dict):
        return "tool input must be a JSON object", True
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
        elif name == "delete_page":
            page_index = tool_input["page_index"]
            session.delete_page(page_index)
            return f"deleted the page at index {page_index}", False
        elif name == "move_page":
            page_index, to_index = tool_input["page_index"], tool_input["to_index"]
            session.move_page(page_index, to_index)
            return f"moved the page at index {page_index} to index {to_index}", False
        elif name == "rotate_page":
            page_index = tool_input["page_index"]
            session.rotate_page(page_index, tool_input["rotation"])
            # M2: report what was actually stored, not the raw request --
            # rotate_page normalises (e.g. -450 becomes 270).
            actual_rotation = session.get_pages_summary()[page_index]["rotation"]
            return f"set the page at index {page_index}'s rotation to {actual_rotation}", False
        elif name == "insert_page":
            at_index = tool_input["at_index"]
            session.insert_page(at_index, width=tool_input.get("width"), height=tool_input.get("height"))
            return f"inserted a blank page at index {at_index}", False
        elif name == "duplicate_page":
            page_index = tool_input["page_index"]
            session.duplicate_page(page_index)
            return (
                f"duplicated the page at index {page_index}; the copy is at index "
                f"{page_index + 1}",
                False,
            )
        else:
            return f"unknown tool: {name}", True
    except KeyError as exc:
        # M1: a missing required argument, distinguished from an engine
        # rejection (ValueError/LookupError below) -- KeyError IS a
        # LookupError, so this must be caught first to give a clear message
        # instead of a bare repr of the missing key.
        return f"missing required argument {exc.args[0]!r}", True
    except (ValueError, LookupError) as exc:
        return str(exc), True
