---
baseline_commit: b18437a
---

# Story 4.2: pending_actions + action_grants + action_history schema + propose_action verb

Status: done

## Story

As Adam,
I want migrations 015/016/017 creating `pending_actions`, `action_grants`, and `action_history`, plus the Tier-0 verb `propose_action(email_id, action_type, **payload) → ProposeActionOut` that validates `action_type` via `ActionType`, computes tier via `tier_for()`, captures `emails.change_marker` for Tier-3 sends, refuses tier-promotion payloads, and routes the new row to its initial status (`cooling_off` for Tier-3 SEND family, `pending` for Tier-1 / Tier-3 DELETE, `pending_grant` for Tier-2),
so that the agent's first interaction with the action system is structurally tier-aware and the agent cannot promote an action's tier — FR-5.6 is enforced both at the verb boundary AND at the schema via `CHECK` constraints.

## Acceptance Criteria

### AC-1 — Migration 015_pending_actions.sql

**Given** Story 1-3's migration runner is in place and Story 4-1's `ActionType` enum is the source of truth,

**When** `mailbot_api/db/migrations/015_pending_actions.sql` is added,

**Then** it creates `pending_actions` with columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `email_id TEXT NULL` (nullable — `MODIFY_INBOX_RULE` / `TOUCH_DELEGATED_MAILBOX` aren't email-scoped)
- `action_type TEXT NOT NULL` with `CHECK(action_type IN ('mark_read', 'mark_unread', ...))` — explicit list of the 18 Tier-1/2/3 values from `ActionType` (Tier-0 deliberately excluded — Tier-0 verbs never enter pending_actions per the verb-boundary refusal at AC-7 below)
- `tier INTEGER NOT NULL CHECK(tier IN (1, 2, 3))`
- `payload TEXT NOT NULL` (JSON-serialized verb payload; empty `{}` permitted for parameter-less actions like `MARK_READ`)
- `proposed_at TEXT NOT NULL` (UTC ISO-8601 with `Z`)
- `proposed_by_grant_id INTEGER NULL` (FK to `action_grants.id` for Tier-2 actions covered by a batch grant)
- `change_marker_at_propose TEXT NULL` (captured at propose-time for Tier-3 ETag check at drain — set ONLY for Tier-3 rows with `email_id`; NULL for Tier-1 / Tier-2 / email-less Tier-3)
- `status TEXT NOT NULL CHECK(status IN ('pending', 'cooling_off', 'pending_grant', 'draining', 'applied', 'failed', 'cancelled'))`
- `retry_count INTEGER NOT NULL DEFAULT 0`
- `failure_reason TEXT NULL`
- `terminal_at TEXT NULL`
- `budget_consumed INTEGER NOT NULL DEFAULT 0 CHECK(budget_consumed IN (0, 1))`

**And** indexes:

- `ix_pending_actions_status_proposed_at ON pending_actions (status, proposed_at)`
- `ix_pending_actions_email_id ON pending_actions (email_id)`
- `ix_pending_actions_action_type ON pending_actions (action_type)`

**And** the migration header documents the `CHECK(action_type IN (...))` list as **sync'd with `mailbot_api/actions/types.py`** — if a new Tier-1/2/3 action is added there, this CHECK must be amended via a follow-up migration. The story's tests assert the in-migration list equals `{at.value for at in ActionType if tier_for(at) >= 1}`.

### AC-2 — Migration 016_action_grants.sql

**Given** migration 015 lands first,

**When** `mailbot_api/db/migrations/016_action_grants.sql` is added,

**Then** it creates `action_grants` with columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `action_type TEXT NOT NULL` with the same `CHECK(action_type IN (...))` Tier-1/2/3 list as 015 (mint_grant only mints grants for Tier-2/3 in Story 4-3, but the schema allows Tier-1 as a CHECK simplification — runtime enforcement of "Tier-1 doesn't need a grant" lives in Story 4-3's `mint_grant` verb)
- `email_ids TEXT NOT NULL` (JSON array; can be empty `[]` for grants like `MODIFY_INBOX_RULE` that aren't email-scoped — Story 4-3 enforces the per-action-type rule)
- `expires_at TEXT NOT NULL` (UTC ISO-8601 `Z`)
- `minted_at TEXT NOT NULL` (UTC ISO-8601 `Z`)
- `revoked_at TEXT NULL` (UTC ISO-8601 `Z`)

**And** indexes:

- `ix_action_grants_action_type_expires_at ON action_grants (action_type, expires_at)` (drainer's primary lookup pattern: "is there a valid grant for THIS action_type that hasn't expired?")

### AC-3 — Migration 017_action_history.sql

**Given** migrations 015/016 land first,

**When** `mailbot_api/db/migrations/017_action_history.sql` is added,

**Then** it creates `action_history` with columns:

- `action_id INTEGER PRIMARY KEY` (FK to `pending_actions.id`; PK because exactly one history row per action — written before Graph dispatch by Story 4-4's drainer)
- `pre_state TEXT NOT NULL` (JSON snapshot of the fields the action will modify; empty `{}` for actions with no pre-state to capture like `DELETE`)
- `applied_at TEXT NOT NULL` (UTC ISO-8601 `Z`)
- `reverted_at TEXT NULL` (UTC ISO-8601 `Z`; populated by Story 4-8's reverter)

**No additional indexes** — the PK on `action_id` is the only access pattern Story 4-8 needs.

### AC-4 — Migration chain integrity

**Given** the 3 new migrations land,

**When** the app starts on a fresh DB,

**Then** migrations 001 through 017 apply in numeric order (014 → 015 → 016 → 017), the `_migrations` table records each, and an integration test seeds a fresh DB through the lifespan then asserts `PRAGMA table_info(pending_actions)`, `PRAGMA table_info(action_grants)`, `PRAGMA table_info(action_history)`, and `PRAGMA index_list(pending_actions)` match the expected shapes.

**And** an idempotency test runs migrations twice (re-runs the lifespan) and asserts 015/016/017 are NOT re-applied (the "WHERE filename = ?" exists-check honored from Story 1-3).

**And** the `CHECK(action_type IN (...))` constraint is verified by attempting an INSERT with an invalid action_type and asserting `sqlite3.IntegrityError`.

### AC-5 — SQL constants for pending_actions / action_grants / action_history in queries.py

**Given** Story 1-4's Rule C (raw SQL only in `mailbot_api/db/queries.py` and `mailbot_api/db/migrations_runner.py`),

**When** `mailbot_api/db/queries.py` is extended,

**Then** the following constants are added (named per existing convention):

- `PENDING_ACTION_INSERT` — `INSERT INTO pending_actions (email_id, action_type, tier, payload, proposed_at, proposed_by_grant_id, change_marker_at_propose, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)` — returns `lastrowid` via the connection wrapper
- `PENDING_ACTION_SELECT_BY_ID` — `SELECT * FROM pending_actions WHERE id = ?` (for tests + future audit reads)
- `EMAIL_CHANGE_MARKER_SELECT` — `SELECT change_marker FROM emails WHERE graph_id = ?` (consumed by `propose_action` for Tier-3 send capture)

**And** the boundary checker continues to pass — no string-literal action types appear in `queries.py` (the SQL uses bound parameters `?`, not literals).

### AC-6 — ProposeActionOut + ProposeActionError Pydantic shapes

**Given** the existing pattern of `RouterResult` / `RouterError` from Story 2-1 / 2-4,

**When** `mailbot_api/actions/propose.py` is implemented (NEW module; not to be confused with `mailbot_api/verbs/propose_action.py` which is the MCP-facing shim),

**Then** the module exposes:

- `ProposeActionError(BaseModel, frozen)` with `code: Literal["INVALID_ACTION_TYPE", "TIER_PROMOTION_ATTEMPT", "TIER_0_NOT_QUEUEABLE", "EMAIL_NOT_FOUND", "EMAIL_DELETED", "INVALID_PAYLOAD"]` and `message: str`
- `ProposeActionOut(BaseModel, frozen)` with `ok: bool`, `action_id: int | None`, `tier: Literal[0, 1, 2, 3] | None`, `status: Literal["pending", "cooling_off", "pending_grant"] | None`, `error: ProposeActionError | None`
- `propose_action(...)` async function (the actual implementation; verb shim wraps it)

**And** `ProposeActionOut.model_validate({...})` round-trips cleanly for both success and error cases.

### AC-7 — `propose_action` implementation: tier-0 refusal + payload validation + tier-promotion guard

**Given** `mailbot_api/actions/propose.py` is implemented,

**When** `propose_action(email_id: str | None, action_type: ActionType, *, payload: dict | None = None, db_path: str | None = None) -> ProposeActionOut` is called,

**Then** the implementation:

1. **Validates `action_type` is an ActionType member** — the typed signature already enforces this at mypy time; at runtime, if a caller passes a non-member (e.g., via MCP JSON), the verb shim (AC-12) converts the string → `ActionType` via `ActionType(value)` first and surfaces a `ProposeActionError(code="INVALID_ACTION_TYPE")` on `ValueError`.
2. **Refuses Tier 0 at the verb boundary** — if `tier_for(action_type) == 0`, returns `ProposeActionOut(ok=False, action_id=None, tier=0, status=None, error=ProposeActionError(code="TIER_0_NOT_QUEUEABLE", message="Tier 0 actions are verb-level capabilities, not user-visible actions — they do not enter pending_actions"))`.
3. **Refuses payloads containing a `tier` key** — FR-5.6 verb-boundary defense. If `payload is not None and "tier" in payload`, returns `ProposeActionOut(ok=False, ..., error=ProposeActionError(code="TIER_PROMOTION_ATTEMPT", message="tier is computed by the verb API and cannot be agent-specified"))`.
4. **Computes `tier = tier_for(action_type)`** (cannot be 0 at this point per step 2).
5. **For Tier 3 SEND family** (`is_send_family(action_type)`) AND `email_id is not None`: queries `EMAIL_CHANGE_MARKER_SELECT` for `email_id`. If the row is missing → `ProposeActionOut(ok=False, ..., error=ProposeActionError(code="EMAIL_NOT_FOUND", message=f"email_id {email_id} not found"))`. If `emails.deleted_at IS NOT NULL` → `EMAIL_DELETED`. Otherwise, capture `change_marker_at_propose = <value>` and insert with `status="cooling_off"`.
6. **For Tier 3 DELETE** (and other Tier-3 non-SEND): same email lookup + change_marker capture, but insert with `status="pending"` (no cooling-off for non-send actions — they're already grant-gated via Story 4-3).
7. **For Tier 2**: inserts with `status="pending_grant"`, `change_marker_at_propose=NULL`.
8. **For Tier 1**: inserts with `status="pending"`, `change_marker_at_propose=NULL`.
9. **Payload serialization**: `json.dumps(payload or {})` — store as TEXT.
10. **Returns** `ProposeActionOut(ok=True, action_id=<new lastrowid>, tier=<tier>, status=<initial>, error=None)`.

### AC-8 — Email-scope validation: `email_id is None` allowed only for non-email-scoped actions

**Given** some actions are not email-scoped (per AC-1 nullable `email_id` rationale),

**When** the verb is called with `email_id=None`,

**Then** the implementation refuses with `ProposeActionError(code="INVALID_PAYLOAD", message="action_type X requires an email_id")` for any action_type that IS email-scoped (defined as `action_type not in EMAIL_LESS_ACTIONS` where `EMAIL_LESS_ACTIONS = {ActionType.MODIFY_INBOX_RULE, ActionType.MODIFY_OUTLOOK_FILTER, ActionType.TOUCH_DELEGATED_MAILBOX}`).

**And** `EMAIL_LESS_ACTIONS` is exported from `mailbot_api/actions/types.py` (the type module owns this membership classification, mirroring `is_send_family`).

**And** for `email_id is not None` but action_type IS email-less, the call is accepted (the email_id becomes contextual metadata — the drainer in Story 4-4 will ignore it for email-less actions). This is permissive by design — the verb shouldn't refuse harmless extra context.

### AC-9 — Structured logging

**Given** Story 1-4's JSON logger,

**When** `propose_action` succeeds,

**Then** an `event="action.proposed"` log line is emitted with `action_id`, `action_type` (the `.value` string), `tier`, `status`, `email_id` (or `null`).

**And** sensitive payload fields (e.g., `body` in SEND_REPLY payloads) are NOT logged — only the metadata above.

**And** on refusal, an `event="action.propose.refused"` line is emitted with `action_type`, `tier_attempted` (if computable), and the error code.

### AC-10 — Boundary check: `EMAIL_LESS_ACTIONS` is exported from `types.py`

**Given** Story 4-1 established `mailbot_api/actions/types.py` as the sole owner of action-classification helpers,

**When** Story 4-2 adds `EMAIL_LESS_ACTIONS: Final[frozenset[ActionType]]` to `types.py` and re-exports from `mailbot_api/actions/__init__.py`,

**Then** the new helper is alongside `is_send_family` / `requires_grant` in `__all__`.

**And** a unit test asserts `EMAIL_LESS_ACTIONS == {ActionType.MODIFY_INBOX_RULE, ActionType.MODIFY_OUTLOOK_FILTER, ActionType.TOUCH_DELEGATED_MAILBOX}` (so adding a new email-less action requires deliberate test+constant update).

### AC-11 — Verb shim at `mailbot_api/verbs/propose_action.py`

**Given** the existing verb-shim pattern from `mailbot_api/verbs/ask_router.py`,

**When** `mailbot_api/verbs/propose_action.py` is implemented,

**Then** the shim:

1. Accepts the agent-facing signature `propose_action(email_id: str | None, action_type: str, payload: dict | None = None)` — note `action_type: str` because the agent passes JSON strings; conversion to `ActionType` happens inside.
2. Wraps `ActionType(action_type)` in a try/except — `ValueError` → `ProposeActionOut(ok=False, ..., error=ProposeActionError(code="INVALID_ACTION_TYPE", message=f"unknown action_type {action_type!r}"))`.
3. On success, delegates to `mailbot_api.actions.propose.propose_action(...)`.
4. Module exposes only `propose_action` in `__all__`.

### AC-12 — Comprehensive tests

**Given** `tests/unit/actions/test_propose_action.py` is implemented,

**When** the test suite runs,

**Then** the following scenarios are covered (using a real on-disk SQLite via tmp_path + fresh migration apply):

- **Tier 0 refusal** — `propose_action(None, ActionType.READ_SQL)` → `ok=False`, `code="TIER_0_NOT_QUEUEABLE"`.
- **Tier-promotion guard** — `propose_action("eid", ActionType.MARK_READ, payload={"tier": 0})` → `ok=False`, `code="TIER_PROMOTION_ATTEMPT"`.
- **Invalid action_type via shim** — `verbs.propose_action.propose_action("eid", "fake_action")` → `ok=False`, `code="INVALID_ACTION_TYPE"`.
- **Email-scoped action without email_id** — `propose_action(None, ActionType.MARK_READ)` → `ok=False`, `code="INVALID_PAYLOAD"`.
- **Email-less action without email_id** — `propose_action(None, ActionType.MODIFY_INBOX_RULE, payload={"rule": "x"})` → `ok=True`, `tier=3`, `status="pending"`, `change_marker_at_propose IS NULL`.
- **Tier 1 happy path** — `propose_action("eid", ActionType.MARK_READ)` → row inserted with `status="pending"`, `change_marker_at_propose IS NULL`.
- **Tier 2 happy path** — `propose_action("eid", ActionType.ARCHIVE)` → row inserted with `status="pending_grant"`, `change_marker_at_propose IS NULL`.
- **Tier 3 DELETE happy path** — `propose_action("eid", ActionType.DELETE)` → row inserted with `status="pending"`, `change_marker_at_propose = <captured value>`.
- **Tier 3 SEND_REPLY happy path** — `propose_action("eid", ActionType.SEND_REPLY, payload={"body": "..."})` → row inserted with `status="cooling_off"`, `change_marker_at_propose = <captured value>`.
- **Email not found (Tier 3 SEND)** — propose against unknown email_id → `ok=False`, `code="EMAIL_NOT_FOUND"`.
- **Email soft-deleted (Tier 3 SEND)** — propose against `emails.deleted_at IS NOT NULL` → `ok=False`, `code="EMAIL_DELETED"`.
- **Payload serialization** — payload `{"body": "Hi", "to": ["x@y.com"]}` round-trips through the row as `json.loads(row["payload"])`.
- **`action.proposed` log line** captured with the right `action_id` / `action_type` / `tier` / `status` fields and NO `body` content.
- **`action.propose.refused` log line** captured on each refusal path.
- **CHECK constraint** — direct SQL `INSERT INTO pending_actions (action_type, ...) VALUES ('not_a_real_action', ...)` raises `sqlite3.IntegrityError`.

### AC-13 — Schema integration test for action_grants and action_history

**Given** the migrations land,

**When** `tests/integration/test_action_schema.py` runs:

- `PRAGMA table_info(pending_actions)` returns the expected 12 columns with correct types + nullability.
- `PRAGMA table_info(action_grants)` returns the expected 6 columns.
- `PRAGMA table_info(action_history)` returns the expected 4 columns.
- `PRAGMA index_list(pending_actions)` includes `ix_pending_actions_status_proposed_at`, `ix_pending_actions_email_id`, `ix_pending_actions_action_type`.
- `PRAGMA index_list(action_grants)` includes `ix_action_grants_action_type_expires_at`.

### AC-14 — Schema sync test: in-migration CHECK list ↔ ActionType Tier-1/2/3

**Given** the `CHECK(action_type IN (...))` in 015 + 016 is hand-written SQL,

**When** `tests/integration/test_action_schema.py` runs an additional `test_check_constraint_in_sync_with_enum`:

- Read the migration file at `mailbot_api/db/migrations/015_pending_actions.sql` as text.
- Extract the action-type list from the `CHECK(action_type IN ('a', 'b', ...))` block via regex.
- Assert the parsed set equals `{at.value for at in ActionType if tier_for(at) >= 1}` (the same 18-value set Story 4-1's boundary check uses).
- Same assertion for 016.

**Then** drift between the enum and the CHECK constraint is caught at test time, BEFORE production-DB-divergence becomes a real problem.

### AC-15 — All gates green

- `pytest -q` → 492 (post 4-1) + (new from 4-2) passing, 0 failures
- `ruff check .` → exit 0
- `mypy --strict mailbot_api/` → exit 0
- `python scripts/check_boundaries.py` → exit 0

## Tasks / Subtasks

- [x] **Task 1 — Three migration files** (AC-1..AC-4) — 015/016/017 shipped with CHECK constraints on action_type/tier/status/budget_consumed
- [x] **Task 2 — SQL constants in `queries.py`** (AC-5) — PENDING_ACTION_INSERT + PENDING_ACTION_SELECT_BY_ID + EMAIL_MARKER_AND_DELETED_AT_SELECT (combined the change_marker + deleted_at lookups into one query for atomicity)
- [x] **Task 3 — `EMAIL_LESS_ACTIONS` in `types.py`** (AC-10) — frozenset + `__init__.py` re-export + invariant test
- [x] **Task 4 — `mailbot_api/actions/propose.py`** (AC-6, AC-7, AC-8, AC-9) — ProposeActionError/Out Pydantic shapes + propose_action(...) async + structured logging
- [x] **Task 5 — Verb shim** (AC-11) — `mailbot_api/verbs/propose_action.py` with string→ActionType + ValueError handling
- [x] **Task 6 — Unit tests** (AC-12) — `tests/unit/actions/test_propose_action.py` with 15 scenarios
- [x] **Task 7 — Integration tests** (AC-13, AC-14) — `tests/integration/test_action_schema.py` with PRAGMA + CHECK-constraint + schema-sync tests
- [x] **Task 8 — Pre-review self-audit + gate sweep** (AC-15)
  - [x] `pytest -q` green → 518 passed + 2 skipped
  - [x] `ruff check .` clean
  - [x] `mypy --strict mailbot_api/` clean (70 source files)
  - [x] `scripts/check_boundaries.py` clean
  - [x] Added `execute_insert_returning_id` to `mailbot_api/db/connection.py` (new wrapper — existing `execute_write` returns rowcount, not lastrowid)
  - [ ] Subtask 8.5: Pre-review self-audit artifact pending (orchestrator handles Step 2.3.5 next)

## Dev Notes

### What this story is about

Story 4-2 is the **schema + first-verb** story of Epic 4. It establishes:

1. The 3 queue tables that every later Epic-4 story writes to (or reads from)
2. The agent-facing `propose_action` verb that all action proposals flow through
3. The first hard enforcement of FR-5.6 ("agent cannot promote tier") — both at the verb boundary (returning `TIER_PROMOTION_ATTEMPT` on `payload["tier"]`) AND at the schema (`CHECK(tier IN (1, 2, 3))` rejects Tier-0 inserts)

The CHECK constraints on `action_type` AND `tier` are deliberate redundancy: the verb's `tier_for()` lookup is the producer, but a buggy direct SQL insert from a future verb (or a manual operator INSERT) is caught by the schema. Defense-in-depth.

### Architecture references

- **epics.md §"Epic 4 Detail" → Story 4.2** — canonical scope
- **architecture.md §AR-SCHEMA-3, AR-SCHEMA-4, AR-SCHEMA-5** — schemas for pending_actions / action_grants / action_history
- **FR-5.6** — Agent cannot promote tier (this story is the load-bearing enforcement)
- **AR-D14-1** — append-only migration chain (015/016/017 next after 014)
- **AR-D5-4** — tier-banded notification strategy (Story 4-4 implements; Story 4-2 establishes the `failure_reason` column that drives it)

### Migration numbering

Current chain ends at `014_thread_continuity.sql`. Story 4-2 adds `015`, `016`, `017` in that order — all three in this single story so the chain stays atomic.

### Pre-allocated columns from earlier stories that 4-2 leverages

- `emails.change_marker` — Story 1-3 already shipped this (per architecture); `EMAIL_CHANGE_MARKER_SELECT` reads it for Tier-3 send capture.
- `emails.deleted_at` — Story 1-7's `@removed` handling already shipped this; `propose_action` consults it for the `EMAIL_DELETED` refusal.
- `router_calls.sensitivity_grant_id` / `sensitivity_grant_minted_at` — Story 2-1 pre-allocated these; Story 4-7 (not 4-2) populates.

### Sample structural sketches (NOT verbatim)

**015_pending_actions.sql** (excerpt):

```sql
-- 015_pending_actions.sql — Story 4-2 AC-1.
--
-- pending_actions: queue table for all Tier-1/2/3 action proposals.
-- CHECK(action_type IN (...)) deliberately mirrors mailbot_api.actions.types
-- Tier-1/2/3 enum members. Drift caught by
-- tests/integration/test_action_schema.py::test_check_constraint_in_sync_with_enum.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NULL,
    action_type TEXT NOT NULL CHECK(action_type IN (
        'mark_read', 'mark_unread', 'add_local_category', 'remove_local_category', 'move_to_triage_folder',
        'archive', 'mark_junk', 'move_to_user_folder', 'unsubscribe', 'move_to_inbox',
        'delete', 'send_reply', 'send_new_email', 'send_forward', 'reply_to_inactive_thread',
        'modify_inbox_rule', 'modify_outlook_filter', 'touch_delegated_mailbox'
    )),
    tier INTEGER NOT NULL CHECK(tier IN (1, 2, 3)),
    payload TEXT NOT NULL,
    proposed_at TEXT NOT NULL,
    proposed_by_grant_id INTEGER NULL,
    change_marker_at_propose TEXT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'cooling_off', 'pending_grant', 'draining', 'applied', 'failed', 'cancelled'
    )),
    retry_count INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT NULL,
    terminal_at TEXT NULL,
    budget_consumed INTEGER NOT NULL DEFAULT 0 CHECK(budget_consumed IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_pending_actions_status_proposed_at
    ON pending_actions (status, proposed_at);
CREATE INDEX IF NOT EXISTS ix_pending_actions_email_id
    ON pending_actions (email_id);
CREATE INDEX IF NOT EXISTS ix_pending_actions_action_type
    ON pending_actions (action_type);
```

**`propose.py`** (excerpt):

```python
async def propose_action(
    email_id: str | None,
    action_type: ActionType,
    *,
    payload: dict | None = None,
    db_path: str | None = None,
) -> ProposeActionOut:
    if tier_for(action_type) == 0:
        return ProposeActionOut(ok=False, error=ProposeActionError(
            code="TIER_0_NOT_QUEUEABLE", message="..."))

    if payload is not None and "tier" in payload:
        return ProposeActionOut(ok=False, error=ProposeActionError(
            code="TIER_PROMOTION_ATTEMPT", message="..."))

    if email_id is None and action_type not in EMAIL_LESS_ACTIONS:
        return ProposeActionOut(ok=False, error=ProposeActionError(
            code="INVALID_PAYLOAD", message=f"action_type {action_type.value} requires email_id"))

    tier = tier_for(action_type)
    initial_status, change_marker = _route(action_type, tier, email_id, db_path)
    if isinstance(initial_status, ProposeActionError):  # email-not-found / email-deleted
        return ProposeActionOut(ok=False, error=initial_status)

    payload_json = json.dumps(payload or {})
    proposed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    action_id = await execute_write(
        PENDING_ACTION_INSERT,
        (email_id, action_type.value, tier, payload_json, proposed_at, None, change_marker, initial_status),
        db_path=db_path,
    )
    log_proposed(action_id, action_type, tier, initial_status, email_id)
    return ProposeActionOut(ok=True, action_id=action_id, tier=tier, status=initial_status, error=None)
```

### File list — files this story creates / modifies

**NEW:**

- `mailbot_api/db/migrations/015_pending_actions.sql`
- `mailbot_api/db/migrations/016_action_grants.sql`
- `mailbot_api/db/migrations/017_action_history.sql`
- `mailbot_api/actions/propose.py`
- `mailbot_api/verbs/propose_action.py`
- `tests/unit/actions/test_propose_action.py`
- `tests/integration/test_action_schema.py`

**MODIFIED:**

- `mailbot_api/db/queries.py` (+ PENDING_ACTION_INSERT / PENDING_ACTION_SELECT_BY_ID / EMAIL_CHANGE_MARKER_SELECT)
- `mailbot_api/actions/types.py` (+ EMAIL_LESS_ACTIONS frozenset)
- `mailbot_api/actions/__init__.py` (+ EMAIL_LESS_ACTIONS in re-exports)

### Posture Audit §5 expectations

- **§5.1** — N/A; no new deps
- **§5.2 (Cross-doc consistency)** — verify the 18-value CHECK list in 015/016 matches `{at.value for at in ActionType if tier_for(at) >= 1}` (the new test AC-14 IS this check)
- **§5.7 (Module-mutable-state)** — `EMAIL_LESS_ACTIONS` is `Final[frozenset[ActionType]]` (immutable by construction)
- **§5.10 (Producer-boundary contract)** — `ProposeActionOut`/`ProposeActionError` use Pydantic v2 `frozen=True`; payload JSON is validated by `json.dumps` round-trip (no type coercion surprises). The schema CHECK constraints ARE the producer-boundary defense for raw-SQL bypass attempts.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2]
- [Source: _bmad-output/implementation-artifacts/4-1-action-type-enum-and-tier-for-and-cross-cutting-properties-table.md] — ActionType + helpers
- [Source: mailbot_api/db/migrations/013_derivations_idempotency.sql] — migration shape pattern
- [Source: mailbot_api/db/queries.py] — Rule C SQL constants
- [Source: mailbot_api/verbs/ask_router.py] — verb-shim pattern

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Debug Log References

- 2 mid-dev test fixes: (a) SQLite reports `notnull=0` for INTEGER PRIMARY KEY AUTOINCREMENT columns (PK enforcement is at insert time, not in PRAGMA table_info — revised the test to check `pk=1` via index 5); (b) the regex parsing `CHECK(action_type IN (...))` initially matched the header comment's placeholder text instead of the real constraint — fixed by stripping `--` comment lines before the regex match.
- 1 mid-dev mypy fix: `tier_for()` returns plain `int`, but `ProposeActionOut.tier: Literal[0,1,2,3]` requires the narrowed literal — wrapped with `cast(Literal[0,1,2,3], tier_for(...))`.

### Completion Notes List

**Scope shipped:**

- 3 migrations (015 `pending_actions` + 016 `action_grants` + 017 `action_history`) with CHECK constraints on `action_type` (18-value Tier-1/2/3 list synced with `ActionType`), `tier` (1/2/3 — Tier-0 forbidden as defense-in-depth for FR-5.6), `status` (7-state lifecycle), `budget_consumed` (0/1 boolean).
- `EMAIL_LESS_ACTIONS: Final[frozenset[ActionType]]` added to `mailbot_api/actions/types.py` + re-exported via `__init__.py`; 3 members (`MODIFY_INBOX_RULE`, `MODIFY_OUTLOOK_FILTER`, `TOUCH_DELEGATED_MAILBOX`).
- `mailbot_api/actions/propose.py` — frozen Pydantic `ProposeActionError` + `ProposeActionOut`, async `propose_action(email_id, action_type, *, payload, db_path)` with Tier-0 refusal, tier-promotion guard, email-scope validation, change_marker capture for Tier-3 with email, per-tier status routing.
- `mailbot_api/verbs/propose_action.py` — MCP-facing shim that converts the JSON string `action_type` → `ActionType` enum + surfaces `INVALID_ACTION_TYPE` on `ValueError`.
- `mailbot_api/db/connection.py` — new `execute_insert_returning_id` async wrapper (existing `execute_write` returns rowcount; INSERT needs lastrowid).
- `tests/unit/actions/test_propose_action.py` — 15 scenarios covering every AC-7/8/9/11/12 case.
- `tests/integration/test_action_schema.py` — schema shape, index list, CHECK rejection of invalid action_type/tier/status, AC-14 enum↔CHECK sync tests for 015 + 016.

**Gate sweep results:**

- `pytest -q` → 518 passed + 2 skipped (was 492 after Story 4-1; +26 net new tests for 4-2)
- `ruff check .` → exit 0 (1 auto-fix consumed during dev: import-order on two new files)
- `mypy --strict mailbot_api/` → exit 0 across 70 source files (was 68 — +2 for `actions/propose.py` and `verbs/propose_action.py`)
- `scripts/check_boundaries.py` → exit 0 (the new SQL constants in `queries.py` are allowlisted; the new modules use enum member references only)

**Open items for the reviewer:**

- Pre-review self-audit artifact pending — Step 2.3.5 handled by orchestrator next.
- `execute_insert_returning_id` is a new connection-layer API; future stories writing to AUTOINCREMENT tables (`action_grants` in Story 4-3, `action_history` row writes in Story 4-4) will use it instead of `execute_write`.
- AC-12's `_seed_email` helper uses a raw `INSERT INTO emails (...)` inside `tests/` — boundary checker only scans `mailbot_api/`, so this is permitted; documented here for clarity.

### File List

**New:**

- `mailbot_api/db/migrations/015_pending_actions.sql`
- `mailbot_api/db/migrations/016_action_grants.sql`
- `mailbot_api/db/migrations/017_action_history.sql`
- `mailbot_api/actions/propose.py`
- `mailbot_api/verbs/propose_action.py`
- `tests/unit/actions/test_propose_action.py`
- `tests/integration/test_action_schema.py`

**Modified:**

- `mailbot_api/db/queries.py` (+ PENDING_ACTION_INSERT / PENDING_ACTION_SELECT_BY_ID / EMAIL_MARKER_AND_DELETED_AT_SELECT)
- `mailbot_api/db/connection.py` (+ execute_insert_returning_id async wrapper + `_execute_insert_returning_id_sync` helper)
- `mailbot_api/actions/types.py` (+ EMAIL_LESS_ACTIONS frozenset + updated `__all__`)
- `mailbot_api/actions/__init__.py` (+ EMAIL_LESS_ACTIONS in re-exports + updated `__all__`)
- `tests/unit/actions/test_types.py` (+ test_email_less_actions_membership_exact + EMAIL_LESS_ACTIONS import)

**Modified (workflow state):**

- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/4-2-pending-actions-and-action-grants-and-action-history-schema-and-propose-action-verb.md` (this file)

### Review Findings

- [x] `Review` `Decision` **SEND_NEW_EMAIL was email-scoped only** — APPLIED. Added `ActionType.SEND_NEW_EMAIL` to `EMAIL_LESS_ACTIONS` + propagated through `propose_action` so compose-from-scratch sends go through the SEND-family cooling_off branch even with `email_id=None`. New test `test_send_new_email_without_email_id_accepted`. Story 4-1's `test_send_new_email_in_email_less_but_other_sends_not` pins the asymmetry. Updated EMAIL_LESS_ACTIONS member count: 3 → 4.
- [x] `Review` `Decision` **email-less Tier-3 `change_marker_required=True` mismatch** — DEFERRED-TO-4-4 (with documented behavior). Story 4-1's `ActionProperties` says `change_marker_required=True` for every Tier-3 action, but email-less Tier-3 rows (MODIFY_INBOX_RULE, MODIFY_OUTLOOK_FILTER, TOUCH_DELEGATED_MAILBOX, SEND_NEW_EMAIL) have no email to capture from and store `change_marker_at_propose=NULL`. Story 4-4's drainer MUST special-case email-less Tier-3 rows: skip the strict-ETag check when `email_id IS NULL` (no row to compare against). Flagged in epic-run-flags.md "Cross-story decisions owed."
- [x] `Review` `Patch` **EMAIL_NEVER_SYNCED distinct code** — APPLIED. Added `EMAIL_NEVER_SYNCED` to `ProposeErrorCode` literal. `_capture_change_marker` now returns the distinct code when the row exists but `change_marker IS NULL`. New test `test_tier_3_against_never_synced_email_refused` covers this branch.
- [x] `Review` `Patch` **lastrowid None-check before commit** — APPLIED. Moved the None-check to BEFORE `conn.commit()` in `_execute_insert_returning_id_sync`. If the (defensive) RuntimeError fires, the transaction rolls back instead of leaving an orphan row.
- [x] `Review` `Patch` **No coverage of change_marker IS NULL** — APPLIED (combined with CR-3). The new test seeds an email with `change_marker=NULL` directly and asserts the `EMAIL_NEVER_SYNCED` refusal.
- [x] `Review` `Defer` AC-14 regex `[^)]+` fragile against action-type values containing `)` or future multi-column CHECK in same migration — current 18 values are safe but regex silently truncates if a value ever contains `)`; consider switching to a more robust SQL parser — `tests/integration/test_action_schema.py:161-169` — deferred, pre-existing test design, no current bug
