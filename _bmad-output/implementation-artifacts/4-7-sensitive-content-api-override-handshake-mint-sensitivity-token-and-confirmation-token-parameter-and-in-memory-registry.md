---
baseline_commit: b18437a
---

# Story 4.7: Sensitive-content API override handshake — mint_sensitivity_token + confirmation_token + in-memory registry

Status: done

## Story

As Adam,
I want `mint_sensitivity_token(email_id, task_type) → token` as a Tier-0 verb (refuses `confidential`), an in-memory token registry with 10-minute TTL, the `ask_router(..., confirmation_token=None)` parameter, and the Router precondition layer that consumes the token on a single sensitive-to-API dispatch and writes `sensitivity_grant_id` + `sensitivity_grant_minted_at` to `router_calls`,
so that every sensitive-to-API call carries a one-to-one mint/consume audit pair and `confidential` emails admit no override path at all.

## Acceptance Criteria

### AC-1 — In-memory token registry at `mailbot_api/actions/sensitivity_tokens.py`

- Module-level `_REGISTRY: dict[str, SensitivityToken]` — process-local; dies on worker restart by design (per AR-D12-1)
- `SensitivityToken(BaseModel, frozen)` with `token_value: str` (the secret), `email_id: str`, `task_type: str`, `expires_at: datetime`, `minted_at: datetime`, `consumed: bool`, `grant_id: str` (short hash for audit linkage)
- `mint(email_id, task_type) -> SensitivityToken` — generates `secrets.token_urlsafe(32)` + hashes for `grant_id` (sha256-hex first 16 chars), inserts into registry with `expires_at = now + 10min`, `consumed=False`
- `consume(token_value, email_id, task_type) -> str | None` — returns the `grant_id` if exists/matches/unexpired/unconsumed, then flips `consumed=True`; returns `None` otherwise
- `sweep()` — removes expired tokens (bounded-dict hygiene)
- `_clear_registry_for_tests()` — test-only helper to wipe state between tests

### AC-2 — `mint_sensitivity_token` verb

`mailbot_api/verbs/mint_sensitivity_token.py`:

- `mint_sensitivity_token(email_id: str, task_type: str, *, db_path: str) -> MintSensitivityTokenOut`
- Reads `emails.sensitivity` for `email_id` via existing `EMAIL_SENSITIVITY_SELECT`
- If `confidential` → `MintSensitivityTokenOut(ok=False, error=...code="SENSITIVITY_BLOCKS_API", message="confidential emails admit no API override")`
- If `normal` → `MintSensitivityTokenOut(ok=False, error=...code="EMAIL_NOT_SENSITIVE", message="email is not sensitive; no token required")`
- If `sensitive` → calls `sensitivity_tokens.mint(email_id, task_type)`, returns `MintSensitivityTokenOut(ok=True, token=token_value, expires_at=<iso>, grant_id=<hash>)`
- Logs `event="sensitivity.token.minted"` with `email_id, task_type, grant_id, expires_at` — **never the token value**

### AC-3 — `MintSensitivityTokenOut` + `MintSensitivityTokenError` Pydantic shapes (frozen)

- `MintSensitivityTokenError(code: Literal["EMAIL_NOT_FOUND", "EMAIL_NOT_SENSITIVE", "SENSITIVITY_BLOCKS_API"], message: str)`
- `MintSensitivityTokenOut(ok: bool, token: str | None, expires_at: str | None, grant_id: str | None, error: MintSensitivityTokenError | None)`

### AC-4 — `ask_router` extended with `confirmation_token` kwarg

- Add `confirmation_token: str | None = None` to `ask_router(...)`
- In the existing FR-2.3 precondition layer, when `sensitivity == 'sensitive'` AND API-bound model: check the token
  - If `confirmation_token is None` → existing `SENSITIVITY_BLOCKS_API` refusal (but with updated message naming the handshake)
  - If token provided → call `sensitivity_tokens.consume(token, email_id, task_type)`:
    - returns `None` → `RouterResult(ok=False, error=RouterError(code=NEEDS_SENSITIVITY_CONFIRMATION, message="confirmation token invalid, expired, or already consumed"))`
    - returns `grant_id` → allow dispatch
- `confidential` ALWAYS refuses with `SENSITIVITY_BLOCKS_API` regardless of token (per NFR-PRIV-2)
- The `grant_id` returned by `consume` is propagated to the `record_router_call` write path so `router_calls.sensitivity_grant_id` is populated

### AC-5 — Populate `router_calls.sensitivity_grant_id` + `sensitivity_grant_minted_at`

The `record_router_call` (Story 2-1) writer needs to accept these two new fields. Inspect: the columns exist in 006_router_calls.sql (per Story 2-1 pre-allocation). Extend `record_router_call` signature with `sensitivity_grant_id: str | None = None` + `sensitivity_grant_minted_at: str | None = None` and pass through to the INSERT.

The dispatch path in `ask_router` (post-precondition-check, on the successful-consume branch) plumbs the grant_id + minted_at through to `_record` / `record_router_call`.

### AC-6 — Tests

`tests/unit/actions/test_sensitivity_tokens.py`:

- `mint` on normal email refused with `EMAIL_NOT_SENSITIVE`
- `mint` on confidential email refused with `SENSITIVITY_BLOCKS_API`
- `mint` on sensitive succeeds → token is 32+ chars, grant_id is 16 chars hex
- `consume` with correct (token, email_id, task_type) returns grant_id + marks consumed
- `consume` with mismatched task_type returns None (no mark)
- `consume` after 10-min TTL returns None
- `consume` second-call on same token returns None (single-use)
- `sweep` removes only expired tokens
- Registry survives across tests when not cleared (verify with `_clear_registry_for_tests`)
- Verb shim path: `mint_sensitivity_token` mint logs the structured `sensitivity.token.minted` event with grant_id, no token value

`tests/integration/test_router_sensitivity_handshake.py`:

- ask_router on sensitive email + confirmation_token=None → SENSITIVITY_BLOCKS_API
- ask_router on sensitive email + invalid token → NEEDS_SENSITIVITY_CONFIRMATION
- ask_router on sensitive email + valid token → dispatch succeeds + grant_id populated on router_calls row
- ask_router on confidential email + valid token → SENSITIVITY_BLOCKS_API (token does NOT unlock confidential)
- mint → consume cycle: token minted, used in ask_router call, consumed once, second ask_router with same token refused

### AC-7 — All gates green

586 baseline + new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] sensitivity_tokens.py + tests
- [x] mint_sensitivity_token verb + shim
- [x] ask_router extended with confirmation_token parameter
- [x] Router precondition layer consumes token on sensitive emails
- [x] record_router_call extended to write sensitivity_grant_id
- [x] Integration test
- [x] Gate sweep

## Dev Notes

### Why in-memory + dict-based registry

Per AR-D12-1 ("dies on worker process restart by design, forcing re-confirmation"), the spec mandates that tokens NOT survive across restarts. A SQLite-backed registry would survive — undesirable. The audit trail lives on `router_calls.sensitivity_grant_id` so the consume event is forensically recoverable even after the registry is gone.

### `grant_id` hash format

`secrets.token_urlsafe(32)` produces ~43 chars. We hash that with sha256 → take first 16 hex chars as the `grant_id` for audit linkage. Short enough to embed in log lines without bloating, long enough to uniquely identify across plausible mint rates (worker process lifetime ~hours, mint rate ~1 per minute = ~60-120 mints / hour, collision risk astronomically low at 16 hex chars).

### Confidential is unconditionally refused

Per NFR-PRIV-2 + AR-D12-2: the handshake exists for `sensitive`. `confidential` has no override at all — `mint_sensitivity_token` refuses for confidential AND `ask_router` refuses for confidential even with a token. Verified by 2 tests.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass (gate-coverage-only)

### Completion Notes List

(Filled after implementation)

### File List

(Filled after implementation)
