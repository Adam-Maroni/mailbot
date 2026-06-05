---
baseline_commit: b1784a5
---

# Story 6.16: OAuth public-client secret-leak startup validation — F25 closure

Status: backlog

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

- [ ] Task 1 — Decision: pick Option A (cheap, no env-var churn) OR Option B (operator-gated, more explicit) OR Option C (both). Document rationale in Completion Notes. Recommended: C.
- [ ] Task 2 — Implement AC-1: new event in `_exchange_refresh_token` failure path that detects AADSTS90023 substring in `error_description` and fires the dedicated log. Same site at [graph_client.py](../../mailbot_api/sync/graph_client.py).
- [ ] Task 3 — Implement AC-2 (if chosen): new `OUTLOOK_PUBLIC_CLIENT: bool` via `get_secret_optional` + boolean parse. Gate the `if client_secret is not None` append on `not public_client_mode`.
- [ ] Task 4 — Documentation update per AC-4.
- [ ] Task 5 — Regression tests per AC-5.
- [ ] Task 6 — MANDATORY-CR pass.

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

- 2026-06-05 — Story 6.16 filed as STUB during Story 6-6.5 fourth-pass walk. Root-cause-identified (F25 = F23's true root cause), fix-shape-clear, awaits context-engineering + dev pickup.
