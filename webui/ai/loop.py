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
