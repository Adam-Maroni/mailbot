#!/usr/bin/env bash
# Story 6-7: one-time Hostinger KVM 2 (Ubuntu 24.04) bootstrap.
#
# Idempotent: every step checks current state before mutating. Re-running
# produces zero state changes when state is already correct, and zero
# errors. Tested via tests/integration/test_deploy_scripts.sh (@manual,
# docker-in-docker fixture).
#
# Run as root, ON the VPS:
#   scp scripts/setup_vps.sh root@<vps>:/tmp/
#   ssh root@<vps> bash /tmp/setup_vps.sh
#
# Before any production change, run: shellcheck scripts/setup_vps.sh
set -euo pipefail

MAILBOT_HOME="/opt/mailbot"
MAILBOT_USER="mailbot"

log() {
    printf '[setup_vps] %s\n' "$*" >&2
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "FATAL: setup_vps.sh must run as root (got uid=$(id -u))"
        exit 1
    fi
}

install_docker() {
    # Official Docker Engine + compose plugin per docs.docker.com instructions
    # for Ubuntu 24.04.
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        log "Docker + compose plugin already present — skipping install"
        return 0
    fi
    log "Installing Docker Engine + compose plugin..."

    # Remove unofficial packages that might clash with docker-ce.
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    apt-get update
    apt-get install -y ca-certificates curl gnupg

    # Set up Docker's official GPG key + apt repository.
    install -m 0755 -d /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
    fi

    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update
    fi

    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    log "Docker installed: $(docker --version)"
}

create_service_user() {
    if id "$MAILBOT_USER" >/dev/null 2>&1; then
        log "User '$MAILBOT_USER' already exists — skipping useradd"
    else
        log "Creating service user '$MAILBOT_USER' (no shell, no sudo)..."
        useradd --system --no-create-home --shell /usr/sbin/nologin "$MAILBOT_USER"
    fi

    # Always idempotent: usermod -aG is safe to re-run.
    if ! id -nG "$MAILBOT_USER" | tr ' ' '\n' | grep -qx docker; then
        log "Adding '$MAILBOT_USER' to docker group..."
        usermod -aG docker "$MAILBOT_USER"
    fi
}

create_directories() {
    # /opt/mailbot + subdirs at 0700 owned by mailbot:mailbot.
    for d in "" data hermes-data ollama logs backups; do
        local target="$MAILBOT_HOME${d:+/$d}"
        if [ ! -d "$target" ]; then
            log "Creating $target"
            install -d -o "$MAILBOT_USER" -g "$MAILBOT_USER" -m 0700 "$target"
        else
            # Idempotency: re-chown/chmod is safe.
            chown "$MAILBOT_USER:$MAILBOT_USER" "$target"
            chmod 0700 "$target"
        fi
    done
}

create_env_stub() {
    local env_file="$MAILBOT_HOME/.env"
    if [ -f "$env_file" ]; then
        log "/opt/mailbot/.env already present — preserving operator-edited content"
        return 0
    fi
    log "Writing empty /opt/mailbot/.env stub (operator must populate per Rule U)"
    # CR-7 (Story 6-7 review 2026-06-03): write the heredoc to a temp file
    # FIRST, then `install -m 0600 -o mailbot -g mailbot $tmp $env_file`
    # which atomically replaces the destination with the right mode/owner.
    # Original (install /dev/null + cat redirect) had a window where the
    # file was root-owned + 0600 + potentially partial heredoc if the
    # script died mid-write. The temp-then-install pattern eliminates the
    # window.
    local tmpfile
    tmpfile="$(mktemp -t mailbot-env-XXXXXX)"
    # Ensure tmpfile is cleaned up even on heredoc failure.
    trap 'rm -f "$tmpfile"' RETURN
    cat > "$tmpfile" <<'ENV_EOF'
# /opt/mailbot/.env — operator-populated production secrets.
#
# Story 6-7 created this stub via setup_vps.sh. Story 4-0's credential
# capture flow walked Adam through populating every key. Re-run the
# Story 4-0 flow (in dev / on the VPS interactively) to refresh.

# Discord
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USERS=
DISCORD_HOME_CHANNEL=

# UID/GID alignment for Hermes container (production-Linux specific).
# Run: id -u mailbot ; id -g mailbot
PUID=
PGID=

# Anthropic — NFR-OPS-6 fallback only (set via `hermes fallback add ...`
# after the stack is up; see docs/setup-vps-runbook.md §4).
ANTHROPIC_API_KEY=

# Microsoft Graph OAuth.
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_TENANT_ID=
OUTLOOK_REFRESH_TOKEN=

# Container-config + bearer key.
MAILBOT_DB_PATH=/data/mailbot.db
MAILBOT_POLICY_PATH=/app/router/policy.yaml
OLLAMA_URL=http://ollama:11434
MAILBOT_ROUTER_KEY=
ENV_EOF
    # Atomic install: temp file → /opt/mailbot/.env with right mode/owner
    # in a single syscall. No mid-write window.
    install -m 0600 -o "$MAILBOT_USER" -g "$MAILBOT_USER" "$tmpfile" "$env_file"
}

print_next_steps() {
    cat <<'NEXT_EOF'

============================================================
  setup_vps.sh complete — operator next steps:
============================================================

  1. EDIT THE .env FILE WITH YOUR SECRETS:
       sudo -u mailbot vi /opt/mailbot/.env
     (Story 4-0 captured these in dev; re-paste the values.)

  2. COPY docker-compose.yml FROM YOUR DEV CHECKOUT:
       scp docker-compose.yml mailbot@<vps>:/opt/mailbot/

  3. RUN THE FIRST DEPLOY FROM YOUR DEV BOX:
       MAILBOT_VPS_HOST=<vps> make deploy

  4. (One-time) PROVISION HERMES FALLBACK CHAIN per
     docs/external/hermes-agent/RECONCILIATION-NOTES.md §6 item 3:
       sudo -u mailbot docker compose -f /opt/mailbot/docker-compose.yml \
           exec mailbot-hermes hermes fallback add anthropic claude-opus-4-7

  5. ENABLE NIGHTLY BACKUPS by appending this cron entry to the
     mailbot user's crontab (idempotently — grep first):
       0 3 * * * /usr/bin/bash /opt/mailbot/scripts/backup.sh \
           >> /opt/mailbot/logs/backup.cron.log 2>&1

  6. VERIFY: SSH into the VPS as root, then run
       sudo -u mailbot mailbot status
     (or equivalent CLI invocation per Story 6-1)

See docs/setup-vps-runbook.md for the full runbook.

============================================================
NEXT_EOF
}

main() {
    require_root
    install_docker
    create_service_user
    create_directories
    create_env_stub
    print_next_steps
}

main "$@"
