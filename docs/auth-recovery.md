# Microsoft Graph OAuth — Recovery Procedure

This document describes how to recover when the Microsoft Graph refresh token
fails (`invalid_grant`, expired, revoked) and the sync-health alarm starts
firing (Story 1-8, FR-1.5).

## Symptoms

- Discord urgent notification: `"sync stale > 1h"` (or local log line
  `event="sync.health.alarm"` in `mailbot_logs`).
- `mailbot status` (Epic 6) reports `sync.last_outcome = failed` and the
  last_error mentions `invalid_grant`, `unauthorized_client`, or `invalid_client`.
- Structured log line `event="oauth.refresh.failed"` from `mailbot_api.sync.oauth`
  with `error_code` indicating an auth problem.

## Cause

The refresh token used to mint access tokens has been revoked or expired. This
can happen if:

1. The conditional-access policy on the Azure tenant changed (e.g., MFA
   re-required).
2. Someone explicitly revoked the refresh token from the Azure portal
   (`Enterprise Applications` → app → `User settings` → revoke).
3. The refresh token went unused for longer than the tenant's inactive-refresh
   timeout (typically 90 days; varies by tenant config).
4. Suspicious activity caused Azure AD to invalidate the token (rare but
   possible).

## Recovery Sequence

The architecture pins a **bootstrap seed** approach (per AR-D9-2): the `.env`
file's `OUTLOOK_REFRESH_TOKEN` is used on first deploy to populate the
`oauth_state` SQLite row. After that, rotation events update the row in place
and `.env` is never re-read.

To recover from a revoked refresh token, you must re-seed the row from a
freshly-obtained refresh token. The high-level sequence:

### Step 1 — Mint a new refresh token on your dev box

On your local dev machine (the same one with a browser):

```bash
python scripts/mint_refresh_token.py
```

The script reads `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_SECRET`
from env (or your local `.env`), opens the consent flow in your browser,
captures the callback on `localhost:8765`, exchanges the code for tokens, and
prints the refresh token between two `===== ... =====` marker lines.

For first-time setup (not just recovery), follow the prerequisites in
[docs/entra-app-registration.md](./entra-app-registration.md) first — you need a
registered app and its client ID/secret before this script can run.

Copy the printed refresh token (the value between the marker lines). Continue to Step 2.

### Step 2 — Hand-copy the new refresh token into the VPS `.env`

SSH into the VPS:

```bash
ssh vps.example.com
sudo -u mailbot vi /srv/mailbot/.env
```

Edit `OUTLOOK_REFRESH_TOKEN=<paste the new token here>`. Save & exit. Verify
`chmod 600 /srv/mailbot/.env` (the file should already be 600-perms per
NFR-SEC-1).

### Step 3 — Force a re-seed by clearing the old `oauth_state` row

The runtime trusts `oauth_state` over `.env` once seeded (per AR-D9-2). To force
the seed flow to re-run with the new refresh token, delete the row:

```bash
docker compose exec mailbot-api sqlite3 /data/mailbot.db \
    "DELETE FROM oauth_state WHERE provider='microsoft_graph';"
```

### Step 4 — Restart the container

```bash
docker compose restart mailbot-api
```

The next sync iteration (within 4 minutes) will:

1. Call `load_oauth_state(...)` → returns None (row deleted).
2. Call `seed_oauth_state_from_env(...)` → reads OUTLOOK_REFRESH_TOKEN from
   `.env`, inserts the row with `rotation_count=0`.
3. Call `exchange_and_persist(...)` → exchanges for an access token and updates
   the row.

The sync-health alarm will clear on the next successful sync iteration.

### Step 5 — Confirm recovery

```bash
docker compose exec mailbot-api python scripts/check_graph_auth.py
```

Expected output: `OK: signed in as 'Adam Aroni' ('adam@example.onmicrosoft.com')`.

The structured log line `event="oauth.refresh.ok"` should appear in the
`mailbot_logs` volume shortly after.

## Why not auto-fall-back-to-env?

After the bootstrap seed, the runtime never re-reads `OUTLOOK_REFRESH_TOKEN` from
`.env`. This is by design: if it did, every rotation would be silently undone on
container restart (the env-var value is the stale original). The
`oauth_state.refresh_token` column is the source of truth precisely because it
captures rotation events.

Forcing a manual re-seed (Step 3 above) is the deliberate, explicit way to
bring a new refresh token into the runtime — and it's only needed when
something has actually gone wrong.

## Monitoring

- `mailbot status` reports `last_rotated_at` and `rotation_count` per
  `worker_health` heartbeats (Epic 6).
- `oauth.token.rotated` log events are persisted in the `mailbot_logs` Docker
  volume (Rule W).
- Backup tarballs (NFR-OPS-5) include `oauth_state` automatically because the
  SQLite `.backup` covers all tables; `.env` is excluded (NFR-SEC-6).
