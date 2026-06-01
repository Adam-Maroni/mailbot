# Microsoft Entra app registration — MailBot bootstrap recipe

This is the one-time setup that produces the values MailBot needs in its `.env`
to talk to Microsoft Graph as a delegated app. You do this **once**, then
[scripts/mint_refresh_token.py](../scripts/mint_refresh_token.py) does the
ongoing token-minting whenever a refresh token is lost (see
[docs/auth-recovery.md](./auth-recovery.md)).

Architecture pin: AR-D9-1 / AR-D9-2 in
[_bmad-output/planning-artifacts/epics.md](../_bmad-output/planning-artifacts/epics.md)
(see also [architecture.md](../_bmad-output/planning-artifacts/architecture.md)
§ "Sync ↔ Actions (D4 + D5 + D9)"). The VPS itself is never an OAuth redirect
URI target — the redirect URI is your local dev box, and you hand-copy the
minted refresh token to the VPS `.env`.

## Prerequisites

- A Microsoft account that owns (or has delegated access to) the Outlook mailbox
  MailBot will read.
- A local dev machine with a browser and Python 3.12+.
- The `mailbot` repo checked out locally with `pip install -r requirements.txt`
  completed.

## Step 1 — Sign in to the Entra admin center

Open <https://entra.microsoft.com/> and sign in with the **same Microsoft account
that owns the target Outlook mailbox**. For Adam's primary case this is an
`@hotmail.fr` / `@outlook.com` account. You'll be signing in on behalf of that
mailbox so the consent step in Step 7 grants the right delegated permissions.

## Step 2 — Create the app registration

Navigate to **Identity → Applications → App registrations → New registration**.

Fill in:

| Field | Value |
| --- | --- |
| Name | `MailBot` |
| Supported account types | **"Personal Microsoft accounts only"** (Adam's case) |
| Redirect URI | leave blank for now — set in Step 3 |

**Supported account types — which to pick:**

- **Personal Microsoft accounts only** — pick this when the target mailbox is
  `@outlook.com`, `@hotmail.*`, `@live.com`, etc. The tenant value you'll paste
  into `.env` later is the literal string `consumers`.
- **Accounts in this organizational directory only (single tenant)** — work or
  school account in one specific tenant. The tenant value you'll paste later
  is the **directory (tenant) GUID**.
- **Accounts in any organizational directory + personal Microsoft accounts** —
  mixed-mode app. The tenant value you'll paste later is `common`.

Click **Register**.

## Step 3 — Add the local-callback redirect URI

Inside the new app registration, go to **Authentication → Add a platform**.

- Choose **"Mobile and desktop applications"** (Entra calls this the
  *public client / native* platform). **Do not** pick "Web" — Web platforms
  require a client secret on every redirect, which the loopback-localhost flow
  is not designed for.
- Add custom redirect URI: `http://localhost:8765/callback`
- Click **Configure**, then **Save**.

The port `8765` is the one [scripts/mint_refresh_token.py](../scripts/mint_refresh_token.py)
binds. If you change the port in `.env`, change it here too — they must match
exactly or Entra will reject the callback.

## Step 4 — Record the Application (client) ID and Tenant value

On the app's **Overview** page, copy:

- **Application (client) ID** → this is the literal value you'll paste into
  `OUTLOOK_CLIENT_ID` in `.env`.
- **Directory (tenant) ID** → a GUID. For Entra admin-center navigation this is
  the value you'll see referenced; for `OUTLOOK_TENANT_ID` in `.env` you paste
  the **routing value** that matches your account-type choice in Step 2:
  - Personal MS account → `consumers`
  - Work/school single tenant → paste the GUID itself
  - Mixed-mode → `common`

## Step 5 — Create the client secret

Go to **Certificates & secrets → Client secrets → New client secret**.

| Field | Value |
| --- | --- |
| Description | `MailBot bootstrap secret` |
| Expires | 24 months (or your org's max policy) |

Click **Add**.

**CRITICAL:** copy the **Value** column immediately — once you navigate away
from this page, Entra hides the value forever and you'll have to generate a new
secret. Paste it into a temporary scratch buffer; you'll move it to `.env` in
Step 8.

## Step 6 — Grant delegated API permissions

Go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions**.

Search for and tick:

- `User.Read`
- `Mail.Read`
- `Mail.ReadWrite`
- `Mail.Send`
- `offline_access` ← this is the one that makes refresh tokens come back. Easy
  to miss; without it, the OAuth flow succeeds but issues only an access token
  (1 hour validity) and no refresh token.

Click **Add permissions**.

If a **Grant admin consent for `<tenant>`** button is offered (work/school
tenants typically show it), click it. For personal accounts the consent happens
interactively in Step 7's browser flow.

## Step 7 — Pre-flight checklist

Before running [scripts/mint_refresh_token.py](../scripts/mint_refresh_token.py),
confirm you have all four values:

- [ ] Client ID (from Step 4)
- [ ] Tenant routing value: `consumers` / GUID / `common` (from Step 4 + Step 2)
- [ ] Client secret **value** (from Step 5)
- [ ] Redirect URI: `http://localhost:8765/callback` (matches Step 3)

Put them in your local dev-box `.env`:

```dotenv
OUTLOOK_CLIENT_ID=<client-id-from-step-4>
OUTLOOK_TENANT_ID=consumers
OUTLOOK_CLIENT_SECRET=<value-from-step-5>
OUTLOOK_REDIRECT_URI=http://localhost:8765/callback
```

These are dev-box only — they do **not** go on the VPS yet. The VPS gets the
refresh token after Step 8 finishes.

## Step 8 — First-time mint walkthrough

On your local dev box, with the venv activated:

```bash
python scripts/mint_refresh_token.py
```

Expected operator experience:

1. The terminal prints a one-line status: `"Opening browser to consumers
   consent page; awaiting callback on http://127.0.0.1:8765/ ..."`.
2. Your default browser opens to the Microsoft sign-in page. Sign in with the
   account that owns the target mailbox. Consent to the requested permissions
   (the same five from Step 6).
3. After consent, the browser is redirected to
   `http://localhost:8765/callback?code=...&state=...`. The script's local HTTP
   server captures the callback, returns a one-line "Success — you may close
   this tab" page, and shuts down.
4. The script exchanges the code for tokens and prints to **stdout**:

   ```text
   ===== REFRESH TOKEN (paste into VPS .env as OUTLOOK_REFRESH_TOKEN) =====
   M.C5...<long token string>
   ===== END =====
   expires_in: 3600
   granted_scope: offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send
   ```

   Exit code `0`. Total elapsed time: ~10 seconds.

5. Copy the value between the marker lines (NOT the marker lines themselves)
   into your VPS `.env`:

   ```bash
   ssh vps.example.com
   sudo -u mailbot vi /srv/mailbot/.env
   # Paste: OUTLOOK_REFRESH_TOKEN=M.C5...
   # Save & exit. Verify chmod 600 /srv/mailbot/.env.
   ```

6. **Best practice:** run from a local terminal, not over SSH; clear scrollback
   after copy (`clear; printf '\\e[3J'` on most shells). The refresh token is
   the keys-to-the-mailbox secret — treat it like a password.

## Step 9 — Verify the minted token authenticates (Phase 3.5 check)

Still on the dev box, populate the four runtime env vars then run the smoke
script that ships with Story 1-5:

```bash
export OUTLOOK_REFRESH_TOKEN=<paste the same value here>
python scripts/check_graph_auth.py
```

Expected output: `OK: signed in as 'Your Name' ('your-account@outlook.com')`,
exit code `0`. If you get a non-zero exit, the most common causes:

- Tenant value wrong (e.g., set to a GUID for a personal account → use `consumers`)
- `offline_access` not granted in Step 6 — re-do Step 6 and Step 8
- Client secret expired (24-month limit set in Step 5) — generate a new one in
  Step 5 and re-do Step 8

Once `check_graph_auth.py` prints OK locally, the same token is paste-ready
for the VPS `.env`.

## Recovery (refresh token lost or revoked)

See [docs/auth-recovery.md](./auth-recovery.md). The high-level flow is:
re-run `python scripts/mint_refresh_token.py` on your dev box, paste the new
token into the VPS `.env`, delete the `oauth_state` row so the bootstrap-seed
path re-engages, restart the container.

## Common failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Browser shows `AADSTS50011: redirect URI mismatch` | The script's redirect URI does not exactly match the one registered in Step 3 | Re-check Step 3; URL must be byte-identical including trailing slash |
| Script prints `FATAL: state mismatch` | Someone else's callback arrived first, OR the browser session is from an old run | Re-run the script; close any stale browser tabs from previous runs |
| Script prints `FATAL: token exchange failed status=400 body={'error': 'invalid_client'}` | Client secret value wrong or expired | Re-do Step 5; paste the new secret into `.env`; re-run |
| Script prints `FATAL: token exchange failed status=400 body={'error': 'invalid_grant'}` | Auth code was reused or expired (codes are single-use, valid ~10 min) | Re-run the script — the code is regenerated each run |
| Token response has no `refresh_token` field | `offline_access` not requested or not granted | Re-do Step 6 (ensure `offline_access` is ticked); re-do Step 8 |
| Script appears to hang after "Opening browser..."; no browser tab opens | WSL or headless dev box where `webbrowser.open` silently no-ops | The script also prints the authorize URL to stderr — copy it into any browser manually. Then complete sign-in/consent; the callback to `localhost:8765` still works because the redirect goes to your local machine |

## References

- [Microsoft Graph OAuth 2.0 Authorization Code flow](https://learn.microsoft.com/en-us/graph/auth-v2-user)
- Local archive: [docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md](./external/learn-microsoft-azure/pages/graph/auth-v2-user.md)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://datatracker.ietf.org/doc/html/rfc8252) (why `http://localhost` is allowed without TLS)
- [scripts/mint_refresh_token.py](../scripts/mint_refresh_token.py) — the bootstrap script itself
- [scripts/check_graph_auth.py](../scripts/check_graph_auth.py) — the Phase 3.5 verification script (Story 1-5)
- [docs/auth-recovery.md](./auth-recovery.md) — what to do when a refresh token is lost in production
