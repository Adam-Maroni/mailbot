---
baseline_commit: dd32faa5a26a13c98db9df26b13c6b7374140422
---

# Story 6.15: Outlook OAuth re-authorization runbook + rotation reminder — F23 closure

Status: done

> Filed 2026-06-04 during Story 6-6.5 third-pass walk. F23 is an **operational** finding (refresh-token lifecycle), not a code defect — but the operational gap that hid it for 9+ hours IS code-fixable: the system needs a visible alarm, a one-step recovery surface, and a decision on auto-pause to avoid pending_actions pile-up.
>
> **This story unblocks Story 6-6.5 Section B CP-A/B live re-walk** (recipient-inbox verification). Once it ships AND Adam re-authorizes, the 5-minute agent-driven CP-A/B re-walk can run (see `epic-6-run-flags.md § Re-invocation guidance`).

## Story

As MailBot operator,
I want a documented re-authorization runbook + proactive rotation reminder + visible alarm when OAuth refresh starts failing,
So that an expired Microsoft refresh token cannot silently strand the entire send pipeline — and so I can re-auth in 5 minutes when it does happen.

## Acceptance Criteria

**AC-1 (re-auth runbook, VPS-side)**: `docs/auth-recovery.md` is updated so the recovery sequence is **executable from the VPS itself** (current §Step 1–§Step 5 assumes the operator runs `mint_refresh_token.py` on a dev box and hand-copies the token into the VPS `.env`). The updated runbook MUST either (a) keep the dev-box mint flow but add a VPS-side `mailbot reauth` (or `scripts/refresh_outlook_oauth.py`) command that accepts the freshly-minted refresh token via stdin / `--from-file` and persists it directly into the `oauth_state` row without going through `.env` (preferred — eliminates Step 2's `vi /opt/mailbot/.env` + Step 3's DELETE + Step 4's container restart); OR (b) keep the existing `.env` + DELETE + restart sequence but reduce it to one command via a shell wrapper, with explicit justification for why the more invasive flow is preferred. The runbook MUST work from a clean state — operator has `.env` credentials + a running `mailbot-api` container, nothing else.

**AC-2 (CLI surface OR one-shot script — token-handling discipline)**: `scripts/refresh_outlook_oauth.py` (or `mailbot reauth` subcommand in `scripts/mailbot.py`) exists. Behavior contract:

- Accepts the new refresh token via `--from-file <path>` OR stdin (`-`) — NEVER as a CLI argument (would land in shell history).
- Calls `mailbot_api.sync.oauth.exchange_and_persist(...)` (or an equivalent helper) to perform a fresh `grant_type=refresh_token` exchange against `_TOKEN_URL_TEMPLATE` and UPSERT the row via `OAUTH_STATE_UPDATE_AFTER_EXCHANGE` (resetting `rotation_count` to 0 on first exchange, then the existing rotation logic takes over).
- Honors the existing module-level `OAUTH_STATE_INSERT_SEED` for the "no row yet" case (matches `seed_oauth_state_from_env` semantics).
- Logging discipline per Story 4-0 capture rubric + Story 5-7 redactor: MUST log `event="oauth.reauth.persisted"` with `presence=True`, `length=<int>`, `rotation_count_after=<int>` ONLY. MUST NOT log the token value, MUST NOT echo it to stdout, MUST NOT include it in error messages. The Story 5-7 chat redactor primitive (`mailbot_api/observability/redactor.py`) is the reference; reuse if applicable.
- Exit codes mirror `mint_refresh_token.py` (0 = ok, 2 = token endpoint rejected the new token, 4 = transport, 130 = aborted).

**AC-3 (`mailbot status` alarm)**: `assemble_status` (Story 6-1, `mailbot_api/observability/status.py`) gains a new field on a NEW `OAuthStatus` section (sibling to `SyncStatus` / `IngestStatus` / etc.) with the following shape:

```python
class OAuthStatus(BaseModel):
    last_rotated_at: str | None         # from oauth_state.last_rotated_at
    rotation_count: int                 # from oauth_state.rotation_count
    consecutive_refresh_failures: int   # count since last `ok`
    oauth_refresh_failing: bool         # True when consecutive_refresh_failures >= OAUTH_REFRESH_FAIL_THRESHOLD (default 3)
    access_token_expires_at: str | None # from oauth_state.access_expires_at
    access_token_stale_minutes: float | None  # elapsed since access_expires_at if past expiry, else None
```

Surface this in `/admin/status` JSON AND the `mailbot status` CLI rendering. The CLI MUST visibly flag `oauth_refresh_failing=True` as an alarm row (same severity tier as `sync_health_alarm`).

**Source of truth for `consecutive_refresh_failures`**: The cleanest option is a new `worker_health` component `oauth_refresh` written by `mailbot_api/sync/oauth.py`'s `exchange_and_persist` success/failure paths (component already has `last_outcome` semantics — adopt the same pattern as `sync`). Then `_read_oauth(...)` counts elapsed `failed` ticks since the last `ok`. The alternative (read `mailbot_logs` Docker volume for `event="oauth.refresh.failed"` lines) is rejected because the status assembler is a SQLite reader, not a log reader. Pick the worker_health approach unless a stronger pattern surfaces.

**AC-4 (drainer auto-pause on oauth_refresh_failing — DECISION REQUIRED)**: Investigate the question: should the drainer auto-pause its dispatch loop when `oauth_refresh_failing=True` so the pile of pending Tier-2/3 rows doesn't all fail with `provider_4xx_401` (each one burning a `budget_consumed=1`)? Two paths, pick one with rationale documented in this story's Completion Notes:

- **Path A (auto-pause)**: Add an early-exit guard in `mailbot_api/actions/drainer.py:run_loop` (or its `_check_tier_2`/`_check_tier_3` cousins) that consults a new `oauth_refresh_failing()` helper and short-circuits without claiming the row. Trade-off: drainer correctly preserves rows for post-re-auth retry, BUT introduces a cross-module dependency (drainer reads oauth state) that today is clean.
- **Path B (rely on existing router-pause)**: When `oauth_refresh_failing` becomes True, the existing `event="oauth.refresh.failed"` log already fires per tick. Add an automatic `pause.pause(reason="oauth_refresh_failing")` call from `_refresh_access_token_cache` (or `exchange_and_persist`) on the K-th consecutive failure. The drainer ALREADY respects pause state — no drainer-side change. On the next successful refresh, auto-`resume`. Trade-off: reuses existing pause/resume plumbing, BUT pause/resume is currently operator-driven only (Story 6-2); making it automatic changes the contract.

Decision will likely lean Path B (less coupling), but both are valid — document the choice + rationale, then implement.

**AC-5 (proactive-refresh schedule audit)**: The OAuth refresher task is registered on the scheduler at `SYNC_INTERVAL_SECONDS = 240` (4 min) in `mailbot_api/worker.py:_worker_main` as `oauth_token_refresh`. Audit whether this cadence keeps the **refresh** token alive (sliding 24h-if-unused / up-to-90d-if-continuously-rotated window per Microsoft consumer-tier docs). If the cadence is fine for access-token freshness (1h validity, 4min poll = safe) but the refresh-token rotation only happens when MS actually rotates it on a particular exchange, document the actual rotation cadence and confirm it stays inside the 24h floor. If NOT, either (a) shorten the cadence, or (b) add a proactive "rotate-anyway" ping inside the sliding window. The cadence audit MUST cite live evidence from `oauth_state.last_rotated_at` deltas (already persisted) OR a documented Microsoft policy reference.

**AC-6 (regression tests)**: Three tests minimum:

1. `test_oauth_refresh_failing_alarm_fires_after_k_failures` — given a fresh DB, simulate K consecutive `exchange_and_persist` failures via `httpx.MockTransport`, assert `OAuthStatus.oauth_refresh_failing` flips True after K-th failure.
2. `test_oauth_refresh_failing_alarm_clears_on_success` — after the alarm fires, simulate a success, assert `oauth_refresh_failing` flips False AND `consecutive_refresh_failures` resets to 0.
3. `test_reauth_script_persists_token_without_logging_value` — invoke the AC-2 script with a synthetic refresh token, intercept `mailbot_api.sync.oauth` logger, assert NO log record contains the token value (substring check against the test fixture token string).

If Path A is chosen for AC-4, add a 4th test: drainer skips claim when `oauth_refresh_failing=True`. If Path B is chosen, add a 4th test: `_refresh_access_token_cache` calls `pause.pause` on the K-th failure.

**AC-7 (MANDATORY-CR per §5.12)**: Multiple criteria fire — (a) external-credential surface (touches refresh token), (b) operator-facing (CLI + runbook), (c) cross-story load-bearing (Story 6-1 status + Story 6-2 pause + Story 4-4 drainer + Story 1-6/1-7 sync.oauth). Minimum one CR pass before done-flip.

## Tasks / Subtasks

- [x] **Task 1: Implement the re-auth CLI / script (AC-2)** — chose `scripts/refresh_outlook_oauth.py` (new file, parallels `mint_refresh_token.py`).
  - [x] 1.1 Read the new refresh token from `--from-file <path>` or stdin (`-`) — reject CLI-arg passing.
  - [x] 1.2 Build a minimal `OAuthState` (`provider="microsoft_graph"`, `refresh_token=<the-new-token>`, `access_token=None`, `rotation_count=0` for first call) — DO NOT call `seed_oauth_state_from_env` (that reads `.env`).
  - [x] 1.3 Call `exchange_and_persist(db_path, state=state)` — exercises real `_TOKEN_URL_TEMPLATE` exchange + UPSERTs `oauth_state` via existing query.
  - [x] 1.4 If no row exists yet: insert via `OAUTH_STATE_INSERT_SEED` first (so the UPDATE has a row to hit). Idempotent — re-running is safe.
  - [x] 1.5 Logging discipline: ONLY `event="oauth.reauth.persisted"`-equivalent on stdout (`OK: oauth_state persisted presence=True length=<N> rotation_count_after=<K>`). NEVER the token value.
- [x] **Task 2: Extend `assemble_status` with `OAuthStatus` section (AC-3)** — folds into Story 6-1's parallel `asyncio.create_task` block.
  - [x] 2.1 Added `OAUTH_REFRESH_FAIL_THRESHOLD = 3` module constant in `mailbot_api/sync/oauth.py` (re-exported by `observability/status.py` via import). Source-of-truth shifted to a new `oauth_state.consecutive_refresh_failures` column (migration 023) — worker_health is single-row-per-component and can't track consecutive count. See Dev Agent Record → Completion Notes for the rationale.
  - [x] 2.2 Defined `OAuthStatus(BaseModel)` per AC-3 schema; added `oauth: OAuthStatus` field to `StatusReport`.
  - [x] 2.3 Implemented `_read_oauth(db_path)` reading the single-row `oauth_state` via new `OAUTH_STATE_STATUS_SELECT` query. `access_token_stale_minutes` derived from `access_expires_at`.
  - [x] 2.4 Registered `oauth_t = asyncio.create_task(_read_oauth(db_path))` next to the other section tasks in `assemble_status`.
  - [x] 2.5 Updated `scripts/mailbot.py:_render_status_report` to print an OAUTH section flagged on `oauth_refresh_failing`.
  - [x] 2.6 `exchange_and_persist` now writes `worker_health[oauth_refresh]` heartbeats on every success/failure path (via `mailbot_api.observability.scheduler.upsert_worker_health`) AND bumps `oauth_state.consecutive_refresh_failures` atomically on failure via new `OAUTH_STATE_BUMP_REFRESH_FAILURE` query. Success path resets the counter via the existing UPDATE.
- [x] **Task 3: AC-4 decision + implementation (auto-pause)** — Chose **Path B (router auto-pause via Story 2-9 plumbing)** with the scope-widening flagged in the original story: added a single-line pause-state check at the top of `mailbot_api/actions/drainer.py:run_tick`. Rationale: reuses existing pause/resume machinery, avoids a second cross-module dependency from drainer → oauth_state, and the same check protects against ANY future automatic pause (not just oauth) for free. The check sits before `_claim_row` so paused rows stay `pending` — no stuck-in-draining state.
- [x] **Task 4: AC-5 cadence audit** — Conclusion: cadence is fine, NO change required. The `oauth_token_refresh` interval task at `worker.py:354` (240s) only refreshes the in-memory access-token cache; the real refresh-token EXCHANGE fires from `sync.sync_worker.run_once` every ~1h (when `access_token_is_valid()` flips False against the 1h MS access-token lifetime). That cadence sits well inside the consumer-tier sliding 24h-if-unused window AND the 90d-if-rotated ceiling. F23 was a visibility gap, not a cadence gap. Documented in `docs/auth-recovery.md § Refresh cadence (audit, Story 6-15 AC-5)`.
- [x] **Task 5: Update `docs/auth-recovery.md` (AC-1)** — Replaced the prior 5-step recovery sequence (mint → `vi .env` → DELETE row → restart container → verify) with a 3-step flow (mint → run `scripts/refresh_outlook_oauth.py` → verify via `mailbot status`). Added the new OAUTH alarm fields to the Symptoms section and a Refresh-cadence audit subsection.
- [x] **Task 6: Regression tests (AC-6)** — 7 tests added in `tests/integration/test_oauth_refresh_alarm.py` covering all four AC-6.1/.2/.3/.4 cases plus counter-tests for below-threshold + foreign-pause + happy-path drainer. All 4 gates green: ruff clean, mypy --strict clean (123 files), boundary clean, pytest 1067 + 2 skipped (+9 net vs baseline 1058+2).
- [x] **Task 7: MANDATORY-CR pass (AC-7)** — COMPLETED 2026-06-05 via bmad-code-review (Blind Hunter + Edge Case Hunter + Acceptance Auditor). 18 findings triaged (2 decision-needed both resolved, 16 patches all applied, 8 dismissed as noise). New helpers introduced: `PauseState.try_pause_if_unpaused` / `try_resume_if_reason` (atomic check-and-mutate to fix CR-1 + CR-10), `execute_write_returning` connection helper + `OAUTH_STATE_BUMP_REFRESH_FAILURE ... RETURNING` (CR-2 race-safe threshold-crossing), `OAUTH_STATE_DELETE` query + fresh-deploy rollback in `scripts/refresh_outlook_oauth.py` (CR-7), drainer mid-tick recheck + `_release_claim` helper (CR-3), realpath unlink (CR-6), narrowed exit-code surface 4=httpx-only + 5=sqlite (CR-5). 3 new tests added (CR-9 pre-pause-clobber, CR-15 transport-error bump, CR-16 fresh-deploy rollback). All 4 gates green: ruff clean, mypy --strict clean (128 files, +5 vs Story 6-15 dev-complete baseline of 123), boundary clean, pytest 1070 + 2 skipped (+3 net vs dev-complete baseline of 1067+2). Story 6-15 ready for done-flip.

### Review Findings (2026-06-05 — bmad-code-review, Blind Hunter + Edge Case Hunter + Acceptance Auditor)

**Triage:** 2 `decision-needed`, 16 `patch`, 0 `defer`, 8 dismissed as noise. Severity rolls up to **0 critical, 2 high, 11 medium, 5 low**.

- [x] `[Review][Decision]` CR-D1 (HIGH) Drainer pause-check gates ALL tiers — **RESOLVED 2026-06-05: Adam-decided option (a) accept scope-widening.** Matches the rationale Adam wrote into Task 3 of this story ("same check protects against ANY future automatic pause for free"). Tier-1 backlog accumulation during outage is the documented trade. No code change. Edge-hunter finding dismissed as already-decided.
- [x] `[Review][Decision]` CR-D2 (MEDIUM) AC-5 cadence audit fails literal MUST clause — **RESOLVED 2026-06-05: option (c) both.** `docs/auth-recovery.md § Refresh cadence § Evidence (AC-5 MUST clause)` now contains (1) a `last_rotated_at` delta SQL snippet + reference output captured 2026-06-05, AND (2) two Microsoft Learn URLs with cite-date (refresh tokens + configurable token lifetimes). AC-5 MUST clause now satisfied twice over. See [docs/auth-recovery.md:205-244](../../docs/auth-recovery.md#L205-L244).

- [x] `[Review][Patch]` CR-1 (HIGH) Auto-pause clobbers operator-initiated pause [mailbot_api/sync/oauth.py:472-494] — `_record_refresh_failure` unconditionally calls `get_pause_state().pause(db_path, reason=_OAUTH_PAUSE_REASON)` on the K-th failure with no "already paused?" check. `PauseState.pause` overwrites `_paused`/`_reason`. If operator paused for `reason="manual_hold"` BEFORE the K-th failure, the operator's reason is silently rewritten; the next successful refresh then auto-resumes via `_record_refresh_success` (which only checks `reason == _OAUTH_PAUSE_REASON`), silently dropping the operator's intentional pause. Fix: before calling `pause()`, check `if pause_state.is_paused(): _logger.warning(...); return` — only auto-pause when not already paused. Source: edge+blind.
- [x] `[Review][Patch]` CR-2 (MEDIUM) Threshold-crossing decision uses stale in-memory snapshot [mailbot_api/sync/oauth.py:472-494] — `new_failures = prior_failures + 1` is computed from `state.consecutive_refresh_failures` captured at function entry, not from the returned counter of the `OAUTH_STATE_BUMP_REFRESH_FAILURE` UPDATE. Two concurrent failure paths each snapshot `prior_failures=K-1`, both bump (DB → K+1), and BOTH evaluate `prior<K AND new>=K`, double-firing pause. Or with K-2 snapshot, both calls miss the threshold even though DB reaches K. Fix: have the BUMP query `RETURNING consecutive_refresh_failures` (or re-SELECT inside the same transaction) and use that as `new_failures`. Source: edge+blind.
- [x] `[Review][Patch]` CR-3 (MEDIUM) Mid-tick pause doesn't abort already-claimed rows [mailbot_api/actions/drainer.py:run_tick] — Pause-check sits once at top of `run_tick` before `_claim_row`. Long ticks that already claimed `batch_size` rows continue dispatching all of them on Graph after pause flips mid-iteration; one batch of `budget_consumed=1` still burns. Fix: re-check `get_pause_state().is_paused()` inside the per-row loop before each dispatch attempt (or at minimum before each Tier-3 Graph call). Source: edge.
- [x] `[Review][Patch]` CR-4 (MEDIUM) argparse mutually-exclusive `required=True` + `nargs="?"` positional fails to fail-fast [scripts/refresh_outlook_oauth.py:169-180] — Running `python scripts/refresh_outlook_oauth.py` with neither `-` nor `--from-file` parses successfully (positional defaults to None), falls through to `_read_token_from_stdin()`, hangs forever on a TTY. argparse bpo-#15112. Fix: drop the mutually-exclusive-group + positional pattern; check explicitly after parsing — `if not args.from_file and not args.read_stdin: parser.error("--from-file or - is required")`. Source: edge+blind.
- [x] `[Review][Patch]` CR-5 (MEDIUM) Bare `except Exception` mislabels DB-lock/programming errors as transport [scripts/refresh_outlook_oauth.py:892-901] — The `except Exception` in `main()` unconditionally renders `"FATAL: transport error: {type}"` and returns exit code 4. `sqlite3.OperationalError` (DB locked), `ImportError`, attribute errors all collapse to transport. Operator misdiagnoses. Fix: narrow the catch to `httpx.RequestError`/`httpx.HTTPStatusError` for exit 4; let other exceptions either propagate or be classified under a generic exit 1. Source: edge+blind.
- [x] `[Review][Patch]` CR-6 (MEDIUM) `--unlink-after-read` removes symlink, not target [scripts/refresh_outlook_oauth.py:231-239] — `os.unlink(args.from_file)` on a symlink unlinks the LINK; the actual token file persists at the canonical path. Fix: `os.unlink(os.path.realpath(args.from_file))` (and optionally also unlink the link). Document the resolved path in the success log if realpath != arg. Source: edge.
- [x] `[Review][Patch]` CR-7 (MEDIUM) Failed re-auth contaminates DB on fresh deploy [scripts/refresh_outlook_oauth.py:111-120] — On `existing is None`, script INSERTs `(provider, new_refresh_token, rotation_count=0)` BEFORE `exchange_and_persist`. If the new token is `invalid_grant`, the bad token is now persisted; subsequent worker calls read it and fail. Fix: wrap INSERT + `exchange_and_persist` in a transaction and roll back on `GraphAuthError`, OR call `exchange_and_persist` first against an in-memory `OAuthState` and only INSERT after the exchange succeeds. Source: edge.
- [x] `[Review][Patch]` CR-8 (MEDIUM) Status reader crashes pre-migration (early-boot race) [mailbot_api/observability/status.py:_read_oauth] — `OAUTH_STATE_STATUS_SELECT` references `consecutive_refresh_failures`. If a healthcheck hits `/admin/status` BEFORE `apply_pending_migrations` completes in lifespan, `sqlite3.OperationalError: no such column` propagates with no try/except. Tests that import `load_oauth_state` without running migrations also crash. Fix: wrap `_read_oauth`'s SELECT in try/except `sqlite3.OperationalError` returning all-zero OAuthStatus on missing-column, OR enforce migration completion before `assemble_status` is registered. Source: edge+blind.
- [x] `[Review][Patch]` CR-9 (MEDIUM) Missing test: pre-pause-clobber scenario [tests/integration/test_oauth_refresh_alarm.py] — `test_auto_resume_skips_when_pause_reason_is_not_ours` covers operator re-pausing AFTER our auto-pause; the mirror case (operator paused FIRST, then K failures) is untested and is the failure mode for CR-1. Add a test that pauses with `reason="manual_hold"`, drives K failures, asserts pause reason stays `"manual_hold"` (CR-1 fix verified) AND that subsequent success does NOT auto-resume. Source: edge.
- [x] `[Review][Patch]` CR-10 (MEDIUM) Auto-resume sequence is three non-atomic calls [mailbot_api/sync/oauth.py:534-540] — `_record_refresh_success` calls `is_paused()` → `reason()` → `resume()` as three separate reads. Between `reason()` and `resume()` an operator can re-pause for a different reason; the resume then clobbers that pause. Fix: collapse to a single atomic check-and-resume helper on `PauseState` — `try_resume_if_reason(expected_reason)` — that holds the internal lock for the duration. Source: blind.
- [x] `[Review][Patch]` CR-11 (LOW) Token-length disclosure in success log [scripts/refresh_outlook_oauth.py:825-830] — `length={len(new_refresh_token)}` is a weak side-channel. Microsoft refresh tokens have predictable length classes; logging it confirms format heuristics. Fix: drop `length=...` from the success line — `presence=True rotation_count_after=<K>` is sufficient. Source: blind.
- [x] `[Review][Patch]` CR-12 (LOW) `error=error_code[:200]` slice is not a sanitizer [mailbot_api/sync/oauth.py:484-489] — Slicing the HTTP-error body's `error_description` to 200 chars is a length cap, not a redactor. If Microsoft ever returns a token fragment in `error_description`, the worker_health row leaks it. Fix: pass the error string through the Story 5-7 redactor primitive (`mailbot_api/observability/redactor.py`) before persisting. Source: blind.
- [x] `[Review][Patch]` CR-13 (LOW) Drainer pause-check double-calls `get_pause_state()` — log `reason` can race to `None` [mailbot_api/actions/drainer.py:415-424] — `if get_pause_state().is_paused(): _logger.info(..., extra={"reason": get_pause_state().reason()})` reads the state twice; if pause clears between calls, the log reports `reason=None` while the function still early-returns. Harmless correctness, misleading log. Fix: snapshot once — `state = get_pause_state(); paused, reason = state.is_paused(), state.reason()`. Source: blind.
- [x] `[Review][Patch]` CR-14 (LOW) `last_rotated_at=None` renders as literal "None" in CLI [scripts/mailbot.py:606] — `f"  last rotated at:   {oauth.get('last_rotated_at')}"` prints "None" for never-rotated. Fix: `{oauth.get('last_rotated_at') or 'never'}`. Source: edge.
- [x] `[Review][Patch]` CR-15 (LOW) No test for `httpx.RequestError` (transport) bump path [tests/integration/test_oauth_refresh_alarm.py] — Only HTTP 400 invalid_grant exercises the counter bump; the `httpx.RequestError` branch (`oauth.py:268-282`) also bumps and is untested. Fix: add a test using `httpx.MockTransport` that raises `httpx.ConnectError` and asserts `consecutive_refresh_failures` increments. Source: edge.
- [x] `[Review][Patch]` CR-16 (LOW) No test for script's `existing is None` INSERT-then-fail leak [tests/integration/test_oauth_refresh_alarm.py] — All current tests pre-seed `oauth_state`; the fresh-deploy INSERT path of CR-7 is untested. Fix: add a test that starts with empty `oauth_state` table, invokes the script with a token the mock-transport will reject as `invalid_grant`, and asserts NO row was persisted (or the bad token was rolled back). Source: edge.

**Dismissed as noise (8):** test patches imported symbol (brittle test, not runtime defect); `bool` is `int` subclass guard (defensive against schema drift, no current defect); K+1/K+10 unbounded counter cosmetic (alarm field correctly `>=K`, counter resets on next success); auditor exit-code-3-not-in-spec (defensible expansion, runbook documents); auditor AC-3 source-of-truth pivot (spec explicitly permitted alternative); auditor AC-6.4 spec text mismatch (Dev Notes corrected the seam; intent fully tested); migration-23-DEFAULT-0-no-backfill-verification (subsumed by CR-8 column-not-exist scenario); drainer-pause-toctou-on-reason (subsumed by CR-13).

## Dev Notes

### Why this story exists

Story 6-6.5 third-pass walk wired the entire send pipeline end-to-end through Graph dispatch — every code seam proven live (`router_calls.id=416` Opus draft_reply $0.0242 717→179 tokens, drainer claimed `pending_actions.id=1`, Outlook adapter POSTed `/me/messages/{id}/reply`). Then it hit HTTP 401 on the real Graph endpoint because the Microsoft refresh token had silently died ~9 hours earlier without anyone noticing. The pipeline log fired `oauth.refresh.failed` every refresher tick (`rotation_count=12`) but it never escalated — `mailbot status` had no field for it, the drainer kept claiming Tier-3 sends and burning `budget_consumed=1` per row.

That operational gap is what this story closes. Per Adam's 2026-06-04 priority decision (epic-6-run-flags.md §F23), F23 BLOCKS Story 6-6.5 Section B CP-A/B live re-walk; Story 6-6.5 stays `ready-for-walk` until this story closes AND Adam re-auths.

### Existing-state read (files this story touches)

#### `mailbot_api/sync/oauth.py` (Story 1-6) — refresh path

- `OAuthState` dataclass mirrors the `oauth_state` row.
- `load_oauth_state(db_path)` reads via `OAUTH_STATE_SELECT`; returns `None` on no-row.
- `seed_oauth_state_from_env(db_path)` reads `OUTLOOK_REFRESH_TOKEN` from `.env` and INSERTs via `OAUTH_STATE_INSERT_SEED` with `rotation_count=0`. Idempotent if row exists.
- `exchange_and_persist(db_path, *, state, transport=None, timeout_seconds=30.0)` is the core seam — POSTs `grant_type=refresh_token` to `_TOKEN_URL_TEMPLATE.format(tenant=tenant_id)`. On non-2xx, fires `event="oauth.refresh.failed"` log with `{status_code, error_code, rotation_count}`, raises `GraphAuthError`. On 2xx, fires `event="oauth.token.rotated"` log with `{persistence, rotation_count, expires_in_s}` and UPSERTs via `OAUTH_STATE_UPDATE_AFTER_EXCHANGE`. **Neither path writes `worker_health`** — that's the AC-3/Task 2.6 gap to close.
- `get_access_token(db_path)` is the high-level helper that the sync worker uses. Returns cached `access_token` if `access_token_is_valid()` (within `_REFRESH_LEEWAY_SECONDS=60` of expiry), otherwise exchanges.

**Must preserve**: the existing log line shape, the `OAUTH_STATE_UPDATE_AFTER_EXCHANGE` query semantics (don't reset `rotation_count` mid-life — only on a fresh seed). The new reauth script is a NEW caller of this same module — same persistence path, same logging, same rotation counter.

#### `mailbot_api/worker.py` (Story 6-6) — access-token cache refresher

The `oauth_token_refresh` interval task at line 354-358 fires every 240s and reads `oauth_state.access_token` into the `_CachedAccessToken` cell that `OutlookGraphWriteAdapter`'s sync `access_token_provider=lambda: token_cache.value` reads on every Graph call. **This task ONLY reads the cached access token — it does NOT trigger `exchange_and_persist`**. The refresh exchange happens inside `mailbot_api/sync/sync_worker.py:run_once` via `get_access_token` on each sync iteration (every `SYNC_INTERVAL_SECONDS=240` from the `sync` task). So the actual MS-side rotation cadence is 4 minutes per sync — and that's what AC-5 needs to audit against the sliding 24h floor.

**Must preserve**: the `_CachedAccessToken` lifecycle; the lambda contract on `OutlookGraphWriteAdapter`. The new alarm logic plugs in below this layer (write worker_health from `exchange_and_persist`); no change to the cache cell or adapter wiring.

#### `mailbot_api/observability/status.py` (Story 6-1) — status assembler

The pattern for adding a section is dead-simple — copy the `_read_sync` shape:

1. Define a `BaseModel` (`OAuthStatus`).
2. Implement `async def _read_oauth(db_path)` returning that model.
3. Add `oauth: OAuthStatus` field to `StatusReport`.
4. Register `oauth_t = asyncio.create_task(_read_oauth(db_path))` in `assemble_status` next to the other tasks; await it in the `StatusReport(...)` constructor (this preserves the per-task concrete-type pattern documented in the assembler docstring at lines 397-411).
5. Boundary check: `observability/` MAY read `db.connection` + `db.queries` directly, but MUST NOT import from `verbs/` (verbs.cost.cost_breakdown is forbidden — see line 240 comment). The new oauth section reads `db.queries` and `db.connection`, same as other sections.

**Must preserve**: the parallel-fan-out pattern (don't add a synchronous path); the `frozen=True` on the BaseModel; the boundary-check rules. The status board's perf budget (<1s on 100k router_calls) shouldn't be threatened — `oauth_state` is a single-row table, the worker_health lookup is at most K=3 rows.

#### `mailbot_api/router/pause.py` (Story 2-9) — pause-state machine

For Path B of AC-4, the API to call is `get_pause_state().pause(db_path, reason="oauth_refresh_failing")` from inside `exchange_and_persist`'s failure path on the K-th consecutive failure. The drainer ALREADY respects pause state via the router's pre-dispatch short-circuit (`mailbot_api/router/router.py:ask_router` checks `is_paused()` and returns a `PROVIDER_ERROR` retryable error). The drainer's reaction to a paused router is: the Graph adapter call would normally succeed at the HTTP boundary (it doesn't go through the router) — BUT the propose-path is gated. Re-check this: the drainer's `_check_tier_2`/`_check_tier_3` paths run grant validation and call the adapter directly; they do NOT consult `get_pause_state()` today. So Path B as stated above wouldn't actually stop drainer dispatch. Need to either:

- Pick Path A (drainer reads pause state OR oauth_refresh_failing helper),
- OR widen Path B's scope to add a pause-check at the top of `mailbot_api/actions/drainer.py:run_loop`.

Either way, the implementation requires a real cross-module touch — recommend documenting the chosen seam in Completion Notes with the cross-story implication.

#### `scripts/mint_refresh_token.py` (Story 1-9) — reference implementation

This is the dev-box-side interactive browser flow that produces a refresh token. Reuse its conventions:

- Token marker block (`===== ... =====`) — though for the reauth script, the token comes FROM stdin, so output is different: emit only the persistence confirmation, never echo the token back.
- `OUTLOOK_CLIENT_ID` / `OUTLOOK_TENANT_ID` / `OUTLOOK_CLIENT_SECRET` (optional) env-var pattern.
- `sanitize(...)` from `mailbot_api.observability.logging` for any error-body rendering.
- Exit-code convention (0 ok / 2 token-endpoint-rejected / 4 transport / 130 aborted).

The new reauth script does NOT need the browser flow, the local HTTP callback server, or the state-CSRF check — those are operator-side (dev box). The reauth script's job is just: "I have a token string from somewhere, persist it into `oauth_state` via the existing exchange path."

#### `docs/auth-recovery.md` (Story 1-7) — existing recovery procedure

Already documents the recovery as: §Step 1 mint on dev box → §Step 2 `vi /opt/mailbot/.env` → §Step 3 `DELETE FROM oauth_state` → §Step 4 `docker compose restart mailbot-api` → §Step 5 verify with `check_graph_auth.py`. This story's AC-1 collapses §Step 2–§Step 4 into the AC-2 CLI invocation. The "Why not auto-fall-back-to-env?" §section stays valid and explains why we need an explicit reauth surface rather than a re-read-env hot path. Update Step 5 to reference the new `oauth_refresh_failing` alarm field as the canonical "is recovery complete?" check.

### Threat model

The reauth CLI/script handles a real OAuth refresh token (= long-lived bearer credential to Microsoft Graph). Per Story 5-7 redaction primitives + Story 4-0 capture rubric:

- The token MUST NOT be passed as a CLI argument (lands in shell history + ps).
- The token MUST NOT be echoed to stdout, even on success.
- The token MUST NOT appear in any log field (the Story 5-7 redactor catches a few patterns, but defense-in-depth = don't log it in the first place).
- The token MUST NOT be persisted anywhere except the `oauth_state` SQLite row (no `.env`, no `/tmp` scratch file).
- Stdin / `--from-file` are the only acceptable input channels. `--from-file` should `os.unlink` the source after read if the operator opts in (`--unlink-after-read` flag).
- Error messages MUST NOT include the token value — `sanitize(...)` covers most cases but think about it explicitly.

CR will look hard at this surface.

### F23 raw details (from epic-6-run-flags.md § Third pass § F23)

- Microsoft `https://login.microsoftonline.com/consumers/oauth2/v2.0/token` endpoint returning `HTTP 400 invalid_request` on every refresh attempt for 9+ hours at walk time.
- `oauth.refresh.failed` log fires every refresher tick; `rotation_count=12` at sample time.
- `oauth_state.access_token` was 40+ minutes stale at walk time; refresher could not get a new one.
- Microsoft consumer-tier refresh tokens have sliding 24h lifetime if unused (or up to 90d if continuously rotated).
- Classification: OPERATIONAL, not code. Adam needs interactive re-auth via the browser flow.

### Cadence-audit reference data (AC-5)

The `oauth_token_refresh` task at `mailbot_api/worker.py:354` ticks every 240s but ONLY reads the cached access token — it does not trigger `exchange_and_persist`. The actual rotation cadence is driven by `mailbot_api/sync/sync_worker.py:run_once` (called every `SYNC_INTERVAL_SECONDS=240`s from the `sync` interval task), which calls `get_access_token` → which only rotates when `access_token_is_valid()` returns False (i.e., when the cached access token expires, typically every ~1h since MS issues 1h access tokens). So under normal operation, the refresh token IS exchanged every ~1h → well inside the 24h sliding floor.

The 9-hour F23 silence happened because something Microsoft-side invalidated the refresh token (revoked / conditional access / inactivity timeout), AND the failures didn't surface anywhere visible. So the AC-5 audit conclusion is likely: "the cadence is fine; the gap was visibility, not frequency." Confirm via SQLite query on `oauth_state.last_rotated_at` deltas.

### Project Structure Notes

- New file: `scripts/refresh_outlook_oauth.py` (sibling to `mint_refresh_token.py`).
- Modified: `mailbot_api/observability/status.py` (+ `OAuthStatus` + `_read_oauth` + `oauth` field on `StatusReport`).
- Modified: `mailbot_api/sync/oauth.py` (write `worker_health[oauth_refresh]` heartbeats from `exchange_and_persist` success/failure paths).
- Modified: `mailbot_api/db/queries.py` (new `WORKER_HEALTH_RECENT_OUTCOMES_FOR_COMPONENT` query).
- Modified: `scripts/mailbot.py` (status CLI rendering: surface `oauth_refresh_failing` row; optionally add `reauth` subcommand if Task 1 chooses that path).
- Modified: `docs/auth-recovery.md` (rewrite recovery sequence).
- Modified: `mailbot_api/actions/drainer.py` OR `mailbot_api/sync/oauth.py` (AC-4, depending on Path A / Path B).
- New tests: `tests/integration/test_oauth_refresh_alarm.py` (AC-6).

No new migrations. The `oauth_state` schema already has every field we need; `worker_health` already supports arbitrary `component` strings (Story 6-6).

### References

- Story file `_bmad-output/implementation-artifacts/epic-6-run-flags.md` § "Story 6-6.5 walk record § Third pass (2026-06-04) § F23 — Microsoft refresh token rejected"
- Story 6-1: `mailbot_api/observability/status.py` (assembler pattern + boundary rules)
- Story 6-6: `mailbot_api/worker.py:_worker_main` (scheduler registration + oauth_token_refresh task at line 354)
- Story 1-6: `mailbot_api/sync/oauth.py` (exchange_and_persist + GraphAuthError)
- Story 1-9: `scripts/mint_refresh_token.py` (dev-box mint flow + token-handling discipline reference)
- Story 1-7: `docs/auth-recovery.md` (current recovery procedure to be updated)
- Story 2-9: `mailbot_api/router/pause.py` (pause state machine for Path B of AC-4)
- Story 4-4: `mailbot_api/actions/drainer.py` (drain loop for Path A of AC-4 or pause-check insertion site for Path B)
- Story 4-5: `mailbot_api/actions/outlook_adapter.py` (consumer of the access token cache)
- Story 4-0: capture/storage rubric for OAuth credentials
- Story 5-7: `mailbot_api/observability/redactor.py` (chat input redactor — defensive secondary scrub if log lines slip)
- Architecture: `_bmad-output/planning-artifacts/architecture.md § OAuth refresh-token rotation (D9)` (lines 415-421) — pins `oauth_state` as runtime source of truth; `.env` is bootstrap-only
- Schema: `mailbot_api/db/migrations/002_oauth_state.sql` (oauth_state table shape)
- DB constants: `mailbot_api/db/queries.py § oauth_state (Story 1-6)` (lines 20-37)
- Graph identity endpoints: `mailbot_api/sync/graph_client.py` — `_TOKEN_URL_TEMPLATE` / `_DEFAULT_SCOPE` / `_REFRESH_LEEWAY_SECONDS` / `GraphAuthError`
- `.env` keys: `OUTLOOK_CLIENT_ID` / `OUTLOOK_CLIENT_SECRET` (optional, public-client recipe omits it) / `OUTLOOK_TENANT_ID` / `OUTLOOK_REFRESH_TOKEN` (bootstrap seed only) / `OUTLOOK_USER_EMAIL`

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (Claude Opus 4.7, 1M context)

### Debug Log References

- `mailbot_api.sync.oauth` log lines: `oauth.refresh.failed` (existing) +
  new `oauth.refresh.auto_paused` / `oauth.refresh.auto_resumed` /
  `oauth.refresh.auto_pause_failed` / `oauth.refresh.auto_resume_failed`.
- `mailbot_api.actions.drainer` new log line: `action.drainer.tick.skipped`
  with `reason` field reflecting the pause-state reason.

### Completion Notes List

**Source-of-truth pivot (Story-spec to implementation drift).** The original
AC-3 sketch in the story file pointed at `worker_health[oauth_refresh]` as
the source of truth for the `consecutive_refresh_failures` count. That
doesn't work: `worker_health` is single-row-per-component with only a
`last_outcome` field — it can't carry a count, and reconstructing the
"consecutive failures since last ok" count from a single-row snapshot is
impossible. The implementation pivots to a new
`oauth_state.consecutive_refresh_failures` column (migration 023):

- single SQL UPDATE on failure (`OAUTH_STATE_BUMP_REFRESH_FAILURE`),
- single SQL UPDATE on success (the existing `OAUTH_STATE_UPDATE_AFTER_EXCHANGE`
  is extended to reset the counter to 0),
- single SQL SELECT on status assembly (`OAUTH_STATE_STATUS_SELECT`).

`worker_health[oauth_refresh]` is still written on every exchange — it gives
the operator a "latest outcome" signal on the same component-axis the rest
of the worker uses, and matches the pattern Story 6-6 established for every
other scheduler task. But the count itself lives on `oauth_state`.

**AC-4 path choice (Path B with scope-widening).** The original AC-4 text
flagged that "Path B as stated wouldn't actually stop drainer dispatch"
because the drainer talks to Graph directly via the adapter and doesn't go
through `ask_router`. Resolution: keep the pause-state plumbing (Path B's
pause/resume mechanics, reusing Story 2-9) AND add a single early-exit at
the top of `drainer.run_tick`. That single line covers the AC-4 intent
fully — if any caller (oauth, future auto-pause logic, the operator) sets
the router to paused, the drainer stops claiming rows. Trade-off accepted:
the drainer now consults the pause state directly (one new import), but
the alternative (drainer reads oauth_state directly) would couple the
drainer to the oauth refresh-token lifecycle, which is conceptually wrong.

**Pause-state singleton initialization.** The `PauseState` object is a
module-level singleton with an in-memory `_paused` flag. Both processes
(api + worker) call `get_pause_state().initialize(db_path)` at startup
(`main.py:188` for the api lifespan, `pipeline.init_pipeline_runtime` for
the worker process — already called from `_worker_main` per Story 6-11).
Auto-pause from `exchange_and_persist` runs in the worker process, sets
both the DB row AND the worker-side in-memory flag — so the drainer's
`is_paused()` check sees the update immediately on the next tick (no DB
re-read required). The API process picks up the change on its next
PAUSE_STATE_SELECT (every `/admin/status` read does this fresh).

**Refresh cadence audit (AC-5).** No cadence change. The `oauth_token_refresh`
interval task (240s) only refreshes the in-memory access-token cache that
the Outlook adapter reads on every Graph dispatch. The actual refresh-token
EXCHANGE happens inside `sync.sync_worker.run_once` which is called every
`SYNC_INTERVAL_SECONDS = 240` (4 min) but only triggers `exchange_and_persist`
when `access_token_is_valid()` returns False — i.e., when the cached MS
access token is within `_REFRESH_LEEWAY_SECONDS = 60` of its 1-hour expiry.
Practical effect: ~1h between exchanges, well inside the sliding 24h-if-unused
window. F23 was a visibility gap; cadence change would not have prevented it.

**Foreign-pause-reason auto-resume guard.** If the operator pauses the
router for an unrelated reason while our refresh exchange is still failing,
then we eventually succeed, the auto-resume MUST NOT clobber the operator's
pause. The success-path helper `_record_refresh_success` checks
`pause_state.reason() == _OAUTH_PAUSE_REASON` before calling `resume(...)`.
Test `test_auto_resume_skips_when_pause_reason_is_not_ours` locks this in.

**Migration numbering.** Next migration was 023 (002 → 022 with 003
historically skipped per the existing repo state; migrations runner is
ordered by file-name sort, not by sequential integer presence). No
backfill — the new column has `DEFAULT 0`, so existing rows on a
production DB get `consecutive_refresh_failures = 0` automatically.

**Gates evidence (Task 6 close):**

- ruff: `All checks passed!` (no output from `-m ruff check` = clean)
- mypy --strict: `Success: no issues found in 123 source files`
- boundary: `scripts/check_boundaries.py` exit 0 with no output (consistent
  with all prior Epic 6 stories — silent-on-success)
- pytest: `1067 passed, 2 skipped, 1 warning in 223.11s` (+9 net vs the
  Story 6-11 baseline of 1058 + 2)
- All 7 new tests in `tests/integration/test_oauth_refresh_alarm.py` pass
  cold (no flake on first run).

### File List

**Added:**

- `mailbot_api/db/migrations/023_oauth_state_consecutive_failures.sql`
- `scripts/refresh_outlook_oauth.py`
- `tests/integration/test_oauth_refresh_alarm.py`

**Modified:**

- `mailbot_api/db/queries.py` — extended `OAUTH_STATE_SELECT` to read the
  new column, extended `OAUTH_STATE_UPDATE_AFTER_EXCHANGE` to reset the
  counter on success, added `OAUTH_STATE_BUMP_REFRESH_FAILURE` +
  `OAUTH_STATE_STATUS_SELECT`.
- `mailbot_api/sync/oauth.py` — `OAuthState` dataclass gains
  `consecutive_refresh_failures: int = 0`, `load_oauth_state` reads it,
  new `_record_refresh_failure` + `_record_refresh_success` helpers wire
  the worker_health heartbeat + auto-pause / auto-resume seam,
  `exchange_and_persist` calls the helpers on every code path. New
  constants: `OAUTH_REFRESH_FAIL_THRESHOLD`, `_OAUTH_PAUSE_REASON`,
  `_OAUTH_WORKER_HEALTH_COMPONENT`.
- `mailbot_api/observability/status.py` — new `OAuthStatus` model + `oauth`
  field on `StatusReport` + `_read_oauth` reader + scheduling in
  `assemble_status`. Module docstring + `__all__` updated.
- `mailbot_api/actions/drainer.py` — early-exit pause-state check at the
  top of `run_tick` (Path B for AC-4); new import from
  `mailbot_api.router.pause`.
- `scripts/mailbot.py` — `_render_status_report` prints the new OAUTH
  section + flags it on `oauth_refresh_failing`. Docstring verdict-rule
  list updated.
- `docs/auth-recovery.md` — Symptoms section gains the new alarm fields;
  prior §Step 2–§Step 4 collapsed into a single VPS-side CLI invocation;
  new §Refresh-cadence (audit) subsection.

### Change Log

- 2026-06-05 — Story 6-15 shipped: F23 closure via
  `scripts/refresh_outlook_oauth.py` + `OAuthStatus` status section + drainer
  pause-check + auth-recovery runbook collapse. All 4 gates green at
  1067 + 2 skipped (+9 net vs Story 6-11 baseline).
