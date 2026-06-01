# Story 1.9: One-time refresh-token bootstrap + Entra app-registration recipe

Status: backlog

## Story

As Adam,
I want a one-time interactive bootstrap script that runs the OAuth 2.0 Authorization Code flow on a local dev machine with a browser and prints a refresh token for hand-copy to the VPS `.env`, plus a step-by-step recipe for registering the MailBot app in the Microsoft Entra admin center,
so that there is a documented, reproducible path from "fresh Outlook account" to "VPS `.env` contains a working `OUTLOOK_REFRESH_TOKEN`" — closing the bootstrap gap Stories 1-5/1-6 silently assumed away.

## Context (why this story exists)

The Azure docs review after Epic 1 surfaced that:

1. Refresh tokens for delegated access are issued **only at the end of an Authorization Code flow** with a browser-based user-consent step ([docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md)).
2. Story 1-5's `OUTLOOK_REFRESH_TOKEN` env var has **no story owning its initial population**.
3. The current `docs/auth-recovery.md` ends with "re-mint refresh token on dev box → hand-copy to VPS `.env`" without specifying *how* to mint.
4. Microsoft Entra app registration is a 6-step UI flow that Adam must do exactly once and document for any future re-creation (lost client, expired secret, new account).

This story closes both gaps: the operator recipe (Entra setup) and the automation (the bootstrap script).

## Acceptance Criteria

**AC-1.** `docs/entra-app-registration.md` exists and walks the reader through Entra app registration end-to-end:

- Sign in to <https://entra.microsoft.com/> with the same Microsoft account that owns the target Outlook mailbox.
- Navigate to **Identity → Applications → App registrations → New registration**.
- Set: Name = `MailBot`; Supported account types = **Personal Microsoft accounts only** (because the target mailbox is Adam's personal Outlook.com) — note that work/school accounts choose a different option and the recipe spells out both.
- Set redirect URI: Platform = **Public client/native (mobile & desktop)**, URI = `http://localhost:8765/callback`. (The bootstrap script binds 8765 locally; the VPS never receives a redirect.)
- Record: Application (client) ID, Directory (tenant) ID. For personal Microsoft accounts, the tenant value Adam will paste into `.env` is the literal string `consumers` (not the directory GUID — the GUID is for the Entra admin center only).
- Under **Certificates & secrets → New client secret**: create a secret named `MailBot bootstrap secret`, valid 24 months; copy the secret **value** immediately (Entra hides it after the page reloads).
- Under **API permissions → Add a permission → Microsoft Graph → Delegated permissions**: grant `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `User.Read`, and `offline_access` (the last is what makes refresh tokens come back). Click **Grant admin consent** if the button is offered.
- Recipe ends with a checklist of values the operator should have in hand before running the bootstrap script: Client ID, Tenant value (`consumers` for personal, GUID for work/school, `common` for mixed-mode), Client Secret value, Redirect URI (`http://localhost:8765/callback`).

**AC-2.** `scripts/mint_refresh_token.py` is a self-contained one-shot CLI that runs the Authorization Code flow locally:

- Reads four required env vars or `--flag` arguments: `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_REDIRECT_URI` (defaults to `http://localhost:8765/callback`).
- Builds the `/authorize` URL per [auth-v2-user.md §Step 1](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md): `client_id`, `response_type=code`, `redirect_uri`, `response_mode=query`, `scope=offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send`, `state=<random 32-char hex>`.
- Spawns a `http.server.HTTPServer` listening on 127.0.0.1:8765 for one request, then exits.
- Opens the authorize URL in the default browser via `webbrowser.open(...)`. If `webbrowser.open` returns False (headless dev machine), falls back to printing the URL with the instruction "open this URL manually in any browser."
- The local HTTP handler captures `?code=...&state=...` query params on the callback. Verifies `state` matches; if not, prints `state mismatch — possible CSRF; aborting` and exits non-zero.
- Exchanges the code for tokens via `POST {tenant}/oauth2/v2.0/token` with `grant_type=authorization_code` per [auth-v2-user.md §Step 2](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md).
- Prints the refresh token to stdout with a marker block:
  ```
  ===== REFRESH TOKEN (paste into VPS .env as OUTLOOK_REFRESH_TOKEN) =====
  <token here>
  ===== END =====
  ```
- Also prints the **access token's `expires_in`** and **the scopes the token was granted** for sanity-checking before paste.
- On any HTTP error from the token endpoint, prints the **sanitized** error body (per Story 1-4's sanitizer rules — but this script is in `scripts/` and bypasses the boundary checker, so it imports the sanitizer module directly) plus exit code 2.

**AC-3.** `docs/auth-recovery.md` is updated to point at Story 1-9 as the canonical re-mint procedure, replacing the previous hand-wavy "re-mint refresh token on dev box" line. The recovery flow becomes:

1. On dev machine: `python scripts/mint_refresh_token.py` (interactive browser flow).
2. Copy the printed refresh token.
3. SSH to VPS: edit `/path/to/mailbot/.env`, set `OUTLOOK_REFRESH_TOKEN=<pasted value>`.
4. Inside the container: `DELETE FROM oauth_state WHERE provider='microsoft_graph';` (so the bootstrap-seed path re-engages on next worker tick).
5. `docker compose restart mailbot-api` — the worker reads the seeded `.env` value, performs the first token exchange, persists to `oauth_state`, and resumes sync.

**AC-4.** `scripts/mint_refresh_token.py` is excluded from the `check_boundaries.py` allowlist constraints (it lives in `scripts/`, which is already allowlisted by Story 1-4's per-file-ignores) but **must** import the JSON sanitizer from `mailbot_api/observability/logging.py` so any printed error body is redacted to the same standard as runtime logs.

**AC-5.** Integration test at `tests/integration/test_mint_refresh_token.py` exercises the **token-exchange path** of `mint_refresh_token.py` via `httpx.MockTransport` — covers: (a) successful exchange returning `refresh_token`, (b) `invalid_grant` error response, (c) state mismatch. The browser-spawn + local-server-callback path is NOT integration-tested (it requires a real browser); manual verification is documented in `docs/entra-app-registration.md` § "First-time mint walkthrough."

**AC-6.** `.env.example` is updated to mark `OUTLOOK_REFRESH_TOKEN` with a comment pointer: `# obtained via scripts/mint_refresh_token.py — see docs/entra-app-registration.md`.

## Tasks / Subtasks

- [ ] **Task 1** — Author `docs/entra-app-registration.md` end-to-end recipe (AC: #1)
- [ ] **Task 2** — `scripts/mint_refresh_token.py` — argparse CLI + `/authorize` URL build + local HTTP server callback + token exchange (AC: #2, #4)
- [ ] **Task 3** — Update `docs/auth-recovery.md` to point at the new script + Entra recipe (AC: #3)
- [ ] **Task 4** — Update `.env.example` comment on `OUTLOOK_REFRESH_TOKEN` (AC: #6)
- [ ] **Task 5** — Integration tests at `tests/integration/test_mint_refresh_token.py` (AC: #5)
- [ ] **Task 6** — Verify Phase 3.5 checkpoint: the printed refresh token actually works against the real Graph endpoint by manually running `python scripts/check_graph_auth.py` immediately after paste (operator step in the recipe, not automated)
- [ ] **Task 7** — All gates green (ruff, mypy --strict, boundary checker, pytest)

## Dev Notes

### Why this is its own story (not folded into 1-5 or 1-6)

Story 1-5 ships the *runtime* path that consumes an already-extant refresh token. Story 1-6 ships *persistence* of rotated tokens. Neither owns the bootstrap. This is also the only story in Epic 1 with an explicit operator-facing UI surface (the browser flow + Entra UI) — it has a fundamentally different test posture (manual walkthrough + mock-only automated tests).

### Why `tenant=consumers` for personal Outlook

[auth-v2-user.md parameters table](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md) documents the allowed `{tenant}` values: `common` (both), `organizations` (work/school only), `consumers` (Microsoft accounts only), or a tenant identifier. Adam's target mailbox is a personal `@outlook.com` / `@hotmail.fr` account → `consumers`. If MailBot is later pointed at a work/school account, the tenant flips to a GUID. The recipe documents all three cases.

### Why a public-client redirect URI on `http://localhost:8765/callback`

Public-client native/desktop redirect URIs are the documented pattern for headless-but-bootstrapped flows. The localhost loopback is special-cased in OAuth 2.0 RFC 8252 — Microsoft Entra accepts it without TLS. Port 8765 is high enough to avoid `/etc/services` conflicts and low enough to be a plain `bind()` (no privileged-port concern).

### Why the script bypasses the boundary checker for HTTP-to-Graph

`scripts/check_boundaries.py` enforces Rule B (only `mailbot_api/sync/graph_client.py` may call `graph.microsoft.com`). But `scripts/mint_refresh_token.py` targets `login.microsoftonline.com` (token endpoint), NOT `graph.microsoft.com` — Rule B doesn't apply. Per Story 1-4, `scripts/` is already in `per-file-ignores` for the broader code-boundary lint set, so no special carve-out is needed. The boundary checker will pass cleanly.

### Why we don't use MSAL here

MSAL would be the canonical choice for token acquisition (per [auth-v2-user.md §"Use the Microsoft Authentication Library (MSAL)"](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md)). We deliberately avoid it for this one-shot script because: (a) the script runs on the dev machine, not in production — failure mode is "Adam reruns it"; (b) adding `msal` to the project's `requirements.txt` for one-time use pollutes the runtime image; (c) the protocol is simple enough to express in ~80 lines of `httpx` + `http.server`. The architectural decision to retain hand-rolled httpx for the runtime client (per the post-Epic-1 docs review) carries through here.

### References

- [docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md) — Authorization Code flow protocol details
- [docs/external/learn-microsoft-azure/pages/graph/auth/auth-concepts.md](../../docs/external/learn-microsoft-azure/pages/graph/auth/auth-concepts.md) — delegated vs app-only access
- [docs/external/learn-microsoft-azure/pages/graph/permissions-reference.md](../../docs/external/learn-microsoft-azure/pages/graph/permissions-reference.md) — Mail.Read / Mail.ReadWrite / Mail.Send delegated permission scopes
- [docs/auth-recovery.md](../../docs/auth-recovery.md) — existing recovery flow (to be updated by this story)
- architecture.md § "Sync ↔ Actions (D4 + D5 + D9)" — OAuth refresh-token rotation (D9) — context for why this story matters
