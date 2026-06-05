# Pre-Review Self-Audit — 6-17-oauth-auto-resume-script-driven-success-race-f26-closure

**Generated:** 2026-06-05 21:35 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/6-17-oauth-auto-resume-script-driven-success-race-f26-closure.md
**Status at audit time:** in-progress (post dev-story, pre code-review dispatch)

## 1. AC-vs-code drift scan

- AC-1: MATCH — `_record_refresh_success` now always calls `try_resume_if_reason(expected_reason="oauth_refresh_failing")` after the worker_health row write. The atomic helper handles all pause-state shapes safely. AC-3 + AC-4 tests verify auto-resume fires on script-driven success against paused pre-state.
- AC-2: MATCH — Option A shipped (drop the threshold gate). Rationale documented in classifier docstring + story Completion Notes: `try_resume_if_reason` is the only safety check needed; the threshold gate at oauth.py:231-232 was redundant AND was the F26 root cause. Cost: one extra DB read per successful exchange when no pause is in place; negligible.
- AC-3: MATCH — `test_auto_resume_fires_when_prior_failures_below_threshold_and_pause_is_ours` reproduces the F26 race precondition (paused with our reason + counter=0) and asserts auto-resume fires + `oauth.refresh.auto_resumed` log fires.
- AC-4: MATCH — `test_script_driven_success_auto_resumes_paused_router_f26_e2e` invokes `scripts.refresh_outlook_oauth._persist` end-to-end against the same F26 pre-state (mirrors Story 6-15 AC-6.3 harness pattern).
- AC-5: MATCH — `docs/auth-recovery.md:148-155` amended with Story 6-17 reference: explains the auto-resume is now reactive even when `consecutive_refresh_failures` was below the alarm threshold.
- AC-6: MATCH — MANDATORY-CR will dispatch per §5.12 verdict (2 criteria fire). Sonnet 4.6 reviewer.

Bonus: 2 regression-guard tests added — `test_auto_resume_skips_when_pause_reason_is_not_ours_even_below_threshold` (Story 6-15 CR-10 atomic-helper contract preserved post-F26 fix) + `test_auto_resume_fires_when_router_not_paused_no_log` (no spurious resume logs on healthy refresh).

## 2. File-List-vs-git diff check

Per `rtk git status --porcelain` (just for 6-17-related paths):

```
?? tests/integration/test_oauth_auto_resume_race_f26.py
?? _bmad-output/implementation-artifacts/6-17-oauth-auto-resume-script-driven-success-race-f26-closure.pre-review.md
 M mailbot_api/sync/oauth.py
 M docs/auth-recovery.md
 M _bmad-output/implementation-artifacts/6-17-oauth-auto-resume-script-driven-success-race-f26-closure.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
```

Cross-reference against story File List (to be filled at done-time):
- All 6 paths accounted for. No phantom or missing.
- The 16 staged files from Story 6-18 + 6-16 remain staged separately.

## 3. Adversarial self-review

- [LOW] `mailbot_api/sync/oauth.py:_record_refresh_success` — the function signature still carries `prior_failures: int` even though the threshold check is removed. The parameter is preserved for observability (passed to the auto_resumed log event). A reader might wonder why we keep an unused-looking parameter. Mitigation: docstring explicitly explains "preserved for observability" — clear intent.
- [LOW] `tests/integration/test_oauth_auto_resume_race_f26.py:55-72` — F26 race precondition is simulated by calling `get_pause_state().pause(db_path, reason="oauth_refresh_failing")` directly. Production would reach this state via K failures bumping the counter + counter being reset by a transient success. The test telescope is shorter (direct pause), which is fine for the unit-level F26 contract assertion but doesn't exercise the K-failures-then-counter-reset full race. Mitigation: AC-3 explicitly calls for this telescope (paused pre-state + counter=0); the longer narrative is covered by AC-4 script-driven test + existing Story 6-15 AC-6.2 test.
- [INFO] `docs/auth-recovery.md:148-155` — the new paragraph explains the threshold-gate removal but doesn't show a concrete recovery example. Acceptable for the runbook's "expected output" context; full F26-narrative reproduction lives in `epic-6-run-flags.md § F26` (already populated 2026-06-05).

## 4. Self-caught issues remediated this audit

- §3 [LOW] unused-looking `prior_failures` parameter: **ACCEPT WITH RATIONALE** — docstring explains, log event consumes it for observability. Removing it would be a public-API change to `_record_refresh_success` (called by `exchange_and_persist` at line 432-ish). Trivial maintenance cost.
- §3 [LOW] short-telescope F26 test: **ACCEPT WITH RATIONALE** — unit-level contract assertion; longer narrative covered elsewhere.
- §3 [INFO] runbook recovery example: **ACCEPT WITH RATIONALE** — runbook scope is operational checklist, not narrative; finding-grade docs live in epic-6-run-flags.md.

## 5. Posture Audit

### 5.1 Lockfile hygiene
N/A — no `requirements.txt` change.

### 5.2 Cross-doc consistency
APPLIED — `docs/auth-recovery.md` line 148 amended with Story 6-17 reference. `epic-6-run-flags.md § F26` (filed 2026-06-05 during Story 6-6.5 fourth-pass walk) is the canonical finding source; this audit confirms it remains accurate. Story 6-17 file references both upstream Story 6-15 CR-10 atomic helper AND Story 2-9 PauseState lineage.

### 5.3 Lifecycle-string check
N/A — no schema migration, no new env var, no lifespan touch.

### 5.4 Multi-consumer audit
APPLIED — `_record_refresh_success` has ONE consumer (`exchange_and_persist` in oauth.py). `try_resume_if_reason` has ONE consumer post-Story-6-17 (this function). No other callers of either.

```
$ rg "_record_refresh_success|try_resume_if_reason" mailbot_api/ scripts/ tests/ 2>&1 | grep -v __pycache__
mailbot_api/router/pause.py: # function definition
mailbot_api/sync/oauth.py: # function definition + caller
tests/integration/test_oauth_*.py: # test assertions
```

### 5.5 Screenshot-perception check
N/A — no graphical UI.

### 5.6 Upstream-contract check
APPLIED — the upstream contract is `PauseState.try_resume_if_reason(db_path, expected_reason)` returning bool. Reviewed `mailbot_api/router/pause.py` — the helper returns False if not paused, False if paused with different reason, True only when paused with expected reason. Atomic via the internal threading lock + the SQL UPDATE WHERE clause. Story 6-15 CR-10 contract preserved.

### 5.7 Module-mutable-state check
N/A — no new module-level state.

### 5.8 Dev-fixture seed-vs-production-shape parity
APPLIED — the F26 pre-state simulation (paused with reason="oauth_refresh_failing" + counter=0) matches the production-captured 2026-06-05 trace per story Dev Notes lines 71-75. Mock transport returns 200 OK with valid refresh_token/access_token/expires_in — matches production Microsoft response shape.

### 5.9 Grep-verify-cited-figures
APPLIED — 1099 + 2 skipped + 3 deselected verified via PowerShell full pytest. Baseline pre-Story-6-17 = 1095 + 2 + 3. Net +4 (4 new F26 tests, all selected).

### 5.10 Producer-boundary contract
APPLIED — the producer boundary (Microsoft identity endpoint) is opaque JSON; the boundary contract is preserved (200 OK with refresh_token/access_token/expires_in). No producer-side change.

### 5.11 Git-evidence consistency
APPLIED — `rtk git status --porcelain` matches the 6-file scope. No extra untracked artifacts in changed-directory neighborhoods.

### 5.12 CR-cadence-mandatory surface classification
**Cadence verdict: MANDATORY-CR**

Criteria fired (2 of the §5.12 trigger set):

1. **State-machine seam** — touches Story 2-9's PauseState contract (specifically the `try_resume_if_reason` interaction) AND Story 6-15's auto-resume contract. Behavioral change: a previously-skipped code path now always executes. A defect here could (a) leave the router permanently paused under F26-shape races (regressing F26 to perpetual) or (b) spuriously resume operator-set pauses (regressing Story 6-15 CR-10).
2. **Cross-story load-bearing** — Story 1-6 oauth.py + Story 2-9 PauseState + Story 6-15 reauth script + Story 6-1 mailbot status surfacing all consume the auto-resume contract. The script's recovery sequence (`mailbot status` reports paused: no after `scripts/refresh_outlook_oauth.py` succeeds) depends on this fix.

CR dispatch is non-negotiable per Adam-decided Epic 4 retro 2026-06-02 action item #1 (option A). Sonnet 4.6 reviewer at Step 2.4.

Summary table:

| Check | Status |
|---|---|
| 5.1 Lockfile | N/A — no deps change |
| 5.2 Cross-doc | APPLIED |
| 5.3 Lifecycle-string | N/A — no schema/env/lifespan |
| 5.4 Multi-consumer | APPLIED |
| 5.5 Screenshot-perception | N/A — no graphical UI |
| 5.6 Upstream-contract | APPLIED |
| 5.7 Module-mutable-state | N/A — no new state |
| 5.8 Dev-fixture parity | APPLIED |
| 5.9 Grep-verify | APPLIED (1099 passed verified) |
| 5.10 Producer-boundary | APPLIED |
| 5.11 Git-evidence | APPLIED |
| 5.12 Cadence verdict | **MANDATORY-CR** |
