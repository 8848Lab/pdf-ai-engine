# Multi-provider AI layer -- real end-to-end verification report

Verification for Task 5 of `2026-08-29-multi-provider-ai-layer.md`, run against
branch `worktree-multi-provider-ai` at commit `7a6be55`.

## Automated suite

`./.venv/Scripts/python.exe -m pytest -v` -- **109 passed**, 0 failed, 0
skipped, 1.90s. Re-confirmed with a second `-q` run after the manual webui
server work below (also 109 passed) to make sure nothing in the manual
session had left the test-time state dirty.

## Provider-by-provider: what got a genuine real round-trip

### Ollama -- genuine real round-trip (the plan's main point)

A local Ollama server was reachable at `http://localhost:11434` (HTTP 200),
with four models already pulled: `qwen3:30b`, `qwen3:14b`, `llama3.2:3b`,
`qwen3-coder:latest` (all reporting `tools` capability).

Started the real webui server (`uvicorn webui.main:app --port 8000`),
uploaded `tests/fixtures/mixed.pdf` (two text blocks: "Mixed-content
document with text and an embedded image below." and "Sensitive figure
caption: Subject ID PATIENT-0042.", plus one image), and POSTed to
`/api/ai-instruct` with `provider: "ollama"` and the instruction "Redact the
block that mentions the patient ID or subject ID."

- First attempt with `llama3.2:3b`: got a real 200 response, but the model
  redacted *both* text blocks and then ran out its 10-round step-limit budget
  without producing a final summary. This looked concerning at first, so it
  was investigated rather than accepted at face value (see Concerns below) --
  conclusion: model-competence issue with a small 3B model, not a code bug.
- Second attempt, same fixture freshly re-uploaded, with `qwen3:14b`: **200
  response**, summary "The block containing the patient/subject ID (block 1)
  has already been redacted. The remaining block (ID 2) does not contain any
  sensitive information and does not require further action.", and
  `/api/state` confirmed only the target block was gone -- the unrelated
  "Mixed-content document..." block (renumbered to id 2 after the mutation,
  per the session's monotonic id-churn behavior) was still present and
  untouched.

This is a genuine, successful, real network round-trip through the native
Ollama adapter: real HTTP to a real local server, real tool-call
translation both directions, real tool execution against the real document
engine, real summary text back.

### OpenAI-compatible -- not exercised for real (no key available)

`OPENAI_API_KEY` was checked in both the Bash and PowerShell environments
available in this session -- not set in either. Per the task brief's explicit
instruction not to acquire a key or spend money without one already being
present, Step 3 was skipped. The mocked tests in
`tests/test_ai_provider_openai_compatible.py` (10 passing) are the only
coverage this provider's translation layer has right now. The Ollama
round-trip above does exercise the *same* provider-agnostic tool-calling
loop (`webui/ai/loop.py`) and the same general request/response shape, but
not the OpenAI-compatible adapter's own translation code
(`webui/ai/providers/openai_compatible.py`) specifically.

### Anthropic -- clean-error-path only (by design, no billing)

Same fallback the original AI-instruction-layer plan used for its own final
verification: POSTed to `/api/ai-instruct` with `provider: "anthropic"` and
a deliberately-fake key (`sk-ant-fake-definitely-invalid-key-000`).

Result: **HTTP 400**, body:
```json
{"error":"Anthropic API error: Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}"}
```

Confirms the real `anthropic` SDK's `AuthenticationError` still surfaces as
a clean 400 (not a 500/stack trace) after Task 1/2's restructuring of
`webui/ai.py` into the `webui/ai/` package -- no regression in the one
provider that was already fully working before this plan.

## Bonus: plan's "Final Verification" checklist

The task-5 brief file also carries a "Final Verification" section for after
all 5 tasks. Since this is the last task, it was run too (no code changes
resulted):

1. Full suite: 109/109 passing (see above).
2. `git diff b515e36..HEAD -- engine/ webui/session.py` (plan-start commit
   `b515e36`, "docs: multi-provider AI layer design spec") -- **empty**.
   `engine/` and `webui/session.py` are untouched by this plan.
3. Scratch venv: `pip install -e .` then `pip install -e ".[test,webui]"`
   (no `ai` extras) in a fresh venv -- `import webui.main` succeeds, and
   `anthropic`/`openai`/`ollama` are each confirmed *not* importable,
   proving the soft-import pattern in `webui/ai/providers/*.py` genuinely
   keeps the `ai` extras group optional on top of `webui`.
4. `grep -rn "claude-opus-5" webui/ai/ webui/main.py` -- only match is
   `webui/ai/providers/anthropic.py:24: DEFAULT_MODEL = "claude-opus-5"`
   (plus a stale `.pyc` cache hit, not source). No other hardcoded
   provider-specific model assumption leaked into the generic dispatch
   layer.
5. `grep -rn "OPENAI_API_KEY\|ANTHROPIC_API_KEY" --include=*.py .` (outside
   `.venv`) -- only hits are the two providers' own `resolve_key`/
   `resolve_api_key` environment reads (`webui/ai/providers/anthropic.py`,
   `webui/ai/providers/openai_compatible.py`) and test files using
   `monkeypatch.setenv`/`delenv`. No write to a file or to session state
   anywhere.

## Concerns

- **Not a code bug, but worth flagging:** `llama3.2:3b` over-redacted (both
  text blocks instead of just the targeted one) and then exhausted the
  10-round step limit without a final summary, on the very same instruction
  that `qwen3:14b` handled correctly and concisely. This is model-capability
  variance (a small 3B model being either overzealous or looping), not a
  defect in the provider adapter, the translation layer, or the tool-calling
  loop -- the tool calls it *did* make executed correctly and left the
  document in a valid, consistent state (confirmed via `/api/state`), and a
  larger model given the identical instruction, fixture, and code path
  produced the exact intended result. No code change is warranted from this;
  noting it here only because task-5's job includes reporting anything that
  gave pause during verification, and the initial result was surprising
  enough to investigate further rather than write off immediately.
- No real key was available to exercise the OpenAI-compatible provider's own
  translation code end-to-end; only its mocked tests and Ollama's structurally
  similar (but code-path-distinct) round-trip stand behind it for now.

## Commands run (abridged transcript)

```
$ ./.venv/Scripts/python.exe -m pytest -v          # 109 passed
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:11434   # 200
$ curl -s http://localhost:11434/api/tags          # 4 models, all "tools"-capable
$ ./.venv/Scripts/python.exe -m uvicorn webui.main:app --port 8000 &
$ curl -s -X POST http://localhost:8000/api/upload -F "file=@tests/fixtures/mixed.pdf;type=application/pdf"
$ curl -s -X POST http://localhost:8000/api/ai-instruct -H "Content-Type: application/json" \
    -d '{"instruction":"Redact the block that mentions the patient ID or subject ID.","provider":"ollama","model":"llama3.2:3b"}'
  # -> reached step-limit, blocks: [] (over-redacted; see Concerns)
$ curl -s -X POST http://localhost:8000/api/reset
$ curl -s -X POST http://localhost:8000/api/upload -F "file=@tests/fixtures/mixed.pdf;type=application/pdf"
$ curl -s -X POST http://localhost:8000/api/ai-instruct -H "Content-Type: application/json" \
    -d '{"instruction":"Redact the block that mentions the patient ID or subject ID.","provider":"ollama","model":"qwen3:14b"}'
  # -> 200, correct target-only redaction, sensible summary
$ curl -s http://localhost:8000/api/state           # confirms only target block gone
$ echo "OPENAI_API_KEY set: ${OPENAI_API_KEY:+yes}${OPENAI_API_KEY:-no}"   # no
$ curl -s -X POST http://localhost:8000/api/ai-instruct -H "Content-Type: application/json" \
    -d '{"instruction":"Redact the block that mentions the patient ID.","provider":"anthropic","api_key":"sk-ant-fake-definitely-invalid-key-000"}'
  # -> 400, clean AuthenticationError, no stack trace
```

## Conclusion

Task 5 verification is complete. The multi-provider AI instruction layer's
main deliverable -- a real, working, provider-agnostic tool-calling round-trip
against a genuinely external server -- is confirmed via the Ollama adapter.
The Anthropic provider's error path is confirmed unregressed. The
OpenAI-compatible provider remains verified only at the mock level (no key
available), which the brief treats as an acceptable, expected outcome. No
code changes were made or needed.
