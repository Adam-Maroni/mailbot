#!/usr/bin/env bash
# Story 6-7: build + ship mailbot-api from dev machine to VPS.
#
# `make deploy` → bash scripts/deploy.sh. Runs ON the dev machine; ssh's
# to the VPS for the install steps. Hermes + Ollama are NOT touched per
# Rule T (updated separately via `docker compose pull` on the VPS).
#
# Required env vars:
#   MAILBOT_VPS_HOST    — VPS hostname or IP (e.g., mailbot.example.com)
# Optional env vars:
#   MAILBOT_VPS_PORT    — SSH port (default 22)
#   MAILBOT_VPS_USER    — SSH user (default mailbot)
#   MAILBOT_IMAGE_TAG   — image tag to deploy (default mailbot-mailbot-api:latest)
#
# Before any production change, run: shellcheck scripts/deploy.sh
set -euo pipefail

: "${MAILBOT_VPS_HOST:?FATAL: MAILBOT_VPS_HOST env var required (e.g., MAILBOT_VPS_HOST=1.2.3.4)}"
MAILBOT_VPS_PORT="${MAILBOT_VPS_PORT:-22}"
MAILBOT_VPS_USER="${MAILBOT_VPS_USER:-mailbot}"
MAILBOT_IMAGE_TAG="${MAILBOT_IMAGE_TAG:-mailbot-mailbot-api:latest}"

TARFILE="$(mktemp -t mailbot-api-XXXXXX.tar)"
trap 'rm -f "$TARFILE"' EXIT

log() {
    printf '[deploy] %s\n' "$*" >&2
}

emit_deploy_json() {
    local outcome="$1"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)"
    printf '{"event":"deploy.%s","timestamp":"%s","vps_host":"%s","image_tag":"%s"}\n' \
        "$outcome" "$ts" "$MAILBOT_VPS_HOST" "$MAILBOT_IMAGE_TAG"
}

build_image() {
    log "Building mailbot-api image..."
    docker compose build mailbot-api
}

save_image() {
    log "Saving image to $TARFILE..."
    docker save "$MAILBOT_IMAGE_TAG" -o "$TARFILE"
    log "Image saved: $(du -h "$TARFILE" | cut -f1)"
}

scp_image() {
    # CR-2 (Story 6-7 review 2026-06-03): StrictHostKeyChecking=yes (NOT
    # accept-new) — TOFU on first connection is MitM-vulnerable for a deploy
    # carrying a production image tarball. Operator MUST pre-populate
    # ~/.ssh/known_hosts before first deploy:
    #   ssh-keyscan -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_HOST" >> ~/.ssh/known_hosts
    # See docs/setup-vps-runbook.md §5 for the documented one-liner.
    log "scp'ing image to $MAILBOT_VPS_USER@$MAILBOT_VPS_HOST:/tmp/mailbot-api.tar..."
    scp -P "$MAILBOT_VPS_PORT" -o StrictHostKeyChecking=yes \
        "$TARFILE" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST:/tmp/mailbot-api.tar"
}

ssh_run_remote() {
    # Single-shot ssh invocation. Loads the image, restarts the API container
    # only (--no-deps per AC; Hermes + Ollama stay).
    log "Loading image on VPS and restarting mailbot-api..."
    ssh -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST" \
        "set -euo pipefail && \
         docker load < /tmp/mailbot-api.tar && \
         cd /opt/mailbot && \
         docker compose up -d --no-deps mailbot-api && \
         rm -f /tmp/mailbot-api.tar"
}

wait_for_health() {
    # CR-1 (Story 6-7 review 2026-06-03): poll /health via SSH-tunneled
    # localhost call instead of curl against external IP:8000. Port 8000
    # is commonly NOT externally exposed in production (firewall hardening);
    # the external curl would always fail even when the container is healthy.
    # SSH-tunneled curl works regardless of external port exposure AND
    # doesn't require opening the firewall just for deploy verification.
    # 60s budget; 2s polling = 30 retries.
    log "Waiting for /health to return 200 (60s budget; SSH-tunneled)..."
    local i
    for i in $(seq 1 30); do
        if ssh -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST" \
            "curl -fsS -m 5 http://localhost:8000/health" >/dev/null 2>&1; then
            log "/health returned 200 (attempt $i)"
            return 0
        fi
        sleep 2
    done
    return 1
}

abort_with_logs() {
    log "FATAL: /health did NOT return 200 within 60s — fetching last 30 log lines..."
    ssh -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST" \
        "docker logs --tail 30 mailbot-api" >&2 || true
    # CR-8 (Story 6-7 review 2026-06-03): clean up the VPS-side tarball
    # even on deploy failure. The success-path `&&` chain in ssh_run_remote
    # bails before `rm -f /tmp/mailbot-api.tar` if docker compose up fails,
    # so repeated failed deploys would accumulate full image-sized tarballs.
    ssh -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST" \
        "rm -f /tmp/mailbot-api.tar" >/dev/null 2>&1 || true
    emit_deploy_json "failed"
    exit 1
}

tail_for_30s() {
    log "Tailing mailbot-api logs for 30s so startup issues surface..."
    # background ssh with `timeout` so we don't hang forever if the tail blocks.
    timeout 30 ssh -p "$MAILBOT_VPS_PORT" "$MAILBOT_VPS_USER@$MAILBOT_VPS_HOST" \
        "docker logs -f --tail 0 mailbot-api" || true
}

main() {
    build_image
    save_image
    scp_image
    ssh_run_remote
    if ! wait_for_health; then
        abort_with_logs
    fi
    tail_for_30s
    emit_deploy_json "completed"
    log "Deploy OK."
}

main "$@"
