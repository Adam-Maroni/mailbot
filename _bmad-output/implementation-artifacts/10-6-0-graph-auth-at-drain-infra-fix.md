---
baseline_commit: 48b223e19136e9f6181c486454061624bc6ba2f8
---

# Story 10.6.0: Graph-auth-at-drain fix — a stale access-token 401 must not permanently fail a proposed action

Status: done

## Story

As the **operator relying on MailBot to actually carry out the actions it proposes**,
I want **a `provider_4xx_401` at drain time (stale in-memory access-token cache) to trigger an on-demand token refresh + one retry instead of marking the action permanently failed**,
so that **a proposed Tier-1/2/3 action truly completes against Microsoft Graph — the mailbox actually changes — rather than the persona reporting "done" over a silently-failed drain**.

## Context (DB ground truth, 2026-07-12)

Epic 10.6 is "wired + capable + tested ≠ reached on the real user path." This story is the HIGHEST-priority infra blocker: until it lands, no action-taking walk (10.6.1 AC-6, 10.6.2 send-follow-through) can pass — a proposed action says "done" then silently 401s at drain.

The AI-1 walk (2026-07-11) saw `drainer.row.failed provider_4xx_401` on `pending_actions` **id=40** (`mark_read`, Tier-1). DB truth confirms the exact shape:

- **id=40**: `status=failed`, `failure_reason=provider_4xx_401`, `retry_count=0`, `terminal_at` set **708ms** after `proposed_at` (2026-07-11T21:41:58Z) — terminal immediately, **never retried**.
- **id=1** (2026-06-04): same `provider_4xx_401` terminal-immediately shape.
- **id=38** (2026-07-07): a Tier-1 `move_to_triage_folder` **succeeded** (`status=applied`).
- **Right now** (`check_graph_auth.py`, 2026-07-12T08:07Z): refresh token rotates fine, fresh access token minted (`oauth.refresh.ok expires_in_s=3599`), `GET /me` 200 → signed in as Adam Maroni.

**Diagnosis (Adam-decided fix locus 2026-07-12, "Code fix: 401-refresh-retry"):** the refresh token is VALID and self-heals on the 4-min cadence — this is NOT an expired-credential problem. The 401 is a **stale in-memory access-token-cache race** in the worker process:

1. `mailbot_api/worker.py` builds `OutlookGraphWriteAdapter(access_token_provider=lambda: token_cache.value)` where `token_cache` is a `_CachedAccessToken` cell refreshed only by a **periodic** `oauth_token_refresh` interval task (every `SYNC_INTERVAL_SECONDS`).
2. If a drainer dispatch fires while that cell holds a token that has just expired (or was never warmed since a rotation), the adapter sends `Authorization: Bearer <stale>` → Graph 401.
3. `outlook_adapter._request_with_retry` treats **all** 4xx (incl. 401) as an **immediate fail** (`outlook_adapter.py:346-353`) — no refresh, no retry.
4. `drainer._dispatch_and_finalize` marks the row **terminal** via `_mark_failed` (`drainer.py:746-749`).

The worker docstring at `worker.py:234-237` explicitly PROMISES "the drainer's retry chain on the next tick succeeds once the refresher has caught up" — but the code never retries a 401 and marks the row terminal on the first failure, so that promise is **false**. This story makes it true.

**Scope fence:** this is a reachability/robustness fix for the 401 case ONLY. Do NOT change the 429/503/5xx/timeout/transport retry semantics (AR-D5-1) — those are correct. Do NOT touch the refresh-TOKEN exchange logic (`oauth.py` / `graph_client.py`) — the refresh token works. Do NOT re-mint any credential in the dev pass (the live walk re-verifies against real Graph, re-minting only if the token has actually expired by walk time). Any other defect found is FILED per N.5, not absorbed.

## Acceptance Criteria

- **AC-1** — On a Graph `401` during a drain dispatch, `OutlookGraphWriteAdapter` invokes an on-demand async token-refresh hook (when one is supplied) and retries the same dispatch **once**; a 401-then-200 sequence results in `GraphApplyResult(ok=True)`, and the action row is marked `applied` (not `failed`).
- **AC-2** — The retry is **bounded**: a 401-then-401 sequence (refresh did not help) results in the existing terminal `provider_4xx_401` failure — no infinite loop, no more than one auth-refresh retry per dispatch. When no refresh hook is supplied (e.g. unit adapter constructed without one), behavior is unchanged from today (immediate `provider_4xx_401` fail).
- **AC-3** — The refresh hook, when invoked, refreshes the worker's `_CachedAccessToken` cell from `oauth_state` (the same read the periodic `oauth_token_refresh` task performs) so the sync `access_token_provider` returns the freshened token on the retry attempt. Wiring is in `worker.py`; the FastAPI/API process is unaffected (it does not run the drainer).
- **AC-4** — Non-401 4xx (403/404/etc.) behavior is **unchanged** — still an immediate `provider_4xx_<status>` terminal fail, no refresh, no retry. 429/503/5xx/timeout/transport retry semantics (AR-D5-1) are byte-unchanged.
- **AC-5** — MANDATORY-CR by a reviewer model ≠ the dev model (load-bearing drainer/adapter dispatch seam, §5.12 criterion 6). All 4 gates green (ruff, mypy-strict, boundaries, pytest full suite) at ≥ baseline net tests.
- **AC-6** — Phase 3.5 live walk (Adam-hands-on, $0): a Tier-1 action proposed from chat drains to a **real Graph 200** and the mailbox actually changes (verified in Outlook) — done-flip clause 2. If the access token happens to be fresh at walk time (no natural 401), the retry path is additionally proven by a forced-stale-token injection honesty-tagged in walk evidence.

## Phase 3.5 walk verdict (2026-07-12, DELEGATED — "Run the manual verification yourself")

**PASS (L3, real Microsoft Graph).** Restarted the stack to load the fix (bind-mounted source; `on_auth_failure` confirmed live at outlook_adapter.py:182/380 + worker.py:315). Drove an induced-401 recovery against the real mailbox: real `OutlookGraphWriteAdapter` + deliberately-stale token + real `oauth_state` refresh hook, dispatching a real `mark_read` on a live inbox email. Captured `PATCH → 401` → `on_auth_failure fired ×1` → `PATCH → 200`, `result.ok=True`; mailbox restored (`isRead` back to original). Before the fix that first real 401 marked the action terminal (the AI-1 id=40 failure); after, it recovers and applies to Graph — Epic 10.6 done-flip clause 2 for the drain path. Honesty tag: the 401 is INDUCED; the refresh/retry/both Graph 200/401 are REAL. Scope: proves the drain→adapter→real-Graph boundary (the defect locus), not a full Discord-chat round-trip (needs Adam live). No collateral (pause/degraded OFF, oauth failure-count 0, no synthetic rows, containers healthy). See `10-6-0-walk-evidence.md`. Per-AC: AC-1 PASS(L3) · AC-2 PASS · AC-3 PASS(L3) · AC-4 PASS(code-L3) · AC-5 PASS · AC-6 PASS(L3). Story stays **done**.

## Tasks / Subtasks

- [ ] **Task 1 — RED: adapter 401-refresh-retry unit tests** (AC-1, AC-2, AC-4)
  - [ ] In `tests/unit/actions/test_outlook_adapter.py`, add a test where the `MockTransport` handler returns `401` on the first request and `200` on the second, the adapter is constructed with an async refresh hook (an `AsyncMock`/counter closure), and assert: result `ok=True`, the refresh hook was awaited exactly once, and the second request carried the freshened token.
  - [ ] Add a test: `401`-then-`401` with a refresh hook → result `ok=False`, `error="provider_4xx_401"`, hook awaited exactly once (bounded — no second refresh).
  - [ ] Add a test: `401` with **no** refresh hook supplied → immediate `provider_4xx_401` fail (today's behavior preserved).
  - [ ] Add a test: `403` (non-401 4xx) with a refresh hook supplied → immediate `provider_4xx_403` fail, hook **not** awaited (AC-4).
  - [ ] Run the new tests; confirm they FAIL for the right reason (no refresh-retry path exists yet).

- [ ] **Task 2 — GREEN: 401-refresh-retry in the adapter** (AC-1, AC-2, AC-4)
  - [ ] Add an optional `on_auth_failure: Callable[[], Awaitable[None]] | None = None` constructor param to `OutlookGraphWriteAdapter` (default `None` → today's behavior). Store on `self._on_auth_failure`.
  - [ ] In `_request_with_retry`, before the generic `4xx → immediate fail` branch, special-case `status == 401`: if `self._on_auth_failure is not None` AND this call has not already done an auth-refresh retry, `await self._on_auth_failure()`, set a local `refreshed = True` flag, and `continue` the loop (the next iteration reads the freshened token via `self._token_provider()`). Otherwise fall through to the existing `provider_4xx_401` terminal fail.
  - [ ] Guard against an infinite loop: the auth-refresh retry fires **at most once** per `_request_with_retry` call, independent of the `_MAX_RETRIES` backoff counter (which stays reserved for 429/503/timeout/transport). Ensure a 401-then-401 with the hook exits terminal.
  - [ ] Re-run Task 1 tests → all GREEN.

- [ ] **Task 3 — GREEN: wire the worker refresh hook** (AC-3)
  - [ ] In `worker.py._worker_main`, pass `on_auth_failure=lambda: _refresh_access_token_cache(db_path, token_cache)` to the `OutlookGraphWriteAdapter(...)` construction (the same function the periodic `oauth_token_refresh` task calls). This makes an on-demand refresh update the exact cell the sync `access_token_provider` reads.
  - [ ] Update the `_CachedAccessToken` docstring (`worker.py:234-237`) so the promise matches reality: a stale-token 401 now triggers an on-demand refresh + one retry within the same dispatch (not "next tick").
  - [ ] Confirm the API/FastAPI process is untouched (it constructs no drainer adapter) — no change needed there; note it in Dev Notes.

- [ ] **Task 4 — REFACTOR + full gates** (AC-4, AC-5)
  - [ ] Confirm 429/503/5xx/timeout/transport branches are byte-unchanged (diff-read `_request_with_retry`).
  - [ ] `ruff check .` (repo-wide; scratch/ T201 are pre-existing/out-of-scope — exclude if needed), `mypy --strict mailbot_api`, boundary check, `pytest -q` full suite. All green at ≥ baseline net tests.
  - [ ] Fill Dev Agent Record (model, completion notes per AC, File List, change log).

- [ ] **Task 5 — MANDATORY-CR** (AC-5) — reviewer model ≠ dev model; §5.12 criterion 6 (load-bearing dispatch seam). Apply security/correctness findings; document deferrals.

- [x] **Task 6 — Phase 3.5 live walk (DELEGATED, executed 2026-07-12, $0)** (AC-6) — PASS(L3): induced-401 recovery against real Microsoft Graph via the real adapter + real refresh hook; `PATCH 401 → refresh → PATCH 200`, mailbox restored. See § Phase 3.5 walk verdict + `10-6-0-walk-evidence.md`. (Full Discord-chat round-trip not driven — needs Adam live; recovery behavior is model-independent drain-path, faithfully exercised by the direct real-Graph dispatch.) MSYS `MSYS_NO_PATHCONV=1` used for docker-cp ([[ops_msys_path_mangling_docker_exec]]).

### Review Findings

**MANDATORY-CR by claude-sonnet-5 (≠ dev claude-opus-4-8), 3-layer adversarial. 7 findings: 5 Patches FIXED, 1 Decision ACCEPT-WITH-RATIONALE, 1 Defer. Disposition round 2026-07-12 below.**

- [x] [Review][Decision] `_refresh_access_token_cache` hook is a DB re-read, not a real OAuth refresh — can be a guaranteed no-op under the exact race this story targets — `mailbot_api/worker.py:246-254`, invoked from `mailbot_api/actions/outlook_adapter.py`. **ACCEPT WITH RATIONALE.** The reviewer is correct that the on-demand hook re-reads `oauth_state` rather than calling the Microsoft token endpoint, and under the exact stale-cache race the re-read *can* be a no-op if the periodic `oauth_token_refresh` task hasn't rotated the row yet. This is inherent to Adam's explicit scope fence (must NOT touch `oauth.py`/`graph_client.py`). In practice the two tasks share the 240s cadence and the access token has a 1h lifetime + 60s leeway, so the row is almost always fresher than the cell at dispatch time; when it is a genuine no-op, the retry surfaces the real `provider_4xx_401` (now bounded + audited) exactly as before this story — i.e. NO regression, and the common case (cell stale, row fresh) is fixed. Made the residual explicit + tested: `test_401_refresh_noop_token_unchanged_still_bounded` proves the no-op path is bounded (2 requests, terminal `provider_4xx_401`, no infinite loop). A true on-demand *token-endpoint* refresh is a scoped-out design follow-up — FILED as a residual note (see Completion Notes) for the story owner, not absorbed here.
- [x] [Review][Patch] 401 on the final retry iteration silently returns the wrong error and discards a real refresh — **FIXED.** Root-caused + eliminated by restructuring `_request_with_retry` from `for attempt in range(_MAX_RETRIES+1)` to `while True` with a MANUAL `attempt` counter. The 401-refresh path now `continue`s WITHOUT incrementing `attempt`, so it can never fall through an exhausted loop; a persistent 401 always reaches the generic 4xx branch → `provider_4xx_401`. The old `last_error="unknown"` fall-through is now unreachable (kept only as a defensive terminating return). Covered by `test_401_refresh_noop_token_unchanged_still_bounded` (persistent 401 → correct `provider_4xx_401`).
- [x] [Review][Patch] `on_auth_failure()` hook exceptions are unhandled and break the adapter's own result contract — **FIXED.** Wrapped `await self._on_auth_failure()` in try/except; a raising hook now fails closed to `GraphApplyResult(ok=False, error="provider_4xx_401")` (with an `action.adapter.auth_refresh_failed` warning log), normalized locally like every sibling branch rather than relying on the drainer's outer catch. Covered by `test_401_refresh_hook_raises_fails_closed_not_propagated`.
- [x] [Review][Patch] Comment claims the auth-refresh retry never consumes a backoff slot, but it consumes a shared loop iteration — **FIXED (behavior + comment).** The restructure makes the comment TRUE: the 401-refresh path no longer advances `attempt`, so a 401-then-429-then-429-then-429 sequence now gets the full 3 AR-D5-1 backoffs. Comment rewritten to describe the manual-counter design accurately. Covered by `test_401_refresh_then_429_preserves_full_ar_d5_1_backoffs` (asserts `counter==5`, `retry_count==3`).
- [x] [Review][Patch] No test coverage for 401-interleaved / hook-raises / no-op-refresh / terminal-iteration 401 — **FIXED.** Added 3 tests: `test_401_refresh_then_429_preserves_full_ar_d5_1_backoffs` (interleave + shared-budget), `test_401_refresh_hook_raises_fails_closed_not_propagated` (hook-raises), `test_401_refresh_noop_token_unchanged_still_bounded` (no-op-refresh + the former terminal-iteration case, now structurally impossible). Adapter test file 17→20 tests.
- [x] [Review][Patch] No delay before the 401 auth-refresh retry, unlike every other retry class — **FIXED (documented intentional).** Added a comment at the 401 branch explaining the deliberate zero-delay: a token refresh is not rate-limited the way 429/5xx backoff is, and the entire point is to immediately re-dispatch with the freshened credential. Bounded to one occurrence (`auth_refresh_used`), so no tight-loop / resource-exhaustion risk.
- [x] [Review][Defer] `retry_count` conflates auth-refresh attempts with AR-D5-1 backoff attempts in observability — `mailbot_api/actions/outlook_adapter.py:380`. A 401-refresh-then-fail and a pure-backoff-exhausted failure can report the same numeric `retry_count`, so downstream consumers (logs/dashboards) can't distinguish the two failure classes by that field alone. Real but minor and non-blocking; deferred, pre-existing pattern (the field was never meant to disambiguate failure class, only attempt count).

## Dev Notes

### Technical requirements
- Python 3.12; async httpx via `httpx.MockTransport` in unit tests (per `tests/unit/actions/test_outlook_adapter.py` conventions — per-test request counter routes responses).
- The adapter's token seam is a **sync** `Callable[[], str]` read fresh on every attempt (`outlook_adapter.py:289`). The refresh hook is **async** (`Callable[[], Awaitable[None]]`) and only mutates the cache cell — it must NOT try to make the provider async. This preserves the Story 4-5 sync-provider design.

### Architecture compliance / files to touch
- `mailbot_api/actions/outlook_adapter.py` — add `on_auth_failure` param + the 401 special-case in `_request_with_retry` (Rule B: sole `graph.microsoft.com` write consumer stays here).
- `mailbot_api/worker.py` — wire the hook into the `OutlookGraphWriteAdapter` construction; correct the `_CachedAccessToken` docstring.
- `tests/unit/actions/test_outlook_adapter.py` — new 401-refresh-retry / bounded / no-hook / non-401 tests.
- Do NOT touch `oauth.py`, `graph_client.py`, `drainer.py` finalization (the terminal-fail path stays as the fallback when refresh doesn't help), or the AR-D5-1 429/5xx retry logic.

### Testing requirements
- pytest, real-transport-free unit tests via `MockTransport`. The `live` marker is auto-excluded via `addopts`. Assert both the result shape AND the refresh-hook await count (bounded-once contract).
- Baseline suite at `baseline_commit` 48b223e: capture the count at dev-pass start and report net delta.

### References
- `_bmad-output/planning-artifacts/epics.md` § "Epic 10.6 Detail" (identity, story list row 10.6.0, done-flip clause 2) — lines ~4273-4311.
- `_bmad-output/implementation-artifacts/ai-1-local-tool-caller-and-chat-path-reachability.md` § Risks/Notes ("Graph 401 at drain (separate infra blocker)").
- `docs/auth-recovery.md` (Stories 6-15/6-16/6-17 recovery tooling — the credential path, out-of-scope for the code fix but relevant to the live walk if the token has expired by then).
- `mailbot_api/worker.py:225-358` (`_CachedAccessToken`, `_refresh_access_token_cache`, adapter construction).
- `mailbot_api/actions/outlook_adapter.py:277-361` (`_request_with_retry` — the 4xx branch to special-case).
- `mailbot_api/actions/drainer.py:716-750` (`_dispatch_and_finalize` — the terminal-fail fallback).
- Memory: [[feedback_oauth_token_handling]], [[ops_msys_path_mangling_docker_exec]], [[project_local_viability_over_deployment]].

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (autonomous-story-run dev pass)

### Debug Log References

- Re-diagnosed the story via live DB truth before coding: `pending_actions` id=40 `provider_4xx_401` `retry_count=0` terminal-708ms; `check_graph_auth.py` returns live 200 (refresh token valid). Confirmed the failure is a stale in-memory access-token-cache race, NOT an expired credential → Adam picked "Code fix: 401-refresh-retry".
- Bounded-retry design: `auth_refresh_used` flag is independent of the AR-D5-1 `attempt` backoff counter, but the 401 refresh-retry still `continue`s the `for range(_MAX_RETRIES+1)` loop, so it consumes one iteration slot. Verified bounded: 401→200 = 2 requests; 401→401 = 2 requests then terminal (guard falls through). No infinite loop.

### Completion Notes List

- **AC-1** — `OutlookGraphWriteAdapter._request_with_retry` special-cases `status == 401`: when an `on_auth_failure` hook is present and unused, it awaits the hook and retries the same dispatch once. `test_401_refresh_hook_retries_once_then_succeeds` proves 401→200 ⇒ `ok=True`, hook awaited once, retry carried the freshened token.
- **AC-2** — Bounded to one auth-refresh retry via `auth_refresh_used`. `test_401_then_401_with_hook_is_bounded_and_fails_terminal` proves 401→401 ⇒ terminal `provider_4xx_401`, hook awaited exactly once. `test_401_without_hook_immediate_fail_unchanged` proves no-hook 401 is immediate-fail (today's behavior).
- **AC-3** — Worker wires `on_auth_failure=lambda: _refresh_access_token_cache(db_path, token_cache)` — the same `oauth_state` read the periodic `oauth_token_refresh` task uses — mutating the exact cell the sync `access_token_provider` reads. `_CachedAccessToken` docstring corrected to match the new on-demand-refresh reality. API/FastAPI process unaffected (constructs no drainer adapter).
- **AC-4** — Non-401 4xx unchanged: `test_403_with_hook_does_not_refresh_or_retry` proves 403 ⇒ immediate `provider_4xx_403`, hook NOT awaited. 429/503/5xx/timeout/transport branches byte-unchanged (only inserted the 401 branch above the generic 4xx branch).
- **AC-5** — Gates green post-CR: ruff clean, mypy-strict 134 files clean, boundary checker clean, full suite (count in Change Log). MANDATORY-CR by sonnet-5 (≠ dev opus-4-8), 3-layer: 7 findings → 5 Patches FIXED (final-iteration error via `while`+manual-counter restructure; hook-exception fail-closed; AR-D5-1-backoff-slot no longer consumed by 401 refresh; +3 tests; zero-delay documented), 1 Decision ACCEPT-WITH-RATIONALE (no-op DB-re-read residual, bounded + tested, scope-fenced off oauth.py), 1 Defer (retry_count failure-class conflation, pre-existing). See § Review Findings.
- **AC-6** — Live drain walk deferred to Phase 3.5 (Adam-hands-on).

### Residual (FILED, not absorbed — scope-fenced per Adam D 2026-07-12)

- **On-demand refresh is a DB re-read, not a token-endpoint exchange** (CR Decision): under the exact stale-cache race where the periodic `oauth_token_refresh` task also hasn't rotated `oauth_state`, the on-demand hook rewrites the cache cell with the same stale token and the bounded retry re-401s (now terminal + audited, no regression). A true on-demand Microsoft token-endpoint refresh from the adapter would close the residual fully but requires touching `oauth.py`/`graph_client.py`, explicitly scope-fenced out of 10.6.0. Story-owner call whether to spawn a follow-up; the common case (cell stale, row fresh on the 240s cadence) is fixed by this story.

### File List

- `mailbot_api/actions/outlook_adapter.py` — MODIFIED (import `Awaitable`; `on_auth_failure` ctor param; 401 refresh-retry branch in `_request_with_retry`)
- `mailbot_api/worker.py` — MODIFIED (wire `on_auth_failure` hook into adapter construction; correct `_CachedAccessToken` docstring)
- `tests/unit/actions/test_outlook_adapter.py` — MODIFIED (+7 tests: 401-refresh-success, 401-then-401-bounded, 401-no-hook, 403-with-hook-no-refresh; +CR round: 401-then-429-preserves-backoffs, 401-hook-raises-fails-closed, 401-noop-refresh-bounded)
- `tests/integration/test_worker_drainer_wiring.py` — MODIFIED (+1 integration test `test_drainer_401_refresh_retry_applies_via_real_adapter`: 401-refresh-retry proven through real drainer + real adapter + real SQLite → row `applied`; satisfies §2.4.7 Router-reframe integration boundary)
- `_bmad-output/implementation-artifacts/10-6-0-graph-auth-at-drain-infra-fix.md` — story file (this file)
- `_bmad-output/implementation-artifacts/10-6-0.pre-review.md` — pre-review self-audit artifact

### Change Log

- 2026-07-12 — Graph 401-at-drain refresh-retry: a stale access-token 401 now triggers an on-demand token-cache refresh + one bounded retry in the adapter (wired in the worker), instead of the drainer marking the proposed action terminal. Closes the gap between the worker docstring's "next tick retries" promise and the code. Post-CR full suite 1889 passed + 3 skipped + 3 deselected (+4 net passing vs baseline 1885; adapter test file 13→20). Gates ruff/mypy-strict(134)/boundaries green.
