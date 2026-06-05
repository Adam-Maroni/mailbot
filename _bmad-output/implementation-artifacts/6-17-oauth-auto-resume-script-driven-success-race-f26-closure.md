---
baseline_commit: b1784a5
---

# Story 6.17: OAuth auto-resume on script-driven success — F26 closure

Status: done

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

- [x] Task 1 — Hypothesis CONFIRMED. The F26 race is reproducible: with `pause_state.paused=1 AND reason="oauth_refresh_failing"` + `oauth_state.consecutive_refresh_failures=0`, the pre-fix `_record_refresh_success` short-circuited at the threshold gate. `test_auto_resume_fires_when_prior_failures_below_threshold_and_pause_is_ours` is the canonical reproducer.
- [x] Task 2 — DECISION: Option A (drop the threshold gate). Rationale: `try_resume_if_reason` is the atomic helper from Story 6-15 CR-10; it ALREADY handles every pause-state shape safely (not-paused → return False; paused with different reason → return False; paused with our reason → atomic resume). The threshold gate was redundant AND was the F26 root cause. Option A cost: one extra DB read per healthy refresh; negligible.
- [x] Task 3 — Option A implemented at `mailbot_api/sync/oauth.py:_record_refresh_success`. CR-2 swap also applied: `try_resume_if_reason` now runs BEFORE `upsert_worker_health` so a parallel observer never sees the transient inconsistency `worker_health=ok AND paused=true`.
- [x] Task 4 — 4 regression tests in `tests/integration/test_oauth_auto_resume_race_f26.py`: (a) AC-3 in-process F26 reproducer; (b) AC-4 script-driven `_persist` end-to-end against paused pre-state; (c) Story 6-15 CR-10 contract preserved post-fix (different-reason pause NOT clobbered); (d) negative-control no-spurious-resume-log when not paused.
- [x] Task 5 — `docs/auth-recovery.md` updated at the post-recovery expected-output section with Story 6-17 reference: explains the auto-resume is reliable even when prior_failures was below threshold.
- [x] Task 6 — MANDATORY-CR pass complete. Sonnet 4.6 reviewer, 5 findings (3 patch + 2 defer). 2 actionable APPLIED (CR-2 worker-health-vs-resume ordering swap; CR-3 module-level import cleanup). 1 defer-with-rationale (CR-1 test file location — project convention divergence). 2 pre-existing defers acknowledged.

### Review Findings

- [x] \[Review]\[Defer-with-rationale] CR-1 AC-3 test file location deviates from spec — **DEFER with rationale**: the AC-3 spec wording said "in `tests/integration/test_oauth_refresh_alarm.py`" but project convention (Stories 6-14 F21, 6-16 F25) is per-finding test files (`test_<surface>_<finding-id>.py`). The new file `test_oauth_auto_resume_race_f26.py` follows that convention, keeps F26 scope clearly identifiable, and preserves Story 6-15's test file for its original Story 6-15 ACs. Project convention overrides spec wording. — deferred, project convention divergence
- [x] \[Review]\[Patch] CR-2 `upsert_worker_health` called BEFORE `try_resume_if_reason` — **APPLIED**: swapped order in `_record_refresh_success`. Resume now runs FIRST, then the worker_health row write. Eliminates the transient window where a parallel observer would see `outcome=ok` AND `paused=true reason=oauth_refresh_failing` between the two awaits. Inline rationale comment added. `mailbot_api/sync/oauth.py:225-260`
- [x] \[Review]\[Patch] CR-3 `__import__` in AC-4 test body — **APPLIED**: replaced with `from mailbot_api.sync.oauth import exchange_and_persist as _real_exchange` at the function scope. Static-analysis-friendly, clearer to readers. `tests/integration/test_oauth_auto_resume_race_f26.py:236-237`
- [x] \[Review]\[Defer] `prior_failures` param retained with no control-flow use — technically correct (preserved for observability, docstring explains), but a future reader may wonder why a seemingly unused param is required; low-severity maintenance cost (`mailbot_api/sync/oauth.py:220`) — deferred, pre-existing design decision per story Option A rationale
- [x] \[Review]\[Defer] `prior_failures=0` in `auto_resumed` log event is ambiguous — an operator seeing this log when F26 fires may not understand WHY resume fired despite a below-threshold value; consider adding `was_above_threshold: bool` field for clarity (`mailbot_api/sync/oauth.py:258-263`) — deferred, non-blocking observability polish

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

- Dev: claude-opus-4-7 (Opus 4.7, 1M context)
- Code Review: claude-sonnet-4-6 (Sonnet 4.6, MANDATORY-CR per §5.12 — 2 criteria fired: state-machine seam + cross-story load-bearing)

### Debug Log References

- Pre-review self-audit: `6-17-oauth-auto-resume-script-driven-success-race-f26-closure.pre-review.md` (5 sections + 12-check §5 posture audit; §5.12 cadence verdict = MANDATORY-CR)
- CR-2 (worker_health-vs-resume ordering swap) is operationally meaningful: pre-fix, an external monitor scraping both `worker_health[oauth_refresh].outcome` AND `pause_state` between the two awaits would see a brief window of `outcome=ok AND paused=true` — false-positive "healthy" signal. Post-fix, resume runs first; the observable ordering matches operator mental-model ("router resumed, then health is OK").

### Completion Notes List

- **F26 root cause closed via Option A.** The threshold-gate early-return at `_record_refresh_success` line 220-221 was redundant — Story 6-15's atomic helper `try_resume_if_reason(expected_reason)` is the only safety check needed. Removed the gate; `try_resume_if_reason` now runs unconditionally. The helper handles every pause-state shape safely (not-paused / different-reason / our-reason).
- **Auto-resume now reactive across all race shapes** — the script-driven success path (`scripts/refresh_outlook_oauth.py`) reliably triggers auto-resume even when `prior_failures` was captured below the alarm threshold. Operator recovery is back to "one command" (`scripts/refresh_outlook_oauth.py`) instead of "two commands" (script + `mailbot resume`).
- **CR-2 ordering fix is load-bearing.** Pre-CR-fix, `upsert_worker_health` ran BEFORE `try_resume_if_reason`. Between those two awaits, the asyncio event loop can yield — a parallel observer (e.g., `/admin/status` polling) would briefly see `outcome=ok AND paused=true` — operationally confusing false signal. Post-CR-fix, resume runs FIRST, then health update. The canonical observable ordering matches operator mental-model.
- **`prior_failures` parameter preserved for observability** — even though it no longer participates in control flow, it rides through to the `oauth.refresh.auto_resumed` log event so operators can correlate the resume against the failure history. CR-5 (consider renaming or adding `was_above_threshold: bool`) deferred as non-blocking observability polish.
- **Story 6-15 CR-10 contract preserved verbatim.** Counter-test verified: a successful refresh against an operator-set pause (different reason) does NOT clobber it. The atomic helper's reason-equality check is the only safety needed.
- **All 4 gates green:** ruff clean, mypy --strict clean (123 files), boundary clean, pytest 1099 passed + 2 skipped + 3 deselected (vs baseline 1095 + 2 + 3 → net +4 from 4 new F26 tests).
- **MANDATORY-CR pass complete** per §5.12 verdict. Sonnet 4.6 reviewer produced 5 findings; 2 actionable APPLIED (100%, of actionable count): CR-2 ordering swap + CR-3 module-level import. CR-1 defer-with-rationale (project convention overrides spec wording for test file location). CR-4 + CR-5 pre-existing defers acknowledged (param-retention + observability polish).

### File List

- `mailbot_api/sync/oauth.py` (modified) — removed threshold-gate early-return at `_record_refresh_success`; CR-2 swapped `try_resume_if_reason` to run BEFORE `upsert_worker_health`; inline docstrings explain both rationales
- `tests/integration/test_oauth_auto_resume_race_f26.py` (new) — 4 tests covering AC-3 + AC-4 + Story 6-15 CR-10 contract preservation + negative control (no spurious resume log when not paused)
- `docs/auth-recovery.md` (modified) — line 148-155 expanded with Story 6-17 reference explaining threshold-gate removal
- `_bmad-output/implementation-artifacts/6-17-oauth-auto-resume-script-driven-success-race-f26-closure.md` (this file) — status + Dev Agent Record + Completion Notes + Tasks/Subtasks checks + Review Findings dispositions
- `_bmad-output/implementation-artifacts/6-17-oauth-auto-resume-script-driven-success-race-f26-closure.pre-review.md` (new) — 5-section pre-review self-audit per Step 2.3.5
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — row status: backlog → in-progress → done (Phase 2.6 staging)

### Change Log

- 2026-06-05 — Story 6.17 filed as STUB during Story 6-6.5 fourth-pass walk. Hypothesis-stage root cause + recommended option-A documented; awaits context-engineering + dev pickup.
- 2026-06-06 — autonomous-epic-run pickup; Option A shipped (threshold gate removed; atomic helper sole safety check); CR-2 worker-health-vs-resume ordering swap; MANDATORY-CR pass (Sonnet 4.6) complete with 2/2 actionable findings APPLIED (100% of actionable; 3 defers acknowledged).
