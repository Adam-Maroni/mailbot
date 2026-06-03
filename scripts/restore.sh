#!/usr/bin/env bash
# Story 6-7: disaster-recovery restore from backup tarball.
#
# Usage:
#   sudo bash scripts/restore.sh /opt/mailbot/backups/mailbot-YYYYMMDD-HHMMSS.tar.gz
#
# Runs ON the VPS as root. Stops containers; extracts; chowns; restarts;
# runs `mailbot status` to confirm health. Prints warning if backup is
# older than 48h (operator's call to proceed).
#
# Before any production change, run: shellcheck scripts/restore.sh
set -euo pipefail

MAILBOT_HOME="${MAILBOT_HOME:-/opt/mailbot}"
MAILBOT_USER="${MAILBOT_USER:-mailbot}"
COMPOSE_FILE="$MAILBOT_HOME/docker-compose.yml"
WORK_DIR="$(mktemp -d -t mailbot-restore-XXXXXX)"
LOG_FILE="$MAILBOT_HOME/logs/restore.jsonl"

trap 'rm -rf "$WORK_DIR"' EXIT

log() {
    printf '[restore] %s\n' "$*" >&2
}

emit_failed() {
    local step="$1"
    local error="$2"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '{"event":"restore.failed","timestamp":"%s","step":"%s","error":"%s"}\n' \
        "$ts" "$step" "$error" | tee -a "$LOG_FILE"
}

emit_completed() {
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '{"event":"restore.completed","timestamp":"%s","tarball":"%s"}\n' \
        "$ts" "$TARBALL" | tee -a "$LOG_FILE"
}

usage() {
    cat <<USAGE_EOF
Usage: $0 <tarball-path>

  Restore mailbot-api SQLite + hermes-data from a backup tarball
  produced by scripts/backup.sh. Stops + restarts the relevant
  containers. Must run as root on the VPS.

  Example:
    sudo bash $0 /opt/mailbot/backups/mailbot-20260603-030000.tar.gz
USAGE_EOF
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "FATAL: restore.sh must run as root (got uid=$(id -u))"
        exit 1
    fi
}

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    usage
    exit 2
fi
TARBALL="$1"

if [ ! -f "$TARBALL" ]; then
    log "FATAL: tarball not found: $TARBALL"
    exit 2
fi

check_age_warning() {
    local age_seconds tarball_mtime now
    now="$(date +%s)"
    tarball_mtime="$(stat -c %Y "$TARBALL")"
    age_seconds=$((now - tarball_mtime))
    if [ "$age_seconds" -gt 172800 ]; then
        local age_hours=$((age_seconds / 3600))
        log "WARNING: Restoring from a ${age_hours}h-old backup. You may have lost recent state."
    fi
}

stop_containers() {
    log "Stopping mailbot-api + mailbot-hermes..."
    cd "$MAILBOT_HOME"
    docker compose -f "$COMPOSE_FILE" stop mailbot-api mailbot-hermes
}

extract_tarball() {
    log "Extracting $TARBALL into $WORK_DIR..."
    tar -xzf "$TARBALL" -C "$WORK_DIR"

    # The tarball contains: mailbot-YYYYMMDD-HHMMSS.db + hermes-data/...
    local db_file
    db_file="$(find "$WORK_DIR" -maxdepth 1 -name 'mailbot-*.db' -type f | head -n 1)"
    if [ -z "$db_file" ]; then
        log "FATAL: no mailbot-*.db file found in tarball"
        return 1
    fi

    log "Restoring DB from $db_file to $MAILBOT_HOME/data/mailbot.db..."
    mkdir -p "$MAILBOT_HOME/data"
    mv "$db_file" "$MAILBOT_HOME/data/mailbot.db"

    if [ -d "$WORK_DIR/hermes-data" ]; then
        # CR-6 (Story 6-7 review 2026-06-03 — biggest concern): staged swap
        # so the existing hermes-data isn't deleted until the new copy is
        # in place. Original sequence (`rm -rf` then `mv`) had a window
        # under `set -euo pipefail` where a failed `mv` left BOTH copies
        # gone with no recovery path short of a fresh restore.
        local backup_dir="$MAILBOT_HOME/hermes-data.bak.$$"
        log "Restoring hermes-data (staged swap via $backup_dir)..."
        if [ -d "$MAILBOT_HOME/hermes-data" ]; then
            mv "$MAILBOT_HOME/hermes-data" "$backup_dir"
        fi
        if ! mv "$WORK_DIR/hermes-data" "$MAILBOT_HOME/hermes-data"; then
            log "FATAL: mv of new hermes-data failed; rolling back to $backup_dir"
            if [ -d "$backup_dir" ]; then
                mv "$backup_dir" "$MAILBOT_HOME/hermes-data"
            fi
            return 1
        fi
        # New copy is in place; safe to delete the backup.
        if [ -d "$backup_dir" ]; then
            rm -rf "$backup_dir"
        fi
    fi
}

chown_restored_dirs() {
    log "Chowning $MAILBOT_HOME/{data,hermes-data} back to $MAILBOT_USER..."
    chown -R "$MAILBOT_USER:$MAILBOT_USER" "$MAILBOT_HOME/data" "$MAILBOT_HOME/hermes-data"
}

start_containers() {
    log "Starting mailbot-api + mailbot-hermes..."
    cd "$MAILBOT_HOME"
    docker compose -f "$COMPOSE_FILE" start mailbot-api mailbot-hermes
}

wait_for_health() {
    log "Waiting 30s for /health to return 200..."
    local i
    for i in $(seq 1 15); do
        if curl -fsS -m 5 "http://localhost:8000/health" >/dev/null 2>&1; then
            log "/health returned 200 (attempt $i)"
            return 0
        fi
        sleep 2
    done
    log "WARNING: /health did NOT return 200 within 30s — investigate manually"
    return 1
}

run_status_check() {
    # Try the `mailbot` CLI if installed on PATH; fall back to docker exec.
    log "Running mailbot status to confirm health..."
    if command -v mailbot >/dev/null 2>&1; then
        mailbot status || true
    else
        # Fallback: docker exec into the container.
        docker exec mailbot-api python -m mailbot_api.cli status 2>/dev/null \
            || docker exec mailbot-api python scripts/mailbot.py status 2>/dev/null \
            || log "WARNING: could not run 'mailbot status' — verify manually"
    fi
}

main() {
    require_root
    check_age_warning

    local step
    step="stop_containers"
    if ! stop_containers; then emit_failed "$step" "container stop failed"; exit 1; fi

    step="extract_tarball"
    if ! extract_tarball; then emit_failed "$step" "extract failed"; exit 1; fi

    step="chown_restored_dirs"
    if ! chown_restored_dirs; then emit_failed "$step" "chown failed"; exit 1; fi

    step="start_containers"
    if ! start_containers; then emit_failed "$step" "container start failed"; exit 1; fi

    wait_for_health || true  # health-check failure logged but not fatal
    run_status_check

    emit_completed
    log "Restore complete. Verify with: mailbot status"
}

main "$@"
