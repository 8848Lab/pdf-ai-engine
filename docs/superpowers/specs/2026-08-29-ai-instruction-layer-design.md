# 8848 PDF — AI Instruction Layer — Design

## Overview

The first slice of the AI/tool-calling layer the project's "Cursor for
documents" direction has been sized toward since the v0.1/v0.2 engine and
the manual-verification web UI shipped. Gives Claude the engine's existing
operations (`redact_region`/`replace_text`, already wrapped by
`webui/session.py`'s `redact`/`replace`) as tools, so a natural-language
instruction ("redact the patient's name", "fix the typo in the second
paragraph") turns into the right calls against whatever PDF is loaded in
the manual-verification tool's session — the same session, same block
registry, same page rendering already built.

**Why bolt this onto the existing manual-verification tool rather than
build new plumbing:** `webui/session.py` already holds exactly the state
an agent needs (a live document handle, a stable block registry) and
`webui/main.py` already has the upload/page-image/export/reset machinery
around it. The AI layer needs one new capability — turn an instruction into
tool calls — not a new document-handling stack.

**Why BYOK, not a server-side key:** this is a local, single-operator tool
(established for the whole `webui/` package already) — there is no
"server" with its own budget to protect, only the person running it on
their own machine. Baking in a shared key would be the wrong model for
something that runs on `localhost` for one person at a time.

## Non-goals (explicit, this pass)

- No multi-turn chat memory across instructions — each instruction is a
  fresh loop with the current block list as its only context. A user who
  wants to chain edits sends a new instruction after seeing the result of
  the last one (the existing UI's re-render already shows this).
- No auto-detection layer (PII/NER pattern-matching) — Claude reads the
  block list itself and decides what matches the instruction using its own
  language understanding, not a separate detection pass. If that proves
  insufficient for some class of instruction, a real detection layer is a
  later, separate slice.
- No real multi-provider abstraction. BYOK covers "your own Anthropic key"
  and an optional `base_url` override (a proxy/gateway in front of the
  Anthropic API) — not a pluggable-backend system supporting non-Anthropic
  SDKs. This project's own tooling (the `claude-api` skill) is
  Anthropic-specific, and building real provider abstraction for a
  single-operator local tool is exactly the premature complexity this
  project's specs have consistently ruled out elsewhere.
- No image-block instructions (redacting/replacing an `Image`) — text
  operations only, matching the manual-verification tool's own existing
  scope.
- No persistence of API keys, conversation history, or instruction logs
  anywhere — keys live in the browser only for the tab's lifetime, nothing
  is written to disk server-side.
- No new engine capability, no engine file changes.

## Architecture

**Language/stack:** Python, the `anthropic` SDK (`pip install anthropic`),
model `claude-opus-5` by default (overridable per-request). A manual
tool-calling loop, not the SDK's beta Tool Runner — this is a single
bounded server-side call per instruction (build context, loop until Claude
stops calling tools, return), not a long-lived interactive session, so the
Tool Runner's iteration/streaming ergonomics buy nothing here and a manual
loop avoids a beta SDK dependency.

**Package layout:**
```
pdf-ai/
  webui/
    ai.py             # NEW: tool definitions + the manual tool-calling loop
    session.py         # unchanged
    main.py            # + POST /api/ai-instruct
    static/
      index.html         # + instruction box, API key field
      app.js              # + wiring for the new endpoint
  pyproject.toml        # + a new "ai" extras group (anthropic)
```

`anthropic` lives under its own `ai` extras group, separate from `webui`'s
`fastapi`/`uvicorn`/etc. — installing the manual-verification tool's
click-through UI does not require installing the AI layer's dependency,
matching the same "each optional capability gets its own extras group"
pattern `webui` itself already established relative to the base engine
install.

## BYOK — bring your own key

- The frontend has a plain text input for an Anthropic API key. It is held
  in browser memory for the tab's lifetime only (a JS variable, not
  `localStorage` — nothing should survive a page reload silently) and sent
  with every `POST /api/ai-instruct` request.
- If the request doesn't supply a key, the server falls back to
  `ANTHROPIC_API_KEY` from its own environment, if set — so a developer
  running this locally with their own env var configured doesn't have to
  re-paste it into the browser every session. Request-supplied key always
  wins over the environment fallback when both are present.
- If neither is available, the endpoint returns a clean 400
  (`{"error": "no Anthropic API key available -- supply one or set
  ANTHROPIC_API_KEY"}`) before attempting any API call.
- An optional `base_url` field on the request is passed straight to the
  `anthropic.Anthropic(base_url=...)` constructor — covers a
  self-hosted/proxy Anthropic-compatible endpoint without any provider
  abstraction. Omitted means the SDK's own default.
- **The key is never logged, never written to disk, never stored in
  `webui/session.py`'s module-level session state** (which already holds
  the live document — the API key must not become part of that persisted
  state; it exists only for the duration of one request's handler).

## Tools exposed to Claude

Two tools, thin wrappers around the functions `webui/session.py` already
exposes:

**`redact_block`**
```json
{
  "name": "redact_block",
  "description": "Permanently remove the content of one text block from the document. Use this when the instruction asks to delete, remove, black out, or redact something, with no replacement.",
  "input_schema": {
    "type": "object",
    "properties": {
      "block_id": {"type": "integer", "description": "The id of the block to redact, from the block list you were given."}
    },
    "required": ["block_id"],
    "additionalProperties": false
  }
}
```
Implementation: calls `session.redact(block_id)`. On success, returns a
short text result ("redacted block N: '<original text, truncated>'"). On
`LookupError`/`ValueError` from the session layer, returns that message as
an error `tool_result` (`is_error: true`) — Claude sees exactly the same
error text a human clicking the UI would see, and can decide whether to
retry with a different block id, ask a clarifying follow-up in its final
text response, or give up on that part of the instruction.

**`replace_block`**
```json
{
  "name": "replace_block",
  "description": "Replace one text block's content with new text, preserving its layout/font size as much as the engine allows. Use this when the instruction asks to change, fix, reword, or correct something (as opposed to deleting it).",
  "input_schema": {
    "type": "object",
    "properties": {
      "block_id": {"type": "integer", "description": "The id of the block to replace, from the block list you were given."},
      "new_text": {"type": "string", "description": "The full replacement text for this block."}
    },
    "required": ["block_id", "new_text"],
    "additionalProperties": false
  }
}
```
Implementation: calls `session.replace(block_id, new_text)`. Same
success/error shape as `redact_block` — including the "doesn't fit even
shrunk" `ValueError` from `engine/operations.py` surfacing verbatim as a
tool error, which is itself a legitimate outcome Claude should be able to
report back ("I couldn't fit the replacement text into that block").

Both tools use `strict: true` (the schemas above already satisfy strict
mode's `additionalProperties: false` + `required` requirements) so a
malformed tool call is rejected by the API itself rather than reaching
`webui/session.py` with garbage input.

## The instruction loop

```
POST /api/ai-instruct
  {"instruction": "...", "api_key": "sk-ant-...", "base_url": null, "model": null}
```

1. Resolve the API key (request, then environment, then 400 if neither).
2. Build the current block list via the same `session.get_blocks_summary()`
   used elsewhere — `{id, page_index, text, font, size}` per block, no
   bbox (Claude never needs pixel coordinates, only text content).
3. Construct the request: a top-level `system` prompt (not folded into the
   user message) describing the tool surface and the constraint "only
   touch blocks relevant to the instruction; if nothing matches, say so
   instead of guessing" — plus one user message containing the block list
   (as a JSON blob, so it's unambiguous which fields are `id`/`text`/etc.)
   followed by the instruction itself.
4. Loop (manual, not the Tool Runner), capped at **10 rounds**: call
   `client.messages.create(...)` with the two tools; if `stop_reason` is
   `tool_use`, execute every `tool_use` block against the live session
   (parallel tool calls in one turn are legitimate — e.g. "redact both the
   name and the SSN" — execute all of them, return all results in one
   `tool_result` message, per the API's own parallel-tool-use contract);
   if `stop_reason` is `end_turn`, the loop is done and the response's text
   content is the summary.
5. If the cap is hit without `end_turn`, stop anyway and report a summary
   noting the instruction may be incompletely handled — this mirrors the
   engine's own established "bounded loop, fail loudly rather than run
   forever" pattern (the shrink-retry loop in `replace_text`).
6. Return `{"summary": <final text>, "pages": session.get_pages_summary(),
   "blocks": session.get_blocks_summary()}` — same `{pages, blocks}` shape
   `/api/redact`/`/api/replace`/`/api/state` already return, so the
   existing frontend `render()` function needs no new code path to display
   the result; only the summary text is new.

## Error handling

Reuses `webui/main.py`'s existing `ValueError`/`LookupError` → 400
handlers for anything a tool call raises internally. New cases specific to
this endpoint, all returning a clean 400 with `{"error": ...}` (never a
bare 500 leaking an SDK exception):

- No API key available (checked before any API call).
- `anthropic.AuthenticationError` (bad/revoked key).
- `anthropic.RateLimitError` / `anthropic.APIStatusError` — the SDK's own
  automatic retry (default 2 retries for 429/5xx) already runs first; if it
  still fails, surface the error text.
- `anthropic.APIConnectionError` (network/base_url unreachable).
- Empty `instruction` — reject before any API call, same "fail loudly
  before doing anything" posture the engine's own operations use for empty
  `new_text`.

## Frontend

Small additions to `webui/static/index.html`/`app.js`:

- A password-type input for the API key (masked, matching how a real
  credential field should look even in a disposable local tool), persisted
  only as a JS variable for the tab's session — not `localStorage`.
- An optional, collapsed-by-default "advanced" field for `base_url` and
  `model` — most uses need neither.
- An instruction text input + "Run" button, posting to
  `/api/ai-instruct` and re-rendering via the same `render()`/error-path
  logic every other mutating endpoint already uses. The returned
  `summary` is displayed in a distinct area from the error box (a
  successful instruction still deserves a visible "here's what I did," not
  just a silent block-list update).
- The Run button is disabled while a request is in flight (an AI call can
  take several seconds to tens of seconds — the existing per-block
  in-flight guard pattern from the redact/replace fix wave is directly
  reusable here).

## Testing strategy

The engine-facing half (tool implementations calling
`session.redact`/`session.replace`, the loop's error handling, the
request-vs-environment API key resolution) is testable without hitting the
real Anthropic API by constructing fake `anthropic.Message` responses (the
SDK's response objects are plain Pydantic models) and monkeypatching
`client.messages.create` — this repo already has one precedent for a
deliberately-mocked test (`webui`'s defense-in-depth `ValueError`-wrapping
test from the final review fix wave), so this isn't a new convention, just
its second use, for the same reason: there is no way to exercise "what
happens when the model calls a tool with a bad block_id" or "what happens
on a rate-limit error" using only real API calls without spending real
money on every test run.

At minimum:
1. A fake single-turn response (Claude calls `redact_block` once, gets a
   result, ends the turn) — proves the loop executes a tool call and
   returns a summary.
2. A fake multi-round response (Claude calls a tool, the mocked client
   returns another `tool_use` on the next `create()` call, then finally
   `end_turn`) — proves the loop actually loops, not just handles one
   round.
3. A fake response where the tool call targets an unknown `block_id` —
   proves the `LookupError` surfaces as an `is_error` tool result, not an
   unhandled exception.
4. A request with no API key and no environment variable set — proves the
   clean 400 fires before any `anthropic.Anthropic()` client is even
   constructed.
5. A loop that never reaches `end_turn` within the mocked responses —
   proves the round cap fires and returns a "may be incomplete" summary
   rather than looping forever.

No test should make a real network call to the Anthropic API — this keeps
the suite's existing "fast, free, deterministic" property (matching
`engine/`'s and `webui/`'s existing test suites) intact for this new
piece.

## Explicitly out of scope (this pass)

- Multi-turn conversation memory.
- An auto-detect/NER layer.
- Real multi-provider (non-Anthropic) support.
- Image-block instructions.
- Any persistence of keys, history, or instructions.
- Streaming the AI's response to the frontend incrementally (the current
  design waits for the whole loop to finish, then returns one result — a
  reasonable v1 given instructions here are expected to resolve in a
  handful of tool calls, not a long research task).
