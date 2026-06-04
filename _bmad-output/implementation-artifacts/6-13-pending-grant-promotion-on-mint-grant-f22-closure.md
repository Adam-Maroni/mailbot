# Story 6.13: `pending_grant` -> `pending` promotion on `mint_grant` — F22 closure

Status: backlog

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

- [ ] **Task 1**: Verify inline-fixed code is in place: `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` query in `mailbot_api/db/queries.py` + side-effect in `mailbot_api/actions/authorization.py` `mint_grant`.
- [ ] **Task 2**: Add unit tests (AC-3 first two) in `tests/unit/actions/test_authorization.py` (or wherever `mint_grant` is tested).
- [ ] **Task 3**: Add integration test (AC-3 third) — full propose-to-applied lifecycle against synthetic DB + `MockTransport` outlook adapter.
- [ ] **Task 4**: Run the symmetric-demotion audit (AC-4) — write the paragraph + add demotion code if the audit refutes the hypothesis.
- [ ] **Task 5**: Run all 4 gates green; MANDATORY-CR; apply findings.

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

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F22`
- `mailbot_api/actions/authorization.py` + `mailbot_api/db/queries.py` — inline-fixed code
- Story 4-3 `mint_grant` + Story 4-4 drainer revert path — load-bearing seam
- Sibling-quartet pattern: stories 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9
