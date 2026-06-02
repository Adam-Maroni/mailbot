---
baseline_commit: ae3b2c9
---

# Story 5.2: MCP server exposing verbs as tools

Status: done

## Story

As Adam,
I want `mailbot_api/mcp_server.py` to expose every verb in `mailbot_api/verbs/` as an MCP tool using `FastMCP` from the MCP Python SDK 1.27.2 — `<Verb>In` Pydantic models supplying the tool input schema and verb function docstrings supplying the tool description,
so that Hermes can connect as an MCP client over the `uvicorn` HTTP transport (path `/mcp` on port 8000), discover the tools, and invoke them in agent turns using the same data shapes Python tests already exercise.

## Acceptance Criteria

### AC-1 — `mailbot_api/mcp_server.py` builds a `FastMCP` instance and registers every verb as a tool

`mailbot_api/mcp_server.py` (NEW) defines a `build_mcp_server() -> FastMCP` factory that:

- Constructs a `FastMCP(name="mailbot-api", instructions=<short server description>)`.
- Registers each of the **11 currently-shipped verbs** as MCP tools via `mcp.add_tool(...)` or the `@mcp.tool()` decorator pattern. Tool name = verb function name verbatim (per architecture §Naming — "MCP tool names: snake_case matching the verb function name exactly").
- Each tool description is sourced from the verb's docstring (the first sentence, or the first paragraph if the first sentence is shorter than 30 chars). Where the verb docstring does not mention a documented cost-relevant constraint, the registration helper **prepends or appends a one-clause constraint hint** so the agent always sees it. Required constraint hints:
  - `find_emails`: include "Capped at 100 results — Rule J projections only" (the verb refuses `limit > 100`).
  - `hydrate_email`: include "Rate-limited to 5 calls per chat turn — Rule J hydration discipline".
  - `count_emails`: include "Rule J — projections only; returns count".
  - `get_thread`: include "Rule J — projections only; ordered ASC by received_at".
  - `get_sender_summary`: include "Rule J — cached sender enrichment".
  - `propose_action`: include "Tier-aware; second auth check on apply".
  - `mint_grant`, `revoke_grant`: include "Scoped + time-bounded grant".
  - `cancel_action`: include "Atomic cancel of a pending action".
  - `revert_action`: include "Tier-1 only; 24h window".
  - `mint_sensitivity_token`: include "Sensitive emails only; ephemeral 10-min token (AR-D12-1)".
- The 11 verbs:
  1. `find_emails` (read, Story 5-1)
  2. `hydrate_email` (read, Story 5-1)
  3. `get_thread` (read, Story 5-1)
  4. `count_emails` (read, Story 5-1)
  5. `get_sender_summary` (read, Story 5-1)
  6. `propose_action` (write, Story 4-2)
  7. `mint_grant` (write, Story 4-3)
  8. `revoke_grant` (write, Story 4-3)
  9. `cancel_action` (write, Story 4-6)
  10. `revert_action` (write, Story 4-8)
  11. `mint_sensitivity_token` (write, Story 4-7)
- `ask_router`, `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router`, and `reset_hydration_count` are **NOT** registered in this story. Rationale per verb:
  - `ask_router` — internal Router dispatch surface; Hermes-as-agent uses the OpenAI `/v1/chat/completions` endpoint (Story 2-10), not the MCP `ask_router` tool. Re-exposing it as an MCP tool would invite the agent to bypass the cost-discipline path.
  - `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router` — these are the verb-side of Discord slash commands (Story 5-6). They will be MCP-exposed in Story 5-6 alongside the dispatcher, where the tier-1/tier-3 wiring is finalized.
  - `reset_hydration_count` — server-internal lifecycle helper (called by Story 5-2 itself between turns per AC-4). Not an agent-facing tool.
- The registration list is **declarative** — a module-level `_TOOL_SPECS: list[ToolSpec]` (or equivalent) that pairs each verb function with its constraint hint and its `<Verb>In`-shaped argument schema. A typo or missing entry triggers a startup assertion (`assert len(_TOOL_SPECS) == 11`) so silent omission of a verb fails fast.

### AC-2 — `<Verb>In` Pydantic schema becomes the tool input schema

For each registered tool:

- The input parameters MUST match the verb function's keyword-only kwargs (excluding `db_path` and `session_id` — see AC-3).
- Where a verb takes a Pydantic model (e.g. `find_emails(filter: FindEmailsFilter, ...)`), FastMCP auto-derives the JSON schema from that model and exposes the nested fields. Where a verb takes simple kwargs (e.g. `hydrate_email(email_id: str, ...)`), FastMCP derives the schema from the function signature annotations.
- Field descriptions on the `<Verb>In` models (already populated by Story 5-1) propagate into the MCP tool schema — verify via the integration tests at AC-6.
- Schema mismatches in client-provided input surface as **MCP-level validation errors** (the SDK raises before the tool body runs). The integration tests at AC-6 prove this for at least one verb (e.g., send `find_emails` with `limit="not-an-int"`).

### AC-3 — Per-call dependency injection (`db_path` + `session_id`) without leaking them to the agent

The agent NEVER passes `db_path` or `session_id` — those are server-side concerns. The MCP server is responsible for injecting them on every tool dispatch:

- **`db_path`**: resolved once from `MAILBOT_DB_PATH` (via `mailbot_api.config.get_secret`) at server-build time. Stored on a module-level `_ServerContext` dataclass that the tool wrappers close over. Tests inject a different `db_path` by calling `build_mcp_server(db_path=<tmp_path>)`; production code path uses the env var.
- **`session_id`** (for `hydrate_email` only): derived from the **MCP session id** assigned by FastMCP's `StreamableHTTPSessionManager`. The tool wrapper for `hydrate_email` accepts a `ctx: Context` parameter (the FastMCP context object) and reads `ctx.session_id` (or the closest equivalent in the 1.27.2 API — verify at implementation time). If the SDK doesn't expose a stable session id, fall back to a UUID derived from the FastMCP transport-level session.
- The tool wrappers are **thin adapters** — they call the underlying verb function with the agent-supplied args plus the server-injected `db_path` / `session_id`, then serialize the verb's `<Verb>Out` Pydantic model back. No business logic in the wrappers.
- The wrappers MUST NOT expose `db_path` / `session_id` in the tool schema, the tool description, or any error message returned to the agent.

### AC-4 — Per-turn hydration counter reset

Per the Story 5-1 hand-off (see `5-1` Dev Notes → "Why module-level dict for hydration counts"), the MCP server is responsible for resetting `hydrate_email`'s 5/turn counter at per-turn boundaries:

- The reset is keyed by the **same `session_id`** that `hydrate_email` increments — typically the MCP session id from AC-3.
- "Per turn" semantics in the 1.27.2 streamable-HTTP transport: a turn is one MCP request/response cycle from the agent's perspective. Implementations may interpret "turn" as either (a) once per `tools/call` request, which makes the 5-cap apply per individual tool call — **WRONG, defeats the purpose of the cap**; or (b) once per *agent turn*, where a turn spans multiple tool calls until the agent yields back to the user. Since the MCP transport does not natively expose a "turn boundary" event, implement option (c) below.
- **Adopted approach (c) — server-side timeout reset:** the per-session counter auto-resets after **30 seconds of inactivity** on that `session_id`. Rationale: a chat turn is typically completed (or abandoned) within 30s; if the agent legitimately needs more than 5 hydrations across a single turn, the policy guidance is "narrow your filter first" (per the existing error message). The 30s window is a module-level constant `_HYDRATION_TURN_RESET_SECONDS = 30` — adjustable in one place.
- Implementation: track `last_hydration_at: dict[session_id, datetime]` next to the counter; on each `hydrate_email` invocation, if `now - last_hydration_at[sid] > 30s`, call `reset_hydration_count(sid)` before re-checking the rate-limit gate.
- **Where this lives:** in `mailbot_api/mcp_server.py` — the wrapper for `hydrate_email`, NOT in `mailbot_api/verbs/hydrate_email.py`. Keeps the verb pure (no clock dependency).

### AC-5 — `uvicorn` mounts the FastMCP HTTP transport on `/mcp`

`mailbot_api/main.py` is updated to mount the MCP server's streamable-HTTP ASGI app under path `/mcp`:

- A new lifespan section builds the `FastMCP` server via `build_mcp_server()` and stores it on `app.state.mcp_server`.
- The FastMCP server exposes a Starlette ASGI app via `.streamable_http_app()` (returns a Starlette instance). Mount it with `app.mount("/mcp", mcp_server.streamable_http_app())`.
- **Session manager lifecycle:** FastMCP 1.27.2 uses `StreamableHTTPSessionManager` which needs its async context manager entered. The MCP SDK example pattern: wrap mounting with `async with mcp_server.session_manager.run():` inside the FastAPI lifespan, **before** the `yield`. After `yield`, the `async with` block exits and the session manager shuts down. Verify by reading `mcp.server.fastmcp.FastMCP.streamable_http_app` source in 1.27.2.
- The mount happens **AFTER** all other lifespan steps complete (DB migrations, policy load, sensitivity patterns, adapters, lane scheduler, budget guard, anomaly detector, pause state, policy reload loop). The MCP server is the chat-serving surface — it should not accept traffic until the Router is fully ready.
- The `MAILBOT_SKIP_MCP=1` env var skips the MCP mount entirely — used by unit tests that boot the FastAPI app without needing the MCP transport (parallel to the existing `MAILBOT_SKIP_DB` / `MAILBOT_SKIP_POLICY` / `MAILBOT_SKIP_PATTERNS` pattern).
- The lifespan teardown (the `finally` block) handles the session-manager exit cleanly even if startup partially failed.

### AC-6 — Integration tests: full round-trip per verb via the MCP client SDK

`tests/integration/test_mcp_server.py` (NEW):

- Uses the MCP SDK's **in-process** transport for round-trip testing where possible. The 1.27.2 SDK exposes `from mcp.client.streamable_http import streamablehttp_client` for HTTP, and the lower-level `ClientSession` can be wired to in-memory streams. Prefer the in-memory path for speed — but if 1.27.2's API doesn't expose a clean in-memory client/server pair, fall back to spinning up the FastAPI `TestClient` and invoking the MCP endpoint via HTTP (this is acceptable and is the canonical pattern; matches `test_chat_completions_endpoint.py`'s style).
- **Bootstrap helper** (`_bootstrap`): identical pattern to `tests/integration/test_chat_completions_endpoint.py`'s `_bootstrap` — sets `MAILBOT_DB_PATH`, `MAILBOT_POLICY_PATH`, `MAILBOT_PATTERNS_PATH`, applies migrations, seeds a few canonical rows in the test DB.
- **Coverage matrix (≥ 12 tests minimum):**
  1. **Server boots:** `build_mcp_server()` returns a `FastMCP` with exactly 11 tools registered; tool names match the 11-verb list verbatim.
  2. **`list_tools` discoverability:** client lists tools; result contains all 11 names + their descriptions; descriptions contain the documented constraint phrases (e.g., `find_emails` description must contain "100" and "Rule J"; `hydrate_email` must contain "5" and "turn").
  3. **`find_emails` happy path:** client calls `find_emails` with `{filter: {sender_address: "alice@example.com"}, limit: 5}` against a seeded DB; result is a `FindEmailsOut` JSON with `ok=true` and projections matching the seeded row.
  4. **`find_emails` validation error:** client calls with `limit="not-int"`; the MCP layer raises a validation error (NOT a verb-level `ok=false` — this is the schema-mismatch case from AC-2).
  5. **`find_emails` verb-level error:** client calls with `limit=200`; result is `FindEmailsOut(ok=false, error={code: "LIMIT_EXCEEDED", ...})` — error-as-data over MCP (AR-PAT-4); MCP does NOT raise.
  6. **`hydrate_email` happy path:** seed a `normal`-sensitivity classified email, hydrate it, get body_preview back.
  7. **`hydrate_email` privacy gate:** seed a `confidential` email, hydrate it, get `CONFIDENTIAL_HYDRATION_BLOCKED` back as error-as-data.
  8. **`hydrate_email` 5/turn cap:** make 6 calls on the same MCP session within < 30s; the 6th returns `HYDRATE_RATE_LIMITED`.
  9. **`hydrate_email` 30s reset:** call 5 times, advance the test clock by 31s (via `freezegun` or monkeypatching `datetime.now` in the mcp_server module), call again; the 6th call succeeds (counter reset).
  10. **`get_thread`, `count_emails`, `get_sender_summary`:** one round-trip each, exercising the happy path against the seeded DB.
  11. **`propose_action` happy path:** call `propose_action` for a `MARK_READ` action (Tier-1, no grant needed); the result is a `ProposeActionOut` with `ok=true` and an action_id.
  12. **`mint_grant` + `revoke_grant`:** mint a grant, see it returned; revoke it, see the result.
  13. **`mint_sensitivity_token` privacy gate:** seed a `confidential` email; minting a token refuses with `SENSITIVITY_BLOCKS_API`.
  14. **Internal verbs NOT exposed:** asserting `ask_router`, `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router`, `reset_hydration_count` do NOT appear in `list_tools`.
  15. **`db_path` / `session_id` NOT in tool schema:** for every registered tool, the schema's `properties` dict MUST NOT contain `db_path` or `session_id` keys. Loop assertion.
- Test DB seeding helpers go in a shared `tests/integration/_mcp_seed.py` module (or inline if used only here).
- **No mocking of the verb functions themselves.** Verbs run against a real on-disk SQLite per Step 2.4.7 Middleware-Real-Bootstrap MailBot reframing — that is the integration boundary this story tests.

### AC-7 — Boundary check: `mcp_server.py` is the agent-side surface

`scripts/check_boundaries.py` extended (or already covers) to enforce:

- `mailbot_api/mcp_server.py` is added to the existing `verb_modules` / verb-import allowlist (per Story 5-1 AC-8 deferred). The boundary rule: modules outside `mailbot_api/verbs/`, `mailbot_api/mcp_server.py`, and tests MUST NOT import from `mailbot_api.verbs.*`. Story 5-1 deferred this check; **Story 5-2 implements it** (now that there are two legitimate consumers: the verbs themselves + `mcp_server.py`).
- No other module imports from `mcp.server.fastmcp` except `mailbot_api/mcp_server.py` and `tests/`. This keeps the FastMCP dependency localized.

### AC-8 — Structured logging on every MCP tool dispatch

Every tool wrapper emits **one** structured-log line per invocation (per Rule F + FR-7.3):

- On success: `{"event": "mcp.tool.ok", "tool": "<verb_name>", "session_id": "<sid>", "latency_ms": <n>}`
- On verb-level error-as-data: `{"event": "mcp.tool.error_as_data", "tool": "<verb_name>", "session_id": "<sid>", "error_code": "<code>", "latency_ms": <n>}`
- On unexpected exception caught at the wrapper boundary: `{"event": "mcp.tool.crash", "tool": "<verb_name>", "session_id": "<sid>", "exc_type": "<type>", "latency_ms": <n>}` — the exception is then converted to an MCP-level error (the SDK handles this if the wrapper re-raises).
- `db_path` is NEVER logged. The session_id is logged (it's a transport-level identifier, not a secret).
- Argument values (especially `email_id`, `query`) are NOT logged at info level — sanitization-by-omission (Rule F). If a debug log line is desired, it goes at `logger.debug` only, and `email_id` is fine to log per existing convention; raw `query` substrings are not.

### AC-9 — All gates green

693 baseline tests + new tests; ruff clean, mypy clean, boundary check clean. Net test count rises by **≥ 14** (per AC-6 minimum).

## Tasks / Subtasks

- [x] `mailbot_api/mcp_server.py` — `build_mcp_server` factory + declarative `_TOOL_DESCRIPTIONS` list + 11 tool wrappers closed over `_ServerContext` (AC-1, AC-2, AC-3, AC-8)
- [x] Hydration-counter per-turn reset (30s inactivity timeout) in `hydrate_email` wrapper, keyed off `id(ctx.session)` (AC-4)
- [x] `mailbot_api/main.py` — per-lifespan FastMCP build + streamable-HTTP mount on `/mcp` (via `Mount` appended to `app.router.routes`, popped on shutdown); `MAILBOT_SKIP_MCP=1` bypass (AC-5)
- [x] `tests/integration/test_mcp_server.py` — 18 tests via in-memory MCP client/server transport: server boot + 11-tool sanity + internal-verbs-not-exposed + no-db_path/session_id-leakage + set_db_path mutation + 14 round-trips covering happy path / validation error / verb error-as-data / 5-per-turn / 30s reset / 11-verb sanity / mint+revoke / sensitivity privacy gate (AC-6)
- [x] `scripts/check_boundaries.py` — added `_VERBS_IMPORT_ALLOW` (verb-import isolation — was deferred from Story 5-1 AC-8) + `_FASTMCP_IMPORT_ALLOW` (FastMCP dependency localization) (AC-7)
- [x] Gate sweep — 711 pytest pass (+18 net), ruff clean, mypy clean, boundary check clean (AC-9)

### Code Review — 2026-06-02 (Sonnet 4.6)

Gates confirmed green: 711 passed, 2 skipped · ruff clean · mypy clean (92 files) · boundary check clean.
Pre-review self-audit read; ESCALATE-TO-REVIEWER item (hand-maintained `_VERBS_IMPORT_ALLOW`) addressed in findings below.

- [x] [HIGH] mailbot_api/mcp_server.py:148–382 — AC-8 session_id logging gap: 10 of 11 tool wrappers call `_log_ok`/`_log_error_as_data`/`_log_crash` with `sid=None`. AC-8 specifies `"session_id": "<sid>"` in every log line. Only `hydrate_email` receives `ctx: Context` and logs a real session_id. **APPLIED:** added `ctx: Context[Any, Any, Any]` parameter to all 10 remaining wrappers and replaced `None` with `_session_id_from_ctx(ctx)` in every log call. FastMCP auto-omits `Context` params from the tool schema (verified by re-running `test_tool_schemas_never_expose_db_path_or_session_id` — still green).
- [x] [MEDIUM] tests/integration/test_mcp_server.py — cancel_action and revert_action have no round-trip call tests. **APPLIED:** added `test_cancel_action_happy_path` (propose mark_read → cancel via MCP, assert ok=True) and `test_revert_action_unsupported_for_pending` (revert with unknown action_id, assert error-as-data not protocol error). Happy-path revert against a terminal Tier-1 action is out of scope for this story (requires action-history infrastructure exercised by Story 4-8's own tests).
- [x] [MEDIUM] tests/integration/test_mcp_server.py — mint_sensitivity_token success path untested. **APPLIED:** added `test_mint_sensitivity_token_sensitive_success` (seed `sensitivity="sensitive"` email, mint, assert non-None token + expires_at + grant_id). Closes the load-bearing happy-path gap for Story 5-9's draft-reply flow.
- [x] [MEDIUM] tests/integration/test_mcp_server.py:1–30 — module docstring overclaims test coverage. **APPLIED:** rewrote the coverage matrix to enumerate all 21 tests as discrete numbered entries (was previously collapsing item 10 to "3 tests" and listing phantom items 16 + 18). New docstring matches the actual test function count.
- [x] [MEDIUM] scripts/check_boundaries.py:418–440 — boundary checker has an indirect-import bypass: `from mailbot_api import verbs`. **APPLIED:** added a dedicated check in `ast.ImportFrom` handling: when `module == "mailbot_api"` and any alias name is `"verbs"`, the file must be in `_VERBS_IMPORT_ALLOW`. Verified: `python scripts/check_boundaries.py` still exits 0 (no production module currently uses the bypass form).
- [x] [LOW] mailbot_api/main.py:209 — silent MCP non-mount when `db_path is None`. **APPLIED:** added `elif _app is not None and not skip_mcp:` branch emitting `logger.warning("mcp.startup.skipped", reason="db_path_unavailable", ...)` so the misconfiguration surfaces operationally.
- [x] [LOW] mailbot_api/mcp_server.py:522–526 — `_reset_mcp_session_state_for_test` exported in `__all__`. **APPLIED:** removed from `__all__`; added inline comment documenting that test helpers are imported by explicit name.
- [x] [LOW] mailbot_api/mcp_server.py:488–500 — AC-1 fail-fast asserts after registration loop. **APPLIED:** moved `assert len(wrappers) == _EXPECTED_TOOL_COUNT` and `assert set(wrappers) == set(_TOOL_DESCRIPTIONS)` to BEFORE the registration loop so divergence raises `AssertionError` before any partial registration occurs (and before a more cryptic `KeyError` from the loop body).

**ESCALATE-TO-REVIEWER resolved:** `_VERBS_IMPORT_ALLOW` explicit-list vs glob-based (pre-review §4). Recommendation: keep the explicit list. The failure mode is constructive — the boundary check fails when a new verb is added without updating the list, prompting the developer to register it. A glob-based approach would silently allowlist every file in `verbs/`, defeating the intent of the isolation boundary.

### Senior Developer Review (AI)

**Outcome: Changes Requested**

**Issue counts:** 1 HIGH · 3 MEDIUM · 3 LOW · 1 INFO (escalation resolved)

The implementation is solid overall — per-lifespan FastMCP mount, error-as-data discipline, privacy gates, and boundary checks all correct. The biggest concern is the AC-8 session_id logging gap: 10 of 11 tool wrappers emit `session_id=null` in structured logs, which contradicts the spec and degrades operability (session-level correlation is impossible for 10 of the 11 tools). The fix is low-risk (add `ctx: Context` to the remaining wrappers — FastMCP suppresses it from the schema automatically). Three test gaps (cancel/revert round-trips, mint_sensitivity_token success path, docstring overclaim) reduce the integration coverage story. None of the findings are blockers to functionality, but the HIGH logging issue and two of the MEDIUM test gaps must be resolved before `done`.

**CR resolution summary (2026-06-02 dev pass):** all 7 findings applied (7/7 = 100% application rate):

- HIGH session_id logging gap: 10 wrappers gained `ctx: Context[Any, Any, Any]` parameter + `_session_id_from_ctx(ctx)` call in every log line. FastMCP auto-omits Context params from the tool schema (verified: `test_tool_schemas_never_expose_db_path_or_session_id` still green).
- MEDIUM cancel_action / revert_action round-trip: 2 new tests added.
- MEDIUM mint_sensitivity_token success path: 1 new test added.
- MEDIUM docstring overclaim: docstring rewritten with all 21 tests enumerated.
- MEDIUM indirect-import bypass: new boundary check handles `from mailbot_api import verbs`.
- LOW silent MCP non-mount: warning log emitted when skip_mcp=False but db_path=None.
- LOW `__all__` leak: `_reset_mcp_session_state_for_test` removed from `__all__`.
- LOW assert ordering: AC-1 fail-fast asserts moved before the registration loop.

**Gate sweep after CR fixes:** 714 pytest pass (+21 net from 693 baseline, +3 new CR-driven tests beyond the 18 from initial dev pass), 2 skipped; ruff clean; mypy clean; boundary checker clean. All 4 gates remain green.

## Dev Notes

### FastMCP 1.27.2 API anchors

Verified during story creation (via `.venv/Scripts/python.exe`):

- **Import:** `from mcp.server.fastmcp import FastMCP`
- **Constructor kwargs of interest:** `name`, `instructions`, `streamable_http_path="/mcp"` (default), `stateless_http=False` (default — session-aware), `host="127.0.0.1"`, `port=8000`. We do NOT use the constructor's `host`/`port` because we mount under uvicorn-driven FastAPI; FastMCP's own `run()` is for standalone servers.
- **Tool registration:** `@mcp.tool()` decorator OR `mcp.add_tool(fn, name=..., description=...)`. Use the latter for the declarative `_TOOL_SPECS` pattern — keeps registrations data-driven.
- **HTTP ASGI mount:** `mcp.streamable_http_app()` returns a Starlette app. Mount it on FastAPI with `app.mount("/mcp", mcp.streamable_http_app())`.
- **Session manager:** lazily created on first `streamable_http_app()` call. Lifecycle: `async with mcp.session_manager.run(): ...` inside the FastAPI lifespan. The session manager IS the lifecycle holder for streamable-HTTP — exiting the `async with` block tears it down.
- **Client side:** `from mcp.client.streamable_http import streamablehttp_client` — async generator yielding `(receive_stream, send_stream, get_session_id_callable)`. Pair with `mcp.client.session.ClientSession`. For tests, this works against the FastAPI TestClient by using `httpx.AsyncClient` as the transport — but verify at implementation time; the simplest path may be spinning up uvicorn on a free port and pointing the client at it.
- **Context object:** the `Context` parameter on tool functions provides access to `session_id`, `request_id`, etc. Add `ctx: Context` to the wrapper for `hydrate_email`; FastMCP recognizes the annotation and injects it without exposing it in the tool schema.

### How the 11 verbs map to wrapper signatures

| Verb | Function signature (verb side) | MCP-facing kwargs | Server-injected |
|------|--------------------------------|-------------------|-----------------|
| `find_emails` | `(filter: FindEmailsFilter, *, db_path, limit=25)` | `filter`, `limit` | `db_path` |
| `hydrate_email` | `(email_id: str, *, db_path, session_id)` | `email_id` | `db_path`, `session_id` (from `ctx`) |
| `get_thread` | `(thread_id: str, *, db_path)` | `thread_id` | `db_path` |
| `count_emails` | `(filter: FindEmailsFilter, *, db_path)` | `filter` | `db_path` |
| `get_sender_summary` | `(sender_address: str, *, db_path)` | `sender_address` | `db_path` |
| `propose_action` | `(email_id, action_type: str, payload=None, *, db_path)` | `email_id`, `action_type`, `payload` | `db_path` |
| `mint_grant` | `(action_type: str, email_ids: list[str], expires_at: str, *, db_path)` | `action_type`, `email_ids`, `expires_at` | `db_path` |
| `revoke_grant` | `(grant_id: int, *, db_path)` | `grant_id` | `db_path` |
| `cancel_action` | `(action_id: int, *, db_path)` | `action_id` | `db_path` |
| `revert_action` | `(action_id: int, *, db_path)` | `action_id` | `db_path` |
| `mint_sensitivity_token` | `(email_id: str, task_type: str, *, db_path)` | `email_id`, `task_type` | `db_path` |

For verbs taking a `FindEmailsFilter` model (`find_emails`, `count_emails`): the MCP tool input schema MUST nest the filter — i.e., the client supplies `{"filter": {"sender_address": "..."}, "limit": 5}`, NOT `{"sender_address": "..."}` flattened. Pydantic models are first-class in FastMCP tool schemas; this is the natural way.

### Rule references (read these before implementing)

- **AR-PAT-1 Rule C** (architecture §602–608) — verbs are the only code that touches SQL for the agent's benefit. `mcp_server.py` calls into verbs, not into `db/queries.py` or `db/connection.py`.
- **AR-PAT-1 Rule J** (architecture §AR-PAT-1 + Story 5-1 Dev Notes) — hydration discipline: projection by default, body on explicit hydrate, rate-limited 5/turn.
- **AR-PAT-4** (architecture §646–699) — error-as-data: verbs never raise to the agent; the MCP wrappers preserve this. **Verb-level errors** (the `error: VerbError` field on `<Verb>Out`) are returned as data, NOT as MCP protocol errors. Only **schema mismatches** in the input (AC-2) and **unexpected exceptions** in the wrapper (AC-8) become MCP-level errors.
- **AR-PAT-2** (architecture §580–590) — naming. MCP tool name = verb function name verbatim. snake_case throughout.
- **AR-D7-1** (architecture §AR-D7-1) — `uvicorn mailbot_api.main:app` is the chat-serving process. The MCP server runs as part of this same `uvicorn` process (per Story 1-2 architecture call-out, per epics.md AC-1 "the MCP server runs as part of the uvicorn process on the same port (8000)"). NO separate process.
- **FR-7.3** (architecture §660–680) — structured JSON logging. Every MCP tool dispatch emits one log line (AC-8). The shape matches the canonical Router log shape.
- **Rule F** (architecture §660–680 + Rule F definition) — never log secrets, full email bodies, or raw Graph URLs. The MCP wrapper logs MUST sanitize. `email_id` is fine to log (it's a stable Graph handle, not PII per the existing convention); raw `query` substrings are not.

### Story 1-2 + Story 2-10 integration anchors

- `mailbot_api/main.py` already has a fully-fledged lifespan (Stories 1-2, 1-3, 1-8, 2-2, 2-4, 2-5, 2-8, 2-9, 3-3). The MCP mount is the **last lifespan section** before `yield` — it depends on the Router being live.
- The existing lifespan exposes `app.state.db_path`, `app.state.policy_stop_event`, `app.state.policy_watcher_task`, `app.state.lane_scheduler`. Add `app.state.mcp_server` (the FastMCP instance) for parity.
- The `_check_bearer_auth` pattern used by `/v1/chat/completions` (Story 2-10) does NOT apply to the MCP transport. Hermes connects from inside the Docker network (`mailbot-net`); MCP auth is **out of scope** for this story (Story 5-4 wires the Hermes-side `mcp_clients` config). If MCP auth becomes a requirement, FastMCP supports `auth=AuthSettings(...)` at construction time — but do not invent a scheme this story.
- The OpenAI-compatible `/v1/chat/completions` (Story 2-10) and the MCP server `/mcp` are **two distinct surfaces** on the same `uvicorn` process. They share state via `app.state` but have independent transports.

### `MAILBOT_SKIP_MCP` env var convention

Mirrors the existing `MAILBOT_SKIP_DB` / `MAILBOT_SKIP_POLICY` / `MAILBOT_SKIP_PATTERNS` pattern:

```python
skip_mcp = get_secret_optional("MAILBOT_SKIP_MCP", "0") == "1"
...
if not skip_mcp:
    mcp_server = build_mcp_server(db_path=db_path)
    app.state.mcp_server = mcp_server
    async with mcp_server.session_manager.run():
        app.mount("/mcp", mcp_server.streamable_http_app())
        yield
else:
    yield
```

**Caveat:** mounting an ASGI app on FastAPI **after the app has started accepting requests** is unsupported in Starlette/FastAPI. The actual pattern needs the `app.mount(...)` call **before** the lifespan begins (i.e., at module top level or pre-`FastAPI(...)`-instantiation). The dev pass needs to verify which of these two patterns FastMCP 1.27.2 + FastAPI 0.136.1 supports:

- **Pattern A**: build the FastMCP at module import time (no `db_path` yet, since env vars may not be set), mount its ASGI app, and have the wrappers resolve `db_path` lazily from `app.state.db_path` at call time. Use `lifespan` only for `session_manager.run()`.
- **Pattern B**: rebuild the routing table inside the lifespan (Starlette's `Router` supports `add_route` mutations even after app construction — but the lifespan `yield` semantics may interfere).

**Pattern A is preferred** — cleaner, matches the FastMCP example in the SDK README. The implementation should bind `db_path` resolution to a closure that reads `app.state.db_path` at call time, not at `build_mcp_server` time. Tests can either set `MAILBOT_DB_PATH` before importing `main.py` (existing test pattern) OR pass `db_path` directly to `build_mcp_server` for unit-level mcp_server testing without FastAPI.

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. No `.tsx`/`.vue`/`.svelte` files. UI nouns in ACs (none in this story — all ACs are server-side or test-side) would refer to Discord-rendered text. **Step 2.4.5 (UI-Scope Pre-Flight) is N/A.** Step 2.4.7 (Middleware-Real-Bootstrap) is reframed around the MCP transport: this story ships a new chat-serving endpoint (`POST /mcp/*`) — the gate is satisfied by AC-6's integration tests, which exercise the FastAPI TestClient against the real lifespan with real verbs hitting real SQLite.

### Why `ask_router` is intentionally excluded from MCP registration

`ask_router` is the Router's dispatch surface. Hermes-as-agent's path to LLM inference is the OpenAI-compatible `/v1/chat/completions` endpoint (Story 2-10), which internally calls `ask_router(task_type="hermes_aux", ...)`. Re-exposing `ask_router` as an MCP tool would let the agent call any model with any `task_type` — bypassing the policy-driven model selection, the budget guard, the sensitivity precondition layer, and the per-call refusal threshold. Cost-discipline center (Epic 2's whole point) only works if `ask_router` has exactly **one** entry path from the agent: `/v1/chat/completions`. Story 5-4 wires Hermes to call `/v1/chat/completions` for its model inference and the MCP server for tool invocations — two distinct surfaces, two distinct trust boundaries.

### Why `pause_router` / `resume_router` / `cost_breakdown` / `reset_degraded_mode` defer to Story 5-6

These are the verb-side handlers for Discord slash commands (`/pause`, `/resume`, `/cost`, `/budget reset`). Story 5-6 ships the slash-command dispatcher and is the right place to wire them as MCP tools — the dispatcher needs to map slash-command shapes to MCP tool calls in one coherent change, and the tier/authorization wiring (e.g., who can `/pause`) lives there. Exposing them this story would leave the wiring incomplete (the verbs would be MCP-callable but unreachable from Discord).

### Test isolation note

Per the existing test pattern in `tests/integration/test_chat_completions_endpoint.py`, every test using the FastAPI lifespan must clean up Router state via:

```python
_reset_policy_snapshot_for_test()
_reset_registry_for_test()
_reset_rate_limiter_for_test()
_reset_semaphore_registry_for_test()
_reset_guard_for_test()
_reset_loop_detector_for_test()
_reset_pause_state_for_test()
```

…in an autouse fixture. AC-6's tests adopt the same pattern. Additionally, this story's tests need to clear the per-session hydration counter dict + the `last_hydration_at` dict (both module-level in `mcp_server.py`); add `_reset_mcp_session_state_for_test()` to the cleanup.

### Existing tests that must remain green

The 693 baseline tests touch many surfaces. The MCP mount adds a route to the FastAPI app, which shouldn't disturb existing routes — but verify the existing `/health`, `/v1/health`, `/v1/chat/completions`, `/v1/embeddings` integration tests still pass after the mount. If any existing test currently asserts the **exact** list of mounted routes, update it.

### References

- [Source: epics.md Story 5.2](../planning-artifacts/epics.md)
- [Source: architecture.md §HTTP framework, §MCP server, §Communication Patterns, §Naming Patterns, §Format Patterns](../planning-artifacts/architecture.md)
- [Source: Story 5-1 — verb signatures, schemas.py, Rule J](./5-1-read-side-verbs-projection-first-data-window-for-the-agent.md)
- [Source: Story 4-2 — propose_action verb shim pattern](./4-2-pending-actions-and-action-grants-and-action-history-schema-and-propose-action-verb.md)
- [Source: Story 4-7 — mint_sensitivity_token + AR-D12-1 ephemerality](./4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md)
- [Source: Story 2-10 — `/v1/chat/completions` lifespan + bearer auth + integration test pattern](./2-10-cost-slash-command-and-hermes-aux-routing-via-v1-chat-completions-and-caller-origin-tracking.md)
- [Source: MCP Python SDK 1.27.2 — `from mcp.server.fastmcp import FastMCP`; `.add_tool`, `.streamable_http_app`, `.session_manager.run()`; client via `mcp.client.streamable_http.streamablehttp_client` + `ClientSession`]

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-story-run dev pass

### Debug Log References

### Completion Notes List

- Shipped `mailbot_api/mcp_server.py` exposing 11 verbs (5 read + 6 write) as MCP tools via `FastMCP` 1.27.2. Excluded by design (per AC-1 + story rationale): `ask_router` (cost-discipline center — Hermes uses `/v1/chat/completions`), `cost_breakdown` / `reset_degraded_mode` / `pause_router` / `resume_router` (deferred to Story 5-6 alongside the slash-command dispatcher), `reset_hydration_count` (server-internal lifecycle helper).
- Per-call dependency injection (AC-3): `db_path` resolves lazily via closure on a module-private `_ServerContext` dataclass (`build_mcp_server(db_path=...)` for tests; `set_db_path(server, ...)` exists as a public hook for production although the lifespan now builds a fresh server per startup and binds eagerly). `session_id` for `hydrate_email` derived from `id(ctx.session)` — stable per MCP transport session, never exposed in tool schema.
- Per-turn hydration reset (AC-4): `_HYDRATION_TURN_RESET_SECONDS = 30`. Activity-driven — the wrapper calls `reset_hydration_count(sid)` if 30s elapsed since the last call on that session_id. Implementation lives in the MCP server's `hydrate_email` wrapper, NOT in the verb itself (keeps the verb pure / clock-free per Story 5-1 design).
- FastAPI mount strategy (AC-5): the initial Pattern A (module-level `app.mount("/mcp", _mcp_server.streamable_http_app())`) broke `TestClient` reuse across tests because `StreamableHTTPSessionManager` binds to its construction-time event loop. Switched to **per-lifespan mount** — `lifespan()` builds a fresh `FastMCP`, calls `.streamable_http_app()` to lazily create the session manager, enters `session_manager.run()` on the AsyncExitStack, then appends `Mount("/mcp", app=streamable_app)` to `app.router.routes`; teardown pops the mount. Single app, multi-lifespan safe. Also required calling `streamable_http_app()` BEFORE `session_manager` access — the latter is lazy and raises if accessed first.
- Boundary check (AC-7): implements the verb-import-isolation rule that was deferred in Story 5-1 AC-8. `_VERBS_IMPORT_ALLOW` covers the 17 verbs/sibling modules + `mailbot_api/mcp_server.py`. Also added `_FASTMCP_IMPORT_ALLOW = {"mailbot_api/mcp_server.py"}` so the FastMCP dependency stays localized. Both `import X` and `from X import ...` shapes covered.
- Logging (AC-8): every tool dispatch emits one of `mcp.tool.ok` / `mcp.tool.error_as_data` / `mcp.tool.crash` with `tool`, `session_id`, `latency_ms`, and (for error-as-data) `error_code`. `db_path` never logged. Argument values not logged at INFO; the structured logger's existing sanitizer handles any incidental key/value bleeding.
- Test transport choice: used the SDK's in-memory `create_connected_server_and_client_session` helper rather than spinning up uvicorn + the streamable-HTTP client — much faster (~2s for 18 tests) and exercises the same `FastMCP` tool dispatch + Pydantic schema derivation that the HTTP transport relies on. The HTTP-transport path is covered indirectly by the FastAPI lifespan tests that build + mount the server (no chat-completions regressions after Story 5-2).
- 711 tests pass (+18 net from 693 baseline), 2 skipped (pre-existing opt-in real-Ollama). All 4 gates green.

### File List

NEW:

- mailbot_api/mcp_server.py
- tests/integration/test_mcp_server.py
- _bmad-output/implementation-artifacts/5-2-mcp-server-exposing-verbs-as-tools.md
- _bmad-output/implementation-artifacts/5-2.pre-review.md

UPDATED:

- mailbot_api/main.py — module docstring extended for Story 5-2; lifespan builds + mounts the FastMCP streamable-HTTP app per startup with `MAILBOT_SKIP_MCP=1` bypass; AsyncExitStack manages session-manager lifecycle and mount cleanup; CR-6 fix adds `mcp.startup.skipped` warning log when `db_path` unavailable
- scripts/check_boundaries.py — added `_VERBS_IMPORT_ALLOW` + `_FASTMCP_IMPORT_ALLOW` checks (verb-import isolation + FastMCP localization); covers both `import X` and `from X import Y` shapes; CR-5 fix adds dedicated check for `from mailbot_api import verbs` indirect-bypass shape
- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-2 backlog → ready-for-dev → in-progress → review → done; last_updated bumped
- _bmad-output/implementation-artifacts/story-run-flags.md — appended Story 5-2 section + Story 5-2 Manual Verification record

## Completion Notes

### 2026-06-02 — autonomous-story-run close

Story 5-2 closed by autonomous-story-run after Phase 3.5 manual verification PASS (5/5 checkpoints walked end-to-end). 7 CR findings applied (1 HIGH, 4 MEDIUM, 3 LOW = 8 in counts but reconciled to 7 unique items after `_VERBS_IMPORT_ALLOW` ESCALATE closure). Final test count: 714 (+21 net from 693 baseline = 18 initial + 3 CR-driven). All 4 gates green. Story `done`.

Per-lifespan MCP mount strategy is the canonical pattern any future module mounting an anyio-task-group-based session manager should follow — see `mailbot_api/main.py` Story 5-2 lifespan section. Story 5-4 (Hermes container config) is the next consumer of this surface; Story 5-6 (slash-command dispatcher) extends `_TOOL_DESCRIPTIONS` from 11 → 15.
