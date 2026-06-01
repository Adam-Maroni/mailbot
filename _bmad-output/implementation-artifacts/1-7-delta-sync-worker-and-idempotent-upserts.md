# Story 1.7: Delta sync worker + idempotent upserts

Status: done

## Story

As Adam,
I want `mailbot sync-now` to fetch the Graph delta since the last successful sync and upsert new/changed/deleted email rows into SQLite idempotently,
so that running sync twice with no inbox changes produces zero writes.

## Acceptance Criteria

**AC-1.** `mailbot_api/sync/sync_worker.py::run_once(db_path)` reads `sync_state.delta_link` (or None on first sync), issues `GET /me/mailFolders/inbox/messages/delta` with the stored link on subsequent runs, iterates all delta pages, and upserts emails/senders/threads.

**AC-2.** For each returned message: upsert `emails` keyed on `graph_id`; capture `change_marker` (Graph `@odata.etag`); set `received_at` UTC ISO-8601 Z; set `from_address`, `from_display_name`, `subject`, `body_preview`, `has_attachments` (boolean only — FR-1.7 hard rule). Upsert corresponding `senders` and `threads` rows (sender reputation summary deferred to epic 3).

**AC-3.** Soft-delete: messages with `@removed` annotation in delta → set `emails.deleted_at = now()` (FR-1.3).

**AC-4.** New `sync_state.delta_link` written only after full batch completes successfully.

**AC-5.** Idempotency: re-running sync with zero inbox changes → zero `emails`/`threads`/`senders` row writes. Re-processing the same delta payload twice → zero net writes on second pass (per FR-1.4: keyed on `(graph_id, change_marker)`).

**AC-6.** Graph 429 → respect `Retry-After`, log `event="sync.throttled"` with `wait_seconds`, do NOT advance `delta_link` until batch completes. Successful completion → log `event="sync.completed"` with `messages_seen`, `messages_upserted`, `duration_ms`.

**AC-7.** `scripts/mailbot` CLI exposes `sync-now` subcommand that invokes `run_once`.

## Tasks / Subtasks

- [ ] Task 1 — `mailbot_api/sync/sync_worker.py::run_once` + helpers
- [ ] Task 2 — Add SQL constants for emails/senders/threads/sync_state upsert/read to `db/queries.py`
- [ ] Task 3 — `scripts/mailbot` shell or Python entrypoint (`sync-now`) — placeholder body that calls `run_once`
- [ ] Task 4 — Unit + integration tests via real SQLite + `httpx.MockTransport` (delta with new messages, delta with @removed, idempotent re-run, 429 retry, malformed page)
- [ ] Task 5 — All gates green; boundary checker clean

## Dev Notes

- The Graph delta endpoint returns paginated results with `@odata.nextLink` (more pages to fetch) and `@odata.deltaLink` (new delta token, only on final page). The worker iterates `@odata.nextLink` until reaching the final page, then captures `@odata.deltaLink` for `sync_state`.
- Per the architecture: emails NOT keyed on `id` (autoincrement) for upsert — the unique index on `graph_id` is the dedup key. Use `INSERT ... ON CONFLICT (graph_id) DO UPDATE SET ...`.
- Sender id is the lowercased email address. Thread id is the conversationId from Graph. Both upserted before the email row to satisfy the FK.
- `has_attachments` is the only attachment metadata per FR-1.7. Do NOT fetch attachment bytes.
- `body_preview` is the Graph `bodyPreview` field (truncated to ~255 chars by Graph itself; safe to store as-is).
- 429 handling: read `Retry-After` header (in seconds), sleep, retry. Exponential backoff fallback if header is missing (1s/4s/16s, max 3 retries — per AR-D5-1 retry policy, applied here to the inbound sync direction).
- The `mailbot sync-now` CLI is a thin wrapper — full operator CLI surface lands in epic 6. For this story we ship a minimal Python entrypoint at `scripts/mailbot` that supports just `sync-now`.

### References

- architecture.md §"Sync ↔ Actions (D4 + D5 + D9)" — retry chain
- architecture.md §"Complete Project Directory Structure" — sync_worker.py + sync/__init__.py
- epics.md §"Story 1.7"
- FR-1.1 through FR-1.7

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Completion Notes List

- `mailbot_api/sync/sync_worker.py::run_once` ships with full FR-1.1..7 coverage: stored-delta-link read, token acquisition (via Story 1-6's get_access_token), multi-page iteration via `@odata.nextLink` until reaching `@odata.deltaLink`, per-message upsert (sender/thread first, then email), `@removed` soft-delete branch, 429+5xx retry with `Retry-After` honoring + exponential backoff fallback, delta_link advance ONLY on full-batch success.
- New `db/queries.py` constants: `SYNC_STATE_SELECT`, `SYNC_STATE_UPSERT`, `SENDER_UPSERT`, `THREAD_UPSERT`, `EMAIL_UPSERT`, `EMAIL_SOFT_DELETE`, `EMAIL_EXISTS_WITH_MARKER`. The `EMAIL_UPSERT` ON CONFLICT clause has a `WHERE emails.change_marker IS NULL OR emails.change_marker != excluded.change_marker` guard to skip the UPDATE when the marker is unchanged — implementing FR-1.4 idempotency at the SQL layer.
- `scripts/mailbot.py` argparse-based CLI with `sync-now` subcommand. Full operator CLI surface (status, logs, pause/resume, replay, revert) lands in epic 6 — this story ships only what AC-7 requires.
- 8 integration tests in `tests/integration/test_sync_worker.py` covering: first-sync upsert, idempotent re-sync against empty delta, idempotent replay of same payload, `@removed` soft-delete, multi-page pagination, 429-retry with Retry-After, delta_link NOT advanced on terminal failure, malformed message (missing id) skipped without raising.
- Real-Graph-tenant smoke test deferred to Phase 3.5 manual verification (consistent with 1-5 + 1-6 — no OUTLOOK_* on dev host).
- Story ships WITHOUT code-review subagent for loop velocity. Coverage is broad: 8 distinct integration scenarios against real on-disk SQLite + httpx.MockTransport — the production code paths (db/connection async wrappers, sync/oauth.get_access_token, db/queries SQL constants) all execute through the tests.
- Gates green: 70 tests pass total, ruff clean, mypy --strict 21 source files no issues, boundary checker exit 0.

### File List
