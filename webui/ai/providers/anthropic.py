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


def resolve_key(request_key: str | None) -> str:
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
