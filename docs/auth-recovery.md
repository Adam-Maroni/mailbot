# Microsoft Graph OAuth — Recovery Procedure

This document describes how to recover when the Microsoft Graph refresh token
fails (`invalid_grant`, expired, revoked) and the sync-health alarm starts
firing (Story 1-8, FR-1.5).

## Symptoms

- `mailbot status` (Epic 6) shows the **OAUTH** section in warning state
  with `refresh failing: yes (re-auth required)` and a non-zero
  `consecutive fails:` count (Story 6-15).
- `mailbot status` ROUTER section reports `paused: yes` with
  `reason: oauth_refresh_failing` — Story 6-15's auto-pause fires once the
  failure count crosses the threshold (default: 3 consecutive refresh failures),
  so the drainer stops dispatching Tier-2/3 sends that would all 401.
- Discord urgent notification: `"sync stale > 1h"` (or local log line
  `event="sync.health.alarm"` in `mailbot_logs`).
- `mailbot status` sync section reports `sync.last_outcome = failed` and the
  last_error mentions `invalid_grant`, `unauthorized_client`, or `invalid_client`.
- Structured log line `event="oauth.refresh.failed"` from `mailbot_api.sync.oauth`
  with `error_code` indicating an auth problem; once the threshold is crossed,
  `event="oauth.refresh.auto_paused"` also fires.

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

### Step 2 — Persist the new refresh token via the re-auth script

Story 6-15 collapses the prior `.env` edit + DELETE + container-restart
sequence into a single VPS-side command. The script reads the new refresh
token from stdin (preferred — never writes the value to disk) or from a
file you control, then drives `exchange_and_persist(...)` directly so the
`oauth_state` row is overwritten in place with the new token + a fresh
access token.

SCP the freshly-minted token onto the VPS in a short-lived file (Step 1's
script printed it between marker lines):

```bash
# On your dev box — capture the marker block to a transient file.
echo '<the refresh token from Step 1>' > /tmp/new-rt.txt
chmod 600 /tmp/new-rt.txt
scp /tmp/new-rt.txt mailbot@<vps>:/tmp/new-rt.txt
shred -u /tmp/new-rt.txt    # remove the dev-box copy
```

Then on the VPS, persist + auto-clean:

```bash
ssh mailbot@<vps>
docker compose -f /opt/mailbot/docker-compose.yml exec mailbot-api \
    python scripts/refresh_outlook_oauth.py \
        --from-file /tmp/new-rt.txt \
        --unlink-after-read
```

Successful output (the token value is NEVER echoed — only structured
presence + length + rotation_count):

```text
OK: oauth_state persisted presence=True rotation_count_after=13 access_expires_at=2026-06-05T13:05:00.123456Z
```

Exit codes:

- `0` — persisted; auto-resume fires if the router was auto-paused
- `2` — token endpoint rejected the new token (re-check Step 1)
- `3` — input validation (empty file, missing env)
- `4` — transport error (network/DNS) — narrow to httpx errors only
- `5` — database error (SQLite locked / disk full / migration race)

The script's stdin variant is preferred when you can pipe directly without
ever creating the transient file:

```bash
# Pipe the value straight in — leaves no on-disk copy.
ssh mailbot@<vps> 'docker compose -f /opt/mailbot/docker-compose.yml exec -T \
    mailbot-api python scripts/refresh_outlook_oauth.py -' < /tmp/new-rt.txt
shred -u /tmp/new-rt.txt
```

The token MUST NOT be passed as a CLI argument — it would land in shell
history + the process listing. The script enforces this by accepting only
`--from-file` or stdin (`-`).

### Step 3 — Confirm recovery

```bash
docker compose -f /opt/mailbot/docker-compose.yml exec mailbot-api \
    python scripts/check_graph_auth.py
```

Expected output: `OK: signed in as 'Adam Aroni' ('adam@example.onmicrosoft.com')`.

Verify via the status board as well:

```bash
mailbot status
```

The **OAUTH** section should now show:

- `refresh failing: no`
- `consecutive fails: 0`
- `rotation count: <bumped by 1 vs the pre-recovery snapshot>`
- `access token: fresh`

The **ROUTER** section should show `paused: no` (Story 6-15's auto-resume
clears the `oauth_refresh_failing` pause once the script succeeds AND the
pause reason still matches our marker). Story 6-17 (F26 closure) ensures
this auto-resume fires reliably even when the script-driven success path
captured `consecutive_refresh_failures` BELOW the alarm threshold — the
atomic helper `try_resume_if_reason` is the only safety check needed; no
threshold-based short-circuit blocks recovery anymore.

The structured log line `event="oauth.token.rotated"` (followed by
`event="oauth.refresh.auto_resumed"` if we had been auto-paused) confirms
the full recovery cycle.

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

- `mailbot status` exposes a dedicated **OAUTH** section (Story 6-15) with
  `last_rotated_at`, `rotation_count`, `consecutive_refresh_failures`,
  `oauth_refresh_failing` (the alarm boolean), `access_token_expires_at`,
  and `access_token_stale_minutes`. The CLI flags the section as a warning
  whenever `oauth_refresh_failing` is True; `/admin/status` returns the
  same fields in JSON.
- The `oauth_refresh_failing` alarm fires after `OAUTH_REFRESH_FAIL_THRESHOLD`
  consecutive refresh failures (default `3`, defined in
  `mailbot_api/sync/oauth.py`). Crossing the threshold also auto-pauses the
  router with `reason="oauth_refresh_failing"`; the drainer's per-tick
  pause-state check stops dispatching Tier-2/3 sends so they don't all 401
  and burn `budget_consumed=1` each.
- `oauth.token.rotated`, `oauth.refresh.failed`, `oauth.refresh.auto_paused`,
  and `oauth.refresh.auto_resumed` log events are persisted in the
  `mailbot_logs` Docker volume (Rule W).
- Backup tarballs (NFR-OPS-5) include `oauth_state` automatically because the
  SQLite `.backup` covers all tables; `.env` is excluded (NFR-SEC-6).

### Refresh cadence (audit, Story 6-15 AC-5)

The worker scheduler runs an `oauth_token_refresh` interval task every
`SYNC_INTERVAL_SECONDS = 240` (4 min) — but that task ONLY warms the
in-memory access-token cache that `OutlookGraphWriteAdapter` reads on
every Graph dispatch (`mailbot_api/worker.py:_refresh_access_token_cache`).
The actual refresh-token EXCHANGE fires from the sibling `sync` interval
task (also at 240s), which calls `sync.sync_worker.run_once` →
`oauth.get_access_token` → `exchange_and_persist` ONLY when
`access_token_is_valid()` returns False (i.e., the cached access token is
within `_REFRESH_LEEWAY_SECONDS = 60` of its 1-hour expiry).

Practical cadence: a fresh exchange runs every ~1 hour under steady state,
well inside Microsoft's consumer-tier refresh-token sliding 24h-if-unused
window (and trivially inside the 90d-if-rotated window). The F23 silence
was NOT a cadence problem — it was a visibility problem (no alarm field, no
auto-pause, log line drowned in the noise). Story 6-15 closes the
visibility gap; no cadence change required.

#### Evidence (AC-5 MUST clause)

**Live evidence — `oauth_state.last_rotated_at` delta query.** Run on the VPS
SQLite DB to confirm the rotation cadence is inside the 24h floor:

```bash
sqlite3 /opt/mailbot/data/mailbot.db \
  "SELECT provider, last_rotated_at,
          ROUND((julianday('now') - julianday(last_rotated_at)) * 24, 2) AS hours_since_rotation,
          rotation_count
   FROM oauth_state
   WHERE provider = 'microsoft_graph';"
```

Reference output captured during Story 6-15 dev (2026-06-05, post-re-auth):

```text
microsoft_graph|2026-06-05T08:14:22Z|0.17|1
```

Interpretation: `hours_since_rotation = 0.17` (10 min after the operator
re-auth) confirms the rotation timestamp updates on every successful
exchange. Re-running the query a day later on a steady-state system should
return `hours_since_rotation` values that stay below 24 (typical 1.0–1.5 h
between rotations under the 1-hour access-token lifetime + 60s leeway).
Any value `>= 24` is the operational signal that the sliding-window floor
is being approached and re-auth is imminent.

**Documented Microsoft policy reference.** Consumer-tier refresh-token
lifetime is governed by:

- Microsoft identity platform — refresh tokens:
  <https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens>
  (cite-date 2026-06-05; consumer accounts MSA: refresh tokens have an
  inactivity lifetime of 24 hours and a maximum lifetime of 90 days when
  continuously rotated).
- Microsoft identity platform — configurable token lifetimes (work/school
  tenants for comparison, NOT applicable here since MailBot uses a
  consumer/MSA tenant):
  <https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes>

The 1-hour exchange cadence (above) sits ~24× inside the 24-hour
inactivity floor and ~2160× inside the 90-day maximum — both bounds
trivially satisfied at steady state.
