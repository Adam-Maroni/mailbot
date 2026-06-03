# VPS setup runbook

Operator-facing checklist for taking MailBot from a fresh Hostinger KVM 2 (Ubuntu 24.04) to a running production stack.

This runbook is consumed by `scripts/setup_vps.sh` (prints a pointer to it at the end) and by Adam on first deploy.

## §1 — Pre-requisites

- Hostinger KVM 2 instance running **Ubuntu 24.04 LTS**.
- Root SSH access (the default `root@<vps>` Hostinger account is fine for the bootstrap).
- Your dev box has:
  - `git` checkout of the MailBot repo
  - `docker compose` available locally for the build step
  - SSH key authorized for both `root@<vps>` (bootstrap) and `mailbot@<vps>` (deploys)
- Story 4-0 credentials captured in your local `.env` — you'll re-paste them onto the VPS in §3.

## §2 — Initial setup

```sh
# From your dev box:
scp scripts/setup_vps.sh root@<vps>:/tmp/

ssh root@<vps>
bash /tmp/setup_vps.sh
```

What `setup_vps.sh` does (idempotently):

1. Installs Docker Engine + compose plugin via the official Docker apt repository.
2. Creates a `mailbot` service user (no shell, no sudo, member of `docker` group).
3. Creates `/opt/mailbot/{data,hermes-data,ollama,logs,backups}` at mode `0700` owned by `mailbot:mailbot`.
4. Writes a `/opt/mailbot/.env` stub at mode `0600` — values empty per Rule U (operator-populated).
5. Prints next-step instructions (same content as §3-§6 below).

Re-running the script is safe; it skips any step whose target state already exists.

## §3 — Populate `.env`

```sh
ssh root@<vps>
sudo -u mailbot vi /opt/mailbot/.env
```

Re-paste every value Story 4-0 captured in your local `.env`. The stub documents which keys are required.

Critical reminders:

- `MAILBOT_ROUTER_KEY` — same value as your local `.env` (Story 2-10's bearer token used for `/admin/*` endpoints + Hermes's main inference)
- `ANTHROPIC_API_KEY` — fallback-only; provisioned via the CLI in §4 below
- `PUID` / `PGID` — set to the mailbot user's host UID/GID. Find via `id -u mailbot ; id -g mailbot`

## §3.5 — Hermes config shape (F6 closure — load-bearing)

`hermes-config/config.yaml` ships pre-configured. One value is load-bearing and easy to break inadvertently when editing for a new VPS:

> `mcp_servers.mailbot-api.url` MUST end with a trailing slash (`http://mailbot-api:8000/mcp/`, NOT `http://mailbot-api:8000/mcp`).

Without the trailing slash, FastAPI's `Mount("/mcp", ...)` issues a 307 redirect to `/mcp/` — and Hermes's MCP client does NOT follow 307 redirects on its bidirectional POST transport. Tool registration fails after 3 retries with `MCP server 'mailbot-api' initial connection failed`, and ALL 17 MCP tools (`find_emails`, `propose_action`, `render_spend_chart`, etc.) silently never appear in Hermes's tool registry. This was Story 6-0's F6 finding; Story 6-6.6 closed it via a paired `streamable_http_path="/"` server-side fix + the trailing-slash URL.

Verify with the schema-shape checker BEFORE `docker compose up`:

```sh
python scripts/check_hermes_config.py
```

Exit code 0 + `OK: hermes-config/config.yaml shape verified against real Hermes schema.` means safe. Any URL drift (including dropping the trailing slash) is surfaced with the expected-vs-actual diff.

## §4 — Hermes fallback provisioning (CLI-driven, NOT config-YAML)

Per [Story 6-0 RECONCILIATION-NOTES §6 item 3](../docs/external/hermes-agent/RECONCILIATION-NOTES.md), Hermes's `fallback_providers` chain is managed via the `hermes fallback` CLI — NOT via `hermes-config/config.yaml`. After the stack is up (§5), provision the NFR-OPS-6 fallback chain:

```sh
ssh mailbot@<vps>
docker compose -f /opt/mailbot/docker-compose.yml exec mailbot-hermes \
    hermes fallback add anthropic claude-opus-4-7
```

The fallback chain persists across container restarts (Hermes writes it to its own state dir, which lives on the `mailbot_hermes_data` named volume).

## §5 — First `deploy.sh`

```sh
# Pre-populate ~/.ssh/known_hosts so deploy.sh's StrictHostKeyChecking=yes
# doesn't reject the first connection (TOFU is MitM-vulnerable for an image
# tarball deploy — we require the host key to be vetted out-of-band).
ssh-keyscan -p 22 <vps-hostname-or-ip> >> ~/.ssh/known_hosts
# Verify the fingerprint matches what Hostinger emailed you on provisioning.

# Copy docker-compose.yml from your dev checkout to the VPS:
scp docker-compose.yml mailbot@<vps>:/opt/mailbot/

# Then on your dev box:
MAILBOT_VPS_HOST=<vps-hostname-or-ip> make deploy
```

What `scripts/deploy.sh` does:

1. `docker compose build mailbot-api` on the dev box.
2. `docker save mailbot-mailbot-api:latest -o /tmp/mailbot-api.tar`.
3. `scp` the tarball to the VPS.
4. SSH into the VPS, `docker load`, `docker compose up -d --no-deps mailbot-api` (Hermes + Ollama untouched per Rule T).
5. Polls `GET /health` for up to 60s; aborts with the last 30 log lines if health check fails.
6. On success, tails the new container's logs for 30s so startup issues surface.

Subsequent deploys: just `make deploy` (the env var stays in your shell).

To update Hermes or Ollama (rare): `ssh mailbot@<vps> 'cd /opt/mailbot && docker compose pull mailbot-hermes ollama && docker compose up -d'`.

## §6 — Cron entry for nightly backups

`setup_vps.sh` does NOT auto-install cron jobs (avoids invasive modification of user crontabs). Add this entry by hand:

```sh
ssh root@<vps>
sudo -u mailbot crontab -e
# Append:
0 3 * * * /usr/bin/bash /opt/mailbot/scripts/backup.sh >> /opt/mailbot/logs/backup.cron.log 2>&1
```

Idempotency reminder: if you re-run `setup_vps.sh` (e.g., after an OS upgrade), check the existing crontab BEFORE appending — `crontab -l | grep -q backup.sh && echo "already installed"`.

What `scripts/backup.sh` does (each night at 03:00 UTC):

1. SQLite online `.backup` via `docker exec` (non-locking; concurrent writes OK).
2. Tarballs the DB + `/opt/mailbot/hermes-data` (explicitly excluding `.env*` per NFR-SEC-6).
3. Optionally uploads to Backblaze B2 if `B2_BUCKET` env var is set (and `rclone` is installed).
4. Prunes local backups: weekday backups retained 14 days; Sunday backups retained 56 days.
5. Emits a JSON line to stdout + `/opt/mailbot/logs/backup.jsonl` (consumed by Story 6-1's status board).

## §7 — Backblaze B2 setup (optional remote backups)

If you want off-site backups (recommended for production):

```sh
ssh mailbot@<vps>

# Install rclone (one-time):
curl https://rclone.org/install.sh | sudo bash

# Configure the B2 remote interactively. You'll need a B2 application key
# (NOT the master key) with write access to your bucket.
rclone config
# - n (new remote)
# - mailbot-backups (or another name; doesn't matter — we use `b2:` below)
# - 4 (Backblaze B2)
# - <your B2 account id>
# - <your B2 application key>
# - n (no advanced config)
# - q (quit)

# Set B2_BUCKET in /opt/mailbot/.env to your bucket name.
sudo -u mailbot vi /opt/mailbot/.env
# Add: B2_BUCKET=mailbot-backups

# Then re-run backup.sh to verify the upload path:
sudo -u mailbot bash /opt/mailbot/scripts/backup.sh
# Check the JSON log line shows "b2_uploaded":true
```

If `B2_BUCKET` is unset OR `rclone` isn't installed, `backup.sh` silently skips the upload step. Local backups still write to `/opt/mailbot/backups/`.

## §8 — Recovery checklist

When to use `scripts/restore.sh`:

- **VPS disk failure / full loss**: provision a new VPS, run §2-§5, then `restore.sh` from your most recent backup tarball (B2 download or local copy).
- **DB corruption** (rare): stop the stack, `restore.sh` from a known-good backup.
- **Application-level data corruption** (e.g., a bad migration): restore from the backup before the migration ran.

Steps:

```sh
ssh root@<vps>

# Verify the tarball exists and is the version you want:
ls -lh /opt/mailbot/backups/

# Run the restore. Tarball age > 48h emits a warning but does not abort.
sudo bash /opt/mailbot/scripts/restore.sh /opt/mailbot/backups/mailbot-YYYYMMDD-HHMMSS.tar.gz
```

What `scripts/restore.sh` does:

1. Warns if the tarball is > 48h old (operator's call to proceed).
2. Stops `mailbot-api` + `mailbot-hermes` via `docker compose stop`.
3. Extracts the tarball; moves `mailbot.db` to `/opt/mailbot/data/` and `hermes-data/` to `/opt/mailbot/hermes-data/`.
4. Chowns both back to `mailbot:mailbot`.
5. Restarts the containers via `docker compose start`.
6. Waits up to 30s for `/health` to return 200.
7. Runs `mailbot status` to confirm.

For B2-stored backups, fetch first:

```sh
ssh mailbot@<vps>
rclone copy "b2:$B2_BUCKET/mailbot/mailbot-YYYYMMDD-HHMMSS.tar.gz" /tmp/
sudo bash /opt/mailbot/scripts/restore.sh /tmp/mailbot-YYYYMMDD-HHMMSS.tar.gz
```

## §9 — Validation gates (dev-loop quickcheck)

Before pushing any change to the 4 deploy scripts, run on your dev box:

```sh
# Syntax check.
bash -n scripts/setup_vps.sh
bash -n scripts/deploy.sh
bash -n scripts/backup.sh
bash -n scripts/restore.sh

# If shellcheck is installed, run it on all 4.
shellcheck scripts/setup_vps.sh scripts/deploy.sh scripts/backup.sh scripts/restore.sh

# The full lifecycle test (docker-in-docker — heavy, @manual):
bash tests/integration/test_deploy_scripts.sh
```

The test harness requires Docker Desktop or a docker-in-docker-capable host; it's documented as `@manual` (not run by default `pytest`). Phase 3.5 verification surface for end-of-epic walks.
