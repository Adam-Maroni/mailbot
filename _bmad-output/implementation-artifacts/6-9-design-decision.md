# Story 6-9 — Design Decision: F11 closure via sibling `dispatch_tool_call`

**Date:** 2026-06-04
**Author:** Amelia (Developer)
**Status:** Adam-approved 2026-06-04 (Option B selected)

## TL;DR

F11 closure ships as **Option B — a sibling dispatch function** (`dispatch_tool_call`) in the Router subsystem, matching the Story 3-4 `dispatch_embedding` precedent. `ask_router` stays unchanged in signature; the new sibling shares the sensitivity/pause/budget/audit primitives but owns its own dispatch path (no schema-validation retry leg — tool calls don't have schema-failure semantics).

The `/v1/chat/completions` endpoint branches at the request-shape boundary: if `request.tools` is None, the existing `ask_router` path fires (preserving Story 2-10 behavior for compression/title/summarization tasks); if `request.tools` is non-None, the new `dispatch_tool_call` path fires.

## 1 — The shape mismatch that forces a sibling

Story 2-4's `ask_router` contract is:

> "Pydantic-validated text output via a per-prompt-module OUTPUT_SCHEMA, with a retry-leg that re-prompts with stricter instructions on schema-validation failure."

Tool-calling responses violate this on two axes:

1. **Output shape:** Tool calls are `tool_calls=[{"id","type":"function","function":{"name","arguments"}}, ...]`, not a Pydantic-validated text string. The current `hermes_aux/v1.py` OUTPUT_SCHEMA (`HermesAuxOutput.text: str`) cannot accommodate them without becoming a discriminated union.
2. **Failure semantics:** A tool-call response either has `tool_calls` (success) or doesn't (model declined / produced text). There is no "stricter prompt retry" equivalent — re-prompting a model that didn't tool-call doesn't make it tool-call on retry. The schema-validation retry leg is meaningless here.

Story 3-4 hit the same shape-mismatch on embeddings and resolved it via `dispatch_embedding` — a sibling function sharing primitives but with its own dispatch path. F11 closure follows the same pattern.

## 2 — What `dispatch_tool_call` looks like

```python
async def dispatch_tool_call(
    *,
    messages: list[ChatCompletionMessage],          # OpenAI-shape input
    tools: list[ChatCompletionToolDef],             # OpenAI-shape tools
    tool_choice: ChatCompletionToolChoice | None = None,
    model: str,                                     # e.g. "claude-haiku-4-5-20251001"
    max_tokens_out: int = 1024,
    temperature: float = 0.0,
    db_path: str,
    caller_origin: str = "unknown-external",
    caller_verb: str | None = None,
    email_id: str | None = None,                    # caller-supplied OR extracted from tool args
    confirmation_token: str | None = None,
) -> ToolCallResult:
    ...
```

Returns `ToolCallResult` — parallel to `RouterResult` but tailored to tool-call dispatch:

```python
class ToolCallResult(BaseModel):
    ok: bool
    text: str | None = None                         # Anthropic CAN return both text + tool_use blocks
    tool_calls: list[OpenAIToolCall] | None = None  # OpenAI-shape, translated from Anthropic tool_use
    error: RouterError | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    model_used: str = ""
    finish_reason: Literal["stop", "tool_calls", "length"] = "stop"
```

Honors:
- **Pause kill-switch** (Story 2-9) — paused router short-circuits
- **Sensitivity precondition** (Story 3-3 + 4-7) — `email_id` may be passed directly OR extracted from tool-call arguments (see §5)
- **Budget guard** (Story 2-8) — per-call refusal threshold + degraded-mode demotion
- **Audit row** (Story 2-1) — written via the `finally` block, with new `tool_calls_count` + `tool_calls_summary` columns

Does NOT apply (vs. `ask_router`):
- Schema-validation retry leg — tool-call responses don't have schema-failure semantics
- Escalation chain — tool-calling support is per-adapter; escalation to a non-tool-supporting model is meaningless
- Response cache — caching tool-call dispatch is more involved (tool argument inputs may carry per-email state); defer to a future story

## 3 — Anthropic ↔ OpenAI translation

This is the largest sub-component. Four translation directions:

### 3.1 — Tools definition: OpenAI → Anthropic (request shape)

```python
# OpenAI
{"type": "function", "function": {"name": "render_spend_chart", "description": "...", "parameters": {...}}}

# Anthropic
{"name": "render_spend_chart", "description": "...", "input_schema": {...}}
```

Direct field-rename: `function.name` → `name`, `function.description` → `description`, `function.parameters` → `input_schema`. The `"type": "function"` outer envelope is dropped (Anthropic doesn't use it).

### 3.2 — Tool choice: OpenAI → Anthropic

| OpenAI | Anthropic |
|---|---|
| `"auto"` | `{"type": "auto"}` |
| `"none"` | tools list omitted entirely (Anthropic has no "force no tools" mode) |
| `"required"` | `{"type": "any"}` |
| `{"type": "function", "function": {"name": "X"}}` | `{"type": "tool", "name": "X"}` |
| `None` (omitted) | `{"type": "auto"}` (Anthropic default when tools provided) |

### 3.3 — Response: Anthropic → OpenAI

Anthropic response content blocks:
```python
content = [
    {"type": "text", "text": "Let me check that for you."},
    {"type": "tool_use", "id": "toolu_01ABC...", "name": "render_spend_chart", "input": {"period": "month"}},
]
```

Translates to OpenAI:
```python
{
    "message": {
        "role": "assistant",
        "content": "Let me check that for you.",   # joined text blocks, or null if only tool_use
        "tool_calls": [
            {
                "id": "toolu_01ABC...",            # echo Anthropic's id directly
                "type": "function",
                "function": {
                    "name": "render_spend_chart",
                    "arguments": "{\"period\":\"month\"}",  # JSON-stringified, NOT dict
                },
            },
        ],
    },
    "finish_reason": "tool_calls",                  # NOT "stop" when tool_calls present
}
```

Key contract points:
- Anthropic id is forwarded verbatim — caller (Hermes) keys subsequent `tool_result` blocks on this same id
- `function.arguments` is a JSON string (OpenAI shape), not a dict (Anthropic shape) — `json.dumps(input)` at translation time
- `finish_reason` is `"tool_calls"` when any tool_use block present, regardless of accompanying text

### 3.4 — Multi-turn history: OpenAI → Anthropic (message-history shape)

This is the subtle one. When Hermes echoes tool results back on turn 2:

```python
# OpenAI shape (turn 2 request)
messages = [
    {"role": "user", "content": "spend month"},
    {"role": "assistant", "tool_calls": [{"id": "toolu_01ABC", ...}]},  # echo from turn 1
    {"role": "tool", "tool_call_id": "toolu_01ABC", "content": "<chart PNG b64>"},
    # No new user message — Anthropic uses the tool_result to advance
]
```

Translates to Anthropic:

```python
messages = [
    {"role": "user", "content": "spend month"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01ABC", "name": "render_spend_chart", "input": {"period": "month"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01ABC", "content": "<chart PNG b64>"}]},
]
```

Three subtleties:
- The OpenAI `role: "tool"` message becomes a `role: "user"` message in Anthropic shape (tool results travel as user-side content blocks)
- Anthropic requires the echoed `assistant` `tool_use` to include the original `name` + `input` fields. The OpenAI `assistant.tool_calls[].function.{name,arguments}` carries these — `arguments` is parsed from JSON string back to dict
- Adjacent OpenAI `assistant + tool` messages collapse into Anthropic's `assistant + user` alternation — no message ordering inversion

## 4 — Audit row extension

`router_calls` schema gains **two NULL-able columns** via a new migration `022_router_calls_tool_calls.sql`:

| Column | Type | Purpose |
|---|---|---|
| `tool_calls_count` | INTEGER NULL | How many tool_use blocks the response contained. 0 = tool_choice gave no tool calls; NULL = call wasn't a tools-bearing call. |
| `tool_calls_summary` | TEXT NULL | Compact JSON: `[{"name":"render_spend_chart","input_redacted":"{\"period\":\"month\"}"}, ...]`. Per-call dispatched-tool metadata; redacted through Story 5-7's chat-input redactor pipeline before write. NULL on non-tools calls. |

**Why two columns instead of one JSONB-equivalent:**
- `tool_calls_count` enables `WHERE tool_calls_count > 0` queries efficiently (count-aggregations on the audit table are a Story 6-7 cost-attribution use case)
- `tool_calls_summary` carries the redacted per-call metadata for forensic queries ("which tools did Hermes try to call on email X?")

`RouterCallRow` extends with `tool_calls_count: int | None = None` and `tool_calls_summary: str | None = None`. Existing call sites (everywhere else) pass nothing — defaults to NULL. Only `dispatch_tool_call`'s audit row populates these.

## 5 — Sensitivity gate on tool-call arguments

Story 4-7's sensitivity precondition is `email_id`-keyed. `dispatch_tool_call` extends the email_id resolution:

1. If `email_id` is passed directly by the caller → use it (current Story 4-7 behavior)
2. **Else** inspect `tools[].function.parameters` schema: if any tool defines `email_id` as a parameter AND the assistant's chosen tool-call carries an `email_id` argument value → use that
3. Else `email_id=None` (no gate fires — same as ad-hoc Router calls today)

**Edge case — multiple tool_calls in one response:** If the assistant returns N tool_use blocks, all with different `email_id` arguments, the gate fires N independent precondition checks. Any one failing → entire dispatch refused (`SENSITIVITY_BLOCKS_API`). This is conservative (Story 4-7 design intent: sensitive email leakage is never traded for performance).

**Important:** The gate fires on **the request** (when `email_id` is in tool-call ARGS the caller declared as "the assistant might pass") — not on the response. Hermes's request shape carries the tool_call args from the assistant; we don't dispatch until the gate clears. For the initial design, we apply the gate to the *outermost* email_id signal (the request's `email_id` parameter, if passed). Per-tool-call email_id extraction from response-side tool_calls is a Story 6-9 v2 refinement.

## 6 — Cache-key extension

Story 2-7's response cache is keyed on `sha256(model | temperature | system | user)`. For tool-call dispatch:

- `dispatch_tool_call` **does not currently cache** (per §2 — tool arguments carry per-email state; caching across email boundaries is risky)
- However, when Story 2-7's cache lookup runs in **the regular `ask_router` path** for a tool-bearing request, the cache key MUST include the tools shape — otherwise a tools-free call from origin A could hit a tools-bearing cache entry from origin B, returning wrong content

**Implementation:** `compute_cache_key` gains a 5th positional argument `tools_hash: str = ""` (empty string by default to preserve existing call sites; the cache-key SHA changes only when this is non-empty). `dispatch_tool_call` computes `tools_hash = sha256(canonical_json([(t["function"]["name"], t["function"]["parameters"]) for t in tools]))[:16]` and threads it through if it ever calls cache lookup. `ask_router` does not change.

This is defensive: no current policy entry both (a) has caching enabled and (b) would receive a tools-bearing call. But the invariant should hold structurally.

## 7 — Test strategy

`tests/integration/test_chat_completions_tool_calling.py` covers 7 layers:

| # | Layer | Test name (approx) |
|---|---|---|
| 1 | Request schema accepts `tools`/`tool_choice` | `test_chat_completions_accepts_tools_in_request` |
| 2 | Tools forwarded through `/v1/chat/completions` → dispatch_tool_call → adapter | `test_tools_forwarded_to_adapter_via_endpoint` |
| 3 | Adapter translates Anthropic response → OpenAI `tool_calls` shape | `test_anthropic_response_translates_to_openai_tool_calls` |
| 4 | Multi-turn round-trip — request with tools → response with tool_calls → next request with tool_result | `test_multi_turn_tool_result_history_translation` |
| 5 | Audit row captures `tool_calls_count` + `tool_calls_summary` | `test_router_calls_audit_captures_tool_call_metadata` |
| 6 | Sensitivity gate enforced on `email_id` in dispatch | `test_dispatch_tool_call_honors_sensitivity_gate` |
| 7 | Pause kill-switch short-circuits dispatch | `test_dispatch_tool_call_honors_pause_kill_switch` |
| 8 | Cache-key includes tools shape (regression on `compute_cache_key`) | `test_cache_key_changes_when_tools_present` |
| 9 | Adapters without tool support raise structured error | `test_ollama_adapter_raises_tools_unsupported_when_tools_passed` |

No live Anthropic API in tests — uses a `_FakeAnthropicAdapter` that returns a canned tool_use response. The translation logic is the unit under test; the network round-trip is Story 6-9 Phase 3.5 walk territory (Hermes-driven, against real Anthropic).

## 8 — Out of scope (deferred to future work)

- **Per-tool-call email_id extraction on the response side** (the response carries the model's chosen tool-call args; gating on those would require post-response re-gating before delivering to caller). Defer to Story 6-9 v2 if needed; Story 4-7's sensitivity model is request-side, not response-side.
- **Tool-call response caching** — see §6.
- **Streaming tool-call deltas** — OpenAI's streaming format chunks tool_call.arguments deltas across SSE events. Story 6-9 ships non-streaming only (matching the rest of `/v1/chat/completions`).
- **Anthropic's prompt cache interaction with tools** — Anthropic's docs imply tools list is part of the cached prefix; Rule M (`cache_control: ephemeral` on system block) is preserved as-is. If cache hit rates degrade in production with tools-bearing calls, file a follow-up.
- **OllamaAdapter tool support** — Qwen 2.5 doesn't ship tool-calling at the API surface we use. `OllamaAdapter` raises `AdapterProviderError(sanitized_message="tools_unsupported")` when called with tools. Future: switch to a tool-capable local model.

## 9 — Implementation order

1. Migration `022_router_calls_tool_calls.sql` + `RouterCallRow` extension + `ROUTER_CALLS_INSERT` extension + `_param_tuple` extension
2. `ToolCallResult` + `OpenAIToolCall` + `ChatCompletionToolDef` + `ChatCompletionToolChoice` shapes (in `router/errors.py` next to `RouterResult` and `router/models.py` next to `AdapterResponse`)
3. AnthropicAdapter — new `call_with_tools` method (parallel to `call`, doesn't pollute the existing signature)
4. `dispatch_tool_call` in `router/router.py` (sibling to `ask_router`)
5. `_ChatCompletionsRequest` extended + endpoint branches on `request.tools`
6. `compute_cache_key` signature extension (defensive)
7. Integration tests
8. 4 gates + MANDATORY-CR

## 10 — What this does NOT do

- Does NOT close F9 by itself — F9 is "Discord round-trip Empty response". F9 closes when (a) F11 closes AND (b) Hermes's main inference can now successfully tool-call `render_spend_chart`. The Phase 3.5 walk verifies F9 closure; the code change alone doesn't.
- Does NOT change the `hermes_aux` prompt module. `hermes_aux` continues to handle title/compression/summarization tasks via `ask_router`. Tool-calling requests bypass `hermes_aux` entirely (they go through `dispatch_tool_call`, not through any prompt module — the OpenAI-shape `messages` + `tools` is the entire "prompt").
- Does NOT extend the embeddings endpoint (Story 3-4 sibling). Embeddings remain orthogonal.
