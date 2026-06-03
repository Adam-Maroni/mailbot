#!/usr/bin/env bash
# Story 6-7: nightly SQLite + hermes-data backup.
#
# Runs ON the VPS as the mailbot user (via cron). Uses SQLite's `.backup`
# command via docker exec — non-locking online backup that survives
# concurrent writes from the running worker.
#
# Optional env vars:
#   B2_BUCKET           — if set, rclone copy to b2:$B2_BUCKET/mailbot/
#   MAILBOT_HOME        — base dir (default /opt/mailbot)
#   MAILBOT_RETENTION_DAYS — daily retention (default 14)
#   MAILBOT_WEEKLY_RETENTION_DAYS — Sunday retention (default 56)
#
# Before any production change, run: shellcheck scripts/backup.sh
set -euo pipefail

MAILBOT_HOME="${MAILBOT_HOME:-/opt/mailbot}"
BACKUP_DIR="$MAILBOT_HOME/backups"
LOG_DIR="$MAILBOT_HOME/logs"
LOG_FILE="$LOG_DIR/backup.jsonl"

RETENTION_DAYS="${MAILBOT_RETENTION_DAYS:-14}"
WEEKLY_RETENTION_DAYS="${MAILBOT_WEEKLY_RETENTION_DAYS:-56}"

DATE="$(date -u +%Y%m%d-%H%M%S)"
# CR-3 (Story 6-7 review 2026-06-03): separate container-side and host-side
# paths to make the docker exec / docker cp cross-boundary copy explicit
# and safe against future path divergence. They happen to use the same
# /tmp prefix today; the variable split documents the boundary.
CONTAINER_DB_SNAPSHOT="/tmp/mailbot-${DATE}.db"
HOST_DB_SNAPSHOT="/tmp/mailbot-${DATE}.db"
HOST_DB_BASENAME="mailbot-${DATE}.db"
TARBALL="$BACKUP_DIR/mailbot-${DATE}.tar.gz"

# Cleanup on EXIT — never leave the DB snapshot lying around (host or container).
trap 'rm -f "$HOST_DB_SNAPSHOT"; docker exec mailbot-api rm -f "$CONTAINER_DB_SNAPSHOT" >/dev/null 2>&1 || true' EXIT

log() {
    printf '[backup] %s\n' "$*" >&2
}

emit_json() {
    # Emit to BOTH stdout (cron picks up) AND the log file.
    local line="$1"
    printf '%s\n' "$line"
    mkdir -p "$LOG_DIR"
    printf '%s\n' "$line" >> "$LOG_FILE"
}

emit_completed() {
    local size_bytes b2_uploaded ts
    size_bytes="$(stat -c '%s' "$TARBALL" 2>/dev/null || echo 0)"
    b2_uploaded="$1"
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
    emit_json "{\"event\":\"backup.completed\",\"timestamp\":\"$ts\",\"tarball\":\"$TARBALL\",\"size_bytes\":$size_bytes,\"b2_uploaded\":$b2_uploaded}"
}

emit_failed() {
    local step="$1"
    local error="$2"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
    emit_json "{\"event\":\"backup.failed\",\"timestamp\":\"$ts\",\"step\":\"$step\",\"error\":\"$error\"}"
}

# Wrap each step so a failure routes through emit_failed + exit 1.
on_fail() {
    emit_failed "$CURRENT_STEP" "${1:-unknown}"
    exit 1
}

snapshot_sqlite() {
    CURRENT_STEP="snapshot_sqlite"
    log "Taking SQLite online backup via docker exec..."
    # SQLite's .backup is non-locking: writes continue while the backup runs.
    docker exec mailbot-api sqlite3 /data/mailbot.db ".backup '$CONTAINER_DB_SNAPSHOT'"
    # Copy the snapshot OUT to host so we can tar from /tmp.
    docker cp "mailbot-api:$CONTAINER_DB_SNAPSHOT" "$HOST_DB_SNAPSHOT"
}

create_tarball() {
    CURRENT_STEP="create_tarball"
    log "Creating tarball $TARBALL (excluding .env* and __pycache__)..."
    mkdir -p "$BACKUP_DIR"
    # CR-4 (Story 6-7 review 2026-06-03): move --exclude flags BEFORE the
    # first -C operand per GNU tar man-page convention + shellcheck SC2035.
    # POSIX tar does not guarantee exclude-after-operand ordering; GNU tar
    # tolerates it, but our deploy targets MAY use BusyBox tar in dind tests
    # which is stricter.
    # Defensive --exclude='.env*' even though we don't list .env as input —
    # NFR-SEC-6 belt-and-suspenders.
    tar --exclude='.env*' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        -czf "$TARBALL" \
        -C /tmp "$HOST_DB_BASENAME" \
        -C "$MAILBOT_HOME" hermes-data
}

upload_to_b2() {
    CURRENT_STEP="upload_to_b2"
    if [ -z "${B2_BUCKET:-}" ]; then
        log "B2_BUCKET not set — skipping remote upload"
        echo "false"
        return 0
    fi
    if ! command -v rclone >/dev/null 2>&1; then
        log "rclone not installed — skipping remote upload (B2_BUCKET=$B2_BUCKET set but unusable)"
        echo "false"
        return 0
    fi
    log "Uploading $TARBALL to b2:$B2_BUCKET/mailbot/..."
    rclone copy "$TARBALL" "b2:$B2_BUCKET/mailbot/"
    echo "true"
}

prune_old_backups() {
    CURRENT_STEP="prune_old_backups"
    log "Pruning local backups older than $RETENTION_DAYS days (Sundays: $WEEKLY_RETENTION_DAYS days)..."
    # Loop over old files; check day-of-week on the file's name to decide
    # which retention applies. File name pattern: mailbot-YYYYMMDD-HHMMSS.tar.gz
    local file basename date_part day_of_week age_days
    if [ ! -d "$BACKUP_DIR" ]; then
        return 0
    fi
    while IFS= read -r -d '' file; do
        basename="$(basename "$file")"
        # Extract YYYYMMDD from "mailbot-YYYYMMDD-HHMMSS.tar.gz"
        date_part="${basename#mailbot-}"
        date_part="${date_part:0:8}"
        # Sunday = 0 (per `date -d "$date_part" +%w`)
        day_of_week="$(date -d "$date_part" +%w 2>/dev/null || echo X)"
        # File age in days.
        age_days="$(( ($(date +%s) - $(stat -c %Y "$file")) / 86400 ))"
        # CR-5 (Story 6-7 review 2026-06-03): if filename has an unparseable
        # date_part, skip pruning rather than falling through to weekday
        # retention (which would prune a possibly-Sunday backup at 14 days
        # instead of 56). Operator surfaces the parse failure via WARNING.
        if [ "$day_of_week" = "X" ]; then
            log "WARNING: unparseable date in $basename — skipping prune"
            continue
        fi
        if [ "$day_of_week" = "0" ]; then
            # Sunday weekly backup — keep up to WEEKLY_RETENTION_DAYS.
            if [ "$age_days" -gt "$WEEKLY_RETENTION_DAYS" ]; then
                log "Pruning weekly $file (age=${age_days}d > ${WEEKLY_RETENTION_DAYS}d)"
                rm -f "$file"
            fi
        else
            # Weekday daily backup — keep up to RETENTION_DAYS.
            if [ "$age_days" -gt "$RETENTION_DAYS" ]; then
                log "Pruning daily $file (age=${age_days}d > ${RETENTION_DAYS}d)"
                rm -f "$file"
            fi
        fi
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'mailbot-*.tar.gz' -type f -print0)
}

main() {
    CURRENT_STEP="init"
    snapshot_sqlite || on_fail "$?"
    create_tarball || on_fail "$?"
    local b2_uploaded
    b2_uploaded="$(upload_to_b2)" || on_fail "$?"
    prune_old_backups || on_fail "$?"
    emit_completed "$b2_uploaded"
    log "Backup complete: $TARBALL"
}

main "$@"
