---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.4: `ask_router()` core orchestration — dispatch, timeout, schema validation, retry, escalate

Status: done

## Story

As Adam,
I want `ask_router(task_type, content, force_model=None, max_cost_usd=None) -> RouterResult` to be the single agent-facing LLM entry point, with the layered failure chain (timeout → schema validation → single retry with stricter prompt → escalate-to-next-tier or return structured error),
So that every LLM call in the system goes through one cost-disciplined path and the agent never sees raw exceptions.

## Context

This is the capstone of the Router foundation. Story 2-1 shipped error/audit shapes; 2-2 shipped the policy schema + hot-reload; 2-3 shipped the Ollama adapter. Story 2-4 ties them together into the function every downstream Router call goes through. After this story, Stories 2-5 (lanes), 2-6 (Anthropic), 2-7 (response cache), 2-8 (budget), 2-9 (anomaly+kill), 2-10 (Hermes) all bolt onto specific seams of the orchestration.

## Acceptance Criteria

**AC-1 (Adapter registry).** `mailbot_api/router/registry.py` (NEW FILE) holds a `_ADAPTER_REGISTRY: dict[str, ModelAdapter]` keyed by model_id. Exposes:
- `def register_adapter(model_id: str, adapter: ModelAdapter) -> None` — idempotent register.
- `def get_adapter(model_id: str) -> ModelAdapter` — raises `KeyError` if unknown.
- `def init_default_adapters() -> None` — called from FastAPI lifespan: reads `OLLAMA_URL` via `get_secret_optional` and registers an `OllamaAdapter("qwen2.5:3b-instruct-q4_K_M", ...)`. The Anthropic adapters (Story 2-6) will register themselves in their own lifespan-init pass.

**AC-2 (Pricing skeleton).** `mailbot_api/router/pricing.py` (NEW FILE) exposes `def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int, cached_tokens_in: int = 0) -> float`. For Story 2-4: Qwen models return 0.0 (free-tier); Anthropic models return a conservative placeholder estimate using rough May-2026 rates (Story 2-6 will replace with verified numbers + cached-input discount handling). Pricing is a pure function — no DB, no network.

**AC-3 (Prompt-module registry).** `mailbot_api/prompts/__init__.py` (NEW FILE if absent) exposes `def resolve_prompt(task_type: str, prompt_version: str) -> PromptModule` where `PromptModule` is a Pydantic-validated shape with `SYSTEM: str`, `USER_TEMPLATE: str`, `OUTPUT_SCHEMA: type[BaseModel]`. Resolution is `mailbot_api/prompts/<task_type>/<prompt_version>.py` import-as-module. Missing module → `RouterError(code=PROVIDER_ERROR, message="prompt not found: <task>/<version>")`.

Story 2-4 ships a minimal `prompts/coarse_class/v1.py` with the three constants — enough to make the Router runnable in tests. Real prompt bodies land in Epic 3.

**AC-4 (Escalation chain).** `mailbot_api/router/escalation.py` (NEW FILE) exposes `def next_tier(current_model: str) -> str | None` implementing the demotion chain in reverse: `qwen2.5:3b-instruct-q4_K_M` → `claude-haiku-4-5-20251001` → `claude-opus-4-7` → `None`. The chain is the canonical source for `model_chosen_reason="escalated_from_<X>"` semantics.

**AC-5 (`ask_router` core).** `mailbot_api/router/router.py` (NEW FILE) exposes:

```python
async def ask_router(
    task_type: str,
    content: dict[str, Any],
    *,
    force_model: str | None = None,
    max_cost_usd: float | None = None,
    caller_origin: str = "unknown-internal",
    caller_verb: str | None = None,
    email_id: str | None = None,
) -> RouterResult
```

Behavior:
1. Capture policy snapshot via `snapshot_for_dispatch()`. If `task_type` not in policy.tasks → `RouterResult(ok=False, error=RouterError(code=PROVIDER_ERROR, message=f"task_type not in policy: {task_type}"))`.
2. Resolve prompt module via `resolve_prompt(task_type, policy_entry.prompt_version)`. Render `USER_TEMPLATE` with `content` dict (simple `.format(**content)` — prompt bodies own their own templating discipline).
3. Resolve model: `force_model or policy_entry.model`. Resolve adapter via `get_adapter(model)`.
4. Wrap the entire dispatch in a `try/except/finally`:
   - **`try`**: call `adapter.call(...)`; validate response against `OUTPUT_SCHEMA`; on success return `RouterResult(ok=True, output=..., ...)`.
   - **`except AdapterTimeout`** → `RouterResult(ok=False, error=RouterError(code=TIMEOUT, ...), ...)`; NO retry.
   - **`except AdapterProviderError`** → `RouterResult(ok=False, error=RouterError(code=PROVIDER_ERROR, ...), ...)`.
   - **schema-validation failure (ValidationError caught)**: retry ONCE with stricter prompt (USER_TEMPLATE prefixed with "Your previous reply was not valid JSON matching the schema. Reply only with valid JSON matching this schema: SCHEMA_DUMP"). If retry succeeds → `RouterResult(ok=True, ..., outcome="retry_recovered")`. If retry also fails:
     - `policy_entry.escalate=True` → recurse into the same `ask_router` flow with `force_model=next_tier(model)`. On success → `outcome="escalated"`, `model_chosen_reason="escalated_from_<original>"`. On failure → `RouterResult(ok=False, error=RouterError(code=SCHEMA_VALIDATION_FAILED, ...))`.
     - `policy_entry.escalate=False` → `RouterResult(ok=False, error=RouterError(code=SCHEMA_VALIDATION_FAILED, ...))`.
   - **`except Exception`** (catch-all per AR-PAT-4) → `RouterError(code=PROVIDER_ERROR, message=sanitize_error(exc))`.
   - **`finally`**: ALWAYS call `record_router_call(...)` with the row constructed from the result. Audit row never lost.

**AC-6 (`ask_router` verb shim).** `mailbot_api/verbs/ask_router.py` (NEW FILE) re-exports the function for the verb registration surface. For Story 2-4 it's a thin pass-through; Story 2-10 will add the OpenAI-shape adaptation. `mailbot_api/verbs/__init__.py` may need creation.

**AC-7 (Router public API).** `mailbot_api/router/__init__.py` exports ONLY `ask_router` from its public surface. Internal helpers (`get_adapter`, `register_adapter`, etc.) stay accessible by full path but are not in `__all__`.

**AC-8 (lifespan adapter init).** `mailbot_api/main.py` lifespan calls `init_default_adapters()` after policy load. Adapter init reads `OLLAMA_URL` via `get_secret_optional` (default `http://localhost:11434`). Story 2-6 will add Anthropic adapter init in the same hook.

**AC-9 (record_router_call wired into finally).** Every code path through `ask_router` writes a `RouterCallRow` via Story 2-1's `record_router_call`. The row's `outcome` reflects: `ok` / `retry_recovered` / `escalated` / `failed`. The `model_chosen_reason` reflects: `policy` / `override` / `escalated_from_<X>`. `caller_origin` is the caller's argument (default `unknown-internal` per AR-D2-2 placeholder until Story 2-10 wires real values).

**AC-10 (Unit tests — full failure chain coverage).** `tests/unit/router/test_router.py` (NEW FILE) uses a fake `ModelAdapter` that returns scripted responses and exercises:
- Happy path → `ok=True`, `outcome="ok"`, `model_chosen_reason="policy"`, row written.
- `force_model` override → `model_chosen_reason="override"`.
- AdapterTimeout → `ok=False`, `error.code="timeout"`, no retry, row with `outcome="failed"`.
- Schema-validation failure + retry succeeds → `ok=True`, `outcome="retry_recovered"`.
- Schema-validation failure + retry fails + `escalate=False` → `ok=False`, `error.code="schema_validation_failed"`.
- Schema-validation failure + retry fails + `escalate=True` + escalation succeeds → `ok=True`, `outcome="escalated"`, `model_chosen_reason="escalated_from_<X>"`.
- Schema-validation failure + retry fails + `escalate=True` + escalation also fails → `ok=False`, `error.code="schema_validation_failed"`.
- AdapterProviderError → `ok=False`, `error.code="provider_error"`, sanitized message.
- Generic exception inside dispatch → `ok=False`, `error.code="provider_error"`, sanitized message; row written.
- `task_type` not in policy → `ok=False`, `error.code="provider_error"`, helpful message.
- DB-write failure inside the `finally` block doesn't propagate (Story 2-1's audit-loss-acceptable contract is the safety net).
- Policy snapshot captured at dispatch time stays stable even if policy is swapped mid-call (uses Story 2-2's `snapshot_for_dispatch`).

**AC-11 (boundary updates).** None expected — the only new files are inside `mailbot_api/router/`, `mailbot_api/verbs/`, `mailbot_api/prompts/`. Existing rules (no `import ollama` outside `models.py`; no raw `INSERT INTO router_calls` outside `audit.py`; no `yaml.safe_load` outside `policy.py`) all already cover these paths correctly.

**AC-12 (all gates green).** ruff, mypy --strict, boundary, pytest — all clean. Baseline 203 → +N for the router-orchestration tests.

## Tasks / Subtasks

- [x] **Task 1** — Adapter registry (AC: #1)
- [x] **Task 2** — Pricing skeleton (AC: #2)
- [x] **Task 3** — Prompt-module registry + coarse_class/v1.py stub (AC: #3)
- [x] **Task 4** — Escalation chain (AC: #4)
- [x] **Task 5** — `ask_router` core in `router/router.py` (AC: #5, #9)
- [x] **Task 6** — Verb shim + `verbs/__init__.py` (AC: #6)
- [x] **Task 7** — `router/__init__.py` public API (AC: #7)
- [x] **Task 8** — Lifespan adapter init (AC: #8)
- [x] **Task 9** — Unit tests for the full failure chain (AC: #10)
- [x] **Task 10** — All gates green (AC: #12)

## Dev Notes

### Why split the orchestration across 4 files

Splitting `registry.py` / `pricing.py` / `escalation.py` / `router.py` lets each piece be unit-tested in isolation. Story 2-7 (response cache) and Story 2-8 (budget guard) bolt onto specific seams: the cache wraps `router.py`; the budget guard runs as a pre-dispatch gate inside `router.py` and a post-dispatch update via `pricing.py`. Keeping them separable now avoids a 600-line `router.py` later.

### Why the prompt module is .py and not YAML

Per architecture line 852-877, prompt modules carry executable Pydantic OUTPUT_SCHEMA classes — strings won't suffice. Python module imports also give us free dependency-injection for testing.

### Retry-with-stricter-prompt details

The "stricter" prompt prefix is hard-coded inside `router.py` for Story 2-4. Story 2-7's response cache and any future "calibrated retry" logic can lift it into the prompt module itself; for now it's a one-line prefix.

### Why the `Any`-typed `content: dict[str, Any]` parameter

The verb-facing surface accepts any dict that's compatible with `USER_TEMPLATE.format(**content)`. Per-prompt-module schemas (Story 3.x) will tighten this, but at the Router level the constraint is "the prompt module renders correctly" — the Router doesn't inspect content shape itself.

### Files being touched / created

**Created:** `mailbot_api/router/router.py`, `mailbot_api/router/registry.py`, `mailbot_api/router/pricing.py`, `mailbot_api/router/escalation.py`, `mailbot_api/prompts/__init__.py`, `mailbot_api/prompts/coarse_class/__init__.py`, `mailbot_api/prompts/coarse_class/v1.py`, `mailbot_api/verbs/__init__.py`, `mailbot_api/verbs/ask_router.py`, `tests/unit/router/test_router.py`, `tests/unit/router/test_registry.py`, `tests/unit/router/test_escalation.py`, `tests/unit/router/test_pricing.py`

**Updated:** `mailbot_api/router/__init__.py`, `mailbot_api/main.py`

### References

- [Source: epics.md#Story 2.4]
- [Source: architecture.md §"Errors as data" + Rule I + AR-PAT-4]
- [Source: mailbot_api/router/errors.py] for `RouterResult` / `RouterError` / `ErrorCode` / `sanitize_error`
- [Source: mailbot_api/router/policy.py] for `snapshot_for_dispatch` / `PolicyTable`
- [Source: mailbot_api/router/models.py] for `ModelAdapter` / `AdapterTimeout` / `AdapterProviderError`
- [Source: mailbot_api/observability/audit.py] for `RouterCallRow` / `record_router_call`

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- **Capstone story** — Router foundation now complete. Stories 2-5/2-7/2-8 bolt onto specific seams in `router.py`; 2-6 adds the AnthropicAdapter via the same registry; 2-9 adds the kill-switch + anomaly checks; 2-10 adds Hermes aux + caller_origin tracking.
- **Code review (claude-sonnet-4-6): 6 findings → 5 patched + 2 deferred.** HIGH escalation-cap (1-hop enforced via `policy_entry.model_copy(update={"escalate": False})` on the recursive call); MEDIUM retry-exception surfacing (now appears in error message with type + sanitized text); MEDIUM importlib negative-cache popping (`sys.modules.pop(module_path, None)` on ImportError); MEDIUM audit row order documentation (module docstring updated — column addition deferred); LOW `_reset_registry_for_test` removed from `__all__`; 2 LOW deferred (pricing.py 0.0-for-unknown is Story 2-9 anomaly mitigation; test comment was correct after the HIGH fix).
- **Mid-impl fix unlocked by 2-4:** `_ESCALATED_FROM_RE` in `audit.py` (Story 2-1) was too narrow — model ids contain colons (`qwen2.5:3b-instruct-q4_K_M`). Widened to `r"^escalated_from_[\w.:\-]+$"`. Forward-compatible widening; the existing AC-7 reason-validation tests still pass.
- **Escalation cap regression test ships:** `test_ask_router_escalation_cap_at_one_hop` registers all three adapters (qwen + haiku + opus) and asserts opus is NEVER invoked even when the chain would theoretically reach it. Same test pattern for retry-leg exception surfacing: `test_ask_router_retry_timeout_surfaces_in_error_message`.
- **Importlib regression test ships:** `test_resolve_prompt_does_not_wedge_on_failed_import` asserts the negative-cache entry is popped and a re-attempted import is not short-circuited.
- **237 passed + 2 skipped.** (203 baseline → 237, +34 net new tests across 4 new test files + 2 added for review-fix regressions.)
- **Sub-second precision audit-ts (deferred from Story 2-1):** still NOT applied. Acceptable for now; will likely surface as a real correctness issue when Story 2-5's lane scheduler produces audit rows in tight bursts. Note in `epic-run-flags.md`.

### File List

**Created:**

- `mailbot_api/router/router.py` — `ask_router` + `_dispatch_with_failure_chain` + `_record` helpers
- `mailbot_api/router/registry.py` — `_ADAPTER_REGISTRY` + register/get/init/reset
- `mailbot_api/router/pricing.py` — `estimate_cost_usd` skeleton (Story 2-6 verifies)
- `mailbot_api/router/escalation.py` — `next_tier` chain
- `mailbot_api/prompts/__init__.py` — `resolve_prompt` + `PromptModule` + `PromptResolutionError` + sys.modules pop on ImportError
- `mailbot_api/prompts/coarse_class/__init__.py` — package marker
- `mailbot_api/prompts/coarse_class/v1.py` — minimal stub
- `mailbot_api/verbs/__init__.py` — package docstring
- `mailbot_api/verbs/ask_router.py` — verb shim re-export
- `tests/unit/router/test_router.py` — failure-chain coverage + escalation-cap + retry-exc regression tests
- `tests/unit/router/test_registry.py`
- `tests/unit/router/test_escalation.py`
- `tests/unit/router/test_pricing.py`
- `tests/unit/prompts/__init__.py`
- `tests/unit/prompts/test_resolve.py` — sys.modules-pop regression
- `_bmad-output/implementation-artifacts/2-4-...pre-review.md`

**Updated:**

- `mailbot_api/router/__init__.py` — exports only `ask_router`
- `mailbot_api/main.py` — lifespan calls `init_default_adapters()` after policy load
- `mailbot_api/observability/audit.py` — `_ESCALATED_FROM_RE` widened to accept colons; docstring documents row-insertion-order semantics on escalation

## Change Log

- 2026-06-01 (claude-opus-4-7, autonomous-epic-run) — Story 2-4 implemented: ask_router orchestration with full failure chain (timeout → schema-fail-retry → escalate). 9 production modules + 4 test modules. Code-review applied 5 of 6 findings (1 HIGH escalation cap, 3 MEDIUM, 1 LOW) + 2 deferred. 237 tests pass (+34 net). All gates green.


### Review Findings

- [x] \[Review]\[Decision] Unbounded multi-hop escalation — `_dispatch_with_failure_chain` passes `policy_entry` (with `escalate=True`) unchanged into the recursive escalated call, so haiku schema failure will further escalate to opus, creating a 3-hop chain. AC-5 says "recurse into the same `ask_router` flow" which technically permits this, but the test comment at `test_router.py:282-284` explicitly states "the chain only escalates one tier per failure attempt" — evidence of intent divergence. Decide: is unbounded chaining intentional, or should escalation depth be capped at 1 hop (i.e., pass `policy_entry` with `escalate=False` on the recursive call)? [`mailbot_api/router/router.py:327-338`, `tests/unit/router/test_router.py:282-284`]
- [x] \[Review]\[Patch] Retry adapter exception is silently discarded — when the retry call raises `AdapterTimeout` or `AdapterProviderError`, `retry_exc` is set but never surfaced in the final `RouterError.message`. The error returned says `"response failed schema validation; retry also failed"` even when the retry actually timed out or hit a provider error. Callers cannot distinguish a double-validation-fail from a retry-timeout. Fix: incorporate the retry exception type/message into the final error message. [`mailbot_api/router/router.py:285-291, 360-371`]
- [x] \[Review]\[Patch] `importlib.import_module` negative result is cached by Python's module system — if a prompt module raises `ImportError` on first load (bad dependency, syntax error in the module), `sys.modules` stores a `None` sentinel and all subsequent calls to `resolve_prompt` for that path permanently raise `ImportError` without re-attempting the import. The router is permanently wedged for that `task_type` until process restart. Fix: catch `ImportError` and call `sys.modules.pop(module_path, None)` before re-raising `PromptResolutionError`, so a corrected module can be hot-reloaded. [`mailbot_api/prompts/__init__.py:51-55`]
- [x] \[Review]\[Patch] Audit row insertion order is reverse of dispatch order with no sub-second discriminator — on escalation, the inner (escalated) call's `finally` fires before the outer call's `finally`, so the haiku row inserts with a lower `id` than the qwen row. Both rows may share the same second-precision `ts`. Any future query ordering rows by `id` or `ts` to reconstruct dispatch sequence will see the escalated tier BEFORE the original tier. Fix: add a `dispatch_seq` or `parent_call_id` column, or document clearly in `audit.py` that `id` order is `finally`-unwind order (reverse of dispatch). [`mailbot_api/observability/audit.py`, `tests/unit/router/test_router.py:255-266`]
- [x] \[Review]\[Patch] `_reset_registry_for_test` is in `__all__` of `registry.py` — a test-only helper exported in the module's public API. Any `from mailbot_api.router.registry import *` or IDE auto-complete will surface it to production callers. Fix: remove from `__all__`; it remains importable by explicit path for tests. [`mailbot_api/router/registry.py:57-62`]
- [x] \[Review]\[Defer] `estimate_cost_usd` returns 0.0 for unknown models with no log/warning — a `force_model` pointing to an unpriced model silently zeros out cost in the audit trail. Story 2-9's anomaly detection on `caller_origin` is documented as the intended mitigation. [`mailbot_api/router/pricing.py:47-49`] — deferred, pre-existing design choice documented in code; Story 2-9 is the intended resolution
- [x] \[Review]\[Defer] Test comment at `test_router.py:282-284` is factually incorrect — comment says "the chain only escalates one tier per failure attempt in our implementation" but the implementation does not enforce this. If the multi-hop question (Finding 1 above) is resolved as "intentional", this comment must be corrected; if capped at 1 hop, the implementation changes. Either way the comment is wrong as written. [`tests/unit/router/test_router.py:282-284`] — deferred, dependent on resolution of Decision finding above
