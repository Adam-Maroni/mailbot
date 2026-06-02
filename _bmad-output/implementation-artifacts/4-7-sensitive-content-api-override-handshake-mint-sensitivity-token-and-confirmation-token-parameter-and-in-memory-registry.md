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

---

## Retroactive Code Review (2026-06-02)

Per Epic 4 retro action item #2 (Adam, 2026-06-02): Story 4-7 originally shipped under the gate-coverage-only cadence; no CR subagent dispatched at the time. This is the retroactive CR pass — the sensitivity-token handshake is the privacy-invariant surface that protects sensitive email bodies from leaking to Anthropic. A second pair of eyes is owed.

**Reviewer:** claude-sonnet-4-6 via Agent dispatch (model=sonnet) — different model from the original Opus 4.7 dev pass.

**Verdict:** NOTABLE — 10 findings (6 patches, 2 decisions, 2 defers). Applied rate **9/10 = 90%** (above 70% threshold).

### Findings and disposition

- **CR-4-7-1 [HIGH] Blind Hunter** — Escalation recursive call in `_dispatch_with_failure_chain` did NOT forward `sensitivity_grant_id` or `sensitivity_grant_minted_at`. The escalated leg's `router_calls` audit row had NULL forensic columns even though the original dispatch consumed a valid token. Broke "which API calls were made for sensitive email X" forensic queries on escalated dispatches. **PATCHED:** added `sensitivity_grant_id=sensitivity_grant_id, sensitivity_grant_minted_at=sensitivity_grant_minted_at` to the recursive call. (`mailbot_api/router/router.py:683-695`)
- **CR-4-7-2 [HIGH] Blind Hunter** — `sweep()` was defined and documented but never called anywhere. Registry grew unbounded across the worker process lifetime, violating the AR-D12-1 contract ("registry only contains live tokens"). **PATCHED:** `mint()` now calls `sweep()` inline at its top. Mint rate is human-paced (one per confirmation prompt), so the per-mint sweep cost is amortized across rare operations and no worker-side wiring is needed. Closed without an Epic 6 dependency. (`mailbot_api/actions/sensitivity_tokens.py:69-79`)
- **CR-4-7-3 [HIGH] Blind Hunter** — Token leak risk if `consume()` ever raises (today it's a plain dict op but a future DB-backed consume would propagate exceptions including the token value into tracebacks). Adam chose option (a): defensive wrap. **PATCHED:** `try/except` around `consume()` call in `router.py`; catches → logs `event="sensitivity.token.consume_crash"` WITHOUT the token value → returns `NEEDS_SENSITIVITY_CONFIRMATION` as if the token were invalid. (`mailbot_api/router/router.py:319-340`)
- **CR-4-7-4 [MEDIUM] Blind Hunter** — `SensitivityToken` model missing the `consumed: bool` field from AC-1. **ACCEPTED-NO-CHANGE:** the deletion-is-consumed pattern shipped + tested; the field would require unfreezing the model + flip-then-delete pattern + back-compat code. Deviation from AC-1 is intentional and documented in `consume()` docstring; added to module docstring per CR-4-7-10 below.
- **CR-4-7-5 [MEDIUM] Edge Case Hunter** — `confirmation_token` passed for a normal email was silently ignored. **PATCHED:** new `elif sensitivity_value == "normal" and confirmation_token is not None` branch logs `event="sensitivity.token.unexpected"` (without the token value). The call still dispatches normally — only the unexpected presence is observable. (`mailbot_api/router/router.py:343-356`)
- **CR-4-7-6 [MEDIUM] Blind Hunter** — `sensitivity_grant_minted_at` recorded consume-time, not mint-time, with up to TTL-window drift. **PATCHED:** `consume()` now returns `tuple[str, datetime] | None` so the router writes the real mint timestamp via `minted_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")`. Test `test_consume_with_matching_args_returns_grant_id_and_removes_entry` updated to unpack the tuple. (`mailbot_api/actions/sensitivity_tokens.py:78-110`, `mailbot_api/router/router.py:340-355`)
- **CR-4-7-7 [MEDIUM] Edge Case Hunter** — `mint_sensitivity_token` returned `EMAIL_NOT_FOUND` for emails with `sensitivity IS NULL` (unclassified) — caused callers to give up rather than wait. **PATCHED:** new `SENSITIVITY_NOT_CLASSIFIED` error code added to `MintSensitivityTokenErrorCode` literal; defensive branch returns it (with a "run the ingest pipeline's sensitivity_class step first" message for the NULL case). New unit test verifies. (`mailbot_api/verbs/mint_sensitivity_token.py:26-31, 81-96`)
- **CR-4-7-8 [LOW] Blind Hunter** — Dev Notes mischaracterized grant_id collision risk as birthday-bounded; actually sha256 preimage-bounded. **PATCHED (docs):** module docstring corrected. (`mailbot_api/actions/sensitivity_tokens.py:25-30`)
- **CR-4-7-9 [LOW] Acceptance Auditor** — No test proved cross-mint registry persistence (autouse `_clear_registry` fixture wiped state before every test). **PATCHED:** new `TestRegistryLifecycleWithoutAutouse` class with a closer-scoped autouse fixture that explicitly clears at setup + teardown, proving cross-mint persistence within a test. (`tests/unit/actions/test_sensitivity_tokens.py:225-251`)
- **CR-4-7-10 [LOW] Acceptance Auditor** — "Dies on restart" property had no test or top-of-module comment. **PATCHED:** module docstring now explicitly documents the invariant ("Any refactor that introduces persistence violates AR-D12-1 and must be rejected at review time"). New `test_registry_initialized_empty_on_import` pins the type so a persistent-store refactor fails LOUD. (`mailbot_api/actions/sensitivity_tokens.py:8-12`, `tests/unit/actions/test_sensitivity_tokens.py:281-289`)

### Adam's decisions

- **CR-4-7-3 (token leak vector):** Option (a) — defensive wrap on `consume()` call. Rationale: privacy-invariant surface; cost is 5 lines.

### Tests added

- `tests/unit/actions/test_sensitivity_tokens.py` (+4 tests): `test_mint_verb_returns_sensitivity_not_classified_for_unclassified_email` (CR-4-7-7), `TestRegistryLifecycleWithoutAutouse.test_mint_persists_across_subsequent_operations_in_same_test` (CR-4-7-9), `test_sweep_runs_inline_on_mint` (CR-4-7-2), `test_registry_initialized_empty_on_import` (CR-4-7-10). 2 existing tests updated to unpack the new `consume()` tuple return.

### Gates

All 4 quality gates green after patches: pytest (646 → 654 baseline +8 from 4-4 + 4-7 retroactive CR combined), ruff, mypy --strict (85 source files), boundary checker.

### Status

Retroactive CR complete. Story 4-7 is now **CR-cleared**. Privacy invariant strengthened: escalation forensic forwarding, registry self-cleaning, token-leak defensive wrap, mint-time accurate audit, unclassified vs missing-email distinction, regression tests pinning the in-memory invariant.
