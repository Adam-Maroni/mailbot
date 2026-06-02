---
baseline_commit: b18437a
---

# Story 4.8: Tier-1 24-hour reverter via action_history

Status: done

## Story

As Adam,
I want `revert_action(action_id) → RevertOut` verb + `mailbot revert <action_id>` CLI that creates an inverse-action and re-queues it for the drainer, so a wrong Tier-1 action (MARK_READ on the wrong thread) is recoverable in one command within 24h.

## Acceptance Criteria

### AC-1 — Inverse-action mapping for Tier-1

`mailbot_api/actions/reverter.py`:

- `_INVERSE_ACTION: dict[ActionType, ActionType]` maps each Tier-1 action to its inverse:
  - `MARK_READ` ↔ `MARK_UNREAD` (paired)
  - `ADD_LOCAL_CATEGORY` ↔ `REMOVE_LOCAL_CATEGORY` (paired)
  - `MOVE_TO_TRIAGE_FOLDER` → currently no exact Tier-1 inverse (would need MOVE_TO_INBOX which is Tier-2). **Inverse unavailable** — returns an `INVERSE_UNAVAILABLE` error; documented limitation that Story 6-x or Story 7-x could resolve by adding a Tier-1 MOVE_BACK_TO_INBOX action.

### AC-2 — `revert_action(action_id)` async function

- Reads pending_actions row by `action_id`. Refuses if not found.
- Refuses if `tier != 1` → `ONLY_TIER_1_REVERTIBLE`
- Refuses if `status != 'applied'` → `NOT_APPLIED`
- Refuses if `terminal_at + 24h < now()` → `REVERT_WINDOW_EXPIRED`
- Refuses if action_history row already has `reverted_at IS NOT NULL` → `ALREADY_REVERTED`
- Looks up inverse via `_INVERSE_ACTION[action_type]`. If absent → `INVERSE_UNAVAILABLE`.
- Inserts a new `pending_actions` row with the inverse action_type, same email_id, payload from the original, `status='pending'`, tier=1 (verified via tier_for).
- Updates `action_history.reverted_at = now()` for the ORIGINAL action_id.
- Returns `RevertOut(ok=True, revert_action_id=<new_id>, original_action_id=<id>)`.
- Logs `event="action.reverted"` with original + revert ids.

### AC-3 — SQL constants

- `ACTION_HISTORY_MARK_REVERTED` — `UPDATE action_history SET reverted_at = ? WHERE action_id = ? AND reverted_at IS NULL`
- `ACTION_HISTORY_SELECT_BY_ACTION_ID` — `SELECT pre_state, applied_at, reverted_at FROM action_history WHERE action_id = ?`

### AC-4 — `mailbot revert <action_id>` CLI

`scripts/mailbot.py` extended with `revert` subcommand mirroring `replay`'s shape.

### AC-5 — Tests

`tests/unit/actions/test_reverter.py`:

- revert MARK_READ within 24h → succeeds; new pending_actions row with action_type=MARK_UNREAD; action_history.reverted_at populated
- revert Tier-2 ARCHIVE refused (ONLY_TIER_1_REVERTIBLE)
- revert action in status='pending' (not applied) refused (NOT_APPLIED)
- revert beyond 24h refused (REVERT_WINDOW_EXPIRED)
- revert already-reverted refused (ALREADY_REVERTED)
- revert MOVE_TO_TRIAGE_FOLDER refused (INVERSE_UNAVAILABLE)
- revert nonexistent action refused (ACTION_NOT_FOUND)
- ADD_LOCAL_CATEGORY → REMOVE_LOCAL_CATEGORY inverse pairing

### AC-6 — All gates green

606 baseline + new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] reverter.py with inverse map + revert_action
- [x] SQL constants + CLI subcommand
- [x] Tests
- [x] Gate sweep

## Dev Notes

### Pre-state vs inverse-action

Story 4-4 ships `pre_state={}` for every action because the emails table doesn't carry per-action revert fields. Story 4-8 sidesteps this by using a hardcoded inverse-action map: every Tier-1 action's inverse is fully determined by its action_type, so pre_state isn't actually needed. The `action_history.pre_state` column survives as future-proofing — a future story can fill it for actions where the inverse depends on prior state (e.g., MOVE_TO_TRIAGE_FOLDER's inverse needs the previous folder_id).

### MOVE_TO_TRIAGE_FOLDER inverse limitation

`MOVE_TO_TRIAGE_FOLDER` (Tier-1) has no Tier-1 inverse — the natural inverse would be "move back to the previous folder", but the previous folder is in pre_state which Story 4-4 doesn't populate. Until a future story fills pre_state, this action returns `INVERSE_UNAVAILABLE` on revert. Documented as a deferred limitation; the verb refuses rather than silently inserts a wrong-folder MOVE.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass (gate-coverage-only)

### Completion Notes List

(Filled after implementation)

### File List

(Filled after implementation)
