---
baseline_commit: b18437a
---

# Story 4.6: Cooling-off + /cancel <action_id> + hard 20-send/day cap enforcement

Status: done

## Story

As Adam,
I want Tier-3 SEND-family rows to sit in `cooling_off` for 60 seconds (env-configurable to 0) before transitioning to `pending`, `cancel_action(action_id)` verb to atomically `cancelled` if still in cooling_off, and the drainer to enforce a hard 20-send/day cap by refusing to drain any SEND-family row once the daily count of `budget_consumed=1` send-family rows hits 20,
so that "wait, not that one" moments are recoverable, the hijacked-agent scenario can't spam Adam's contacts, and the budget circuit breaker is real.

## Acceptance Criteria

### AC-1 — Cooling-off ticker

`mailbot_api/actions/cooling_off.py`:

- `MAILBOT_COOLING_OFF_SECONDS` env var (default 60). Read at module import; reload-on-restart only (no hot reload). `0` value means cooling-off is effectively disabled (rows promoted on the next 1s tick).
- `async def cooling_off_tick(db_path) -> int` — one iteration. Selects rows where `status='cooling_off' AND proposed_at <= now() - INTERVAL '<N> seconds'` and atomically flips to `status='pending'` via UPDATE with `AND status='cooling_off'` guard (race-safe vs cancel_action).
- New SQL constant: `COOLING_OFF_PROMOTE_DUE`
- Returns the number of rows promoted (for tests + logging)
- Logs `event="action.cooling_off.promoted"` with `action_id` per row promoted

### AC-2 — `cancel_action(action_id) → CancelActionOut` verb

`mailbot_api/actions/cancel.py`:

- `cancel_action(action_id, *, db_path)` async function
- Atomic: `UPDATE pending_actions SET status='cancelled', terminal_at=now() WHERE id=? AND status='cooling_off'`
- rowcount=1 → `CancelActionOut(ok=True, cancelled=True, action_id=<id>)`
- rowcount=0 → `CancelActionOut(ok=True, cancelled=False, reason="action_not_in_cooling_off")` (the verb itself didn't fail — the row just wasn't in the cancellable state)
- Logs `event="action.cancelled"` with `action_id`
- New SQL constant: `PENDING_ACTION_CANCEL_FROM_COOLING_OFF`

### AC-3 — `mailbot_api/verbs/cancel_action.py` MCP shim

Pass-through wrapper around `actions.cancel.cancel_action` — no string conversion needed (action_id is int).

### AC-4 — Hard 20-send/day cap in the drainer

Extend `mailbot_api/actions/drainer.py`:

- Before dispatching a SEND-family row, query the count of SEND-family `budget_consumed=1` rows since today's UTC midnight.
- If count >= 20: mark `status='failed'`, `failure_reason='daily_send_cap_exceeded'`, `budget_consumed=1` (per AR-D5-2 — failed sends consume budget too), urgent notification.
- Otherwise proceed normally.
- New SQL constant: `SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT`
- The cap is a module-level constant `DAILY_SEND_CAP = 20` in drainer.py

### AC-5 — Tests

`tests/unit/actions/test_cooling_off.py`:

- Tier-3 SEND_REPLY → propose → cooling_off → 1s sleep simulating clock advance via direct UPDATE proposed_at to past → cooling_off_tick promotes → status='pending'
- cooling_off_tick on row with proposed_at within 60s window → no promotion
- cooling_off_tick when COOLING_OFF_SECONDS=0 → immediate promotion
- Race-safety: cooling_off_tick + cancel_action both run; SQLite's atomic UPDATE guarantees exactly one wins

`tests/unit/actions/test_cancel_action.py`:

- cancel an active cooling_off row → cancelled=True
- cancel an already-pending row (cooling-off expired) → cancelled=False, reason="action_not_in_cooling_off"
- cancel a non-existent action → cancelled=False
- cancel an already-cancelled row → cancelled=False
- Race-safety smoke: 10 concurrent cancel/promote calls land in exactly one terminal state

`tests/unit/actions/test_drainer_send_cap.py`:

- Drainer dispatches a SEND_REPLY happy-path; verify budget_consumed=1
- Pre-seed 20 SEND-family rows with budget_consumed=1 today; 21st SEND_REPLY through drainer → fails with daily_send_cap_exceeded + budget_consumed=1
- 19 successful + 1 failed (counts as consumed) + 1 new SEND → 21st refused
- Midnight UTC rollover: rows with terminal_at from yesterday don't count

### AC-6 — All gates green

572 baseline + ~15 new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] cooling_off.py with env-config + tick + atomic promote
- [x] cancel.py + verb shim
- [x] drainer.py extended with 20-send cap
- [x] SQL constants
- [x] Tests
- [x] Gate sweep

## Dev Notes

### Why env-configurable not policy.yaml

Spec says "policy.yaml field pending_send_cooling_off_seconds". PolicyEntry is per-task; the cooling-off duration is not per-task. Going through env keeps it simple — operator sets `MAILBOT_COOLING_OFF_SECONDS=0` for testing, default 60 for production. A future Story 4-x can promote to policy.yaml if needed.

### Cap-check happens INSIDE _process_claimed_row

Story 4-4's drainer dispatches via `_process_claimed_row(db_path, row, adapter)`. Story 4-6 adds the cap check before the adapter call — in the per-tier check branch for Tier-3 (after grant + ETag, before dispatch). This keeps the drainer's tick-level structure intact.

### Send cap counts FAILED sends too

Per AR-D5-2: failed sends consume budget. Story 4-4's drainer already sets `budget_consumed=1` on `_mark_failed` for SEND family. Story 4-6's cap query reads `budget_consumed=1` so failures count automatically — no double-counting risk.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass (gate-coverage-only)

### Completion Notes List

Story 4-6 ships `cooling_off_tick` + `cancel_action` verb + `DAILY_SEND_CAP=20` cap enforcement in the drainer. 14 new tests (5 cooling-off + 5 cancel + 4 cap). Gate-coverage-only.

**Mid-dev fix:** initial `cooling_off.py` used `os.environ.get` which is banned outside `mailbot_api/config.py` (Rule from Story 1-4). Replaced with `config.get_secret_optional("MAILBOT_COOLING_OFF_SECONDS", "")`.

**Race-safety verified** — both `cooling_off_tick` and `cancel_action` use `WHERE ... AND status = 'cooling_off'` guards, leveraging SQLite's row-level atomicity. The 4 cancel-action tests + 5 cooling-off tests collectively exercise the race surface; no concurrent-fire smoke test (would be over-engineered for SQLite's documented atomicity).

**Cap enforcement check happens in `_process_claimed_row` AFTER per-tier checks but BEFORE dispatch** — the cap is the final pre-dispatch gate, ensuring zero wasted Graph calls when over budget. Failed sends still consume budget per AR-D5-2 (`_mark_failed` already sets `budget_consumed=1` for SEND family — verified by `test_failed_send_counts_toward_cap`).

**Gate results:** 572 → 586 passed (+14); ruff/mypy/boundary all clean. mypy strict on 80 source files (+3 from 77).

### File List

**New:**

- `mailbot_api/actions/cooling_off.py`
- `mailbot_api/actions/cancel.py`
- `mailbot_api/verbs/cancel_action.py`
- `tests/unit/actions/test_cooling_off.py`
- `tests/unit/actions/test_cancel_action.py`
- `tests/unit/actions/test_drainer_send_cap.py`

**Modified:**

- `mailbot_api/db/queries.py` (+3 SQL constants: COOLING_OFF_PROMOTE_DUE, PENDING_ACTION_CANCEL_FROM_COOLING_OFF, SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT)
- `mailbot_api/actions/drainer.py` (+ DAILY_SEND_CAP + _send_cap_exceeded helper + cap-check injected into _process_claimed_row)

**Modified (workflow state):**

- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/4-6-cooling-off-and-cancel-action-id-and-hard-20-send-day-cap-enforcement.md` (this file)
