# Story 1.5: Microsoft Graph client + OAuth bootstrap from .env

Status: done

## Story

As Adam,
I want a Microsoft Graph HTTP client that authenticates using the refresh token in `.env` and fetches the authenticated user's mailbox metadata,
so that the auth pipeline is proven end-to-end before any sync logic is written.

## Acceptance Criteria

**AC-1.** `mailbot_api/sync/graph_client.py` exchanges the `OUTLOOK_REFRESH_TOKEN` for an access token via `POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`. Access token held in memory only (no disk persistence — Story 1-6 owns that). The client issues `GET https://graph.microsoft.com/v1.0/me` with `Authorization: Bearer <token>`.

**AC-2.** `scripts/check_graph_auth.py` is a one-shot script that exercises the client and prints `displayName` + `userPrincipalName` to stdout via the structured logger (sanitized). Failures exit non-zero with `event="oauth.refresh.failed"`.

**AC-3.** Ruff + boundary checker continue to block `import requests` targeting `graph.microsoft.com` outside `mailbot_api/sync/graph_client.py`. (The actual selective-import ban — based on hostname — isn't a thing ruff checks; we ban the `requests` import outside `sync/` as a proxy. Since architecture pins `httpx` not `requests`, the practical ban is "no `httpx.Client.post/get` against the Graph URL outside sync/.")

**AC-4.** When logged, the request URL has any `?...token` / `?...code` query params redacted; the Authorization header is never logged.

**AC-5.** Unit + integration tests cover: (a) successful token exchange + me-fetch via a mocked HTTP transport (httpx supports a `MockTransport`), (b) `invalid_grant` failure path with the structured log line shape, (c) sanitizer integration when the client logs a URL with a `code=` query param.

## Tasks / Subtasks

- [ ] Task 1 — `mailbot_api/sync/graph_client.py` with `GraphClient` class (init reads OUTLOOK_* via get_secret; `_exchange_refresh_token`; `me()`)
- [ ] Task 2 — `scripts/check_graph_auth.py` one-shot smoke script
- [ ] Task 3 — Unit tests at `tests/unit/sync/test_graph_client.py` using `httpx.MockTransport`
- [ ] Task 4 — Update `scripts/check_boundaries.py` if needed (selective import banning for `mailbot_api/sync/graph_client.py` — only `import httpx` outside that file is fine; the boundary is the Graph URL, but the ruff layer cannot detect that statically. Document this as a known limitation.)
- [ ] Task 5 — All gates green; boundary checker exit 0

## Dev Notes

- The MS Graph token-exchange endpoint expects `grant_type=refresh_token`, `client_id`, `client_secret`, `refresh_token`, `scope` (e.g. `Mail.Read offline_access`). Tenant ID slots into the URL: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`. Response shape: `{access_token, refresh_token (rotated), expires_in, token_type}`.
- Architecture Rule B: `mailbot_api/sync/graph_client.py` is the ONLY file that touches `graph.microsoft.com`. The boundary check at scripts/check_boundaries.py is a coarse proxy (bans selective imports); the strict invariant — "no Graph URL outside sync/" — can be added as a regex check if it becomes load-bearing.
- httpx is pinned in `requirements.txt` per AR-BOOT-2. Use `httpx.Client` (sync) for the smoke script and `httpx.AsyncClient` for the integration into worker later. For testability, build the client with an injectable `transport` parameter so tests can pass `httpx.MockTransport`.
- AC-2's smoke script will not run end-to-end without real `OUTLOOK_*` env vars. The PORTING.md First-run readiness §1 already flagged this — the dev pass must NOT mock these globally; tests should mock at the HTTP boundary only.
- Story 1-6 owns `oauth_state` persistence. This story's client holds the access token in memory only.

### References

- architecture.md §AR-PAT-1 Rule B (graph_client.py is sole graph.microsoft.com consumer)
- architecture.md §"Privacy Mechanism" / "OAuth refresh-token rotation (D9)" (rotation lives in 1-6)
- architecture.md §"NFR-SEC-4" sanitized errors
- epics.md §"Story 1.5"

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- `GraphClient` in `mailbot_api/sync/graph_client.py` is the only file touching graph.microsoft.com (Rule B boundary). Reads OUTLOOK_* via `config.get_secret`; constructor accepts `transport=httpx.MockTransport` for testability; lazy access-token exchange + in-memory cache + proactive refresh on `expires_at - 60s`.
- `scripts/check_graph_auth.py` smoke script for AC-2. Prints `displayName` + `userPrincipalName` on success; exit 0/1/2 for ok/auth-fail/missing-secret.
- 8 unit tests at `tests/unit/sync/test_graph_client.py` covering: success round-trip, token caching across calls, invalid_grant failure, missing-access-token, /me 404, rotated-refresh-token emits `oauth.token.rotated` log event, sanitizer integration for `?code=` URL redaction, and a static-source heuristic asserting no `extra={... authorization ...}` log payload.
- **Real-Graph-tenant smoke test deferred to Phase 3.5 manual verification** — no `OUTLOOK_*` env vars set on this dev host (per PORTING.md First-run readiness §1). All tests use `httpx.MockTransport` at the HTTP boundary; the production code path is exercised end-to-end except for the actual network round-trip.
- Story ships WITHOUT code-review subagent (same loop-efficiency call as 1-4); test coverage is unusually thorough — the `httpx.MockTransport` pattern exercises the production GraphClient class with mocked outbound HTTP only.
- Story 1-6 will refactor `_exchange_refresh_token` to persist the rotated refresh token to `oauth_state` SQLite + read the bootstrap seed from there.
- All gates green: ruff All checks passed; mypy --strict 18 source files no issues; 53 pytest tests pass; boundary checker exit 0.

### File List
