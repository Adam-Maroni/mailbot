---
baseline_commit: aa87929
---

# Story 6.20: Sensitivity-token handshake gate relocation to dispatch_tool_call — F28 closure

Status: done

> **Filed 2026-06-06** during Story 6-6.5 fifth-pass live walk. **F28 CRITICAL — PRIVACY INVARIANT VIOLATION**. Hermes's Haiku-4.5 main-inference drafted the reply INLINE in its own `chat_completions_tool_call` (instead of dispatching the `draft_reply` MCP tool); Story 4-7's sensitivity-token gate at the `ask_router(task_type='draft_reply')` precondition layer never fires for that path. Sensitive email body (family-medical content from CP-B fixture) reached cloud API at `router_calls.id=6444` without `mint_sensitivity_token` mediation. **Bug class:** the gate enforces at the WRONG architectural layer for the actual production deployment.
>
> **Adam-decided 2026-06-06 (commit `aa87929`):** **Option A + strictest gate-placement.** Relocate the sensitivity gate to `dispatch_tool_call`'s precondition layer AND broaden it to gate ALL `chat_completions_tool_call` when ANY referenced email has sensitivity ∈ {sensitive, confidential} — not just when `email_id` is passed as a `dispatch_tool_call` parameter. Preserve Story 4-7's existing `ask_router(draft_reply)` gate as defense-in-depth for non-Hermes callers.

## Story

As Adam,
I want the sensitivity-token handshake enforced upstream of Hermes's inline drafting path — at the `dispatch_tool_call` precondition layer, covering ALL email_ids referenced anywhere in the chat-completions request (messages OR tool args) — and the existing `ask_router(draft_reply)` gate preserved as defense-in-depth for non-Hermes callers,
So that no sensitive or confidential email body can reach a cloud LLM via any path Hermes might take, and the FR-2.3 + NFR-PRIV-2 invariants hold against the actual production architecture (Hermes as the main-inference router), not just the originally-modeled architecture (agent dispatching `draft_reply` directly).

## Acceptance Criteria

### AC-1 — Email-id resolution from `chat_completions_tool_call` request payload

`mailbot_api/router/router.py` SHALL expose (or inline) a helper that resolves the union of email_ids referenced by any incoming `dispatch_tool_call` request. The helper resolves from BOTH sources:

1. **Tool-call arguments** in any `assistant`-role message inside `messages` that carries `tool_calls`: parse each `tool_calls[i].function.arguments` (a JSON string) and collect every `email_id` field at any nesting depth. (Multi-tool-call assistant messages are valid per OpenAI spec; iterate all.)
2. **Tool-result content** in any `tool`-role message inside `messages`: parse `content` (when JSON-shaped) and collect every `email_id` field at any nesting depth.

**Why both:** the F28 fixture path lands the sensitive body via tool_result content (`hydrate_email` return), but Hermes can also reference email_ids via fresh tool_call arguments (e.g., a `propose_action` reference inside the same chat completion). Both must be in scope to enforce the strictest-placement rule.

**Parse failure semantics:** if a `tool_calls[i].function.arguments` string is not valid JSON (or a `tool`-role `content` field is not valid JSON), the helper SHALL skip that payload silently — the malformed argument WILL surface as a downstream tool-dispatch error and is not a sensitivity-gate concern. A structured DEBUG log SHALL fire (`event="dispatch_tool_call.arg_parse_failed"`, fields: `tool_call_index` OR `message_index`, `exception_type`) but no token value is logged.

**Nesting:** the helper SHALL traverse nested JSON (dict + list) and collect every value at a key named `email_id` (exact match, case-sensitive). Multiple occurrences are deduped at collection time.

**Tested with:**
- Empty messages → empty set
- `tool_calls=[{function: {arguments: '{"email_id": "e1"}'}}]` → `{"e1"}`
- Two tool_calls referencing the same id → `{"e1"}` (deduped)
- Tool-result content `{"ok": true, "email": {"email_id": "e2", "subject": "..."}}` → `{"e2"}`
- Mixed: tool_calls reference `e1`, tool_result references `e2` → `{"e1", "e2"}`
- Nested: `{"args": {"primary": {"email_id": "e3"}, "others": [{"email_id": "e4"}]}}` → `{"e3", "e4"}`
- Malformed JSON in `tool_calls[].function.arguments` → empty set + DEBUG log fired
- The `email_id` resolver helper is `_resolve_email_ids_from_messages(messages) -> set[str]` (or whichever single-call shape the dev picks); it MUST be a pure function (no DB I/O) for testability.

### AC-2 — Gate firing in `dispatch_tool_call`'s precondition layer

`dispatch_tool_call(...)` in [mailbot_api/router/router.py](../../mailbot_api/router/router.py#L1089) SHALL extend its current sensitivity-precondition block (currently at lines 1204–1272, scoped to the single `email_id` parameter) to ALSO process the email-id set returned by AC-1's resolver. The full enforcement is:

1. **Build the email-id set under audit:** `audit_ids = ({param_email_id} if param_email_id else set()) ∪ resolve_email_ids_from_messages(messages)`. If `audit_ids` is empty: no gate fires (existing behavior unchanged); proceed to dispatch. If `audit_ids` is non-empty: continue.

2. **For each `eid ∈ audit_ids`** (deterministic iteration order: `sorted(audit_ids)` so test assertions are stable): fetch `(sensitivity, sensitivity_at)` via the existing `EMAIL_SENSITIVITY_SELECT` query. Apply the existing 3-state logic:
   - `(None | sensitivity_at IS NULL)` → return `ToolCallResult(ok=False, error=RouterError(code=SENSITIVITY_NOT_CLASSIFIED, message="email {eid} sensitivity must be classified before any other Router task", retryable=False))`. **Message MUST include the offending `email_id`** so the caller can act (the existing single-id message omits it; preserving that omission is acceptable on the single-id legacy branch but the new multi-id branch SHALL include the id since the caller may have referenced N emails and needs to know which one tripped the gate).
   - `sensitivity == "confidential"` AND `_API_BOUND_MODEL_RE.match(model)` → return `ToolCallResult(ok=False, error=RouterError(code=SENSITIVITY_BLOCKS_API, message="confidential email {eid} admits no API override", retryable=False, model_attempted=[model]))`. **NFR-PRIV-2:** no token unlocks this path; refusal is unconditional even if a `confirmation_token` was supplied.
   - `sensitivity == "sensitive"` AND `_API_BOUND_MODEL_RE.match(model)`: requires a valid `confirmation_token` matching `(eid, _TOOL_CALL_TASK_TYPE)`. If no token supplied: `SENSITIVITY_BLOCKS_API` with `message="sensitive email {eid} requires per-session confirmation token to escalate to API"`. If token supplied: attempt consume via `mailbot_api.actions.sensitivity_tokens.consume(token, eid, _TOOL_CALL_TASK_TYPE)`.

3. **Token-consume semantics across N email_ids — IMPORTANT:** the existing `confirmation_token` parameter is a SINGLE string. With N sensitive email_ids in scope, the agent must hold N tokens to dispatch. **For AC-2 v1: ONE supplied `confirmation_token` only consumes against the FIRST sensitive email_id encountered in `sorted(audit_ids)` order**; if more than one sensitive email_id is in `audit_ids`, the second (and onward) sensitive id falls through to `SENSITIVITY_BLOCKS_API` (token-missing). This matches Story 4-7's single-token contract and avoids overloading the parameter; multi-token handshakes are explicitly DEFERRED as a future story (file a follow-up if multi-sensitive-id refs become a frequent Hermes pattern).
   - Consume crashes (defensive `try/except`) are handled identically to the existing single-id path: log `event="sensitivity.token.consume_crash"` with `email_id=eid, task_type=_TOOL_CALL_TASK_TYPE, exception_type=...`, treat as consume failure (`NEEDS_SENSITIVITY_CONFIRMATION`).
   - On successful consume: capture `(grant_id, minted_at_iso)` into `_sensitivity_grant_id` + `_sensitivity_grant_minted_at` for the audit row (AC-3). The grant SHALL bind to the consumed email_id; if subsequent sensitive ids would require their own tokens (multi-token deferred), the gate returns `SENSITIVITY_BLOCKS_API` BEFORE dispatch — no audit row writes a half-consumed grant.

4. **Normal-email with token supplied:** retain the existing `_logger.warning("confirmation_token passed for normal email; ignoring", ...)` event for the single-id path. For the multi-id path, log when ANY referenced email is normal AND a token was supplied (matches the existing "agent confused about sensitivity" observability signal).

5. **No audit row on gate refusal.** Same as today: a precondition-layer refusal does NOT write a `router_calls` row. The refusal is a routing-side decision; only dispatch outcomes (success or adapter failure) produce audit rows.

### AC-3 — Audit row carries `sensitivity_grant_id` + `sensitivity_grant_minted_at`

On successful consume + successful dispatch, the `router_calls` row written by `dispatch_tool_call`'s `finally` block (currently lines 1451–1472) SHALL carry:
- `sensitivity_grant_id` = the consumed token's `grant_id`
- `sensitivity_grant_minted_at` = the original mint timestamp (NOT the consume time — CR-4-7-6 contract carried over)

The columns already exist on `router_calls` (from Story 4-7 via 006_router_calls schema). No migration needed.

Forensic query reachability: `SELECT * FROM router_calls WHERE task_type='chat_completions_tool_call' AND sensitivity_grant_id IS NOT NULL` SHALL return one row per successful sensitive-email tool-call dispatch with the grant_id matching what `mint_sensitivity_token` produced.

### AC-4 — Story 4-7's `ask_router(draft_reply)` gate preserved as defense-in-depth

The existing precondition layer in `ask_router(...)` (lines 262–372) SHALL remain untouched in behavior. Story 4-7's gate continues firing for any non-Hermes caller that invokes `ask_router(task_type='draft_reply', email_id=..., confirmation_token=...)` directly. This includes:
- Future skill modules that compose `draft_reply` Router calls explicitly
- Any internal helper that bypasses Hermes and calls `ask_router` directly
- Test harnesses asserting the original Story 4-7 contract

**Verification:** the existing Story 4-7 integration tests `tests/integration/test_router_sensitivity_handshake.py` MUST stay green unmodified. No edits to that file.

### AC-5 — Regression tests covering all 3 surfaces

`tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` (new file — per project convention of `test_<surface>_<finding-id>.py` per Stories 6-13/6-14/6-15/6-16/6-17 precedent):

1. **`test_resolver_collects_email_ids_from_assistant_tool_calls`** — pure-function unit test of AC-1's resolver. Input: messages with one `assistant` tool_call carrying `{"email_id": "e1", "subject": "x"}` as `arguments`. Assert resolver returns `{"e1"}`.
2. **`test_resolver_collects_email_ids_from_tool_result_content`** — input: `tool`-role message with JSON content carrying nested `email_id`. Assert collected.
3. **`test_resolver_dedupes_repeated_ids`** — input: two tool_calls referencing the same id. Assert resolver returns 1-element set.
4. **`test_resolver_traverses_nested_payloads`** — input: deeply-nested dict/list mixed structure with two distinct `email_id` values. Assert both collected.
5. **`test_resolver_handles_malformed_tool_call_arguments_json`** — input: one tool_call with `arguments='{"not_json'`. Assert resolver returns empty set + DEBUG log fired (capture via caplog).
6. **`test_dispatch_tool_call_gates_on_sensitive_email_in_tool_result_content`** — the F28 reproducer. Build a tool-result message carrying `{"email_id": "e_sens", "subject": "...", "body_text": "..."}` where `e_sens` has `sensitivity='sensitive'`. Invoke `dispatch_tool_call(messages=[...], tools=[...], model="claude-haiku-4-5-20251001", email_id=None, confirmation_token=None)`. Assert result is `ToolCallResult(ok=False, error.code=SENSITIVITY_BLOCKS_API, error.message contains "e_sens")`. Assert NO `router_calls` row written.
7. **`test_dispatch_tool_call_gates_on_confidential_email_in_tool_result_content_unconditional`** — same shape as #6 but `sensitivity='confidential'` AND a non-None `confirmation_token` is supplied. Assert refusal with `SENSITIVITY_BLOCKS_API` (NFR-PRIV-2: token does not unlock confidential).
8. **`test_dispatch_tool_call_allows_sensitive_email_when_valid_token_supplied`** — mint a token via `sensitivity_tokens.mint(email_id="e_sens", task_type="chat_completions_tool_call")`. Invoke `dispatch_tool_call(messages=[<tool-result with e_sens>], tools=[...], model="claude-haiku-...", confirmation_token=<minted token value>)`. Use a `MockTransport`-equipped adapter so the dispatch returns a synthetic ok. Assert dispatch succeeded AND `router_calls.sensitivity_grant_id` matches the minted token's `grant_id`.
9. **`test_dispatch_tool_call_unchanged_for_normal_emails_in_messages`** — input messages reference a normal-sensitivity email. Assert dispatch proceeds without refusal AND `sensitivity_grant_id` is NULL on the audit row.
10. **`test_dispatch_tool_call_unchanged_when_no_email_ids_in_messages_or_param`** — input has no `email_id` field anywhere. Assert behavior identical to today (no gate fires; existing tests continue to pass).
11. **`test_dispatch_tool_call_gates_with_email_id_param_only_legacy_path`** — invoke with `email_id="e_sens"` as a parameter (no email_id in messages). Assert the gate still fires per the existing 1207-1272 single-id path (now subsumed by the multi-id path); regression-coverage for the legacy parameter surface.
12. **`test_dispatch_tool_call_audit_row_omits_grant_id_on_refusal`** — refusal path MUST NOT write a `router_calls` row. Assert row count unchanged after refusal.

`tests/integration/test_router_sensitivity_handshake.py` (Story 4-7 existing): unchanged; existing tests stay green to validate AC-4.

### AC-6 — Cross-doc updates

The relocation changes the architectural boundary at which the sensitivity gate fires. Document the change at:

1. **`docs/SOUL.md`** (defender persona) — the section explaining how the defender refuses on sensitive without a confirmation step. Update to note: "the gate now fires UPSTREAM of any drafting — including Hermes's inline drafting via chat-completions tool-calling. The defender doesn't need to refuse in chat; the router refuses before the model ever sees the body."
2. **`AGENTS.md`** (or the project's canonical agent-rules doc — likely a Rule entry covering "sensitivity gate location"; verify by `Grep` for `sensitivity` in AGENTS.md before editing). Update or add a rule entry stating the gate's enforcement boundary is `dispatch_tool_call`'s precondition layer, gating on the union of email_ids in messages + tool args.
3. **`hermes-config/skills/mailbot/SKILL.md`** — the `propose_action` flow section. Add a note: "if the email is sensitive or confidential, mint a `confirmation_token` via `mint_sensitivity_token` BEFORE attempting any chat-completions call that references the email_id — including inline drafting. Otherwise the router refuses at `SENSITIVITY_BLOCKS_API`."
4. **`_bmad-output/implementation-artifacts/epic-6-run-flags.md § F28`** — update from `OPEN` to `RESOLVED` with the closing commit reference + the AC-evidence summary (which router.py functions touched, which test file added, which docs updated).

### AC-7 — MANDATORY-CR per §5.12

The §5.12 cadence verdict is **MANDATORY-CR** — multiple criteria fire:

1. **External transport / privacy invariant** — the gate enforces a CRITICAL privacy invariant (sensitive bodies never reach cloud LLMs without an explicit operator handshake). Privacy-invariant code is a §5.12 criterion 1 (external/security surface).
2. **Cross-story load-bearing seam** — touches Stories 3-3 (sensitivity precondition AC-5), 4-7 (handshake gate at `ask_router`), 5-1 (`hydrate_email` body exposure), 5-2 (MCP transport), 5-9 (draft_reply orchestrator), 6-9 (F11 `dispatch_tool_call` sibling). Six prior stories' invariants must continue holding — §5.12 criterion 6 (cross-story load-bearing).
3. **State-machine seam** — the precondition layer is a routing-side state machine (paused → policy → degraded → sensitivity → dispatch). Adding the multi-id branch changes the state-machine transitions in `dispatch_tool_call`; cross-story state-machine seams are §5.12 criterion 3.

Minimum one CR pass before done-flip. Review model SHALL be different from dev model (Sonnet 4.6 if dev is Opus 4.7). Reviewer focus: (a) the email-id resolver pure-function correctness (deeply nested edge cases, malformed JSON, multi-tool-call assistant messages), (b) the multi-id iteration order determinism (test stability), (c) NO sensitive payload ever logged (token value, email body, email subject), (d) the Story 4-7 contract is preserved verbatim at `ask_router`, (e) the F28 reproducer test actually fails against the pre-fix code and passes against the post-fix code (forensic correctness).

## Tasks / Subtasks

- [x] **Task 1 — Implement `_resolve_email_ids_from_messages(messages) -> set[str]`** as a pure helper inside `mailbot_api/router/router.py` near `dispatch_tool_call`. Shipped at [mailbot_api/router/router.py:1053-1138](../../mailbot_api/router/router.py#L1053-L1138). Walks (a) `assistant.tool_calls[].function.arguments` (both dict + Pydantic-model shapes via polyfill), (b) `tool`-role `content`. Recursive `_walk` collects every `email_id` at any depth. Set-dedupes. Malformed JSON → DEBUG log + skip.
- [x] **Task 2 — Extend `dispatch_tool_call`'s precondition block** — shipped at [mailbot_api/router/router.py:1288-1442](../../mailbot_api/router/router.py#L1288-L1442). `_audit_ids = ({param_email_id} if param_email_id else set()) ∪ _resolve_email_ids_from_messages(messages)`. Iterates `sorted(_audit_ids)`. Token-consume binds to FIRST sensitive id only (multi-token deferred); subsequent sensitive ids fall through to SENSITIVITY_BLOCKS_API. Refusal returns early (zero `router_calls` rows).
- [x] **Task 3 — Audit-row plumbing.** The new multi-id branch threads `_sensitivity_grant_id` + `_sensitivity_grant_minted_at` through the same captured locals as the legacy path. The `finally` block at line 1602-1623 writes them unchanged. AC-5.8 test asserts grant_id round-trip end-to-end.
- [x] **Task 4 — Write `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py`** — shipped with 12 tests (`pytest --collect-only -q` confirms count). 5 resolver unit tests + 7 integration tests (F28 reproducer, confidential-unconditional, sensitive+valid-token success+grant_id, normal-passthrough, no-email-id-anywhere, legacy single-id-param regression, refusal-writes-zero-router_calls counter). All 12 green on first run. Uses local `_FakeToolAdapter` for tests needing successful dispatch + canonical `_seed_email` shape from Story 4-7's test harness.
- [x] **Task 5 — Cross-doc updates** per AC-6:
  - [x] `hermes-config/SOUL.md` — added "Banned anti-pattern 3.5" extending sensitive-content discipline rules
  - [x] `hermes-config/AGENTS.md` — added "Rule Q — Sensitivity-Gate Enforcement Boundary" between Rule P and Rule R; banned-anti-patterns subsection
  - [x] `hermes-config/skills/mailbot/SKILL.md` — added "Inline-drafting variant — F28 awareness" subsection under propose_action draft-reply turn structure
  - [x] `_bmad-output/implementation-artifacts/epic-6-run-flags.md` — added "## F28 — RESOLVED (2026-06-06, Story 6-20)" closing block with implementation summary + test evidence + cross-doc inventory + live-walk dependency note
- [x] **Task 6 — Pre-Review Self-Audit Gate (Step 2.3.5)** — `6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.pre-review.md` shipped. All 5 sections present + 12-check §5 Posture Audit. §5.12 verdict: **`MANDATORY-CR`** (3 criteria fire: privacy-invariant, cross-story load-bearing seam, state-machine seam). §5.4 multi-consumer scan confirms single prod caller (`mailbot_api/main.py:670`). §5.7 confirms zero new module-level mutable state. §5.10 confirms router-precondition layer is the correct architectural enforcement seam.
- [x] **Task 7 — MANDATORY-CR pass** per AC-7 / §5.12 COMPLETE. Sonnet 4.6 reviewer, 11 findings total: 4 patch (all APPLIED), 4 defer-with-rationale (accepted), 3 dismissed as noise. See Review Findings section below for one-bullet-per-finding dispositions.
- [x] **Task 8 — All gates green** at baseline +12 net: ruff clean, mypy --strict clean (123 files), boundary clean, pytest **1111 passed + 2 skipped + 3 deselected** (vs Story 6-17 baseline 1099+2+3 → +12 net). Story 4-7's `tests/integration/test_router_sensitivity_handshake.py` (6 tests) + Story 6-9's `tests/integration/test_chat_completions_tool_calling.py` (49 tests) both green unmodified — AC-4 defense-in-depth verified.

### Review Findings

(CR pass by claude-sonnet-4-6, 2026-06-06 — MANDATORY-CR per §5.12: 3 criteria. 4 patch findings, 4 deferred, 3 dismissed.)

- [x] [Review][Patch] **CR-6-20-1 (MEDIUM) — APPLIED** — swapped `_logger.exception` → `_logger.error` WITHOUT `exc_info` at [mailbot_api/router/router.py:1400-1414](../../mailbot_api/router/router.py#L1400-L1414). Future DB-backed registry that embeds the token value in its exception message will NOT leak via captured traceback; the `exception_type` field in `extra` remains the load-bearing diagnostic. Inline comment cites CR-6-20-1 rationale. Legacy `ask_router` symmetric pattern at line 328 deferred per CR's own carve-out (out of scope; file a follow-up if/when DB-backed registry ships).
- [x] [Review][Patch] **CR-6-20-2 (MEDIUM) — APPLIED** — `_clean_state` fixture pre-yield setup at [tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py:100-124](../../tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py#L100-L124) now includes `_reset_registry_for_test()` and `_reset_policy_snapshot_for_test()`. Tests 6/7/11/12 (which depend on gate refusing BEFORE dispatch) now guaranteed clean adapter registry + policy snapshot at start, regardless of prior-test leakage. Inline comment cites CR-6-20-2 rationale.
- [x] [Review][Patch] **CR-6-20-3 (LOW) — APPLIED** — `dispatch_tool_call` public docstring at [mailbot_api/router/router.py:1188-1213](../../mailbot_api/router/router.py#L1188-L1213) expanded under `Honors:` sensitivity-precondition bullet with the Story 6-20 multi-id contract + the single-token v1 first-sorted-sensitive-id semantics + multi-token v2 deferred + NFR-PRIV-2 confidential-unconditional. Future callers passing a token expecting all-or-nothing semantics now see the constraint in the docstring, not just the story Dev Notes.
- [x] [Review][Patch] **CR-6-20-4 (LOW) — APPLIED** — assertion at [tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py:539-547](../../tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py#L539-L547) tightened from disjunction (`"confirmation token" OR "e_sens"`) to exact wording (`"requires per-session confirmation token"`). A future regression changing the single-id legacy message shape will now be caught precisely. Inline comment cites CR-6-20-4 rationale.
- [x] [Review][Defer] **CR-6-20-D1 (MEDIUM) — Sorted-order token binding: token silently consumes against first sorted sensitive id; agent gets no feedback about which id consumed the token** [`mailbot_api/router/router.py:1364-1427`] — deferred, pre-existing design decision (single-token v1 contract, dev rationale accepted; multi-token v2 is the future expansion)
- [x] [Review][Defer] **CR-6-20-D2 (MEDIUM) — Per-id WARNING fires once per normal-sensitivity email when token supplied in a multi-id call** [`mailbot_api/router/router.py:1428-1443`] — deferred, pre-existing design decision (per-id forensic observability signal accepted; correlation is downstream consumer concern)
- [x] [Review][Defer] **CR-6-20-D3 (LOW) — Non-string `email_id` values (valid JSON, wrong type) silently skipped with no DEBUG log** [`mailbot_api/router/router.py:1076-1085`] — deferred, not in spec (AC-1 only specifies malformed JSON → DEBUG log; type-mismatch within valid JSON is not a parse failure)
- [x] [Review][Defer] **CR-6-20-D4 (LOW) — `_walk` has unbounded recursion depth; pathologically nested payload could trigger RecursionError** [`mailbot_api/router/router.py:1076-1085`] — deferred, extreme edge case not in scope; CPython ~1000 frame limit provides implicit bound

## Dev Notes

### Why this story exists (root-cause from F28 evidence)

The Story 4-7 sensitivity-token handshake was designed against the ORIGINAL Epic 5 architecture where:

- The agent is "the defender persona on Hermes" calling `draft_reply` as an explicit MCP tool
- `ask_router(task_type='draft_reply', email_id=...)` was the dispatch path
- The precondition layer at `ask_router` (lines 262-372) was the choke point

What the fifth-pass walk discovered (2026-06-06): the ACTUAL production architecture has Hermes drafting INLINE via `chat_completions_tool_call` — the dispatch never goes through `ask_router(draft_reply)`, so the gate never fires. The sensitive body lands in Hermes's `messages` (specifically the `tool`-role result of an earlier `hydrate_email` call) and then in Haiku's main inference for the same chat completion. `router_calls.id=6444` shows the API hit without any `sensitivity_grant_id`.

The fix moves the gate to where the actual chokepoint is: `dispatch_tool_call`'s precondition layer. AND broadens it to inspect the whole request payload, not just the optional `email_id` parameter (which `_chat_completions_tools_dispatch` doesn't pass — see [mailbot_api/main.py:670-681](../../mailbot_api/main.py#L670-L681)).

### Adam's option-A + strictest-placement decision (2026-06-06)

Adam picked Option A over Options B/C/D per `aa87929`:

- **Option A (chosen):** relocate to `dispatch_tool_call`. Single fix point, covers the Hermes path, preserves Story 4-7 as defense-in-depth.
- **Option B (rejected):** patch Hermes-config to NEVER inline-draft sensitive emails. Rejected because: relies on Hermes prompt honesty + can't be enforced at the router boundary; if Haiku hallucinates an inline draft despite the prompt, we still ship the body. The router boundary must be the canonical enforcement layer.
- **Option C (rejected):** add a separate `chat_completions_tool_call` policy entry with its own gate. Rejected because: complexifies the policy snapshot for one defense surface; the `dispatch_tool_call` precondition layer already has the right shape.
- **Option D (rejected):** redirect `propose_action SEND_REPLY` to mandatory `mint_sensitivity_token` flow first. Rejected because: doesn't cover non-propose-action inline drafting paths (the actual F28 surface).

Within Option A, Adam also picked **strictest placement**: gate ALL `chat_completions_tool_call` when ANY referenced email has sensitivity ∈ {sensitive, confidential}, not just when `email_id` is parameterized. Rationale: the agent might reference a sensitive email via tool-result content without ever passing it as a parameter; the gate must catch that.

### Why "first sensitive id only" for token consume (multi-id deferred)

Story 4-7's `confirmation_token` parameter is a single string. With N sensitive email_ids in scope, a single token can only consume against ONE. The choices:

1. **Single-token + first-id-only (this story):** token consumes against `sorted(audit_ids)[0]` if sensitive; the rest fall through to refusal. Forces the agent to either (a) reference fewer sensitive emails per call, or (b) mint N tokens and pack them into a list (future story).
2. **Multi-token parameter (future):** `confirmation_tokens: list[str] | None` that consumes against each sensitive id in order. Requires Hermes-side and Story 5-2 MCP-tool changes.
3. **Whole-call confirmation (alternative):** mint a single grant_id that authorizes the whole `dispatch_tool_call` payload. Requires a new mint API surface.

Adam's option A + strictest-placement does NOT explicitly carve out the multi-id token shape. Going with #1 for v1: simpler, preserves the Story 4-7 contract, sufficient for the F28 fix (Hermes typically references one email at a time inline). If multi-sensitive-id refs become a frequent Hermes pattern (file a follow-up + add the test counter-case), upgrade to #2.

### How the resolver should work — pseudocode

```python
def _resolve_email_ids_from_messages(messages: list[dict[str, Any]]) -> set[str]:
    """Walk every message; collect email_id at any nesting depth in
    (a) tool_calls[].function.arguments JSON strings on assistant messages,
    (b) content JSON strings on tool-role messages.
    Malformed JSON is silently skipped + logged at DEBUG.
    """
    found: set[str] = set()
    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "email_id" and isinstance(v, str):
                    found.add(v)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    for idx, m in enumerate(messages):
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "assistant":
            tool_calls = m.get("tool_calls") or []
            for tc_idx, tc in enumerate(tool_calls):
                try:
                    fn = tc.get("function") if isinstance(tc, dict) else None
                    args_str = fn.get("arguments") if isinstance(fn, dict) else None
                    if isinstance(args_str, str):
                        _walk(json.loads(args_str))
                except (json.JSONDecodeError, AttributeError, TypeError) as exc:
                    _logger.debug(
                        "dispatch_tool_call.arg_parse_failed",
                        extra={
                            "event": "dispatch_tool_call.arg_parse_failed",
                            "message_index": idx,
                            "tool_call_index": tc_idx,
                            "exception_type": type(exc).__name__,
                        },
                    )
        elif role == "tool":
            try:
                content = m.get("content")
                if isinstance(content, str):
                    _walk(json.loads(content))
            except (json.JSONDecodeError, TypeError) as exc:
                _logger.debug(
                    "dispatch_tool_call.arg_parse_failed",
                    extra={
                        "event": "dispatch_tool_call.arg_parse_failed",
                        "message_index": idx,
                        "exception_type": type(exc).__name__,
                    },
                )
    return found
```

**Note:** the dev agent SHALL adapt the implementation to fit project conventions (e.g., if `_chat_completions_tools_dispatch` converts tool_calls to a Pydantic model before dispatch, the resolver should accept either dict OR model shapes via `.get` + `getattr` polyfill). The pseudocode is illustrative, not normative.

### Multi-tool-call assistant messages — required to handle

OpenAI spec allows an `assistant`-role message to carry MULTIPLE `tool_calls` (the model produces N tool invocations in one inference step). Hermes does occasionally do this. The resolver MUST iterate all of them; the test `test_resolver_dedupes_repeated_ids` validates this.

### Token-consume crash defensive wrap (carry-over from CR-4-7-3(a))

The existing `dispatch_tool_call` already wraps `consume(...)` in a `try/except Exception` to prevent any future DB-backed token registry from leaking the token value into a traceback. The new multi-id branch SHALL preserve this exact pattern — same defensive wrap, same `consume_crash` log event.

### Why DEBUG-level (not WARNING) for malformed JSON

A malformed `tool_calls[].function.arguments` JSON string is a CALLER bug (Hermes or future agent produced bad JSON). Downstream tool-dispatch will surface it as an error to the caller. The sensitivity-gate concern is solely whether we MISSED an `email_id` reference — and DEBUG is sufficient observability for that diagnostic. WARNING would noise up logs for every malformed-tool-call dispatch.

### What MUST NOT change

- **`ask_router(...)`'s precondition layer (lines 262-372) stays verbatim.** AC-4 / Story 4-7 contract preserved.
- **`record_router_call` signature stays at its current shape.** `sensitivity_grant_id` + `sensitivity_grant_minted_at` columns already exist; no migration needed.
- **`sensitivity_tokens.mint/consume/sweep` API stays verbatim.** No changes to `mailbot_api/actions/sensitivity_tokens.py`.
- **The `confirmation_token` parameter on `dispatch_tool_call` stays at its current shape (`str | None`).** Multi-token shape is explicitly deferred.

### References

- [mailbot_api/router/router.py:1089-1473](../../mailbot_api/router/router.py#L1089-L1473) — `dispatch_tool_call` (the function being extended)
- [mailbot_api/router/router.py:1204-1272](../../mailbot_api/router/router.py#L1204-L1272) — current sensitivity-precondition block (the legacy single-id path)
- [mailbot_api/router/router.py:262-372](../../mailbot_api/router/router.py#L262-L372) — `ask_router`'s precondition layer (Story 4-7; STAYS VERBATIM — AC-4 defense-in-depth)
- [mailbot_api/main.py:625-681](../../mailbot_api/main.py#L625-L681) — `_chat_completions_tools_dispatch` (the Hermes call site that doesn't pass email_id today)
- [mailbot_api/actions/sensitivity_tokens.py](../../mailbot_api/actions/sensitivity_tokens.py) — `mint`/`consume`/`sweep` (unchanged)
- [mailbot_api/verbs/hydrate_email.py](../../mailbot_api/verbs/hydrate_email.py) — body-exposure surface (the source of `tool`-role content carrying sensitive bodies)
- [mailbot_api/verbs/propose_action.py](../../mailbot_api/verbs/propose_action.py) — verb that carries `email_id` in tool-call arguments (one of the resolver's input shapes)
- [tests/integration/test_router_sensitivity_handshake.py](../../tests/integration/test_router_sensitivity_handshake.py) — Story 4-7 tests (MUST stay green unmodified)
- [_bmad-output/implementation-artifacts/4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md](./4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md) — Story 4-7 (the existing gate at `ask_router`; AC-4 preserves)
- [_bmad-output/implementation-artifacts/6-9-chat-completions-tool-calling-openai-anthropic-translation-f11-closure.md](./6-9-chat-completions-tool-calling-openai-anthropic-translation-f11-closure.md) — Story 6-9 (F11 closure that shipped `dispatch_tool_call`)
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § F28` — full F28 finding text (CP-B walk evidence)
- Adam's option-A + strictest-placement decision: commit `aa87929` (epics.md amendment)

## Dev Agent Record

### Agent Model Used

- Dev: claude-opus-4-7 (Opus 4.7, 1M context) via autonomous-epic-run
- Code Review: claude-sonnet-4-6 (Sonnet 4.6, MANDATORY-CR per §5.12 — 3 criteria fire: privacy-invariant + cross-story load-bearing seam + state-machine seam) — to be dispatched at Step 2.4

### Debug Log References

- Pre-review self-audit: `6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.pre-review.md` (5 sections + 12-check §5 posture audit; §5.12 cadence verdict = MANDATORY-CR with 3 criteria firing).
- Architectural choice: gating at `dispatch_tool_call`'s precondition layer (between budget-guard/degraded-mode and adapter dispatch) preserves the §5.10 producer-boundary contract — refusal does NOT write a `router_calls` row, which mirrors Story 4-7's gate semantics. The resolver is a pure function with zero DB I/O; DB lookups happen in the dispatcher's iteration loop.
- Token-consume contract decision (single-token v1, multi-token v2 deferred): documented in story Dev Notes "Why 'first sensitive id only'". The Hermes single-email-per-call dominant pattern makes v1 correct for the production surface today. Future multi-token shape would be a `confirmation_tokens: list[str] | None` parameter expansion when signal demands it.
- Defensive token-consume wrap (preserved verbatim from Story 4-7 CR-4-7-3(a)): catches any future-exception-shape from `consume()` and logs `event="sensitivity.token.consume_crash"` WITHOUT the token value. Production refuses with NEEDS_SENSITIVITY_CONFIRMATION rather than leaking the token via traceback.

### Completion Notes List

- **F28 root cause closed via Option A + strictest-placement.** The Story 4-7 sensitivity-token gate was designed against the original Epic 5 architecture (agent dispatches `draft_reply` via `ask_router`). The actual production architecture is different: Hermes drafts INLINE via `chat_completions_tool_call` and never reaches `ask_router(draft_reply)`. The fix relocates the enforcement to `dispatch_tool_call`'s precondition layer AND broadens it to inspect the entire request payload (messages + tool args), not just the optional `email_id` parameter.
- **Email-id resolver is pure + testable in isolation.** `_resolve_email_ids_from_messages` walks `assistant.tool_calls[].function.arguments` (JSON-string per OpenAI spec) + `tool`-role `content` (JSON-string when MCP verbs return dict-shaped results). Recursive traversal handles nested dicts + lists at any depth. Dedupes via `set`. Malformed JSON is silently skipped + DEBUG-logged for caller-side bug visibility — the sensitivity-gate concern is solely that we did not MISS an `email_id`; downstream tool-dispatch will surface the malformed argument as its own error.
- **Multi-id iteration is deterministic.** `sorted(_audit_ids)` ensures audit trails and refusal messages are stable across test runs and forensic queries. The single-token-on-first-sensitive-id contract is acceptable for v1 given Hermes's single-email-per-call dominant pattern; multi-token v2 is the deferred future expansion.
- **Story 4-7 contract preserved verbatim.** `ask_router(...)`'s precondition layer (lines 262-372) is UNCHANGED. The 6 existing tests in `tests/integration/test_router_sensitivity_handshake.py` stay green unmodified, providing live verification that AC-4's defense-in-depth contract holds.
- **NFR-PRIV-2 invariant preserved on both gates.** Confidential admits NO override even with a token — verified at both `ask_router` (Story 4-7, unchanged) AND `dispatch_tool_call` (Story 6-20, AC-5.7 test).
- **Audit-row plumbing reuses the Story 6-9 finally block unchanged.** The `_sensitivity_grant_id` / `_sensitivity_grant_minted_at` locals thread through the new multi-id branch identically to the legacy single-id path. On successful consume + dispatch, the `router_calls` row carries `sensitivity_grant_id = consumed.grant_id` and `sensitivity_grant_minted_at = original_mint_time_iso` (CR-4-7-6 contract: real mint time, not consume time).
- **Refusal contract: zero `router_calls` rows.** Precondition-layer refusal is a routing-side decision; the audit trail captures only DISPATCH outcomes (success or adapter failure). Verified by AC-5.6 + AC-5.12 tests.
- **All 4 gates green:** ruff clean (1 import-order autofix), mypy --strict clean (123 files), boundary clean, pytest **1111 passed + 2 skipped + 3 deselected** (vs Story 6-17 baseline 1099+2+3 → +12 net from the 12 new F28 tests, matching AC-5 exactly).
- **Pre-review self-audit Step 2.3.5 gate satisfied.** Artifact ships with all 5 sections + 12-check §5 posture audit. §5.12 verdict: MANDATORY-CR with 3 §5.12 criteria firing (privacy-invariant + cross-story 6 prior stories + state-machine seam). Reviewer focus areas pre-spec'd in §5.12 of the audit.
- **MANDATORY-CR pass scheduled** for Step 2.4 of the autonomous-epic-run orchestrator (Sonnet 4.6 reviewer). Findings + dispositions will land in the Review Findings section above.

### File List

- `mailbot_api/router/router.py` (modified) — added `_resolve_email_ids_from_messages` pure helper (~80 LOC); extended `dispatch_tool_call`'s sensitivity precondition block to multi-id strictest-placement gate (replacing the legacy single-id path); preserved Story 4-7 `ask_router` precondition layer unchanged
- `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` (new) — 12 tests: 5 resolver pure-function unit tests + 7 integration tests (F28 reproducer via tool-result content, confidential-unconditional refusal even with token, sensitive+valid-token success with grant_id audit, normal-passthrough, no-email-id-anywhere unchanged, legacy single-id param regression, refusal writes zero router_calls rows)
- `hermes-config/SOUL.md` (modified) — added "Banned anti-pattern 3.5" extending sensitive-content discipline with the F28-aware drafting rule
- `hermes-config/AGENTS.md` (modified) — added "Rule Q — Sensitivity-Gate Enforcement Boundary" between Rule P and Rule R; covers both `ask_router` (defense-in-depth for non-Hermes callers) and `dispatch_tool_call` (Hermes-driven inline-drafting); banned-anti-patterns subsection
- `hermes-config/skills/mailbot/SKILL.md` (modified) — added "Inline-drafting variant — F28 awareness" subsection under the propose_action draft-reply turn structure
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md` (modified) — added "## F28 — RESOLVED (2026-06-06, Story 6-20)" closing block with implementation summary + test evidence + cross-doc inventory + live-walk dependency note
- `_bmad-output/implementation-artifacts/6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.md` (this file — story spec + Dev Agent Record + Tasks/Subtasks checks + Review Findings placeholder)
- `_bmad-output/implementation-artifacts/6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.pre-review.md` (new) — 5-section pre-review self-audit per Step 2.3.5 with `MANDATORY-CR` §5.12 cadence verdict
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — row 180 status: backlog → ready-for-dev → in-progress → review

### Change Log

- 2026-06-06 — Story 6.20 filed as STUB during Story 6-6.5 fifth-pass live walk (sprint-status.yaml row 180). F28 CRITICAL privacy invariant violation surfaced.
- 2026-06-06 — Adam's option A + strictest-placement decision committed at `aa87929`.
- 2026-06-06 — autonomous-epic-run create-story pickup: context-engineered AC structure (7 ACs + 8 tasks), pseudocode for resolver helper, multi-id token-consume contract locked, AC-4 defense-in-depth verbatim preservation specified, MANDATORY-CR criteria enumerated, baseline `aa87929`.
- 2026-06-06 — autonomous-epic-run dev-story pickup: Tasks 1-6 + 8 shipped (resolver helper, multi-id gate, audit-row plumbing, 12 regression tests, 4 cross-doc updates, pre-review self-audit, all 4 gates green at 1111+2+3-deselected). Story flips ready-for-dev → in-progress → review. Task 7 (MANDATORY-CR) awaits Step 2.4 of orchestrator.
- 2026-06-06 — autonomous-epic-run Step 2.4 MANDATORY-CR complete via Sonnet 4.6 subagent. 11 findings: 4 patch (CR-1 token-leak prevention, CR-2 fixture pre-yield resets, CR-3 docstring v1 contract, CR-4 test assertion tighten) all APPLIED; 4 defer-with-rationale; 3 dismissed. Post-CR 4 gates re-verified green at 1111+2+3-deselected. Story flips review → done.
