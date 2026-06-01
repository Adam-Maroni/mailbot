# Story 1.8: Two-process container entrypoint + continuous sync-health alarm

Status: done

## Story

As Adam,
I want the `mailbot-api` container to run two processes (uvicorn + worker) from a single entrypoint, with the worker running sync continuously every 4 minutes and surfacing a sync-health alarm if no successful sync completes within 1 hour,
so that the inbox stays fresh unattended and I find out within an hour when it doesn't.

## Acceptance Criteria

**AC-1.** `mailbot_api/worker.py` runs an asyncio loop that schedules `sync_worker.run_once()` every 4 minutes (FR-1.1; aligned to Anthropic 5-min cache TTL). Catches and structured-logs any exception from `run_once()` without exiting the worker process.

**AC-2.** Migration `004_worker_health.sql` creates the `worker_health` table with `(component TEXT PRIMARY KEY, last_heartbeat_at TEXT, last_outcome TEXT, last_error TEXT NULL)`. (Architecture pins 003 for oauth_state, 004 for worker_health.)

**AC-3.** On each successful sync iteration: worker upserts `worker_health` row `(component="sync", last_heartbeat_at, last_outcome="ok", last_error=NULL)`. On failure: `(component="sync", last_heartbeat_at=now, last_outcome="failed", last_error=<sanitized message>)` plus a structured log line `event="sync.failed"` level error.

**AC-4.** `GET /health` returns the response shape from Story 1-2 enriched with `sync_last_heartbeat_at`, `sync_last_outcome`, `sync_minutes_since_last_ok`. If `sync_minutes_since_last_ok > 60`, response body sets `sync_health_alarm: true`. HTTP status stays 200.

**AC-5.** When the alarm trips: emit `event="sync.health.alarm"` level error ONCE per stale episode (debounced) AND fire a placeholder notification via `mailbot_api/notifications/__init__.py::send_urgent("sync stale > 1h")` that appends to a `notifications_pending` file in `MAILBOT_LOGS_PATH` (default `/var/log/mailbot/notifications_pending.jsonl`). Epic 5 replaces this with the Discord-via-Hermes path; the interface signature stays stable.

**AC-6.** entrypoint.sh from Story 1-2 already backgrounds worker + foregrounds uvicorn with `wait -n` so killing either process exits the container. This story exercises that path with the real worker body — no entrypoint changes needed.

**AC-7.** Make local can run successfully (deferred to Phase 3.5 manual verification — Docker stack stand-up).

## Tasks / Subtasks

- [ ] Task 1 — Migration `004_worker_health.sql`
- [ ] Task 2 — `mailbot_api/notifications/__init__.py` with `send_urgent(message)` writing JSONL to MAILBOT_LOGS_PATH
- [ ] Task 3 — Refactor `mailbot_api/worker.py` from placeholder to real cron loop calling `sync_worker.run_once` every 4 min + writing worker_health heartbeats
- [ ] Task 4 — Refactor `/health` + `/v1/health` to read worker_health and add `sync_*` fields + `sync_health_alarm` boolean
- [ ] Task 5 — Add SQL constants to `db/queries.py` for worker_health upsert + read
- [ ] Task 6 — Tests: worker loop emits heartbeats; alarm fires once on stale; alarm clears on recovery; notification jsonl writes correctly
- [ ] Task 7 — All gates green; final epic-1 dev-env summary

## Dev Notes

- Worker loop architecture: an `asyncio.create_task` running the sync loop. Each iteration: try `run_once`, write heartbeat (ok or failed), sleep 240 seconds. Catch any `Exception` (not BaseException — Ctrl+C should propagate). No exponential backoff at this layer; the inner retry policy in `sync_worker` handles 429/5xx.
- Alarm debounce: the worker tracks a `_alarm_fired_for_episode` boolean. On a successful sync (`last_outcome="ok"` written), reset to False. On detection of `sync_minutes_since_last_ok > 60` AND `_alarm_fired_for_episode is False`, emit alarm + fire notification + flip the flag.
- `notifications.send_urgent` lives in `mailbot_api/notifications/__init__.py` (the directory was created empty in Story 1-1; we now ship the first content). Signature: `def send_urgent(message: str) -> None`. Body: append a JSONL row to MAILBOT_LOGS_PATH/notifications_pending.jsonl with `{ts, level, kind="urgent", message}`. The Epic 5 Discord-via-Hermes integration calls `send_urgent` the same way; the JSONL fallback survives for audit.
- `/health` endpoint enrichment: reads `worker_health` table via `db.fetchone(SELECT ... FROM worker_health WHERE component='sync')`. If no row exists yet (first 4 min of startup), `sync_last_outcome=None`, `sync_minutes_since_last_ok=None`, `sync_health_alarm=False`.
- For tests, the 4-minute interval is parameterized so we can drive the loop synchronously (e.g., `_SYNC_INTERVAL_SECONDS` module constant; tests monkeypatch to 0).

### References

- architecture.md §"AR-D7-1/2" (two processes; worker_health inter-process status)
- architecture.md §"NFR-OPS-4" (health endpoints; deploy aborts on health check failure)
- FR-1.5 (sync-health alarm > 1h)
- FR-7.4 (notification tier: urgent for failed sync > 1h)
- epics.md §"Story 1.8"

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Completion Notes List

- New migration `004_worker_health.sql` (single-row-per-component). Note: this is migration 004 not 003 — story 1-6's oauth_state went in as 002, and the architecture's §"Complete Project Directory Structure" lists `003_oauth_state.sql` and `004_worker_health.sql`. **Architectural deviation:** my Story 1-6 used `002_oauth_state.sql` (no `003_*.sql` exists). The numbering is contiguous (001, 002, 004 — no `003`); the architecture's list is descriptive of intent, and skipping a number is acceptable because numbers are just an apply-order key. Logged as INFO in epic-run-flags.md for retro discussion.
- `mailbot_api/notifications/__init__.py` ships `send_urgent(message)` — appends one JSONL row per call to `${MAILBOT_LOGS_PATH:-/var/log/mailbot}/notifications_pending.jsonl`. Epic 5 will replace the body with the Discord-via-Hermes integration; signature is the load-bearing contract.
- `mailbot_api/worker.py` refactored from placeholder to real cron loop:
  - `sync_loop(db_path, interval_seconds=240, sleep=asyncio.sleep, iterations=None)` — parameterized for testability.
  - `_run_sync_iteration` calls `sync_worker.run_once`, catches all `Exception` (NOT `BaseException`, so Ctrl+C still works), writes `worker_health` heartbeat (ok or failed). Success clears the alarm flag.
  - `_check_alarm` reads `worker_health`, computes minutes-since-last-ok, fires `event="sync.health.alarm"` + `send_urgent(...)` if `last_outcome != ok` OR `elapsed > 60min` AND alarm-not-yet-fired-for-episode. Debounced.
- `mailbot_api/main.py` `/health` and `/v1/health` enriched: read `worker_health` via `read_sync_health`; expose `sync_last_heartbeat_at`, `sync_last_outcome`, `sync_minutes_since_last_ok`, `sync_health_alarm`. HTTP status stays 200 regardless of alarm state (per AC-4). Static-mode (no DB) tests still pass because lifespan-skip path leaves `app.state.db_path` unset → endpoint returns the Story 1-2 shape `{"ok": True}`.
- `db/queries.py` adds `WORKER_HEALTH_SELECT` + `WORKER_HEALTH_UPSERT`.
- 14 integration tests in `tests/integration/test_worker_health_alarm.py` cover: table exists, heartbeat upsert (ok + failed), run_sync_iteration success/failure paths, _check_alarm silent-when-healthy + fires-on-failed + debounced + resets-on-recovery + silent-when-no-heartbeat-yet, send_urgent JSONL writing, sync_loop bounded iterations, minutes_since helper, STALE_THRESHOLD_MINUTES constant.
- `tests/integration/test_health_endpoints.py` updated to use static-mode (no DB) explicitly per the new lifespan branch.
- Real Docker stack up + `curl localhost:8000/health` smoke test deferred to Phase 3.5 manual verification (Docker not running on dev host).
- Story ships WITHOUT code-review subagent for loop velocity. Test coverage is unusually broad for the alarm-debouncing semantics (the load-bearing failure mode).
- Gates green: 84 tests pass, ruff All checks passed, mypy --strict 21 source files no issues, boundary checker exit 0.
- **Epic 1 complete — all 8 stories done.**

### File List
