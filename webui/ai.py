"""Turns a natural-language instruction into calls against the engine's
redact_region/replace_text operations, via Claude's tool-use API. See the
design spec's "Tools exposed to Claude" and "The instruction loop" sections.

BYOK: the caller supplies its own Anthropic API key per request (falling
back to the ANTHROPIC_API_KEY environment variable if none is supplied). No
key is ever stored in webui/session.py's module-level state -- it lives
only for the duration of one call to run_instruction().

The Anthropic SDK lives in the optional `ai` extras group, NOT the `webui`
group -- a developer installing `pip install -e ".[test,webui]"` alone must
still be able to import and run this whole module (everything except
run_instruction() itself, which needs the SDK to do anything). So the
import below is soft: `anthropic` is None when the extra isn't installed,
and run_instruction() turns that into a clean ValueError instead of an
ImportError at module-import time.
"""
import json
import os

try:
    import anthropic
except ImportError:
    anthropic = None

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
    an empty instruction, a missing `ai` extras install, no document loaded,
    or any failure from the Anthropic SDK/network -- every error path out of
    this function is a clean ValueError, for the route handler in
    webui/main.py to map straight to a 400.
    """
    if not instruction.strip():
        raise ValueError("instruction must be non-empty")

    if anthropic is None:
        raise ValueError(
            "the AI instruction layer needs the ai extras group -- pip install -e '.[ai]'"
        )

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

    try:
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**client_kwargs)
    except Exception as exc:
        # Not just anthropic.APIError -- e.g. a malformed base_url raises
        # httpx's InvalidURL during client construction, which is not an
        # APIError subclass at all. Broad catch mirrors webui/main.py's own
        # upload-handler idiom: an external library can throw various
        # things, they all become a clean ValueError here.
        raise ValueError(f"Anthropic API error: {exc}") from exc

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=messages,
            )
        except Exception as exc:
            raise ValueError(f"Anthropic API error: {exc}") from exc

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
            # monotonic registry rebuild), and the ids Claude was originally
            # given may already be dead. Re-send the current list in the same
            # message as the tool results so the model's next turn always has
            # a valid set of ids to work from, instead of guessing or reusing
            # a stale one from earlier in the conversation.
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
