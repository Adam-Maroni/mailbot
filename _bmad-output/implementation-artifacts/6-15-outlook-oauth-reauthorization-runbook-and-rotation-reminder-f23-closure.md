# Story 6.15: Outlook OAuth re-authorization runbook + rotation reminder — F23 closure

Status: backlog

> Filed 2026-06-04 during Story 6-6.5 third-pass walk. NO inline fix possible — F23 is OPERATIONAL (refresh-token lifecycle), not a code defect. **This story BLOCKS Story 6-6.5 Section B CP-A/B live re-walk** (recipient-inbox verification) because without a valid refresh token, the Outlook adapter cannot complete the real Graph send.

## Story

As MailBot operator,
I want a documented re-authorization runbook + proactive rotation reminder + visible alarm when OAuth refresh starts failing,
So that an expired Microsoft refresh token cannot silently strand the entire send pipeline — and so I can re-auth in 5 minutes when it does happen.

## Acceptance Criteria

**AC-1 (re-auth runbook)**: A new section in `docs/setup-vps-runbook.md` (or a sibling runbook file if it doesn't fit) titled "Outlook re-authorization" documents the steps to (a) trigger the OAuth interactive consent flow (browser); (b) capture the fresh refresh token; (c) persist the token into the `oauth_state` table (via mailbot CLI command OR one-shot script under `scripts/`). The runbook MUST work from a clean state — i.e., assume the operator has nothing but `.env` credentials and the running mailbot-api container.

**AC-2 (CLI surface OR one-shot script)**: `scripts/refresh_outlook_oauth.py` (or `mailbot reauth` subcommand) exists, accepts the authorization code from the browser flow, exchanges it for refresh+access tokens, persists into `oauth_state`. The script MUST NOT log the token values; it MUST log presence + length + rotation_count.

**AC-3 (mailbot status alarm)**: `assemble_status` (Story 6-1) gains a new field in the OAuth/sync section: `oauth_refresh_failing` — `True` when the last K consecutive refresh attempts failed (K configurable, default 3). The status CLI surfaces this as an alarm; `/admin/status` JSON includes the field.

**AC-4 (drainer auto-pause on oauth_refresh_failing — DECISION REQUIRED)**: investigate whether the drainer should auto-pause its dispatch loop when `oauth_refresh_failing=True` to avoid a pile of `provider_4xx_401` `pending_actions` failures. Either implement the auto-pause OR document the decision-deferral with rationale.

**AC-5 (proactive-refresh schedule)**: The OAuth refresher task currently ticks at the same cadence as the worker scheduler. Audit whether this cadence stays inside Microsoft's consumer-tier refresh-token sliding window (24h if unused; up to 90d if continuously rotated). If not, adjust the schedule OR add a proactive refresh ping to keep the token alive.

**AC-6 (regression test)**: a test asserts the alarm fires after K simulated failures and clears after a success.

**AC-7**: MANDATORY-CR per §5.12: external-credential surface, operator-facing, cross-story (Story 6-1 status + Story 4-4 drainer + sync.oauth). Minimum one CR pass.

## Tasks / Subtasks

- [ ] **Task 1**: Document the re-auth flow (AC-1) — author the runbook section.
- [ ] **Task 2**: Build the CLI subcommand or script (AC-2).
- [ ] **Task 3**: Extend `assemble_status` with `oauth_refresh_failing` field (AC-3) — fold into Story 6-1's existing alarm aggregator.
- [ ] **Task 4**: Run the auto-pause investigation (AC-4) — file the decision.
- [ ] **Task 5**: Audit refresh cadence (AC-5) — adjust if needed.
- [ ] **Task 6**: Regression test (AC-6).
- [ ] **Task 7**: Gates green + CR.

## Dev Notes

### Why this story exists

Story 6-6.5 third-pass walk wired the entire stack end-to-end through Graph dispatch — and then hit HTTP 401 on the real Graph endpoint because the refresh token had silently died 9+ hours earlier without anyone noticing.

This is the kind of operational failure mode that Phase 3.5 walks exist to surface — but it should NOT take a walk to discover it. The system needs an alarm + a runbook + (probably) auto-pause.

### F23 details

- Microsoft `https://login.microsoftonline.com/consumers/oauth2/v2.0/token` endpoint returning `HTTP 400 invalid_request` on every refresh attempt for 9+ hours.
- `oauth.refresh.failed` log fires every refresher tick; `rotation_count=12` at sample time.
- `oauth_state.access_token` was 40+ minutes stale at walk time; refresher could not get a new one.
- Microsoft consumer-tier refresh tokens have sliding 24h lifetime if unused (or up to 90d if continuously rotated).

### Adam-decided priority

F23 BLOCKS Story 6-6.5 Section B CP-A/B live re-walk (the "reply lands in recipient inbox" leg). Story 6-6.5 stays `ready-for-walk` until this story closes + a fresh refresh token is captured.

### Threat-model note

The re-auth CLI/script handles real credentials. Per Story 5-7 redaction + Story 4-0 capture rubric, the implementation MUST never log the token value, MUST never echo it to terminal stdout, MUST only persist via the existing `oauth_state` write path. CR will look hard at this.

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F23`
- `mailbot_api/sync/oauth.py` — refresh path (where 400 is observed)
- `mailbot_api/worker.py:_refresh_access_token_cache` — token cache refresher
- Story 6-1 `assemble_status` — alarm aggregator
- Story 4-0 credential rubric — capture/storage discipline
- `.env` — `OUTLOOK_CLIENT_ID` / `OUTLOOK_CLIENT_SECRET` / `OUTLOOK_TENANT_ID` / `OUTLOOK_USER_EMAIL`
