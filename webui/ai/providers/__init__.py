"""Provider adapters for the AI instruction layer. Each providers/<name>.py
module implements a common interface -- make_client(api_key, base_url),
send(client, system, tools, messages, model, max_tokens) -> Response,
resolve_key(request_key) -> str | None, plus DEFAULT_MODEL/DEFAULT_BASE_URL
constants (None means "no default, required"). See the design spec's
"Provider interface" section.

As of this file, only providers/anthropic.py exists -- the PROVIDERS
registry and the generic resolve_api_key() dispatcher are added once a
second provider does, in a later task.
"""
