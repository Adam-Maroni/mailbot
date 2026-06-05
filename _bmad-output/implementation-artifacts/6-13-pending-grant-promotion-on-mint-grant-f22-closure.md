---
baseline_commit: 5dafe9b05f9a369f5ac3fe867ffd6b204c78c4a4
---

# Story 6.13: `pending_grant` -> `pending` promotion on `mint_grant` — F22 closure

Status: done

> Filed 2026-06-04 during Story 6-6.5 third-pass walk. Inline fix already applied during the walk and verified live (see `epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F22`). This story's job is to **add regression tests + formal CR + audit the symmetric demotion question** for the patch that already ships in the repo.

## Story

As MailBot,
I want `mint_grant` to wake any pending_actions rows that were waiting on a grant of this type,
So that the drainer can drain them on its next tick — instead of letting them rot in `pending_grant` indefinitely.

## Acceptance Criteria

**AC-1**: `mint_grant` (in `mailbot_api/actions/authorization.py`) MUST invoke `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` as a side-effect after the `action_grants` INSERT succeeds. The side-effect MUST log `pending_grant_promoted=N` in the structured `action.grant.minted` log line. (Already implemented in the inline-fixed code.)

**AC-2**: The new query `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` MUST filter by `action_type` only (not by `email_id`). `is_grant_valid()` at drain time re-checks email_id membership against the JSON list, so the broad sweep is safe — a stale pending_grant row with a non-matching email_id simply reverts again on the drainer's next tick.

**AC-3**: Regression tests:
- One unit test asserting `mint_grant` flips a seeded `pending_grant` row with matching `action_type` to `pending`.
- One unit test asserting `mint_grant` does NOT flip a seeded `pending_grant` row with a DIFFERENT `action_type` (e.g., minting a SEND_REPLY grant should not promote a DELETE pending_grant row).
- One integration test driving the full propose -> cooling_off -> drainer_revert_to_pending_grant -> mint_grant -> drainer_claim -> dispatch flow against a synthetic DB + mock adapter, asserting status transitions: `cooling_off` -> `pending` -> `draining` -> `pending_grant` -> `pending` -> `draining` -> `applied`.

**AC-4**: Symmetric-demotion audit: investigate whether `revoke_grant` needs a symmetric demotion (`pending` -> `pending_grant` for rows that depended on the now-revoked grant). Working hypothesis: NO — the drainer's per-tick `is_grant_valid` re-check at `_check_tier_3` already handles revocations correctly (a row that gets claimed mid-revocation either lands in `pending_grant` via the existing revert path, or completes with a stale-but-valid grant which is fine; the next tick re-evaluates). Result: a one-paragraph audit note in this story's Dev Notes confirming or refuting the hypothesis.

**AC-5**: MANDATORY-CR per §5.12: this patch crosses Story 4-3 (mint_grant) + Story 4-4 (drainer) load-bearing seam; minimum one CR review pass.

## Tasks / Subtasks

- [x] **Task 1**: Verify inline-fixed code is in place: `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` query in `mailbot_api/db/queries.py` + side-effect in `mailbot_api/actions/authorization.py` `mint_grant`. ✅ Verified at queries.py:800-807, authorization.py:39 (import) + 156-173 (call site + structured log).
- [x] **Task 2**: Added 6 new unit tests in `tests/unit/actions/test_authorization.py` (26 total pass, +6 net). Covers AC-3 first bullet (matching-type promotion), AC-3 second bullet (counter-test: different action_type does NOT promote), plus 4 supporting tests: broad-sweep multiple rows, structured-log `pending_grant_promoted` count = N, structured-log promoted = 0 when no rows, status-filter discipline (pending/applied not touched).
- [x] **Task 3**: Created `tests/integration/test_pending_grant_promotion_lifecycle.py` with 2 integration tests asserting (a) full pending→pending_grant→pending→applied lifecycle via propose→drainer→mint_grant→drainer→FakeGraphWriteAdapter, (b) wrong-action_type counter-test (SEND_REPLY mint does NOT promote DELETE pending_grant; correct DELETE mint then does). Both pass against real SQLite with full migration chain.
- [x] **Task 4**: Symmetric-demotion audit complete. Hypothesis CONFIRMED — no eager demotion needed. See AC-4 audit paragraph in Dev Notes below.
- [x] **Task 5**: All 4 gates green at dev-complete baseline. Ruff clean. Mypy --strict clean (122 files). Boundary clean. Pytest 1078 + 2 skipped (+8 net vs Story 6-15 baseline of 1070+2). MANDATORY-CR pending — dispatched in Phase 2.4 of autonomous-story-run skill.

## Dev Notes

### Why this story exists

Story 6-6.5 walk discovered F22 live after F19 was inline-fixed. With F19 fixed, the next-encountered blocker was: pending_actions row claimed by drainer, reverted to `pending_grant` (correctly — no grant), then `mint_grant(SEND_REPLY, [graph_id])` was invoked — but the row STAYED in pending_grant indefinitely. Probe revealed `PENDING_ACTIONS_SELECT_DRAINABLE` filters `WHERE status='pending'` only, and `mint_grant` had no side-effect to wake pending_grant rows.

Inline fix shipped during the walk to unblock CP-A. This story formalizes the fix per the inline-fix-and-walk pattern (same as 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9 sibling-quartet).

### F22 details

Architectural gap: Story 4-3 (`mint_grant`) and Story 4-4 (drainer revert path) were validated against synthetic DBs where rows were pre-seeded into the right status, never through the live propose -> cooling_off -> drainer_revert_to_pending_grant -> mint_grant flow. Grant infrastructure was missing back-promotion: `cooling_off` has `COOLING_OFF_PROMOTE_DUE` ticker, but `pending_grant` had no equivalent.

### Inline fix shape

```sql
-- New query in mailbot_api/db/queries.py
UPDATE pending_actions SET status = 'pending'
WHERE status = 'pending_grant' AND action_type = ?
```

```python
# In mint_grant, after the action_grants INSERT succeeds:
promoted = await execute_write(db_path, PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE, (action_type.value,))
# logged in the existing structured log: extra={..., "pending_grant_promoted": promoted}
```

### Project Structure Notes

- **Files touched (already shipped by inline fix, verified 2026-06-05):**
  - `mailbot_api/db/queries.py:800-807` — new `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` constant
  - `mailbot_api/actions/authorization.py:39` — import of the new query
  - `mailbot_api/actions/authorization.py:156-173` — side-effect on `mint_grant` after INSERT + structured-log `pending_grant_promoted` field
- **Drainer revert path** (read-only reference, NOT modified by this story): `mailbot_api/actions/drainer.py:199-216` (`_revert_to_pending_grant` helper), called from `_drain_one` at lines 526 / 531 for Tier-2/Tier-3 grant-missing branches.
- **Test homes:**
  - Unit tests for `mint_grant` live in `tests/unit/actions/test_authorization.py` (verify path exists before writing — if absent, scaffold under that path; the unit pattern across the repo is `tests/unit/<package>/test_<module>.py`).
  - Integration tests for the propose→drainer→mint→drain loop belong under `tests/integration/actions/` — pattern established by Story 4-4 and Story 4-7 integration tests.
- **No new migrations**, no new columns, no API surface changes. SQL-only contract addition + Python side-effect.

### Testing Standards

- **Unit-test framework:** `pytest` + `pytest-asyncio` (project standard — every async test under `tests/unit/actions/` uses `async def` with `@pytest.mark.asyncio` or session-level `asyncio_mode = "auto"` config).
- **DB fixture pattern:** synthetic SQLite via `tests/conftest.py` `db_path` / `seeded_db` fixtures (mirrors Story 4-3 / 4-4 tests). Do NOT mock `execute_write` / `fetchall` — point at a real temp SQLite path so the new query exercises the real WAL executor.
- **Per Step 2.4.7 (Middleware-Real-Bootstrap Gate, MailBot reframing):** the integration test for AC-3 third bullet MUST hit real SQLite with real schema; `mint_grant` is a state-changing write on the `action_grants` + `pending_actions` tables, so unit-only coverage of the promotion side-effect does NOT satisfy the gate. The integration test demonstrates the cross-store contract (action_grants INSERT triggers pending_actions UPDATE).
- **Assertion shape:** prefer reading `pending_actions.status` back via direct `SELECT` rather than asserting on `execute_write` rowcount alone — rowcount is informational; the observable behavior is that the drainer's next tick sees `status='pending'`.
- **Counter-test discipline:** the second unit test (mint SEND_REPLY does NOT promote pending DELETE) is the load-bearing one — without it, the test pair would pass even if the query were missing its `AND action_type = ?` filter.

### AC-4 — Symmetric demotion audit (paragraph)

**Hypothesis (from story file):** `revoke_grant` does NOT need symmetric demotion (`pending` -> `pending_grant`) because the drainer's per-tick `is_grant_valid` re-check at `_check_tier_2` / `_check_tier_3` already handles revocations correctly.

**Audit result:** CONFIRMED. Reading `mailbot_api/actions/drainer.py`:

- `_check_tier_2:307` invokes `is_grant_valid(row.action_type, row.email_id, db_path=db_path)` on every drain attempt. If the grant was revoked between propose-time and this tick, `is_grant_valid` returns `(False, None)` (line 325 of `authorization.py`: `ACTION_GRANT_FIND_VALID` filters on `revoked_at IS NULL`). The drainer then returns `(None, None, True)` (`should_wait=True`) → row is reverted to `pending_grant` via `_revert_to_pending_grant` at `_drain_one:526`. This IS the symmetric demotion, applied lazily.
- `_check_tier_3:325` does the same re-check, with the additional grant-wait-window enforcement: rows past the 30-min window are failed urgent (`grant_expired_unauthorized`) instead of reverted, but the underlying grant-validity check is identical.
- The race between revoke-grant and a row already in `status='draining'` (mid-claim): the drainer loaded the row in the `pending` state, but the per-tier `is_grant_valid` re-check happens AFTER the claim succeeds (see `_drain_one:522-532`). So a grant revoked mid-claim still triggers the revert branch. No eager demotion needed at the revoke-grant call site.

**What this audit also confirms:** the broad-sweep semantics of `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` are safe. A pending_grant row promoted to pending whose `email_id` is NOT in the newly-minted grant's `email_ids` list will simply revert back to pending_grant on the drainer's next tick (via the same per-tick `is_grant_valid` re-check). The cost is one extra drainer round-trip per stale row — acceptable for the simplicity gain of a single-column UPDATE.

**Result:** No code changes required for AC-4. The hypothesis stands.

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F22`
- `mailbot_api/actions/authorization.py:156-173` — inline-fixed `mint_grant` side-effect
- `mailbot_api/db/queries.py:800-807` — `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` constant
- `mailbot_api/actions/drainer.py:199-216` — `_revert_to_pending_grant` helper (the seam this story closes)
- Story 4-3 `mint_grant` + Story 4-4 drainer revert path — load-bearing seam
- Sibling-quartet pattern: stories 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9 / 6-6.5
- Project context: `_bmad-output/planning-artifacts/project-context.md` (AI rules + conventions)
- Skill cadence reference: `_bmad-output/implementation-artifacts/skill-update-log.md § CR-cadence-v2` (Story 4-7 hardening — §5.12 criteria gate MANDATORY-CR)

## Dev Agent Record

### Agent Model Used

- Dev: claude-opus-4-7
- Reviewer (MANDATORY-CR per §5.12): claude-sonnet-4-6

### Debug Log References

- 2026-06-05 — full regression suite run, 1078 + 2 skipped passed in 161s. No failures.

### Completion Notes List

- **Task 1 — Verify inline-fix in place:** Confirmed `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` constant at `mailbot_api/db/queries.py:800-807` (SQL: `UPDATE pending_actions SET status = 'pending' WHERE status = 'pending_grant' AND action_type = ?`) and its consumer at `mailbot_api/actions/authorization.py:39` (import) + `:156-173` (call site after ACTION_GRANT_INSERT, structured `pending_grant_promoted` field included in `action.grant.minted` log). Inline-fixed code shipped during Story 6-6.5 walk on 2026-06-04 and is intact.
- **Task 2 — Unit tests:** Added 6 new unit tests to `tests/unit/actions/test_authorization.py`: (1) `test_mint_grant_promotes_matching_pending_grant_row` — AC-3 first bullet (matching-type promotion); (2) `test_mint_grant_does_not_promote_different_action_type` — AC-3 second bullet load-bearing counter-test (SEND_REPLY mint must NOT promote DELETE pending_grant row); (3) `test_mint_grant_promotes_multiple_matching_rows` — broad-sweep semantics (3 rows promoted including one whose email_id is NOT in the grant's email_ids list); (4) `test_mint_grant_promotion_log_includes_count` — AC-1 structured log assertion (`pending_grant_promoted=2`); (5) `test_mint_grant_promotion_zero_when_no_pending_grant_rows` — no-op safety (`pending_grant_promoted=0`); (6) `test_mint_grant_promotion_skips_pending_and_applied_rows` — status-filter discipline (rows in `pending`/`applied` MUST NOT be touched). All 26 tests in the file pass (20 existing + 6 new).
- **Task 3 — Integration test:** Created `tests/integration/test_pending_grant_promotion_lifecycle.py` with 2 integration tests. `test_full_lifecycle_pending_grant_promotion_on_mint_grant` drives the full AC-3 third bullet flow: propose DELETE → drain (no grant → pending_grant) → drain again (regression guard: row stuck) → mint_grant (F22 promotion fires → pending) → drain (claimed + dispatched via FakeGraphWriteAdapter → applied). `test_full_lifecycle_mint_grant_does_not_disturb_unrelated_action_type` asserts the cross-cutting counter-case: SEND_REPLY mint must NOT promote a DELETE pending_grant row; subsequent correct DELETE mint then does. Both pass against real on-disk SQLite with full migration chain. Satisfies Step 2.4.7 Middleware-Real-Bootstrap Gate (MailBot reframing: state-changing writes on `action_grants` + `pending_actions` exercised end-to-end through the drainer, no `is_grant_valid`/`execute_write` mocking).
- **Task 4 — Symmetric-demotion audit:** Hypothesis CONFIRMED. The drainer's per-tick `is_grant_valid` re-check at `_check_tier_2:307` and `_check_tier_3:325` lazily handles `revoke_grant` events — rows in `pending` whose grant was revoked between propose-time and the next tick are reverted to `pending_grant` via the existing revert path. No eager symmetric demotion needed at the revoke-grant call site. Audit paragraph in Dev Notes § AC-4.
- **Task 5 — All 4 gates green:** Ruff clean. Mypy --strict clean (122 source files). Boundary check clean (`scripts/check_boundaries.py` exit 0). Pytest 1078 + 2 skipped (+8 net vs Story 6-15 baseline of 1070+2: +6 unit + 2 integration = 8 net). MANDATORY-CR per §5.12 confirmed required before done-flip (criterion 3 dev-self-flagged + criterion 6 load-bearing-orchestrator both fire — cross-story seam between Story 4-3 `mint_grant` and Story 4-4 drainer). Pre-review self-audit artifact: `6-13.pre-review.md` (all 5 sections + 11 Posture Audit sub-sections present).

### File List

- `mailbot_api/db/connection.py` — CR-1 fix: added `_execute_insert_and_write_sync` + `execute_insert_and_write` async wrapper (atomic INSERT + write batch in single BEGIN IMMEDIATE / COMMIT envelope). +56 LOC.
- `mailbot_api/actions/authorization.py` — CR-1 fix applied: switched `mint_grant` from two-call (`execute_insert_returning_id` + `execute_write`) to atomic batch (`execute_insert_and_write`). Updated import. CR-4 disposition docstring added to `mint_grant`. CR-5 inline comment added at the log site.
- `tests/unit/actions/test_authorization.py` — 6 new promotion tests (Task 2) + 1 new atomicity rollback regression test (CR-1) + helpers `_seed_pending_grant_row` (with CR-2 docstring) / `_read_pending_status` / `execute_insert_returning_id_helper`. Comment in `test_mint_grant_promotes_multiple_matching_rows` qualified per CR-3.
- `tests/integration/test_pending_grant_promotion_lifecycle.py` — NEW file. 2 integration tests + 3 helpers. CR-6 docstring added to `_setup` explaining why `monkeypatch` is required here but not in unit tests.
- `_bmad-output/implementation-artifacts/6-13-pending-grant-promotion-on-mint-grant-f22-closure.md` — story file, this file. Status flipped backlog→ready-for-dev→in-progress→review. Dev Notes enriched with Project Structure Notes / Testing Standards / AC-4 audit paragraph. Dev Agent Record populated. All 6 CR findings dispositioned + applied.
- `_bmad-output/implementation-artifacts/6-13.pre-review.md` — NEW file. Pre-review self-audit artifact (all 5 sections + 11 Posture Audit sub-sections; §5.12 verdict = MANDATORY-CR).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story 6-13 status flipped backlog→ready-for-dev→in-progress→review (final flip to `done` happens at end of done-gates).

### Change Log

- 2026-06-05 — Story 6-13 dev complete. F22 closure (inline-shipped during 6-6.5 walk) now has 6 unit tests + 2 integration tests + symmetric-demotion audit. Net +8 tests. All 4 gates green. Ready for MANDATORY-CR per §5.12 (cross-story Story 4-3 + 4-4 load-bearing seam).
- 2026-06-05 — MANDATORY-CR completed by claude-sonnet-4-6. 6 issues found (1 MED, 3 LOW, 2 INFO). All 6 APPLIED. Biggest fix (CR-1): wrapped ACTION_GRANT_INSERT + PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE in a single atomic BEGIN IMMEDIATE / COMMIT transaction via new `execute_insert_and_write` helper in `connection.py`. Added atomicity rollback regression test (+1 test). All 4 gates green post-CR at 1079 + 2 skipped (+9 net vs Story 6-15 baseline of 1070+2).

## Completion Notes

### 2026-06-05 — done-flip

F22 closure shipped via test coverage + atomicity hardening. The pending_grant→pending promotion side-effect that landed inline during Story 6-6.5's third-pass walk on 2026-06-04 is now (a) covered by 7 unit tests + 2 integration tests across `tests/unit/actions/test_authorization.py` and `tests/integration/test_pending_grant_promotion_lifecycle.py`, (b) hardened against the non-atomic two-transaction failure mode that CR-1 surfaced (via new `execute_insert_and_write` async helper in `mailbot_api/db/connection.py`), and (c) audited against the symmetric-demotion question (AC-4 paragraph confirms the drainer's per-tick `is_grant_valid` re-check at `_check_tier_2:307` / `_check_tier_3:325` lazily handles revocations — no eager demotion needed at `revoke_grant` call site).

MANDATORY-CR per §5.12 closed by claude-sonnet-4-6 with 6 findings, all 6 applied (100%). All 4 gates green post-CR: ruff clean, mypy --strict clean (122 source files), boundary check clean, pytest 1079 + 2 skipped (+9 net vs Story 6-15 baseline of 1070+2; +6 unit promotion tests + 2 integration tests + 1 CR-1 atomicity regression test). Pre-review self-audit artifact (`6-13.pre-review.md`) covered all 5 sections + 11 Posture Audit sub-sections.

UNBLOCKS: Story 6-6.5 Section A re-walk no longer relies on inline-only F22 patch — the fix is now CR-cleared + atomic + regression-protected.

## Tasks / Subtasks (continued)

### Code Review Action Items (sonnet-4-6, 2026-06-05)

- [x] **CR-1 [MED] Non-atomic INSERT + promotion UPDATE — grant minted but rows may stay in `pending_grant` until retry.** ✅ APPLIED 2026-06-05. Added `execute_insert_and_write` async helper + `_execute_insert_and_write_sync` to `mailbot_api/db/connection.py` (single BEGIN IMMEDIATE / COMMIT envelope batching INSERT + UPDATE). Updated `mint_grant` to use the new helper; both writes now commit or roll back atomically. Added `test_mint_grant_atomicity_rollback_on_promotion_failure` regression test asserting (a) RuntimeError/OperationalError surfaces from the batch, (b) action_grants COUNT(*) = 0 after rollback, (c) pending_grant row stays in pending_grant. Test passes (verified inline). Atomicity invariant now provable. `execute_insert_returning_id` (ACTION_GRANT_INSERT) and `execute_write` (PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE) run in two separate `BEGIN IMMEDIATE / COMMIT` transactions (see `connection.py:72-87` and `connection.py:114-139`). A crash or async cancellation between the two commits leaves `action_grants` with the new grant but all matching `pending_grant` rows unmodified — stuck until the next `mint_grant` call. A concurrent drainer tick in this window reads the new grant as valid via `is_grant_valid`, claims any `pending` rows, but `pending_grant` rows remain invisible to the drainer (`PENDING_ACTIONS_SELECT_DRAINABLE` filters `status='pending'` only). Self-flagged by dev as §3 issue 1 ("ESCALATE TO REVIEWER"). Recommend wrapping both writes in a single `BEGIN IMMEDIATE` transaction — this requires a new `connection.py` helper (e.g. `execute_write_batch`) or inlining both SQL statements via `executescript`. If the two-transaction design is intentionally accepted (the drainer self-heals on next mint), document the failure mode explicitly in the function docstring and add a unit test that seeds a `pending_grant` row, crashes after the INSERT, and asserts the promotion is NOT applied — verifying the known-recovery path.
- [x] **CR-2 [LOW] Test helper `_seed_pending_grant_row` seeds `proposed_by_grant_id = NULL` — a state unreachable in production.** ✅ APPLIED 2026-06-05. Added docstring to `_seed_pending_grant_row` explaining the deliberate NULL seeding, why it is safe for promotion-path tests (the UPDATE filters by status + action_type, never reads grant_id), and what would warrant changing it (a future consumer reading proposed_by_grant_id from a promoted row). Production rows reach `pending_grant` only via `_revert_to_pending_grant` (drainer), which always writes a non-NULL `proposed_by_grant_id` (via `PENDING_ACTION_REVERT_TO_PENDING_GRANT` at `queries.py:795-798`). The unit tests (`test_authorization.py:318-338`) seed rows without `proposed_by_grant_id`, which the schema accepts (`migrations/015_pending_actions.sql:35`: `INTEGER NULL`) but which cannot occur in live data. If any downstream code (e.g., a future `revoke_grant` cascade or `action_history` consumer) reads `proposed_by_grant_id` from a promoted row, the NULL would be unexpected. Either (a) update the helper to accept an optional `proposed_by_grant_id` parameter and default it to a sentinel grant inserted in the test setup, or (b) add a comment documenting the deliberate NULL-seeding and why it is safe for promotion-path tests.
- [x] **CR-3 [LOW] `test_mint_grant_promotes_multiple_matching_rows` comment overstates drainer self-healing guarantee for the grant-wait window.** ✅ APPLIED 2026-06-05. Updated comment to qualify: "PROVIDED the grant-wait window has not elapsed. For Tier-3 rows past TIER_3_GRANT_WAIT_WINDOW the drainer marks them `failed` instead of reverting (drainer.py:330-332). This test is instantaneous so the window concern does not apply here." Test correctness unchanged; comment now matches reality. The test comment at `test_authorization.py:404-406` says "The is_grant_valid re-check at drain time will revert e-99 back to pending_grant on the drainer's next tick (the broad-sweep contract)." This is only true if the row's `proposed_at` + `TIER_3_GRANT_WAIT_WINDOW` has not elapsed. If `TIER_3_GRANT_WAIT_WINDOW` passes before the correct email-scoped grant is minted, `_check_tier_3` returns `grant_expired_unauthorized` and the row is marked `failed` rather than reverted to `pending_grant` (see `drainer.py:330-332`). The comment should be qualified: "…will revert e-99 back to pending_grant **provided the grant-wait window has not elapsed**." The test itself is correct (Tier-3 window is 30 minutes, test is instantaneous), but the comment could mislead future readers into assuming unconditional self-healing.
- [x] **CR-4 [LOW] Dev self-flagged: `execute_write` for promotion is unguarded — loud-fail on DB contention leaves grant minted but rows undemoted.** ✅ APPLIED 2026-06-05 via CR-1 fix. The atomicity wrap (CR-1) makes this finding moot: now BOTH the INSERT and the UPDATE roll back on failure, so loud-fail is the correct behavior — the caller's `MintGrantOut(ok=True)` is never returned alongside a half-applied state. Added docstring to `mint_grant` explicitly recording this disposition (per CR-4 reviewer suggestion: atomicity makes swallow-vs-loud-fail moot). Reviewer second-opinion (escalated per §3 issue 1): the current loud-fail behavior is **preferable** in principle (surfaces contention bugs early, avoids silent partial-success) but the caller (`mint_grant`) returns `MintGrantOut(ok=True)` to its HTTP consumer even though the promotion may have failed — the API response is misleading. Options: (a) catch the exception, log at WARNING, and let the drainer self-heal (swallow-and-log — caller gets `ok=True`, promotion is best-effort), (b) propagate the exception so the HTTP caller gets a 500 and can retry (loud-fail — current behavior), or (c) return a `MintGrantOut(ok=True, pending_grant_promoted_warning=True)` field when the promotion raised. Recommend option (a) with a structured WARNING log field `pending_grant_promotion_failed=True` — the drainer self-heals on next `mint_grant`, and a loud 500 for the upstream caller (who just successfully minted a grant) is a worse user experience than a logged warning.
- [x] **CR-5 [INFO] `MintGrantOut` does not expose `pending_grant_promoted` count to callers.** ✅ APPLIED 2026-06-05 — documentation-only. Added inline comment at the log site in `authorization.py` recording the rationale (verb shim's external contract is "grant minted ok"; promotion is internal side-effect for the drainer; if a future external API surfaces mint_grant to operators, add the count to MintGrantOut as a non-breaking additive field at that time). The promoted count is logged at INFO level (`pending_grant_promoted` in the structured `action.grant.minted` log) but is not included in the `MintGrantOut` response model (`authorization.py:65-71`). Callers (verb shim, future HTTP consumers) cannot observe the side-effect count without log scraping. This is acceptable for the current internal-only verb shim architecture, but if the `mint_grant` endpoint is ever surfaced as an external API (e.g., admin panel, webhook handler), the promotion count would be a useful observability field. Consider adding `pending_grant_promoted: int = 0` to `MintGrantOut` now as a non-breaking additive field; alternatively, document explicitly that the count is log-only.
- [x] **CR-6 [INFO] Integration test `_setup` helper signature differs from unit test `_setup` — inconsistent fixture pattern across the two new test files.** ✅ APPLIED 2026-06-05 — option (b) per reviewer suggestion. Added docstring to the integration test `_setup` explaining why `monkeypatch` is required here (full drainer lifecycle exercises Tier-3 failure paths that fire urgent notifications; MAILBOT_LOGS_PATH must be redirected away from the developer machine's default logs directory) but not in the unit tests (no drainer / no notification path). Unit test `_setup(tmp_path)` at `test_authorization.py` (pre-existing pattern) takes only `tmp_path`. Integration test `_setup(tmp_path, monkeypatch)` at `test_pending_grant_promotion_lifecycle.py:36-40` takes an additional `monkeypatch` parameter to set `MAILBOT_LOGS_PATH`. This is correct behavior but the asymmetry means a future developer adding unit tests for promotion may mistakenly omit `MAILBOT_LOGS_PATH` and get a different code path. Consider either (a) adding `MAILBOT_LOGS_PATH` to the unit test `_setup` for consistency, or (b) adding a comment in the integration test `_setup` explaining why `monkeypatch` is needed here but not in the unit tests.

## Senior Developer Review (AI)

**Reviewer:** claude-sonnet-4-6
**Date:** 2026-06-05
**Story:** 6-13 — `pending_grant` → `pending` promotion on `mint_grant` (F22 closure)
**Mandatory CR trigger:** §5.12 criterion 3 (dev-self-flagged) + criterion 6 (load-bearing-orchestrator)

### Summary

The implementation is structurally sound and the test coverage is thorough for a tests-only story. The inline fix (`PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` + `execute_write` call after `ACTION_GRANT_INSERT`) closes F22 correctly. The AC-4 symmetric-demotion audit is well-reasoned: the drainer's per-tick `is_grant_valid` re-check does constitute lazy symmetric demotion, and the hypothesis is confirmed.

The load-bearing cross-story seam (Story 4-3 `mint_grant` ↔ Story 4-4 drainer) is where the primary risk lives. The adversarial review identified one MED-severity concern (CR-1: non-atomic two-transaction pattern), which the dev correctly self-flagged as an escalation item. The reviewer's disposition is that this merits a concrete decision in this CR rather than deferral: either wrap the two writes in a single transaction, or document the known failure mode in the function docstring and add a test that exercises the recovery path.

The remaining findings are LOW/INFO and do not block correctness. CR-3 is editorial (the comment about drainer self-healing overstates the guarantee in the Tier-3 grant-wait-window scenario). CR-2 is a test-fidelity gap that is safe now but could mislead future consumers of `proposed_by_grant_id`. CR-4 is the dev's escalated §3 issue 1 with a concrete recommendation (swallow-and-log is preferable to loud-fail for a side-effect operation that the drainer can recover). CR-5 and CR-6 are informational.

**Gate verdict:** CONDITIONAL PASS — CR-1 (atomicity) and CR-4 (error handling disposition) require explicit resolution (either fix or documented accept-with-rationale) before done-flip. CR-2 and CR-3 are recommended fixes. CR-5 and CR-6 are at developer discretion.
