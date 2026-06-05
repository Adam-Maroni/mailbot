---
baseline_commit: b1784a5
---

# Story 6.17: OAuth auto-resume on script-driven success — F26 closure

Status: backlog

> **Filed 2026-06-05** during Story 6-6.5 fourth-pass walk, immediately after F25 unblocked the re-auth. `scripts/refresh_outlook_oauth.py` succeeded cleanly (`HTTP 200 OK`, `oauth.token.rotated`, `oauth_state.consecutive_refresh_failures` reset to 0), but the router stayed `paused=true reason=oauth_refresh_failing`. No `oauth.refresh.auto_resumed` log fired. Operator had to run `mailbot resume` manually to unblock the drainer. Story 6-15's auto-resume contract is broken for the script-driven success path. See `epic-6-run-flags.md § F26` for the full finding.

## Story

As MailBot operator,
I want the router auto-resume from `oauth_refresh_failing`-pause whenever a successful refresh-token exchange lands — regardless of which process drove it (worker tick OR reauth script OR future caller),
So that the recovery sequence stays "one command and you are back online" instead of "two commands and you discover the second one by reading the docs."

## Acceptance Criteria

**AC-1 — Auto-resume fires on script-driven success when DB pause state has our reason.**
Given the router is paused with `reason="oauth_refresh_failing"` (from worker-side auto-pause after K consecutive failures),
When `scripts/refresh_outlook_oauth.py` invokes `exchange_and_persist` with a fresh refresh token AND the exchange succeeds,
Then `_record_refresh_success` MUST fire `try_resume_if_reason(expected_reason="oauth_refresh_failing")`,
And `oauth.refresh.auto_resumed` MUST log,
And `/admin/status` post-call MUST show `router.paused=false`.

**AC-2 — Threshold gate removed OR sourced from DB (decision needed).**
Given the current early-return at [mailbot_api/sync/oauth.py:220-221](../../mailbot_api/sync/oauth.py#L220-L221) (`if prior_failures < OAUTH_REFRESH_FAIL_THRESHOLD: return`) is the root cause when `state.consecutive_refresh_failures` was loaded BEFORE the worker bumped past threshold,
When this story closes,
Then ONE of these MUST hold:

- **Option A (drop the threshold gate entirely)**: `_record_refresh_success` ALWAYS calls `try_resume_if_reason(expected_reason="oauth_refresh_failing")`. The atomic check inside the helper already guards against resuming a non-oauth pause, so the threshold gate is redundant.
- **Option B (re-read DB inside `_record_refresh_success`)**: Replace `prior_failures` parameter with a fresh DB SELECT of `consecutive_refresh_failures` before the threshold check. Requires the SELECT to happen INSIDE the same transaction as the success-path UPDATE (otherwise a worker tick can bump between read and check).
- **Option C (move auto-resume to a separate worker tick)**: New scheduler task `oauth_pause_observer` that polls `(oauth_refresh_failing, pause_state.paused, pause_state.reason)` every 30s and resumes when conditions hold. Decouples success-path bookkeeping from pause-state observation.

Decision rationale MUST be documented in Completion Notes. Recommended: A (simplest, atomic helper already handles the safety).

**AC-3 — Regression test for the failure mode F26 surfaced.**
Given the chosen option (A/B/C),
When the fix lands,
Then a regression test in `tests/integration/test_oauth_refresh_alarm.py` MUST cover:
- Pre-state: `oauth_state.consecutive_refresh_failures = 0` AND `pause_state.paused = 1 AND reason = "oauth_refresh_failing"` (simulating the race where success bookkeeping starts from a counter that was already reset)
- Action: call `exchange_and_persist` with a `MockTransport` returning 200 OK
- Assert: `pause_state.paused = 0` post-call AND `oauth.refresh.auto_resumed` log fired

**AC-4 — Script-driven success path explicitly tested.**
Given AC-3 covers the in-process case, an additional test MUST invoke `scripts/refresh_outlook_oauth.py` end-to-end (via the same harness Story 6-15's `test_reauth_script_persists_token_without_logging_value` uses) against a paused pre-state, and assert auto-resume.

**AC-5 — Story 6-15's auth-recovery runbook is updated.**
Given the fix lands,
When [docs/auth-recovery.md](../../docs/auth-recovery.md) is updated,
Then the "expected output" section for Step 3 MUST be amended to reflect that `mailbot status` post-reauth shows ROUTER `paused: no` automatically (currently the doc reads correctly assuming auto-resume works; if Option C is chosen, document the 30s tick lag).

**AC-6 — MANDATORY-CR per §5.12.**
Two criteria fire: (a) state-machine seam (touches Story 2-9 PauseState + Story 6-15 auto-resume contract); (b) cross-story load-bearing (Story 1-6 oauth + 2-9 pause + 6-15 reauth script + 6-1 status surfacing). Minimum one CR pass before done-flip.

## Tasks / Subtasks (high-level, awaits context-engineering)

- [ ] Task 1 — Investigate to confirm hypothesis: reproduce the F26 race in a test (paused pre-state + counter-already-reset + successful exchange => no auto-resume). If hypothesis disproven, document the actual root cause + revise scope.
- [ ] Task 2 — Decision: pick Option A / B / C with rationale. Document in Completion Notes.
- [ ] Task 3 — Implement chosen option.
- [ ] Task 4 — Regression tests per AC-3 + AC-4.
- [ ] Task 5 — Update runbook per AC-5 (probably no change required if Option A; lag-mention if C).
- [ ] Task 6 — MANDATORY-CR pass.

## Dev Notes (light — full context-engineering at pickup time)

### Root-cause evidence

Captured 2026-06-05 fourth-pass walk:

1. Pre-state: `/admin/status` showed `router.paused=true reason=oauth_refresh_failing paused_at=2026-06-05T16:00:57.379360Z` (worker auto-paused after 6 consecutive failures during the F25 misconfiguration period).
2. Action: `scripts/refresh_outlook_oauth.py` with fresh refresh token (after `.env` patched for F25). Container logs show `oauth.token.rotated rotation_count=13`.
3. Post-state: `/admin/status` STILL showed `paused=true reason=oauth_refresh_failing`. `oauth.refresh.auto_resumed` NOT in container logs.
4. Manual: `POST /admin/resume` returned `previously_paused=true, message="router resumed"`. Status cleared.

### Suspected race window

[mailbot_api/sync/oauth.py:272](../../mailbot_api/sync/oauth.py#L272): `prior_failures = state.consecutive_refresh_failures` (captured at function entry).

[mailbot_api/sync/oauth.py:209-246](../../mailbot_api/sync/oauth.py#L209-L246) `_record_refresh_success`:

```python
async def _record_refresh_success(db_path: str, *, prior_failures: int) -> None:
    await upsert_worker_health(...)
    if prior_failures < OAUTH_REFRESH_FAIL_THRESHOLD:   # ← early-return; auto-resume never runs
        return
    ...
    resumed = await get_pause_state().try_resume_if_reason(db_path, expected_reason=_OAUTH_PAUSE_REASON)
```

Script's `_persist` threads `existing.consecutive_refresh_failures` from a DB read into the new `OAuthState`, but pre-recreate the worker had bumped to 6 (DB) and `consecutive_refresh_failures` may have been reset to 0 by a transient inter-recreate success OR may have been at 1-2 from one post-recreate failure. Either way: `prior_failures < 3` triggers the early-return.

### Story 6-15 CR-10 context

Story 6-15 CR-10 fixed the operator-pause-clobber race by introducing `try_resume_if_reason` as an atomic check-and-resume helper. That fix is correct but addresses a DIFFERENT race (operator pauses for `manual_hold` between our `reason()` and `resume()` calls). F26 surfaces a NEW race: the entry threshold-check at line 220 short-circuits BEFORE the atomic helper ever runs, so CR-10 doesn't help here.

### Option-A rationale (recommended)

The atomic helper at [mailbot_api/router/pause.py](../../mailbot_api/router/pause.py) checks `paused AND reason == expected_reason` under its internal lock. If the pause state is NOT ours, `try_resume_if_reason` returns False and logs nothing. Removing the threshold gate (line 220-221) makes auto-resume always attempt — and the helper correctly refuses on mismatch. The cost is one extra DB read per successful exchange when no pause is in place; negligible.

### Cross-impact

Story 6-15's regression test `test_auto_resume_skips_when_pause_reason_is_not_ours` MUST stay green under any chosen option — that test covers the operator-pause-foreign-reason case, which Option A still handles correctly via the helper.

### References

- [mailbot_api/sync/oauth.py:209-246](../../mailbot_api/sync/oauth.py#L209-L246) — `_record_refresh_success`
- [mailbot_api/sync/oauth.py:272](../../mailbot_api/sync/oauth.py#L272) — `prior_failures` capture site
- [mailbot_api/router/pause.py](../../mailbot_api/router/pause.py) — `try_resume_if_reason` atomic helper
- [_bmad-output/implementation-artifacts/6-15-outlook-oauth-reauthorization-runbook-and-rotation-reminder-f23-closure.md](./6-15-outlook-oauth-reauthorization-runbook-and-rotation-reminder-f23-closure.md) — Story 6-15 (CR-10 context + AC-3 auto-resume contract)
- [tests/integration/test_oauth_refresh_alarm.py](../../tests/integration/test_oauth_refresh_alarm.py) — extend with AC-3 + AC-4 tests
- `epic-6-run-flags.md § F26` — full finding text

## Dev Agent Record

### Agent Model Used

(awaiting pickup)

### Debug Log References

(awaiting pickup)

### Completion Notes List

(awaiting pickup)

### File List

(awaiting pickup)

### Change Log

- 2026-06-05 — Story 6.17 filed as STUB during Story 6-6.5 fourth-pass walk. Hypothesis-stage root cause + recommended option-A documented; awaits context-engineering + dev pickup.
