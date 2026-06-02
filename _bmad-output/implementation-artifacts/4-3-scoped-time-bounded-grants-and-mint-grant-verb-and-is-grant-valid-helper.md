---
baseline_commit: b18437a
---

# Story 4.3: Scoped time-bounded grants + mint_grant verb + is_grant_valid helper

Status: done

## Story

As Adam,
I want a `mint_grant(action_type, email_ids, expires_at) → MintGrantOut` Tier-0 verb writing to `action_grants`, an `is_grant_valid(action_type, email_id) → tuple[bool, int|None]` helper the drainer calls at second-auth-check time, and a `revoke_grant(grant_id) → RevokeGrantOut` verb,
so that I can grant "you may delete the 47 emails I just identified" in chat with a 1-hour window, the system enforces grant scope + expiry by construction, and the drainer's second auth check at Story 4-4 has the helper it needs.

## Acceptance Criteria

### AC-1 — `mint_grant` verb at `mailbot_api/actions/authorization.py`

`mint_grant(action_type: ActionType, email_ids: list[str], expires_at: datetime) -> MintGrantOut`:

- Refuses `expires_at <= now()` → `MintGrantOut(ok=False, error=MintGrantError(code="EXPIRES_AT_IN_PAST", ...))`
- Refuses `expires_at > now() + 24h` → `code="GRANT_WINDOW_TOO_LARGE"` (defender bias: short grants by design)
- Refuses `len(email_ids) > 200` → `code="BATCH_TOO_LARGE"`
- Refuses Tier-0 / Tier-1 action_types (Tier-0 doesn't queue; Tier-1 is auto-approved per FR-5.1) → `code="GRANT_NOT_NEEDED"`
- Inserts via `execute_insert_returning_id` into `action_grants(action_type, email_ids=JSON, expires_at, minted_at=now, revoked_at=NULL)`
- Returns `MintGrantOut(ok=True, grant_id=<id>, expires_at=<value>, email_count=len(email_ids), error=None)`
- Emits structured log `event="action.grant.minted"` with `grant_id, action_type, email_count, expires_at`

### AC-2 — `is_grant_valid(action_type, email_id) → tuple[bool, int|None]` helper

- Returns `(True, grant_id)` if there exists a row in `action_grants` where: `action_type == <value>` AND (`email_id IN (parsed email_ids JSON)` OR `email_ids == "[]"` for email-less actions) AND `expires_at > now()` AND `revoked_at IS NULL`
- Returns `(False, None)` otherwise
- Tier-1 callers shouldn't invoke this; if they do, refuses with `(False, None)` (defensive)
- Uses raw SQL constant `ACTION_GRANT_FIND_VALID` in `queries.py`

### AC-3 — `revoke_grant(grant_id) → RevokeGrantOut` verb

- Sets `revoked_at = now()` on the row
- Returns `RevokeGrantOut(ok=True, grant_id=<id>, revoked_at=<value>)` if affected rowcount = 1
- Returns `RevokeGrantOut(ok=False, error=...code="GRANT_NOT_FOUND")` if no row matched
- Emits `event="action.grant.revoked"` with `grant_id`

### AC-4 — SQL constants in `queries.py`

- `ACTION_GRANT_INSERT` — `INSERT INTO action_grants (action_type, email_ids, expires_at, minted_at) VALUES (?, ?, ?, ?)`
- `ACTION_GRANT_FIND_VALID` — `SELECT id, email_ids FROM action_grants WHERE action_type = ? AND expires_at > ? AND revoked_at IS NULL`
- `ACTION_GRANT_REVOKE` — `UPDATE action_grants SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL`

### AC-5 — Frozen Pydantic shapes

- `MintGrantError(code: Literal["EXPIRES_AT_IN_PAST", "GRANT_WINDOW_TOO_LARGE", "BATCH_TOO_LARGE", "GRANT_NOT_NEEDED"], message: str)`
- `MintGrantOut(ok: bool, grant_id: int | None = None, expires_at: str | None = None, email_count: int | None = None, error: MintGrantError | None = None)`
- `RevokeGrantError(code: Literal["GRANT_NOT_FOUND"], message: str)`
- `RevokeGrantOut(ok: bool, grant_id: int | None = None, revoked_at: str | None = None, error: RevokeGrantError | None = None)`

### AC-6 — Verb shims

- `mailbot_api/verbs/mint_grant.py` — string→ActionType conversion + ValueError → MintGrantError with code from existing 4-2 propose ProposeError? No — needs its own code. Add `INVALID_ACTION_TYPE` to MintGrantError too.
- `mailbot_api/verbs/revoke_grant.py` — pass-through (no string conversion needed; grant_id is int)

### AC-7 — Tests

`tests/unit/actions/test_authorization.py`:

- `mint_grant` happy path → row inserted with right shape
- `mint_grant` past expires_at → EXPIRES_AT_IN_PAST
- `mint_grant` > 24h window → GRANT_WINDOW_TOO_LARGE
- `mint_grant` 201 email_ids → BATCH_TOO_LARGE
- `mint_grant` for Tier-0 → GRANT_NOT_NEEDED
- `mint_grant` for Tier-1 → GRANT_NOT_NEEDED
- `is_grant_valid` happy path: valid row, email_id in list → (True, grant_id)
- `is_grant_valid` email not in list → (False, None)
- `is_grant_valid` wrong action_type → (False, None)
- `is_grant_valid` expired → (False, None)
- `is_grant_valid` revoked → (False, None)
- `is_grant_valid` email-less grant (email_ids=[]) matches any email_id passed
- `revoke_grant` happy path
- `revoke_grant` non-existent → GRANT_NOT_FOUND
- `revoke_grant` already-revoked → GRANT_NOT_FOUND (defensive)
- Log lines `action.grant.minted` and `action.grant.revoked` captured

### AC-8 — All gates green

521 + new tests, ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] Authorization module shipped
- [x] mint_grant + revoke_grant verb shims
- [x] SQL constants
- [x] Tests
- [x] Gate sweep

## Dev Notes

Tier-1 returning `GRANT_NOT_NEEDED` from `mint_grant` is the defender-bias call: a Tier-1 action doesn't need a grant per FR-5.1 (auto-approved + revertible). If the agent calls `mint_grant(MARK_READ, ...)`, that's a redundant operation we surface rather than silently mint a useless grant.

`is_grant_valid` returning `(False, None)` for Tier-1 is defensive — the drainer should never call this for Tier-1 rows per Story 4-4's per-tier branching, but if it does, the (False, None) gives a sensible no-op-style refusal.

`email_ids JSON encoding` — list[str] → `json.dumps(email_ids, sort_keys=False)` (preserves order for audit). Helper `_parse_email_ids(blob) -> list[str]` reverses.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass (gate-coverage-only — mechanical infrastructure on top of 4-2's schema)

### Completion Notes List

Story 4-3 ships mint_grant + is_grant_valid + revoke_grant — the Tier-2/3 grant infrastructure that Story 4-4's drainer will consult at the second auth check. Gate-coverage-only (no CR subagent): the surface is mechanical CRUD against 4-2's `action_grants` table with strict validation rules from the spec; tests cover every validation path. 521 baseline → final test count documented below.

### File List

**New:**
- `mailbot_api/actions/authorization.py`
- `mailbot_api/verbs/mint_grant.py`
- `mailbot_api/verbs/revoke_grant.py`
- `tests/unit/actions/test_authorization.py`

**Modified:**
- `mailbot_api/db/queries.py` (+ ACTION_GRANT_INSERT / FIND_VALID / REVOKE)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
