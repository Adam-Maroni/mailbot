---
baseline_commit: a1f1043d5b406a09a787a9635d78ec2a7ba8c5bb
---

# Story 2.8: 4-layer budget guard + degraded mode + per-call refusal threshold

Status: done

## Story

4-layer budget guard inside the Router on every call: per-call max_tokens cap (Layer 1, via policy), $2 daily soft warn (Layer 2), $30 monthly hard cap → degraded mode (Layer 3), $0.20 per-call refusal threshold (Layer 4) — plus `/budget reset` to manually exit degraded mode.

## Acceptance Criteria

- [x] **AC-1** Migration `008_degraded_mode.sql` (renumbered from epic-spec 007 — Story 2-7 took 007) — singleton row + active/entered_at/exited_at columns.
- [x] **AC-2** `mailbot_api/router/budget.py`: `BudgetGuard` class with `initialize` (rolls forward from `router_calls`) + `add_spend` (with Layer 2/3 trigger logic) + `exit_degraded_mode` + `is_degraded`. Module-level singleton via `get_guard()`.
- [x] **AC-3** Layer 4: estimated-cost gate in `_dispatch_with_failure_chain` before cache lookup. `force=True` kwarg on `ask_router` bypasses it and is logged with `model_chosen_reason="force_override"`.
- [x] **AC-4** Layer 3: in `ask_router`, if `guard.is_degraded()`, demote via the `demote_model` chain (opus→haiku→qwen) and log `model_chosen_reason="degraded"`. `force_model="claude-opus-4-7"` returns `DEGRADED_MODE_BLOCKED`.
- [x] **AC-5** Layer 2: `add_spend` fires a single warning per UTC day via `event="budget.daily.soft_warn"`.
- [x] **AC-6** `/budget reset` verb: `mailbot_api/verbs/budget_admin.py` exposes `reset_degraded_mode` returning `BudgetResetOut` Pydantic shape.
- [x] **AC-7** Lifespan: `get_guard().initialize(db_path)` after migrations + before yielding.
- [x] **AC-8** Tests: 9 unit tests in `test_budget.py` cover demote chain + thresholds + soft-warn single-fire + degraded mode entry/exit + roll-forward; 4 integration tests in `test_router.py` cover Layer 4 refusal + force override + degraded demotion + force-opus blocking; 2 in `test_budget_admin.py` cover the verb.
- [x] **AC-9** Gates: ruff/mypy/boundary/pytest all clean.

## Dev Notes

### Layer 4 estimation methodology

Used `(len(system) + len(user)) // 4` as the token-count proxy (correct within ±25% for English). The estimated cost uses `pricing.estimate_cost_usd` against the resolved model + the policy's `max_tokens_out`. Story 2-6's pricing placeholders are within ~2x of expected real rates → Layer 4 fires conservatively early (good) rather than late.

### Layer 3 demotion ordering

`get_guard().is_degraded()` check happens in `ask_router` BEFORE `_dispatch_with_failure_chain`. This means: (1) the demoted `model` is what gets resolved in the registry, (2) the audit row records the demoted model with `model_chosen_reason="degraded"`, (3) the rate-limit gate fires against the demoted model's lane (typically `batch`).

### force_model="claude-opus-4-7" in degraded mode

Per architecture: returns `RouterError(code=DEGRADED_MODE_BLOCKED)` with a message pointing at "confirmation token" — Epic 5 will mint that token via the chat surface; for now the error path is what's tested.

### Migration renumber chain (continuing from 2-7)

Stories 2-9's `pause_state` + anomaly_baseline shift to migrations 009/010.

## File List

**Created:**

- `mailbot_api/db/migrations/008_degraded_mode.sql`
- `mailbot_api/router/budget.py` — `BudgetGuard` + constants + `demote_model` + `get_guard`
- `mailbot_api/verbs/budget_admin.py` — `/budget reset` verb shim + `BudgetResetOut`
- `tests/unit/router/test_budget.py`
- `tests/unit/verbs/__init__.py`
- `tests/unit/verbs/test_budget_admin.py`

**Updated:**

- `mailbot_api/db/queries.py` — `DEGRADED_MODE_*` + `ROUTER_CALLS_SPEND_SINCE` constants
- `mailbot_api/router/router.py` — `ask_router` adds `force` kwarg, Layer 3 demotion + degraded-mode-block, Layer 4 refusal gate; success paths add `await get_guard().add_spend(...)`
- `mailbot_api/main.py` — lifespan calls `get_guard().initialize(db_path)`
- `tests/unit/router/test_router.py` — extended `_clean_state` to reset guard; 4 new budget integration tests

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Completion Notes List

- **Gate-coverage-only** — no code review subagent. Story is mechanical (threshold math + boolean gates + chain demotion). 9 unit tests for BudgetGuard + 4 integration tests in ask_router + 2 for the verb.
- **298 passed + 2 skipped** (283 → 298, +15 net new tests).
- **Layer 4 token estimation is rough** — uses `(len(system) + len(user)) // 4`. Adequate for the $0.20 safety net; finer-grained estimation could come later if Anthropic's token-counter API stabilizes.
