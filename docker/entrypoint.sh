#!/usr/bin/env bash
# Container entrypoint per architecture §D7-1: two processes inside one container —
# background worker + foreground uvicorn. tini (PID 1, set in Dockerfile ENTRYPOINT)
# handles signal forwarding and zombie reaping.
#
# AC contract from Story 1-8: if EITHER process dies, the container must exit
# (so Docker can restart it). `wait -n` returns as soon as any child exits and
# we propagate the exit code, guaranteeing the worker is not silently swallowed.

set -euo pipefail

# Dev-mode reload flag (set by docker-compose.override.yml via env var).
UVICORN_RELOAD_FLAG=""
if [ "${UVICORN_RELOAD:-0}" = "1" ]; then
    UVICORN_RELOAD_FLAG="--reload"
fi

# Background the worker. tini (PID 1) reaps when this script eventually exits.
python -m mailbot_api.worker &
WORKER_PID=$!

# Background uvicorn too — we need the shell alive to `wait -n` on either.
# `exec` is NOT used here (per CR-9): exec would replace the shell and break wait.
# shellcheck disable=SC2086 # UVICORN_RELOAD_FLAG may be empty; word splitting is intentional
uvicorn mailbot_api.main:app --host 0.0.0.0 --port 8000 $UVICORN_RELOAD_FLAG &
UVICORN_PID=$!

# Forward SIGTERM/SIGINT to both children, then wait for them to exit cleanly.
trap 'kill -TERM "$WORKER_PID" "$UVICORN_PID" 2>/dev/null || true' TERM INT

# `wait -n` returns as soon as ANY child exits. We then propagate that exit code
# so Docker treats the container as failed and triggers `restart: unless-stopped`.
wait -n
EXIT_CODE=$?

# Whichever process is still alive — kill it so we don't leave orphans.
kill -TERM "$WORKER_PID" "$UVICORN_PID" 2>/dev/null || true
wait 2>/dev/null || true

exit $EXIT_CODE
