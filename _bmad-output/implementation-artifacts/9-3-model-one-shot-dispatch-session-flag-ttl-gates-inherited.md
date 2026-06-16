---
baseline_commit: 2be249c842e451511d822746ec7ee941158e6d25
---

# Story 9.3: `/model` one-shot dispatch — session-scoped per-call override from chat

Status: done

## Story

As Adam,
I want to type `/model qwen` (or `/model haiku`, `/model opus`) in a Hermes Discord chat session and have the very next `ask_router` call use the specified model via the existing `force_model` parameter, with all sensitivity + budget + degraded-mode gates UNCHANGED, the one-shot flag consumed on first use, and the audit row carrying `model_chosen_reason=ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT`,
So that I can experiment with routing decisions inline during real conversations without editing `policy.yaml`, and so the override is visibly logged with full provenance.

## Open Questions / Architectural Decisions

### OQ-1 — Session-id sourcing (Adam-decided 2026-06-14: Option B, single-slot global flag)

**Background:** Story 9.3's AC framing assumes the one-shot override is keyed by Hermes session_id sourced from MCP ctx (the pattern `_session_id_from_ctx(ctx)` used by other verbs). But `ask_router` is invoked via the `/v1/chat/completions` HTTP endpoint (Story 2-10), NOT as an MCP tool — the endpoint has no MCP ctx. Hermes calls the MCP server to set the override (`set_model_oneshot` IS an MCP tool, has ctx.session_id) but then chats via HTTP (no session passthrough). Real architectural seam between MCP-set and HTTP-consumed.

**Options considered:**
- (a) Add `X-Mailbot-Session-Id` header on `/v1/chat/completions` calls. Cleanest but requires Hermes-side coordination AND Hermes upstream may not support per-call dynamic headers (per RECONCILIATION-NOTES §1.6, auxiliary entries don't support `headers:` key).
- (b) **Single-slot global flag.** MailBot is Adam-only (single-user deploy). The "session" abstraction collapses to "the one user's next call." Store a single global `_oneshot_override: OneShotOverride | None`. Set via MCP tool, consume on next `ask_router`. Drops session-isolation semantics that the AC's "session_id" framing implies; future multi-user would require revisiting.
- (c) caller-origin keyed — doesn't work (call-type identifiers, not session identifiers).

**Decision:** Adam picked (b) on 2026-06-14. Rationale: MailBot is explicitly single-user; the TTL (5 min) + consume-on-use already provide bounded-lifetime guarantees; minimizes Hermes-side coordination. ACs below are reframed accordingly — `session_id` becomes implicit (the single Adam-user identity).

**Implication for AC-2 wording:** the MCP `set_model_oneshot` verb still accepts a `ctx` parameter (consistent with the verb signature pattern), but the override is stored in a module-level `_oneshot_override` slot rather than a `dict[session_id, ...]`. The session_id from ctx is logged for audit trail but does NOT key the lookup.

### OQ-2 — Slash command registration drift (expanded 2026-06-16 — deferred to Story 9-10)

**Initial framing (story-creation time):** the current `hermes-config/config.yaml` does NOT contain a `slash_commands` block despite Story 5-6 documenting one under `gateway.discord.slash_commands[]`. Either the 5-6 work was reverted, the path was wrong, or it never actually landed. Story 9-10 ("Hermes config.yaml slash registration drift test") explicitly owns the verification.

**Expanded finding (dev-pass 2026-06-16):** the existing test `test_hermes_config_discord_at_top_level_not_under_gateway` EXPLICITLY FORBIDS `discord.slash_commands` per `RECONCILIATION-NOTES §1.4 §1.5`. The Story 5-4 reconciliation determined that `slash_commands` was a **fictional contract** — real Hermes registers Discord slash commands at runtime via the Discord Developer Portal, NOT via `config.yaml`. The Story 5-6 documentation was wrong about how Hermes actually works.

**Decision (revised):** Story 9.3's AC-4 is **scope-reduced** to: (a) document `/model qwen|haiku|opus` in `hermes-config/skills/mailbot/SKILL.md` with the gate-inheritance + TTL + audit notes; (b) add a comment block to `hermes-config/config.yaml` explaining the OQ-2 finding so future readers don't re-add the slash_commands block; (c) the verb `set_model_oneshot` IS dispatchable via MCP today, so any future slash-command-registration mechanism (Story 9-10's eventual scope) can wire it up. AC-4's `slash_commands` YAML block requirement is **DISCHARGED** as architecturally-impossible-given-real-Hermes-schema rather than implemented.

## Acceptance Criteria

**AC-1 — `set_model_oneshot` MCP verb.**

**Given** the MCP server (Story 5-2) exposes verbs as tools
**When** a new verb `set_model_oneshot(model: str) → SetModelOneShotOut` is added to `mailbot_api/verbs/router_control.py`
**Then** the verb validates `model` against the policy-allowed model set: full IDs (`qwen2.5:3b-instruct-q4_K_M`, `claude-haiku-4-5-20251001`, `claude-opus-4-7`) and the shorthand aliases (`qwen`, `haiku`, `opus`); shorthand is normalized to the full ID before storage
**And** the verb writes a module-level `_oneshot_override: OneShotOverride | None` (single-slot global flag per OQ-1) — NOT a session_id-keyed dict
**And** the override has a TTL of 5 minutes from set-time; expired overrides are evicted on read (not just on write)
**And** the verb returns `SetModelOneShotOut(ok=True, model=<normalized>, expires_at=<ISO>, session_id=<ctx-derived>)` on success or `SetModelOneShotOut(ok=False, error=<message>)` on unknown model
**And** the session_id is captured for audit-trail visibility (logged in the structured log) but does NOT key the storage lookup
**And** setting a new override when one is already armed replaces it (last-write-wins) with a one-line structured-log warning (`event="oneshot_override.replaced"`)

**AC-2 — `ask_router` consumes the override at the head of the function.**

**Given** the next `ask_router` call fires within the TTL after `/model qwen` was set
**When** the router enters `ask_router(task_type, content, force_model=None, ...)`
**Then** a NEW pre-check near the head of the function (after the pause-state check, before model resolution) looks up the module-level `_oneshot_override`
**And** if a valid (non-expired) override is present AND `force_model is None`, the override's model is used as if `force_model` had been explicitly passed
**And** if `force_model` was explicitly passed (`force_model is not None`), the explicit value wins and the one-shot stays armed for the next call (consume-on-actual-use semantics)
**And** the flag is CONSUMED (cleared from the module-level slot) when actually used, regardless of whether the call succeeds or fails downstream — consume happens at the point of effective use, not at any-call entry
**And** the resulting `router_calls` row carries `model_chosen_reason=ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value`
**And** the override slot is keyed neither by caller_origin nor by HTTP session — it's global; any next `ask_router` call from any caller consumes it (matches OQ-1's single-user reality)

**AC-3 — Gate inheritance — sensitivity, budget, degraded-mode all UNCHANGED.**

**Given** the sensitivity + budget + degraded-mode gates are already enforced in the router
**When** `/model opus` is set and the next call is `ask_router(task_type="draft_reply", email_id=<sensitive_id>)` (an API-bound model on a sensitive email)
**Then** the existing sensitivity-token precondition layer refuses the call with `SENSITIVITY_BLOCKS_API` UNCHANGED — the override does NOT punch through
**And** the audit row carries `model_chosen_reason=ModelChosenReason.SENSITIVITY_GATE_REFUSED.value` not `OVERRIDE_SLASH_ONE_SHOT.value` (the override never took effect because the gate fired first)
**And** the one-shot override is **NOT consumed** when the gate refuses (Adam re-issues a non-sensitive call; the override remains armed within TTL). Rationale: consume-on-actual-use, and a gate refusal means no actual use occurred.
**And** when the next call is on a `confidential` email, refusal is unconditional UNCHANGED (the override would have been blocked by NFR-PRIV-2 regardless)
**And** when the estimated cost exceeds the $0.20 per-call refusal threshold, the call is refused with `PER_CALL_THRESHOLD_EXCEEDED` UNCHANGED — one-shot does NOT carry implicit `force=true`; Adam must re-issue with explicit force if he wants to bypass
**And** when degraded mode is active and the override targets `claude-opus-4-7`, the existing degraded-mode block fires UNCHANGED (returns `DEGRADED_MODE_BLOCKED`; override does NOT consume; Adam must use the existing confirmation-token flow)

**AC-4 — Slash command registration in `hermes-config/config.yaml`.**

**Given** Story 5-6's documented pattern (`gateway.discord.slash_commands[]` block, per `5-6-slash-command-dispatcher.md` AC-6 lines 97-200) — see OQ-2 for the current-drift caveat
**When** the slash command is added
**Then** `hermes-config/config.yaml` gains a `gateway.discord.slash_commands` entry (creating the `gateway:` and `gateway.discord.slash_commands` keys if absent — they're absent today per OQ-2) with:
  - `name: "model"`
  - `description: "Set a one-shot model override for the next router call (5-min TTL, gates inherited)."`
  - `options[0]: {name: "model", type: "string", choices: ["qwen", "haiku", "opus"], required: true}`
  - `verb: "set_model_oneshot"`
  - `ephemeral: false` (Adam wants the override-set confirmation visible in chat, not hidden)
**And** `hermes-config/skills/mailbot/SKILL.md` gets a new section "Model override" with 1-line examples for `/model qwen` / `/model haiku` / `/model opus` (one-shot here; persistent forward-references Story 9.4 — note that section is added now and Story 9.4 extends it)
**And** the slash command help text explains: 5-minute TTL, one-shot consumption on first effective use, gate-inheritance (sensitivity / budget / degraded all unchanged), audit trail via `ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT`

**AC-5 — Sensitivity-gate regression test matrix.**

**Given** the parametrized sensitivity-gate regression matrix is the load-bearing test for AC-3
**When** `tests/unit/router/test_oneshot_override_sensitivity_gate.py` runs
**Then** the test asserts: 4 task_types (`draft_reply`, `summary_short`, `importance_scoring`, `action_extraction`) × 3 sensitivity levels (`normal`, `sensitive`, `confidential`) × {with confirmation_token, without confirmation_token} = parametrized matrix verifying the override-DOES-NOT-punch-through invariant
**And** for each (task_type, sensitivity, token-presence) tuple: the test seeds an email row with the given sensitivity, arms the one-shot override targeting `claude-opus-4-7`, calls `ask_router`, asserts the gate verdict (refused with `SENSITIVITY_BLOCKS_API` for sensitive-without-token + API model, refused with `SENSITIVITY_BLOCKS_API` for confidential always, allowed for normal-and-token-bearing-sensitive)
**And** the test asserts the audit row's `model_chosen_reason` is `SENSITIVITY_GATE_REFUSED` (not `OVERRIDE_SLASH_ONE_SHOT`) on refusal
**And** the test asserts the override remains armed (not consumed) on gate-refusal per AC-3
**And** `tests/unit/router/test_oneshot_override_budget_gate.py` covers the $0.20 per-call threshold path (override does NOT carry implicit `force=true`; PER_CALL_THRESHOLD_EXCEEDED fires) and the degraded-mode opus-block path (override does NOT consume; DEGRADED_MODE_BLOCKED fires)
**And** `tests/integration/test_oneshot_yaml_equivalence.py` asserts: same `(email, task, model)` triple dispatched via one-shot override vs via direct `force_model=<model>` produces equivalent `router_calls` rows EXCEPT for `model_chosen_reason` (one-shot writes `OVERRIDE_SLASH_ONE_SHOT`, direct writes `OVERRIDE_API`)

**AC-6 — TTL expiry + consume-on-use unit tests.**

**Given** the override has a 5-minute TTL and consume-on-actual-use semantics
**When** `tests/unit/verbs/test_set_model_oneshot.py` runs
**Then** the tests cover:
  - Setting an override returns `ok=True` with `expires_at = now + 300s`
  - Setting `set_model_oneshot("qwen")` normalizes to `qwen2.5:3b-instruct-q4_K_M`
  - Setting `set_model_oneshot("nonsense")` returns `ok=False, error=<reason>` and does NOT replace any existing override
  - Setting a new override when one is armed: returns `ok=True` for the new one, logs the replacement warning
  - TTL expiry: setting at T=0 and reading the slot at T=301s evicts and returns None
**And** the read-path eviction logic is exercised independent of any `ask_router` call (a direct unit test on the lookup helper)

**AC-7 — MANDATORY-CR per §5.12.**

**Given** the touch surface (new MCP verb + new slash + Hermes config + privacy-gate parity + cross-story dependencies on Stories 4-7 / 5-2 / 5-6 / 6-20 / 9-2)
**When** CR cadence is evaluated per the 6 §5.12 criteria
**Then** the §5.12 verdict is **MANDATORY-CR** because criteria 1 (new verb + new slash + new global mutable module-state) AND 2 (external Discord-facing surface) AND 5 (privacy-invariant — sensitivity gate parity is load-bearing for AC-3) AND 6 (load-bearing — touches the `ask_router` hot path) all fire
**And** the code-review subagent runs under `claude-sonnet-4-6` per the dev-vs-review-different-model invariant (dev model: `claude-opus-4-7`)
**And** the pre-review self-audit artifact (`9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.pre-review.md`) records the §5.12 verdict before the CR dispatch

## Tasks / Subtasks

- [x] **Task 1 — `OneShotOverride` shape + module-level slot** (AC: 1, 2, 6) — DONE: shape + 4 helpers shipped; 12 helper tests pass.
  - [x] Subtask 1.1 — `OneShotOverride(BaseModel)` shipped at `mailbot_api/verbs/router_control.py` with all 4 fields (model, expires_at, set_at, session_id audit-only).
  - [x] Subtask 1.2 — Module-level `_oneshot_override: OneShotOverride | None = None` slot present.
  - [x] Subtask 1.3 — `_get_active_oneshot_override()` evicts expired entries on read.
  - [x] Subtask 1.4 — `_consume_oneshot_override()` returns + clears atomically (single-threaded asyncio).
  - [x] Subtask 1.5 — `_set_oneshot_override(...)` writes slot + logs structured `oneshot_override.replaced` warning on replacement.
  - [x] Subtask 1.6 — `_reset_oneshot_override_for_test()` available as autouse fixture target.

- [x] **Task 2 — Model alias normalization** (AC: 1) — DONE: `_MODEL_ALIASES` frozen dict + `_normalize_model_id` helper + alias normalization tests (3/3 parametrize cases pass).
  - [x] Subtask 2.1 — `_MODEL_ALIASES: Final[dict[str, str]]` with qwen/haiku/opus → full IDs.
  - [x] Subtask 2.2 — `_normalize_model_id(model) -> str | None` accepts shorthand + full IDs, returns None for unknown.
  - [x] Subtask 2.3 — Validation uses `_ALLOWED_FULL_MODEL_IDS = frozenset(_MODEL_ALIASES.values())` derived from the alias map. NOTE deferred: did not source from `snapshot_for_dispatch()` because policy.yaml may contain models we don't want one-shot to target (e.g., embeddings models like `nomic-embed-text`). The 3-model alias-map IS the validation set — narrower than policy-allowed, more correct for the chat-override use case. If a future task adds a new chat-eligible model, it's added to `_MODEL_ALIASES`.

- [x] **Task 3 — `set_model_oneshot` verb** (AC: 1, 6) — DONE: verb + `SetModelOneShotOut` shape shipped; 7 verb-level tests pass + 1 OQ-1 regression sentinel pass.
  - [x] Subtask 3.1 — `SetModelOneShotOut(BaseModel)` with all 5 fields.
  - [x] Subtask 3.2 — `async set_model_oneshot(*, db_path, model, session_id=None)` normalizes + validates + returns ok/error response. Unknown model returns explicit allowed-list in error message.
  - [x] Subtask 3.3 — `__all__` exports the verb + shape + test-only reset helper + the 3 internal helpers (audit/regression sentinel access).

- [x] **Task 4 — MCP server wiring** (AC: 1) — DONE: wrapper registered following pause_router/resume_router pattern; tool count bumped 22→23 (fail-fast assertion at `_EXPECTED_TOOL_COUNT` + 3 regression tests updated); all 28 MCP server integration tests pass.
  - [x] Subtask 4.1 — Imported `set_model_oneshot` via dedicated import block.
  - [x] Subtask 4.2 — `async def set_model_oneshot(ctx, model)` wrapper at `mcp_server.py` after `resume_router`; extracts `sid = _session_id_from_ctx(ctx)`, passes as audit-only param per OQ-1, logs via `_log_ok`/`_log_error_as_data`/`_log_crash`.
  - [x] Subtask 4.3 — Added to `tool_callables` dict at `_build_wrappers` exit.
  - [x] Subtask 4.4 — `_TOOL_DESCRIPTIONS["set_model_oneshot"]` describes 5-min TTL + gate-inheritance + consume-on-use + audit reason.
  - [x] Subtask 4.5 (added during impl) — Updated `_EXPECTED_TOOL_COUNT: 22 → 23` and 3 test sites (`test_build_mcp_server_registers_22_tools_with_expected_names → 23`, `test_mcp_server_registers_22_tools → 23`, `test_list_tools_returns_constraint_phrases` count). Story 9-3 appears in the expected-names sorted list.

- [x] **Task 5 — `ask_router` consumer at function head** (AC: 2, 3) — DONE: peek-and-consume integrated; existing 25/25 router unit tests pass; gate-refused paths verified to bypass consume (all 9 early `return RouterResult` paths are above the consume site).
  - [x] Subtask 5.1 — Added Story 9-3 peek block AFTER pause-state check + BEFORE policy snapshot. Sets local `_oneshot_engaged: bool` to discriminate the audit-reason branch.
  - [x] Subtask 5.2 — Peek via `_get_active_oneshot_override()` (no consume) when `force_model is None`. Lifts override.model into local `force_model`. Explicit-caller `force_model` always wins (one-shot stays armed for next call per AC-2).
  - [x] Subtask 5.3 — Consume via `_consume_oneshot_override()` at line just before `_dispatch_with_failure_chain()` invocation. All 9 early returns (pause / policy / prompt / degraded-opus / sensitivity / budget) are ABOVE this point, so gate-refused calls leave the override armed within TTL per AC-3.
  - [x] Subtask 5.4 — Branched the existing `OVERRIDE_API` audit-string write: if `_oneshot_engaged` → `OVERRIDE_SLASH_ONE_SHOT.value`, else → `OVERRIDE_API.value`. Distinguishes Adam's chat `/model` from a direct API-caller force_model.

- [x] **Task 6 — `hermes-config/config.yaml` slash registration** (AC: 4) — DONE WITH SCOPE-REDUCTION (OQ-2 expanded): the `slash_commands` YAML block requirement is DISCHARGED as architecturally-impossible — RECONCILIATION-NOTES §1.4/§1.5 documents that real Hermes registers Discord slash commands at runtime (Developer Portal), NOT via config.yaml. The Story 5-6 path was a fictional contract. SKILL.md docs + verb dispatchability remain shipped.
  - [x] Subtask 6.1 — REVISED: removed the initial `slash_commands` YAML attempt (would have failed `test_hermes_config_discord_at_top_level_not_under_gateway`). Replaced with an OQ-2 comment block in config.yaml explaining the Hermes-side-runtime-registration reality.
  - [x] Subtask 6.2 — OQ-2 expanded finding documented in story file's Open Questions section: Story 5-6's `gateway.discord.slash_commands[]` was a fictional contract, not a drifted one. Story 9-10 will introduce the runtime-registration mechanism. The verb `set_model_oneshot` IS dispatchable via MCP today.
  - [x] Subtask 6.3 — Added `### set_model_oneshot — Model override (Story 9-3)` section to `hermes-config/skills/mailbot/SKILL.md` with 3 slash examples + OQ-2 caveat ("Hermes-side registration is Story 9-10's scope") + gate-inheritance explainer + audit-trail note + Story 9-4 forward-reference. Bumped frontmatter "22 MCP tools" → "23 MCP tools".

- [x] **Task 6.5 (added during dev-pass) — Refactor: relocate slot storage to `mailbot_api/router/oneshot.py`** — Story 5-2 AC-7's verb-import isolation boundary check failed when `router.py` imported from `verbs/router_control.py`. Architecturally correct fix: the slot lives in the consumer's territory (`router/`), not the writer's (`verbs/`). Created new `mailbot_api/router/oneshot.py` (155 lines) holding `OneShotOverride` + 4 helpers + `_now_utc`. `verbs/router_control.py` re-exports the helpers + keeps the `set_model_oneshot` verb (which sets the slot via the new module). Tests updated to monkeypatch `mailbot_api.router.oneshot._now_utc` instead of the old `verbs.router_control._now_utc`. mypy --strict goes 126→127 source files clean; boundary check exit 0.

- [x] **Task 7 — Sensitivity-gate regression test matrix** (AC: 5) — DONE: 24 parametrized matrix tests pass + 2 budget-gate tests + 1 YAML-equivalence integration test = 27 net new tests; CRITICAL architectural fix discovered + applied (consume relocated INTO `_dispatch_with_failure_chain` after budget gate).
  - [x] Subtask 7.1 — Wrote `tests/unit/router/test_oneshot_override_sensitivity_gate.py`. Parametrized 4 tasks × 3 sensitivities × {with-token, without-token} = 24 matrix cells. Each asserts gate verdict + audit-row reason + override-armed state. ALL 24 PASS.
  - [x] Subtask 7.2 — Wrote `tests/unit/router/test_oneshot_override_budget_gate.py` covering `PER_CALL_THRESHOLD_EXCEEDED` (used `max_tokens_out: 1000000` to guarantee >$0.20 estimated cost on Haiku) + `DEGRADED_MODE_BLOCKED` (entered degraded mode via `guard._enter_degraded_mode`; armed override → opus). Both confirm override remains armed.
  - [x] Subtask 7.3 — Wrote `tests/integration/test_oneshot_yaml_equivalence.py`. Verifies 16-of-18 RouterCallRow columns are equal between one-shot and direct-force_model dispatch; the 2 differing columns (`model_chosen_reason` + `ts`) differ in the expected way.
  - [x] **CRITICAL fix during Task 7:** the initial Task 5 consume site was BEFORE `_dispatch_with_failure_chain`, but the $0.20 budget gate fires INSIDE that function. Under the initial design, a budget-refused call would silently consume the override — violating AC-3. The fix relocated consume to AFTER the budget gate via a new `_oneshot_engaged: bool` kwarg threaded into `_dispatch_with_failure_chain`. All 24 sensitivity-matrix + 2 budget-gate tests verify the corrected semantics.

- [x] **Task 8 — TTL + consume-on-use unit tests** (AC: 6) — DONE: covered by Task 1's 20 tests in `test_set_model_oneshot.py` (which already include AC-6's ok-path / alias-normalization / unknown-rejection / replacement-warning / TTL-eviction / OQ-1-regression-sentinel). No additional file needed — Task 1's test file IS the AC-6 fulfillment.
  - [x] Subtask 8.1 — Covered by Task 1's `tests/unit/verbs/test_set_model_oneshot.py` (20 tests). TTL tested via `monkeypatch.setattr(rc_module, "_now_utc", lambda: fake_now)` — no `freezegun` dep needed.
  - [x] Subtask 8.2 — Single-slot regression sentinel: `test_override_set_with_session_a_consumed_from_session_b` verifies the override slot is keyed neither by session nor caller_origin.

- [ ] **Task 9 — Pre-review self-audit + MANDATORY-CR** (AC: 7)
  - [ ] Subtask 9.1 — Write `9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.pre-review.md` with all 5 sections + 11 Posture Audit sub-sections per Step 2.3.5 of the autonomous-story-run skill.
  - [ ] Subtask 9.2 — Dispatch code review under `claude-sonnet-4-6` per AC-7.

## Dev Notes

### Technical Requirements (Stack / Libraries / Versions)

- Python 3.11+ — Pydantic v2 BaseModel + `from __future__ import annotations`
- No new third-party deps. Uses stdlib `datetime`, existing project Pydantic + asyncio + `mcp.server.fastmcp.Context` (already imported across mcp_server.py)
- Optional: `freezegun` for TTL testing IF it's already in `requirements-dev.txt`; otherwise monkeypatch `datetime.now` per the existing test_audit.py pattern.

### Architecture Compliance

- **OQ-1 single-slot semantics.** The module-level `_oneshot_override` slot in `router_control.py` is intentional single-user-deploy state. Document with a one-line `# module-singleton: per-process one-shot override; single-user assumption per OQ-1; reset on container restart` comment per posture-audit §5.7's MailBot-specific anti-pattern note.
- **MCP wrapper pattern.** Follow `pause_router` / `resume_router` (lines 513-543 in `mcp_server.py`) verbatim — `sid = _session_id_from_ctx(ctx)`, `t0 = time.perf_counter()`, try/except for crash logging, `_maybe_error_code`, `_log_ok` / `_log_error_as_data` / `_log_crash` for outcome logging.
- **`ask_router` precondition order.** AR-PRECONDITION-ORDER documents the existing order: pause-state (line ~196) → policy snapshot (line ~208) → force_model resolution (line ~234) → degraded-mode gate (line ~242) → sensitivity gate (line ~280). The Story 9.3 hook fits between policy snapshot and force_model resolution.
- **Audit vocabulary closed-set (Story 9.2).** `ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value` is the canonical write — do NOT introduce a new templated form. The literal value `"slash_command:one_shot:adam"` was reserved by Story 9.2 specifically for this consumer.
- **Single-user assumption.** OQ-1's option (b) explicitly accepts the single-user constraint. A `# Story 9.3 NOTE` comment at the module level documents that multi-user would require introducing a session-keyed dict (the test in Subtask 8.2 is the regression sentinel).

### File Structure Requirements

- **MODIFIED:** `mailbot_api/verbs/router_control.py` (~80 net lines added: `OneShotOverride` model + module-level slot + 4 helpers + `set_model_oneshot` verb + `SetModelOneShotOut`)
- **MODIFIED:** `mailbot_api/mcp_server.py` (~25 net lines added: import + wrapper + registry entry + description)
- **MODIFIED:** `mailbot_api/router/router.py` (~15 net lines added: pre-check at function head + consume-at-effective-dispatch + audit-reason branch)
- **MODIFIED:** `hermes-config/config.yaml` (~12 net lines added: `gateway.discord.slash_commands[]` block creation + `model` entry)
- **MODIFIED:** `hermes-config/skills/mailbot/SKILL.md` (~15 net lines: "Model override" section)
- **NEW:** `tests/unit/verbs/test_set_model_oneshot.py` (~150 lines covering AC-6)
- **NEW:** `tests/unit/router/test_oneshot_override_sensitivity_gate.py` (~200 lines, parametrized matrix per AC-5)
- **NEW:** `tests/unit/router/test_oneshot_override_budget_gate.py` (~80 lines)
- **NEW:** `tests/integration/test_oneshot_yaml_equivalence.py` (~80 lines)
- No database migration — `_oneshot_override` is in-memory only; resets on container restart by design.

### Testing Requirements

- Test framework: `pytest` + `pytest-asyncio` for async verb tests. Project standard from existing `test_pause.py` / `test_router.py`.
- Type checking: `mypy --strict` clean on all touched files. Helper return types are explicit (`OneShotOverride | None`, not `Optional[...]` short-form per project convention).
- Boundary check: `python scripts/check_boundaries.py` must exit 0. The new `model_chosen_reason=ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value` write in `router.py` goes through the enum (no raw string), so it passes Story 9.2's `forbid_raw_model_chosen_reason_strings` rule.
- Full suite: `pytest -q` baseline at story start is **1288 passed + 2 skipped + 3 deselected** (per Story 9.2 done-flip note). Target post-9.3: +20 to +40 net tests (Tasks 7 + 8 contribute ~25 unit + 1 integration).

### Cross-Story Dependencies

- **Upstream Story 9.2 (done 2026-06-13):** provides `ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT` enum member + the validator that accepts its value. Story 9.3 is the first production consumer of this member.
- **Upstream Story 5-2 (done):** MCP tool registration pattern + `_session_id_from_ctx(ctx)` helper.
- **Upstream Story 5-6 (drift per OQ-2):** `gateway.discord.slash_commands[]` documentation pattern. The pattern is followed verbatim; whether it actually wires up at Discord-REST-registration time is Story 9-10's scope.
- **Upstream Story 4-7 (done):** sensitivity-token handshake gate — the gate that the test matrix in Task 7 exercises. Story 9.3 does NOT modify the gate logic; it only verifies override does not punch through.
- **Upstream Story 6-20 (done):** sensitivity gate placement in `dispatch_tool_call` — same precondition layer, same parity story (override does not punch through).
- **Downstream Story 9.4:** `/model <task> <model>` persistent override + `/model` inspect verb. Both consume `mailbot_api/verbs/router_control.py` patterns established here. The "Model override" section in SKILL.md is extended by 9.4 with persistent variant.

### Previous Story Intelligence (from 9.2)

- **MANDATORY-CR cadence v2:** 9.2 ran CR under `claude-sonnet-4-6`, applied 8 of 8 actionable findings (100%). Aim for similar applied-rate ≥ 70% per the CR cadence v2 memory.
- **Selective staging:** stage only File List + `9-3-*.pre-review.md` + sprint-status flips. Do NOT `git add -A`.
- **OPS note (CR-finding-count discipline):** 9.2 had a count-drift between the prose ("8 findings") and actual ("9 findings"). Self-verify the count in pre-review §1 / §4 / sprint-status before flipping to done.
- **Open Question framing pattern:** 9.2 had a Migration Notes section flagging the `force_override` / `override` semantic collapse as a deliberate Adam-authorized contract change. Story 9.3 follows the same pattern via OQ-1 (session_id sourcing) and OQ-2 (slash registration drift).

### References

- [_bmad-output/planning-artifacts/epics.md:3192-3236](../planning-artifacts/epics.md) — Story 9.3 spec block (canonical AC source)
- [mailbot_api/router/audit_vocab.py](../../mailbot_api/router/audit_vocab.py) — Story 9.2's `ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT` enum member
- [mailbot_api/verbs/router_control.py](../../mailbot_api/verbs/router_control.py) — existing `pause_router` / `resume_router` pattern to follow
- [mailbot_api/mcp_server.py:513-543](../../mailbot_api/mcp_server.py) — MCP wrapper pattern (`pause_router` / `resume_router`)
- [mailbot_api/mcp_server.py:169](../../mailbot_api/mcp_server.py) — `_session_id_from_ctx(ctx)` helper (used for AUDIT-ONLY logging per OQ-1)
- [mailbot_api/router/router.py:196-260](../../mailbot_api/router/router.py) — `ask_router` precondition chain (pause → snapshot → force_model resolution → degraded → sensitivity)
- [_bmad-output/implementation-artifacts/5-6-slash-command-dispatcher.md:97-200](5-6-slash-command-dispatcher.md) — slash-command-registry pattern
- [_bmad-output/implementation-artifacts/9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor.md](9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor.md) — Story 9.2 (audit vocab consumer)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (via autonomous-story-run skill, Phase 2 inline dev-story walk, resumed 2026-06-16 from a 2026-06-14 stop checkpoint)

### Debug Log References

- **OQ-1 decision baked in (Option B single-slot global, Adam-decided 2026-06-14):** the original epic-9 AC framing assumed session-keyed storage. Adam's call collapsed it to a module-level global because MailBot is single-user. The regression sentinel (`test_override_set_with_session_a_consumed_from_session_b`) verifies the single-slot semantics — if a future story introduces multi-user, that test fails and forces re-architecture.
- **CRITICAL fix at Task 5 / Task 7 boundary — consume-site relocation:** initial Task 5 placed `_consume_oneshot_override()` BEFORE `_dispatch_with_failure_chain()`. But the $0.20 per-call budget gate fires INSIDE that function (line 541). Under the initial design, a budget-refused call would silently consume the override — violating AC-3. The fix threaded `_oneshot_engaged: bool` as a kwarg into `_dispatch_with_failure_chain` and relocated the consume to AFTER the budget gate. All 24 sensitivity-matrix + 2 budget-gate tests verify the corrected semantics. This is the kind of architectural detail the parametrized matrix existed to catch — a single happy-path test would have missed it.
- **Story 5-2 AC-7 boundary check (Task 6.5 added):** placing the override slot in `mailbot_api/verbs/router_control.py` failed the boundary check — `router.py` cannot import from `verbs/*`. Architecturally correct fix: the slot is router-internal state, not a verb. Created new `mailbot_api/router/oneshot.py` (155 lines) holding `OneShotOverride` + 4 helpers + `_now_utc`. `verbs/router_control.py` re-exports the helpers (test backward-compat) + keeps the `set_model_oneshot` verb. Tests updated to monkeypatch `mailbot_api.router.oneshot._now_utc` instead of `verbs.router_control._now_utc`.
- **OQ-2 expanded during dev-pass (Task 6 scope-reduction):** initial story framing followed Story 5-6's documented `gateway.discord.slash_commands[]` path. But `test_hermes_config_discord_at_top_level_not_under_gateway` EXPLICITLY FORBIDS that block — per `RECONCILIATION-NOTES §1.4/§1.5`, slash_commands was a Story 5-4 fictional contract. Real Hermes registers Discord slash commands at runtime via the Developer Portal, NOT via config.yaml. AC-4's YAML block requirement is DISCHARGED as architecturally-impossible-given-real-Hermes-schema; SKILL.md docs + verb MCP-dispatchability remain shipped. Story 9-10 will introduce the runtime-registration mechanism.
- **`_FakeAdapter` per-task schema responses:** the sensitivity-gate matrix test had to provide per-task schema-valid JSON responses (`draft_reply` ≠ `summary_short` ≠ `importance_scoring` ≠ `action_extraction`). Built `_VALID_RESPONSE_PER_TASK` dict + `_good_response_for_task(task_type)` helper. Also had to over-provision the content dict with `source_email` + `thread_context` + `tone_signals` (draft_reply's required template variables).
- **Gate 4 net-test delta:** baseline 1288+2+3-deselected (per Story 9.2 done-flip). Post-9.3: 1335+2+3-deselected = **+47 net tests**. Breakdown: 20 unit (test_set_model_oneshot.py) + 24 unit (test_oneshot_override_sensitivity_gate.py — 4 tasks × 3 sensitivities × 2 token-presence) + 2 unit (test_oneshot_override_budget_gate.py) + 1 integration (test_oneshot_yaml_equivalence.py).

### Completion Notes List

- **AC-1 (verb + shape + TTL):** `set_model_oneshot` verb in `mailbot_api/verbs/router_control.py`; `OneShotOverride` shape + module-level slot in NEW `mailbot_api/router/oneshot.py`; 5-min TTL with eviction-on-read; structured `oneshot_override.replaced` warning on replacement. 20 tests in `test_set_model_oneshot.py` verify all sub-clauses.
- **AC-2 (ask_router consumes at function head):** peek block in `ask_router` after pause-state check, before policy snapshot — sets local `_oneshot_engaged: bool`. Audit reason branches: `_oneshot_engaged ? OVERRIDE_SLASH_ONE_SHOT : OVERRIDE_API`. Explicit `force_model` from API caller still wins; one-shot stays armed for the next call (consume-on-actual-use).
- **AC-3 (gate inheritance — sensitivity, budget, degraded all UNCHANGED):** sensitivity gate fires in `ask_router` (above consume); budget gate fires in `_dispatch_with_failure_chain` (where consume now ALSO lives, AFTER the budget check). 24 parametrized sensitivity-matrix tests + 2 budget-gate tests verify the override remains armed on gate refusal AND consumed only on actual dispatch.
- **AC-4 (slash registration — SCOPE-REDUCED per OQ-2 expanded):** the YAML `slash_commands` block is architecturally-impossible-given-real-Hermes-schema. SKILL.md docs shipped + verb dispatchable via MCP. Story 9-10 owns runtime registration.
- **AC-5 (parametrized test matrix):** 24 sensitivity matrix + 2 budget + 1 YAML-equivalence integration = 27 tests covering all AC-5 sub-bullets.
- **AC-6 (TTL + consume-on-use unit tests):** covered by Task 1's `test_set_model_oneshot.py` (20 tests); no separate file needed.
- **AC-7 (MANDATORY-CR per §5.12):** criteria 1 (new verb + slash + global mutable module-state + new boundary module `router/oneshot.py`) + 2 (Discord-facing) + 5 (privacy-invariant — sensitivity gate parity) + 6 (load-bearing — `ask_router` hot path) all fire. Pre-review + code-review under `claude-sonnet-4-6` queued in Step 2.3.5 + Step 2.4.

### File List

- `mailbot_api/router/oneshot.py` (NEW) — `OneShotOverride` shape + 4 helpers + `_now_utc`; module-level slot
- `mailbot_api/verbs/router_control.py` (MODIFIED) — re-export helpers from `router/oneshot`; add `set_model_oneshot` verb + `SetModelOneShotOut` + alias normalization; remove obsolete state-management code
- `mailbot_api/router/router.py` (MODIFIED) — Story 9-3 peek block + audit-reason branch + threaded `_oneshot_engaged` kwarg through to `_dispatch_with_failure_chain`; consume call relocated after budget gate
- `mailbot_api/mcp_server.py` (MODIFIED) — import + tool wrapper + tool registry entry + `_TOOL_DESCRIPTIONS` entry; bumped `_EXPECTED_TOOL_COUNT: 22 → 23`
- `hermes-config/config.yaml` (MODIFIED) — OQ-2 comment block explaining why `slash_commands` block is NOT added (RECONCILIATION-NOTES §1.4/§1.5 architectural ban)
- `hermes-config/skills/mailbot/SKILL.md` (MODIFIED) — frontmatter "22 MCP tools" → "23"; new `### set_model_oneshot — Model override (Story 9-3)` section with OQ-2 caveat
- `tests/unit/verbs/test_set_model_oneshot.py` (NEW) — 20 tests for AC-1 + AC-6 + OQ-1 regression sentinel
- `tests/unit/router/test_oneshot_override_sensitivity_gate.py` (NEW) — 24 parametrized matrix tests for AC-3 + AC-5
- `tests/unit/router/test_oneshot_override_budget_gate.py` (NEW) — 2 tests for AC-3 budget + degraded gates
- `tests/integration/test_oneshot_yaml_equivalence.py` (NEW) — 1 test for AC-5 third sub-bullet (one-shot vs direct force_model row equivalence)
- `tests/integration/test_mcp_server.py` (MODIFIED) — bumped 22 → 23 in expected-tool-count + name list (added `set_model_oneshot`)
- `tests/integration/test_mcp_server_extended_tools.py` (MODIFIED) — renamed `test_mcp_server_registers_22_tools` → `_23_tools` + bumped expectation
- `tests/integration/test_spend_chart_command.py` (MODIFIED) — renamed `test_mcp_server_has_22_tools_after_story_6_5` → `_23_tools_after_story_9_3` + bumped expectation

### Review Findings

- [x] [Review][Patch] CR-F1 MEDIUM — `model_chosen_reason` overwritten to `CACHE_HIT` on oneshot-engaged cache-hit path, consuming override with no AC-2 audit trail [`mailbot_api/router/router.py:590`] — After `_consume_oneshot_override()` fires at line 571 (`_oneshot_engaged=True`), a response-cache hit at line 581–603 overwrites `model_chosen_reason = ModelChosenReason.CACHE_HIT.value` at line 590, clobbering `OVERRIDE_SLASH_ONE_SHOT`. The `finally`-block audit row then writes `CACHE_HIT`, making Adam's `/model` intent invisible. AC-2 requires `model_chosen_reason=ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value` on the row. Fix: set a local `_oneshot_reason` from `model_chosen_reason` before the cache lookup and pass it explicitly to `_record()` in the cache-hit branch (or append `+oneshot` to the cache-hit value, e.g., `CACHE_HIT+oneshot` — pick whichever approach aligns with AC-2 intent).
- [x] [Review][Patch] CR-F2 LOW — `mcp_server.py` module-level docstring and `_build_wrappers` docstring both say "22 tools"; not updated to 23 [`mailbot_api/mcp_server.py:3,190`] — Line 3: "registers 22 of the project's verbs"; line 190: "Construct the 22 tool wrappers"; neither mentions Story 9-3's `set_model_oneshot`. `_EXPECTED_TOOL_COUNT` was correctly bumped to 23, but two prose counts were missed. Fix: update both to 23 and add `set_model_oneshot` to the enumeration in the module docstring.
- [x] [Review][Patch] CR-F3 LOW — `test_replacement_emits_structured_warning_log` uses wrong logger name in `caplog.at_level`; event emitter is `mailbot_api.router.oneshot` not `mailbot_api.verbs.router_control` [`tests/unit/verbs/test_set_model_oneshot.py:118`] — The `oneshot_override.replaced` warning is emitted by `_log = logging.getLogger(__name__)` in `mailbot_api/router/oneshot.py`. The test uses `logger="mailbot_api.verbs.router_control"` (the pre-Task-6.5 location). The test passes today because pytest caplog captures all records regardless of `logger=`, but the arg is wrong and silently fragile under log-propagation configuration changes. Fix: change `logger=` arg to `"mailbot_api.router.oneshot"`.
- [x] [Review][Patch] CR-F4 LOW — `_clean_oneshot` pytest fixture has incorrect return-type annotation `-> None` for a generator function [`tests/unit/verbs/test_set_model_oneshot.py:29`] — The fixture contains `yield` making it a generator; `mypy --strict` flags `The return type of a generator function should be "Generator"`. Test files are excluded from the project mypy gate so this does not currently break CI, but the annotation is wrong. Fix: annotate as `-> Generator[None, None, None]` (add `from collections.abc import Generator` import) or use `-> Iterator[None]`.
- [x] [Review][Patch] CR-F5 LOW — `test_oneshot_yaml_equivalence.py` doc-comment says "16 columns match" but the assertion loop checks 15 columns; `latency_ms` (col 9) silently excluded [`tests/integration/test_oneshot_yaml_equivalence.py:196`] — The tuple `(1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17)` has 15 elements. The docstring says "16 columns … must match" and the AC-5 note says "16-of-18". Column 9 (`latency_ms`) is the 18th and is excluded because it would differ between two live dispatches — but the exclusion is undocumented. Fix: update the comment to "15 columns checked, 2 differ by design (ts, model_chosen_reason), 1 excluded by design (latency_ms)" to accurately document the assertion scope.
- [x] [Review][Patch] CR-F6 LOW — `_FakeAdapter` imported from private symbol in peer test module across 3 test files; should be a shared helper [`tests/unit/router/test_oneshot_override_sensitivity_gate.py:265`, `test_oneshot_override_budget_gate.py:150`, `tests/integration/test_oneshot_yaml_equivalence.py:155`] — All three import `from tests.unit.router.test_router import _FakeAdapter`, a private-symbol cross-module test dependency. If `test_router.py` renames or removes `_FakeAdapter`, all three break with an obscure `ImportError`. Fix: extract `_FakeAdapter` to `tests/_helpers/fake_adapter.py` (or a conftest fixture) and update all import sites.
- [x] [Review][Patch] CR-F7 LOW — `_dispatch_with_failure_chain` escalation recursive call at line 759 does not document that `_oneshot_engaged` is intentionally omitted (defaults to False) to prevent double-consume [`mailbot_api/router/router.py:759`] — The docstring explains the budget-gate consume semantics but not the escalation-recursion non-forwarding. A future developer may add `_oneshot_engaged=_oneshot_engaged` to the recursive call thinking they are "correctly" forwarding state, causing a double-consume bug where both the outer and inner audit rows try to consume the already-cleared slot. Fix: add a one-line comment at the escalation call site: `# _oneshot_engaged intentionally NOT forwarded — override was already consumed above; recursive escalation row should carry policy_escalation reason, not OVERRIDE_SLASH_ONE_SHOT`.
- [x] [Review][Decision] CR-F8 LOW — `epics.md` AC-4 text still requires the `slash_commands` YAML block; story-file OQ-2 discharge not reflected in planning source-of-truth [`_bmad-output/planning-artifacts/epics.md`] — The story's OQ-2 expanded finding rescoped AC-4 as architecturally-impossible (RECONCILIATION-NOTES §1.4 bans the block); the discharge is documented only in the story file. Future readers of `epics.md` will see a live requirement that was silently abandoned. Decision needed: (a) add a one-line annotation to the epics.md AC-4 text pointing to OQ-2 discharge; or (b) declare the story file the canonical rescope record and accept the drift.

### Change Log

- 2026-06-16 — `/model <model>` one-shot dispatch shipped. Pre-CR: 4 gates green at 1335+2+3-deselected (+47 net tests). Post-CR (sonnet-4-6, 8 Patches all applied = 100% incl. CR-F1 cache-hit-audit-clobber bug fix): 4 gates green at 1337+2+3-deselected (+49 net tests).

## Completion Notes

### 2026-06-16 — done-flip (Step 2.4.8 verbose-row truncation)

**Headline:** `/model <model>` one-shot dispatch shipped. Single-slot global (OQ-1 Option B, Adam-decided 2026-06-14) + 5-min TTL + consume-on-actual-use semantics. New `mailbot_api/router/oneshot.py` leaf module (`OneShotOverride` Pydantic shape + 4 helpers + `_now_utc`) + `set_model_oneshot` MCP verb (`/model qwen|haiku|opus`) + `ask_router` peek-and-consume integration + audit-reason branching (`OVERRIDE_SLASH_ONE_SHOT` vs `OVERRIDE_API`).

**Why this matters:** Adam can inline-experiment with routing decisions during real Discord conversations without editing `policy.yaml`. The 5-min TTL + consume-on-use means a typo or distraction doesn't leave a stale override. The sensitivity / budget / degraded-mode gate-inheritance (verified by 24-cell parametrized matrix + 2 budget tests + 1 cache-hit regression) preserves the privacy + cost invariants — `/model opus` on a sensitive thread still refuses, with the override staying armed for the next non-sensitive call.

**Key technical decisions:**

- **OQ-1 Option B (single-slot global):** Adam picked the single-slot global on 2026-06-14, collapsing the original session-keyed framing because MailBot is explicitly single-user. The MCP `set_model_oneshot` verb captures the session_id for audit-trail visibility but does NOT use it as a lookup key. Future multi-user would require introducing a session-keyed dict + plumbing session_id through the `/v1/chat/completions` HTTP endpoint. Regression sentinel: `test_override_set_with_session_a_consumed_from_session_b`.

- **OQ-2 expanded during dev-pass (AC-4 scope-reduction):** the initial spec assumed Story 5-6's documented `gateway.discord.slash_commands[]` YAML block. The dev-pass found `test_hermes_config_discord_at_top_level_not_under_gateway` EXPLICITLY FORBIDS that block per `RECONCILIATION-NOTES §1.4/§1.5` — real Hermes registers Discord slash commands at runtime via the Developer Portal, not via config.yaml. The Story 5-6 pattern was a fictional contract. AC-4's YAML requirement is **discharged as architecturally-impossible**; Story 9-3 ships SKILL.md docs + MCP-dispatchable verb. Story 9-10 owns runtime registration. Annotation added to `epics.md` AC-4 + the story file's OQ-2 section per CR-F8.

- **Task 6.5 boundary-fix (Story 5-2 AC-7):** initial placement of the override slot in `mailbot_api/verbs/router_control.py` failed the boundary check — `router.py` cannot import from `verbs/*`. Architecturally correct fix: created NEW `mailbot_api/router/oneshot.py` holding the slot + helpers + `_now_utc`. `verbs/router_control.py` re-exports the helpers (test backward-compat) + keeps the `set_model_oneshot` verb (which sets the slot via the new module). mypy --strict goes 126 → 127 source files clean.

- **CRITICAL fix at Task 5 / Task 7 boundary (consume-site relocation):** initial design placed `_consume_oneshot_override()` BEFORE `_dispatch_with_failure_chain`. But the $0.20 per-call budget gate fires INSIDE that function. Under the initial design, a budget-refused call would silently consume the override — violating AC-3 (override must stay armed on gate refusal). Fix threaded `_oneshot_engaged: bool` as a kwarg into `_dispatch_with_failure_chain` and relocated the consume to AFTER the budget gate. This is exactly the kind of bug the parametrized test matrix existed to catch — a single happy-path test would have missed it.

- **CR-F1 fix (cache-hit audit-reason clobber):** sonnet-4-6 reviewer caught that a cache-hit on a one-shot-engaged call was overwriting `model_chosen_reason = CACHE_HIT`, hiding Adam's `/model` intent in the audit log. Fix: only overwrite to `CACHE_HIT` when `_oneshot_engaged is False`. Regression test `test_cache_hit_on_oneshot_engaged_preserves_override_slash_one_shot` + sibling `test_cache_hit_without_oneshot_writes_cache_hit_audit_reason` confirm the narrowed carve-out.

- **CR-F6 test-helper extraction:** sonnet-4-6 flagged the cross-file import `from tests.unit.router.test_router import _FakeAdapter` in 3 new Story 9-3 test files. Extracted to `tests/_helpers/fake_adapter.py` (new package + module). Story 9-3 tests + the original `test_router.py` can both consume the public `FakeAdapter` symbol; future tests can do likewise.

**Test count delta:**

- Baseline (Story 9.2 done-flip 2026-06-13): 1288 passed + 2 skipped + 3 deselected.
- Pre-CR (Story 9-3 dev pass): 1335 + 2 + 3 = +47 net tests.
- Post-CR (after applying 8/8 Patches): 1337 + 2 + 3 = **+49 net tests** (2 new from CR-F1 cache-hit regression).
- Breakdown: 20 unit (test_set_model_oneshot.py) + 24 unit (test_oneshot_override_sensitivity_gate.py — 4 tasks × 3 sensitivities × 2 token-presence) + 2 unit (test_oneshot_override_budget_gate.py) + 1 integration (test_oneshot_yaml_equivalence.py) + 2 unit (test_oneshot_override_cache_hit_audit.py — CR-F1 regression).

**Gate evidence (post-CR):**

- ruff check `.` — exit 0 ("All checks passed!")
- mypy --strict `mailbot_api` — exit 0 ("Success: no issues found in 127 source files")
- `python scripts/check_boundaries.py` — exit 0
- pytest `-q` — 1337 passed, 2 skipped, 3 deselected, 1 warning in 163.03s

**MANDATORY-CR cadence (per CR cadence v2 memory):** §5.12 criteria 1 (new verb + new slash + new global mutable module-state + new `router/oneshot.py` module) + 2 (Discord-facing surface) + 5 (privacy-invariant — sensitivity gate parity) + 6 (load-bearing — `ask_router` hot path) all fire → MANDATORY-CR. CR ran under `claude-sonnet-4-6`. 8 Patches; **8/8 applied = 100%** (CR-F1 cache-hit-clobber, CR-F2 mcp_server docstring count, CR-F3 wrong logger name, CR-F4 generator return type, CR-F5 column-count comment, CR-F6 helper extraction, CR-F7 escalation non-forwarding comment, CR-F8 epics.md OQ-2 annotation). Zero deferrals.

**Downstream consumers ready:** Story 9-4 (`/model <task> <model>` persistent override + `/model` inspect) extends the SKILL.md "Model override" section and the `verbs/router_control.py` verb pattern shipped here. Story 9-10 (Hermes config.yaml slash registration drift test) is the canonical owner of the OQ-2 discharge — when 9-10 ships, it MAY or may NOT introduce a runtime-registration mechanism; either way, the `set_model_oneshot` verb is MCP-dispatchable today.
