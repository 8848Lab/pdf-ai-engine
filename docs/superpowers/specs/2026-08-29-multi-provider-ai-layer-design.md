# 8848 PDF — Multi-Provider AI Layer — Design

## Overview

Extends the AI instruction layer (shipped last session, Anthropic-only) with
real support for other providers — specifically OpenAI-compatible endpoints
(covers most local LLM servers: Ollama's own OpenAI-compat shim, LM Studio,
llama.cpp server, vLLM, and real cloud OpenAI-compatible services) and a
native Ollama adapter. The previous design explicitly ruled this out as
premature complexity for a single-provider v1; this pass reverses that call
on the user's explicit request, now that the core loop (tool schemas, the
round cap, block-id-refresh handling) is built and has already been through
one real bug-fix cycle.

**Why now, not before:** the multi-provider abstraction only pays for itself
once there's a second real provider to abstract over. Building it up front
last session would have been speculative; building it now means designing
against the loop's actual, already-tested behavior rather than a guess at
what it might need.

## Non-goals (explicit, this pass)

- No provider auto-detection — the caller supplies an explicit `provider`
  field. No guessing from key shape or URL pattern.
- No provider plugin system — the three providers (`anthropic`,
  `openai_compatible`, `ollama`) are fixed, registered in code. A fourth
  provider later is a small, contained follow-up, not something this pass
  builds a general registration mechanism for.
- No streaming responses (unchanged from last pass — the endpoint still
  waits for the whole loop to finish before returning).
- No multi-turn chat memory, no auto-detection/NER layer, no image-block
  instructions, no persistence of keys/history — all unchanged non-goals
  from the original design.
- No attempt to unify the *internal* message representation across all
  three providers into a fully neutral format (Approach B, discussed and
  explicitly deferred — see Architecture). Anthropic's shape stays the
  internal canonical format; the other two providers translate into and out
  of it at their own boundary.
- No engine changes.

## Architecture

**Chosen approach (A, not B):** the loop's internal message history keeps
Anthropic's existing shape (a list of role/content messages, where content
is either a string or a list of blocks with `.type` — `"text"` or
`"tool_use"` — and a `.stop_reason` on each turn's response). This is
already what `webui/ai/loop.py`'s `run_instruction` consumes today, and
it's already been through a real bug-fix cycle (block-id staleness,
parallel-tool-call handling) — reusing it unchanged for the Anthropic path
carries zero regression risk. The other two providers each own a thin
translation layer at their own boundary: canonical messages/tools in, a
canonical-shaped `Response` out. `loop.py` never knows which provider it's
talking to beyond looking up `PROVIDERS[provider].send(...)`.

A fully neutral internal format (Approach B) was considered and explicitly
rejected for this pass — see the brainstorming discussion. It's a cheap
refactor later (confined to `loop.py` + `providers/`, since nothing outside
that boundary — `tools.py`, `session.py`, `main.py`, the frontend — ever
sees the internal message shape) if a future provider doesn't fit the
"pretends to be Anthropic" mold; not worth building speculatively now for
three providers that all fit it reasonably well.

**Package layout:**
```
webui/
  ai/
    __init__.py          # re-exports run_instruction, resolve_api_key, PROVIDERS
    loop.py               # run_instruction() -- provider-agnostic
    tools.py              # TOOLS, SYSTEM_PROMPT, _execute_tool -- unchanged from last pass
    providers/
      __init__.py         # Provider protocol + PROVIDERS registry
      anthropic.py         # today's client.messages.create() call, moved here verbatim
      openai_compatible.py # new
      ollama.py             # new
  session.py              # unchanged
  main.py                 # POST /api/ai-instruct gains a `provider` field
  static/
    index.html / app.js   # provider dropdown + per-provider field defaults
pyproject.toml             # ai extras group grows to include openai + ollama SDKs
```

This restructures the existing `webui/ai.py` (currently one file, ~240
lines including tests' worth of surface) into a package — matches this
project's own established preference for small, single-responsibility
files, and the restructuring itself carries low risk since `ai.py`'s public
surface (`resolve_api_key`, `run_instruction`, `TOOLS`, `_execute_tool`) is
already the seam this split follows.

**Provider interface**, implemented by each `providers/*.py` module:

```python
def send(system: str, tools: list[dict], messages: list[dict], model: str,
          max_tokens: int, api_key: str | None, base_url: str | None) -> Response
```

`Response` has `.content` (list of blocks, each with `.type` in
`{"text", "tool_use"}`; text blocks have `.text`, tool_use blocks have
`.id`/`.name`/`.input`) and `.stop_reason` in `{"tool_use", "end_turn", ...}`
— exactly what `loop.py` already reads today. This is already duck-typed
against `SimpleNamespace` in the existing test suite, so no new "response
class" needs to exist for real; a provider can return anything with those
attributes, including the real `anthropic.Message` object unchanged for the
`anthropic` provider.

`PROVIDERS: dict[str, ProviderModule]` in `providers/__init__.py` maps the
three provider name strings to their modules. `loop.py`'s `run_instruction`
gains one new required parameter, `provider: str`; a name outside the
registry raises `ValueError` with the list of valid names, before any
client is constructed.

## BYOK per provider

- **`anthropic`** (unchanged from last pass): request key → `ANTHROPIC_API_KEY`
  env → clean 400 if neither. Default model `claude-opus-5` if omitted.
- **`openai_compatible`**: request key → `OPENAI_API_KEY` env → a placeholder
  string (`"not-needed"`) if neither is set — a missing key is *not* an
  error for this provider, since many local/self-hosted servers behind this
  wire format don't check auth at all, but the `openai` SDK's client
  constructor still wants a non-empty string. `model` is required — no
  default, since local model names vary too widely to guess. `base_url` is
  required too (there's no universally-correct default for "some
  OpenAI-compatible server" the way there is for Anthropic or Ollama).
- **`ollama`**: the `api_key` field is accepted but unused — Ollama has no
  auth concept for a local instance. `base_url` defaults to
  `http://localhost:11434` (Ollama's default port; note this is the native
  API, not the `/v1` OpenAI-compat shim). `model` is required — no default,
  since it depends on what the operator has `ollama pull`ed locally.

As before: no key of any kind is ever logged, written to disk, or stored in
`webui/session.py`'s module-level state.

## Provider specifics

**`providers/anthropic.py`** — today's `client.messages.create(...)` call
moved here verbatim, including `tool_choice={"type": "auto",
"disable_parallel_tool_use": True}`, the `max_tokens=16000` fix, and the
broad `except Exception → ValueError` wrapping scoped to client
construction + the `create()` calls (both from last session's final-review
fix wave). No behavior change for this provider.

**`providers/openai_compatible.py`** (`openai` SDK, `OpenAI(api_key=...,
base_url=...)`, pointed at any `base_url`) —
- Tools: wrap our existing `TOOLS` schema as
  `{"type": "function", "function": {"name": ..., "description": ...,
  "parameters": <same JSON schema>, "strict": true}}`.
- Messages: flatten from Anthropic's block-list shape into OpenAI's flat
  messages — an assistant turn with tool calls becomes one message with a
  `tool_calls` array; each tool result becomes its own
  `{"role": "tool", "tool_call_id": ..., "content": ...}` message (OpenAI's
  tool-message shape has no error flag, so `is_error` is folded in as an
  `"ERROR: "` content prefix, a documented convention).
- Parallel calls disabled via `parallel_tool_calls: false` on the
  `chat.completions.create(...)` call — the OpenAI equivalent of
  Anthropic's `disable_parallel_tool_use`.
- Response translation: `response.choices[0].message.tool_calls` → our
  tool_use blocks; `.content` → a text block;
  `response.choices[0].finish_reason` maps `"tool_calls"` → `"tool_use"`,
  `"stop"` → `"end_turn"`, anything else passes through as-is (surfaced to
  the loop's existing non-`tool_use`/non-`end_turn` handling from last
  session's fix wave).

**`providers/ollama.py`** (official `ollama` package, `Client(host=...)`,
native `/api/chat` — not the OpenAI-compat shim, per your explicit choice
of "both" adapters) — same tool-schema shape as OpenAI (Ollama deliberately
mirrors it). Message/response translation follows the same shape as the
OpenAI adapter as closely as Ollama's actual API allows.

**Flagged verification risk, stated plainly:** unlike Anthropic (covered by
the `claude-api` skill, with a verified exception hierarchy from last
session), I don't have an equivalent authoritative reference for the
`openai` or `ollama` Python packages' exact current method signatures and
response shapes. In particular: whether Ollama's tool_calls include a
correlatable `id` the way OpenAI/Anthropic do, and whether Ollama exposes
any real "disable parallel tool calls" control versus that being purely a
function of which local model is running. Rather than write code that
quietly guesses, the implementation plan makes verifying these two SDKs'
actual current behavior an explicit task step — the same pattern as last
session's "confirm `anthropic.APIError`'s real hierarchy before finalizing"
step, just against two SDKs instead of one. If Ollama doesn't send call
ids, the adapter synthesizes its own for internal bookkeeping only (matching
tool_results to the tool_use blocks that spawned them within our own
message history) — never sent back out over the wire, since the loop
already needs those ids purely for its own correlation.

## Error handling

Every provider's `send()` wraps its own client-construction-and-call scope
in the same broad `except Exception → ValueError` idiom Anthropic's adapter
already uses (established in last session's final-review fix wave) —
deliberately not trying to enumerate each SDK's precise exception hierarchy
the way Anthropic's was verified, since that confidence doesn't exist yet
for the other two. This is already this codebase's convention for "an
external SDK can throw all sorts of things, they all become a clean 400."

`resolve_api_key` becomes provider-aware (see BYOK section) — its shape
changes from "always returns a string or raises" to "may return `None` for
providers where a key is legitimately optional," and callers (the two new
providers) handle a `None` key themselves (substituting the placeholder for
`openai_compatible`, ignoring it entirely for `ollama`).

A `model` missing for `openai_compatible`/`ollama` is rejected with a clean
400 before any client is constructed — mirrors the existing
empty-instruction/no-document-loaded fail-fast checks.

## API surface

```
POST /api/ai-instruct
  {"instruction": "...", "provider": "anthropic" | "openai_compatible" | "ollama",
   "api_key": "...", "base_url": "...", "model": "..."}
```

`provider` is required, with no default — forces an explicit choice rather
than silently defaulting to Anthropic now that there's more than one
option. Response shape (`{summary, pages, blocks}`) is unchanged.

## Frontend

A provider `<select>` (`anthropic` / `openai_compatible` / `ollama`)
replaces the implicit Anthropic-only assumption from last session, in the
existing collapsed "Advanced" section alongside `base_url`/`model`.
Changing the selection updates: the `base_url` field's placeholder (blank
for `anthropic`, blank for `openai_compatible`, `http://localhost:11434`
for `ollama`), and the API key field's label (plain for `anthropic`,
"optional for local providers" for the other two). Reuses the existing
`render()`/`showError()`/button-disable-while-in-flight logic — no new
rendering path.

## Testing strategy

Same "no real network calls in the automated suite" rule as before,
extended to the new SDKs: `openai.OpenAI` and `ollama.Client` get mocked
the same way `anthropic.Anthropic` already is. Per new provider:
- One round-trip test proving both directions of translation (an assistant
  text-only turn, and a tool-calling turn) produce the correct canonical
  `Response` shape.
- One error-translation test (a mocked SDK exception becomes `ValueError`).
- One required-`model`-validation test (missing model → clean 400, no
  client constructed).

One new `/api/ai-instruct` integration test threads `provider` through
end-to-end for `openai_compatible` (mocked), confirming the field is wired
from the request through to the provider lookup.

**Real end-to-end verification:** unlike Anthropic (which costs real money
per call), Ollama is free and runs locally — the implementation plan's
final task checks whether a local Ollama server is actually reachable
(e.g. `GET http://localhost:11434` responds) and, if so, does a genuine
real round-trip against it with whatever model is available (falling back
to the mocked/fake-key verification path, same as last session's Anthropic
verification, if no local server is running). For `openai_compatible`,
there's no single canonical "real" endpoint to test against generically —
verification there stays at the mocked-plus-fake-key level unless the
operator happens to have `OPENAI_API_KEY` set, in which case the same
real-call-with-a-deliberately-broken-input pattern from last session's
Anthropic verification (proving the error path is clean) applies.

## Explicitly out of scope (this pass)

- Provider auto-detection.
- A general provider-plugin/registration mechanism for providers beyond
  the three built in.
- Streaming.
- Unifying the internal message representation into a fully neutral format
  (Approach B) — deferred until a provider that doesn't fit Anthropic's
  shape actually shows up.
- Any change to `engine/`, `session.py`, or the tool schemas/execution
  layer (`tools.py` is untouched by this pass beyond moving files around).
