---
baseline_commit: b1784a5
---

# Story 6.16: OAuth public-client secret-leak startup validation — F25 closure

Status: done

> **Filed 2026-06-05** during Story 6-6.5 fourth-pass walk, after `scripts/refresh_outlook_oauth.py` failed with `AADSTS90023: Public clients can't send a client secret` against a freshly-minted refresh token. The bug had been silently failing every refresh exchange for the lifetime of the current `.env`, which is the **actual root cause of the original F23** ("Microsoft refresh token rejected") — F23 was misdiagnosed as operational when it was code all along. See `epic-6-run-flags.md § F25` for the full finding.

## Story

As MailBot operator,
I want the system to fail-loud at startup (or at first refresh attempt) when `OUTLOOK_CLIENT_SECRET` is set in `.env` but the Entra app is registered as a public client,
So that no future deploy can silently mint stale access tokens for 9+ hours under the same misconfiguration that caused F23.

## Acceptance Criteria

**AC-1 — Detection at first refresh attempt (Option A: probe + loud log).**
Given an Entra app registered as a public client AND `OUTLOOK_CLIENT_SECRET` present in `.env`,
When the worker's first `exchange_and_persist` call fires and Microsoft returns `HTTP 400 invalid_request` with `error_description` containing `AADSTS90023`,
Then `mailbot_api/sync/oauth.py` MUST log a NEW `level=error` event `oauth.refresh.public_client_secret_misconfig` with a message pointing operator at `docs/entra-app-registration.md:235`,
And the existing `oauth.refresh.failed` log line MUST continue firing (defense-in-depth — separate event for the specific class, parallel to existing visibility).

**AC-2 — Explicit operator gate (Option B: `OUTLOOK_PUBLIC_CLIENT` env flag).**
Given `OUTLOOK_PUBLIC_CLIENT=true` is set in `.env`,
When `_exchange_refresh_token` (and the equivalent helper in `graph_client.py`) builds the token-exchange form,
Then `client_secret` MUST NOT be appended to the form regardless of whether `OUTLOOK_CLIENT_SECRET` is set,
And a startup-time log line `event="oauth.config.public_client_mode"` MUST fire confirming the gate is active.

**AC-3 — Both gates land (Option C, recommended).**
AC-1 catches the misconfiguration that exists in production TODAY (no migration needed for existing deployments — they just start seeing the loud log on next refresh). AC-2 provides explicit operator control for future deployments + a clean migration path away from "comment out the env var to silence the bug."

**AC-4 — Documentation update.**
Given AC-1 and/or AC-2 land,
When the docs are updated,
Then [docs/entra-app-registration.md](../../docs/entra-app-registration.md) line 235 (the current AADSTS90023 troubleshooting row) MUST be updated to reference the new alarm event AND the new `OUTLOOK_PUBLIC_CLIENT` env var (Option B). The "Recommended public client setup" subsection MUST recommend setting `OUTLOOK_PUBLIC_CLIENT=true` AND omitting `OUTLOOK_CLIENT_SECRET` (belt-and-suspenders).

**AC-5 — Regression tests.**
Three tests minimum:
1. `test_public_client_secret_misconfig_logs_loud_error` — given an Entra-public-client `.env` + an `httpx.MockTransport` that returns the AADSTS90023 body, assert the new `oauth.refresh.public_client_secret_misconfig` event fires.
2. `test_public_client_env_flag_suppresses_secret_in_form` — given `OUTLOOK_PUBLIC_CLIENT=true` + `OUTLOOK_CLIENT_SECRET=<value>`, assert the outgoing token-exchange form does NOT contain `client_secret`.
3. `test_confidential_client_default_still_sends_secret` — given `OUTLOOK_CLIENT_SECRET=<value>` + `OUTLOOK_PUBLIC_CLIENT` unset, assert the form DOES contain `client_secret` (regression guard for confidential-client deployments).

**AC-6 — MANDATORY-CR per §5.12.**
Two criteria fire: (a) external-credential surface; (b) cross-story load-bearing (Story 1-6 sync.oauth + Story 1-7 auth-recovery doc + Story 6-15 reauth script + Story 4-0 capture rubric). Minimum one CR pass before done-flip.

## Tasks / Subtasks (high-level, awaits context-engineering)

- [x] Task 1 — Option C shipped (both AC-1 detection-event AND AC-2 env-gate). Rationale: F25 has both an installed-base of stale-secret deployments TODAY (AC-1 catches them loudly on next refresh) AND a need for explicit operator control for future deployments (AC-2 lets operators flip without scrubbing `.env`).
- [x] Task 2 — AC-1 detection block implemented in BOTH `mailbot_api/sync/oauth.py:_exchange_refresh_token` AND (per CR-4) `mailbot_api/sync/graph_client.py:_exchange_refresh_token`. Both substring-on-`error_description` AND CR-6 numeric-array-fallback on `error_codes`. Dedicated event fires BEFORE the existing generic `oauth.refresh.failed`.
- [x] Task 3 — AC-2 shipped: new `mailbot_api/config.py:is_public_client_mode()` helper parses `OUTLOOK_PUBLIC_CLIENT` (truthy set: 'true'/'1'/'yes'/'on' case-insensitive). Gate honored at refresh-time in both oauth.py + graph_client.py (CR-5 per-call read in both). docker-compose.yml passthrough added (CR-1). `.env.example` placeholder added with F25 context.
- [x] Task 4 — Documentation: `docs/entra-app-registration.md` Step 5 gained a belt-and-suspenders recommendation for public-client setups; failure-mode table row updated with both the new env gate AND the new dedicated log event remediation pointer (CR-2 anchor-based for line-shift stability).
- [x] Task 5 — Regression tests in `tests/integration/test_oauth_public_client_f25.py`: AC-5.1 (dedicated event fires + generic event also fires), AC-5.2 (form omits client_secret with gate on + value-leak negative assertion), AC-5.3 (confidential-client default still sends secret), CR-3 (confirmation event fires when gate is active), CR-6 (description-localized + error_codes=[90023] fallback), bonus env-parsing truthy/falsy set. 6 tests total.
- [x] Task 6 — MANDATORY-CR pass complete. Sonnet 4.6 reviewer, 8 findings (1 decision-needed + 5 patch + 2 defer + 1 dismissed). All 6 actionable findings APPLIED (100%). CR-1 was the biggest catch: AC-2 gate was dead-on-arrival in production without the docker-compose.yml passthrough.

## Dev Notes (light — full context-engineering at pickup time)

### Root-cause evidence

Captured 2026-06-05 fourth-pass walk:

```
status_code=400 body={'error': 'invalid_request', 'error_description': "AADSTS90023: Public clients can't send a client secret. Trace ID: ... Correlation ID: ..."}
```

Code path: [mailbot_api/sync/oauth.py:276-287](../../mailbot_api/sync/oauth.py#L276-L287):

```python
client_secret = get_secret_optional("OUTLOOK_CLIENT_SECRET") or None
...
if client_secret is not None:
    form["client_secret"] = client_secret
```

Identical pattern in [mailbot_api/sync/graph_client.py:89-95](../../mailbot_api/sync/graph_client.py#L89-L95).

Existing docs already cover the failure mode at [docs/entra-app-registration.md:235](../../docs/entra-app-registration.md#L235):

> Script prints `FATAL: token exchange failed status=400 body={'error': 'invalid_request', ... 'AADSTS90023: ...'}` ... Entra app is registered as a public client ... but `OUTLOOK_CLIENT_SECRET` is set in `.env` ... Remove (or comment out) the `OUTLOOK_CLIENT_SECRET` line in `.env`; re-run

This story closes the "silent failure mode for 9+ hours" gap that hid the bug as operational.

### Why Story 6-15 didn't catch it

Story 6-15 tested every `exchange_and_persist` path with `httpx.MockTransport`. None of those tests exercised the AADSTS90023 case (mocked Microsoft returned `invalid_grant` for the refresh-token-rejected case, never `invalid_request` for the secret-on-public-client case). AC-5.1 fills that test-coverage gap.

### Scope boundary

This story does NOT fix the F26 race (auto-resume edge case from script-driven success) — that's filed separately as Story 6-17. This story also does NOT regenerate the rotation runbook — Story 6-15's runbook is correct; it just assumes the secret-leak bug is already fixed.

### References

- [mailbot_api/sync/oauth.py](../../mailbot_api/sync/oauth.py) — `_exchange_refresh_token` + `_record_refresh_failure`
- [mailbot_api/sync/graph_client.py](../../mailbot_api/sync/graph_client.py) — `GraphClient._exchange_refresh_token` (identical pattern)
- [docs/entra-app-registration.md:235](../../docs/entra-app-registration.md#L235) — existing operator-side mitigation
- [_bmad-output/implementation-artifacts/6-15-outlook-oauth-reauthorization-runbook-and-rotation-reminder-f23-closure.md](./6-15-outlook-oauth-reauthorization-runbook-and-rotation-reminder-f23-closure.md) — Story 6-15 reference; F25 is the load-bearing missing piece that made F23 misclassified
- `epic-6-run-flags.md § F25` — full finding text

### Review Findings

- [x] \[Review]\[Decision-Applied] CR-5: `__init__`-time vs runtime-read asymmetry in graph\_client.py — **APPLIED option (b)**: moved `GraphClient._exchange_refresh_token` to per-call `is_public_client_mode()` read for symmetry with `oauth.py`. `__init__` still resolves `self._client_secret` from env at construction time (matches Story 1-5 pattern), but the gate-application happens at refresh-token-exchange time. Operator hot-flips of `OUTLOOK_PUBLIC_CLIENT` now reactive without container restart across both code paths. `mailbot_api/sync/graph_client.py:117-153`
- [x] \[Review]\[Patch] CR-1: docker-compose.yml passthrough added — **APPLIED**: `- OUTLOOK_PUBLIC_CLIENT=${OUTLOOK_PUBLIC_CLIENT:-}` added to mailbot-api environment block alongside the other OUTLOOK\_ vars. AC-2 gate now functional in production deployments (was dead-on-arrival pre-patch). `docker-compose.yml:87-91`
- [x] \[Review]\[Patch] CR-2: line-number-stable anchor — **APPLIED**: `remediation_doc` constant in both `oauth.py` and `graph_client.py` switched to `docs/entra-app-registration.md#common-failure-modes`. Section anchor is line-shift-stable. Updated F25 test assertion to match. `mailbot_api/sync/oauth.py:362`, `mailbot_api/sync/graph_client.py:194`
- [x] \[Review]\[Patch] CR-3: AC-2 confirmation event — **APPLIED**: `logger.info` with `event="oauth.config.public_client_mode"` + `secret_present_in_env: bool` extras fires whenever `public_client_mode` is True at refresh-time. Emitted from BOTH oauth.py and graph_client.py. New regression test `test_public_client_mode_fires_confirmation_event` locks the contract. `mailbot_api/sync/oauth.py:295-303`, `mailbot_api/sync/graph_client.py:138-146`
- [x] \[Review]\[Patch] CR-4: AADSTS90023 detection mirrored in graph_client.py — **APPLIED**: `_exchange_refresh_token` failure path now fires the dedicated `oauth.refresh.public_client_secret_misconfig` event with the same shape as oauth.py. Legacy Story 1-5 sync path is now operator-routable. `mailbot_api/sync/graph_client.py:182-194`
- [x] \[Review]\[Patch] CR-6: `error_codes` numeric-array fallback — **APPLIED**: detection logic in BOTH oauth.py and graph_client.py is now `"AADSTS90023" in error_description OR 90023 in payload.get("error_codes", [])`. Protects against Microsoft description-text drift (localization, format change). New regression test `test_public_client_secret_misconfig_detected_via_error_codes_array` covers the description-localized case with `error_codes=[90023]`. `mailbot_api/sync/oauth.py:347-359`, `mailbot_api/sync/graph_client.py:183-194`
- [x] \[Review]\[Defer] CR-7: `OUTLOOK_PUBLIC_CLIENT` not added to Story 4-0 credential-capture rubric — `4-0-interactive-credential-capture-and-phase-3-5-verification.md` lists the captured env vars but doesn't include the new `OUTLOOK_PUBLIC_CLIENT` flag. Operators onboarding fresh deployments won't be reminded to set it. Pre-existing gap in the 4-0 rubric process; out of scope for 6-16 code fix but should be tracked. — deferred, pre-existing rubric gap
- [x] \[Review]\[Defer] CR-8: Quoted-value edge case in `is_public_client_mode()` parsing — if an operator sets `OUTLOOK_PUBLIC_CLIENT="true"` (double-quoted, common in some shell `export` patterns or certain `.env` editors), `strip().lower()` returns `'"true"'` which is not in the truthy set, so the function silently returns `False`. No python-dotenv in the stack; Docker Compose `env_file:` also does NOT strip quotes. The test suite covers only bare strings. Risk is low (`.env.example` shows bare value), but could confuse operators. `mailbot_api/config.py:65` — deferred, low-probability edge case; document in .env.example comment as follow-up

## Dev Agent Record

### Agent Model Used

- Dev: claude-opus-4-7 (Opus 4.7, 1M context)
- Code Review: claude-sonnet-4-6 (Sonnet 4.6, MANDATORY-CR per §5.12 — 2 criteria fired: external credential surface + cross-story load-bearing)

### Debug Log References

- Pre-review self-audit: `6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.pre-review.md` (5 sections + 12-check §5 posture audit; §5.12 cadence verdict = MANDATORY-CR)
- 1 test failure surfaced during CR application: existing AC-5.1 test pinned remediation_doc to "docs/entra-app-registration.md:235"; CR-2 switched to anchor `#common-failure-modes` and the test was updated to match.
- CR found 8 findings; biggest catch was CR-1 (docker-compose.yml passthrough missing) — a one-line fix that closed the load-bearing production gap.

### Completion Notes List

- **F25 root cause closed.** OUTLOOK_CLIENT_SECRET was unconditionally appended to the token-exchange form when env-set, even for public-client Entra apps that reject any secret with AADSTS90023. Bug was silent for the lifetime of any `.env` carrying a stale secret against a public-client app. Closed via Option C (both AC-1 detection event + AC-2 explicit operator gate).
- **Dedicated `oauth.refresh.public_client_secret_misconfig` event** fires on AADSTS90023 detection BEFORE the existing generic `oauth.refresh.failed`. Detection is robust to description-text drift (substring OR numeric-array fallback per CR-6). Both code paths emit the event identically — operator routing is consistent regardless of whether the legacy sync GraphClient or the async exchange_and_persist hit the failure.
- **`OUTLOOK_PUBLIC_CLIENT` explicit operator gate** lets operators flip public-client mode in `.env` without scrubbing the legacy `OUTLOOK_CLIENT_SECRET` value (rollback-friendly for confidential-client deployments). Gate is re-read per-call in BOTH oauth.py and graph_client.py (CR-5 symmetric design) so operator hot-flips are reactive without container restart. docker-compose.yml passthrough added (CR-1) so the gate is functional in production deployments.
- **AC-2-mandated confirmation event** (`oauth.config.public_client_mode`) fires when the gate is active at refresh-time, with `secret_present_in_env: bool` extra so operators can spot rollback-friendly setups (gate on + secret still in env).
- **AC-4 documentation** updated at both targets: failure-mode table row links to the new event AND env gate (anchor-based for line-stability), Step 5 gained a belt-and-suspenders recommendation for public-client setups, `.env.example` placeholder added with F25 context.
- **AC-1/AC-2/AC-5 verified via 6 regression tests** in `tests/integration/test_oauth_public_client_f25.py`. CR-3 + CR-6 regression tests added during the CR application pass.
- **All 4 gates green:** ruff clean, mypy --strict clean (123 files), boundary clean, pytest 1095 passed + 2 skipped + 3 deselected (vs baseline 1089 + 2 + 3 → net +6 tests, of which +4 initial F25 + +1 CR-3 + +1 CR-6 = +6).
- **MANDATORY-CR pass complete** per §5.12 verdict. Sonnet 4.6 reviewer produced 8 findings; 6 actionable APPLIED (100%), 2 pre-existing DEFER-acknowledged (CR-7 Story 4-0 rubric, CR-8 quoted-value edge case).
- **CR-7 deferral note:** Story 4-0's credential-capture rubric should be amended in a future polish-pass story to remind operators to set `OUTLOOK_PUBLIC_CLIENT=true` for public-client setups. Out of scope for 6-16's code fix.

### File List

- `mailbot_api/config.py` (modified) — new `is_public_client_mode()` helper for OUTLOOK_PUBLIC_CLIENT truthy-set parsing
- `mailbot_api/sync/oauth.py` (modified) — gate check + confirmation event + AADSTS90023 detection (substring + error_codes fallback per CR-6) + dedicated misconfig event
- `mailbot_api/sync/graph_client.py` (modified) — per-call gate check (CR-5) + confirmation event + AADSTS90023 detection mirrored from oauth.py (CR-4)
- `tests/integration/test_oauth_public_client_f25.py` (new) — 6 tests covering AC-5.1/5.2/5.3 + CR-3 (confirmation event) + CR-6 (error_codes fallback) + env-parsing bonus
- `docker-compose.yml` (modified) — `OUTLOOK_PUBLIC_CLIENT` passthrough (CR-1 — was load-bearing production gap)
- `docs/entra-app-registration.md` (modified) — Step 5 belt-and-suspenders + failure-mode table row updated (CR-2 anchor-based remediation pointer)
- `.env.example` (modified) — `OUTLOOK_PUBLIC_CLIENT=` placeholder + F25 context comment
- `_bmad-output/implementation-artifacts/6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.md` (this file) — status + Dev Agent Record + Completion Notes + Tasks/Subtasks checks + Review Findings dispositions
- `_bmad-output/implementation-artifacts/6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.pre-review.md` (new) — 5-section pre-review self-audit per Step 2.3.5
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — row status: backlog → in-progress → done (Phase 2.6 staging)

### Change Log

- 2026-06-05 — Story 6.16 filed as STUB during Story 6-6.5 fourth-pass walk. Root-cause-identified (F25 = F23's true root cause), fix-shape-clear, awaits context-engineering + dev pickup.
- 2026-06-05 — autonomous-epic-run pickup; Option C (AC-1 + AC-2) shipped; MANDATORY-CR pass (Sonnet 4.6) complete with 6/6 actionable findings APPLIED (100%).
