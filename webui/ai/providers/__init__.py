"""Shared provider interface -- the Response/TextBlock/ToolUseBlock shape
every provider's send() returns, and the PROVIDERS registry every provider
module registers into. See the design spec's "Provider interface" section.

Each providers/<name>.py module exposes:
  - DEFAULT_MODEL: str | None (None means "no default, model is required")
  - DEFAULT_BASE_URL: str | None (None means "no default, required" or "let
    the SDK use its own built-in default" -- see that provider's own
    comment for which)
  - resolve_key(request_key: str | None) -> str | None
  - make_client(api_key, base_url) -> opaque client object
  - send(client, system, tools, messages, model, max_tokens) -> Response
"""
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class Response:
    content: list
    stop_reason: str


# These class definitions MUST come before this import, not after: both
# submodules below do `from webui.ai.providers import Response, TextBlock,
# ToolUseBlock` -- since Python registers this package's module object in
# sys.modules before executing this file's body, that import succeeds only
# if TextBlock/ToolUseBlock/Response already exist as attributes on this
# (still-executing) module by the time the submodule import below runs.
# Reordering this would reintroduce a circular ImportError.
from webui.ai.providers import anthropic, ollama, openai_compatible  # noqa: E402


PROVIDERS = {
    "anthropic": anthropic,
    "openai_compatible": openai_compatible,
    "ollama": ollama,
}


def resolve_api_key(provider: str, request_key: str | None) -> str | None:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} -- must be one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider].resolve_key(request_key)
