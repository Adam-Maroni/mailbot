# Story 1.10: Immutable IDs + change_key semantics + removed_reason + delta-resync recovery

Status: backlog

## Story

As Adam,
I want the sync layer hardened against four documented Microsoft Graph behaviors that the original Epic 1 implementation glossed over — message ID rotation on folder moves, `changeKey` semantics, `@removed.reason` distinction, and `410 Gone`/`syncStateNotFound` full-resync triggers,
so that long-running sync against a real Outlook mailbox doesn't silently corrupt state, lose recoverability, or alarm forever after a delta-token cache eviction.

## Context (why this story exists)

The Azure docs review after Epic 1 surfaced four sync-layer correctness gaps. None block development; all block long-running production correctness. Bundled into one story because they all touch `mailbot_api/sync/sync_worker.py` + `db/migrations/` + `db/queries.py` and share the same test fixtures.

## Acceptance Criteria

**AC-1 (immutable IDs).** Every Graph HTTP request issued by `mailbot_api/sync/graph_client.py` carries the header `Prefer: IdType="ImmutableId"`.

- Verified by static-source assertion in tests: `tests/unit/sync/test_graph_client.py` adds an assertion that the `Prefer` header appears on the recorded mock request for `/me`, `/me/mailFolders/inbox/messages/delta`, and any future-added endpoint.
- Verified by inspection of `_default_headers` (or equivalent) on `GraphClient.__init__`.
- Rationale: per [message.md properties table](../../docs/external/learn-microsoft-azure/pages/graph/api/resources/message.md), the default `id` rotates on folder move. With `Prefer: IdType="ImmutableId"`, IDs stay stable across moves (with documented exceptions like sending a draft, which we accept).

**AC-2 (change_key semantics, no schema rename).** `emails.change_marker` retains its column name (no migration churn). A docstring on `db/queries.py::EMAIL_UPSERT` and a comment in `001_init.sql` document that the value stored in `change_marker` **is** Graph's `changeKey` field on the message resource (not `@odata.etag`, which doesn't exist on messages). `sync_worker.py::_extract_change_marker` (or the equivalent inline extraction) reads `message["changeKey"]` and **falls back to the legacy `@odata.etag` field only if `changeKey` is absent**, with a structured log line `event="sync.change_key_fallback"` (level=warning) when the fallback fires. The fallback is purely defensive — production Graph responses for the message resource will always carry `changeKey`.

**AC-3 (removed_reason).** Migration `005_emails_removed_reason.sql` (or whichever the next sequential apply-order key is at story time) adds column `removed_reason TEXT NULL` to `emails`. `sync_worker.py`'s soft-delete branch is updated: when a delta page row contains `@removed`, write both `deleted_at = <now>` AND `removed_reason = <message["@removed"]["reason"]>` (`changed` or `deleted` per the Graph contract; NULL if Graph omits the field for any reason). Existing rows with `deleted_at NOT NULL AND removed_reason IS NULL` are left untouched (the migration is additive only).

**AC-4 (full-resync recovery on 410 Gone).** `sync_worker.py::run_once` catches HTTP 410 responses from the delta endpoint. On 410: log `event="sync.delta_token_invalidated"` level=warning with the response body's `code` field if present; **set `sync_state.delta_link = NULL`** via `db.execute_write(SYNC_STATE_UPSERT_NULL_LINK, ...)` (new SQL constant in `db/queries.py`); fire `notifications.send_urgent("delta token reset — full resync in progress")` exactly once per reset episode (debounced via a module-level `_resync_notification_fired` flag, cleared when the next sync completes successfully); **return without raising** so the worker's outer cron loop runs the next iteration normally, which performs a fresh delta from scratch.

**AC-5 (full-resync recovery on syncStateNotFound).** Same recovery path as AC-4, but triggered by HTTP 404 with response body containing `"code": "syncStateNotFound"` (case-insensitive substring match on the `code` field — the docs don't pin the exact casing). The two paths (410 and 404+syncStateNotFound) share a single internal helper `_handle_delta_token_invalidation(reason: str) -> None` for code-paths-equivalence.

**AC-6 (single-response duplicate replay test).** New integration test `tests/integration/test_sync_worker.py::test_handles_duplicate_message_in_single_delta_page` exercises the case where the same `graph_id` appears twice in a single delta page with different `changeKey` values. Asserts: exactly one row in `emails` post-sync; the row's `change_marker` matches the **last-seen** value in the page; `messages_upserted=2` is logged (we count writes attempted, not unique rows). This complements the existing two-call replay test by covering the **single-page duplicate** case the Graph docs explicitly permit ([delta-query-overview.md § Replays](../../docs/external/learn-microsoft-azure/pages/graph/delta-query-overview.md)).

**AC-7 (architecture document patches).** Six edits land in `_bmad-output/planning-artifacts/architecture.md` as part of this story's scope:

1. § "OAuth refresh-token rotation (D9)" — add pointer to Story 1-9 as the bootstrap-token source of truth.
2. § "Sync ↔ Actions (D4 + D5 + D9)" Rule B paragraph — add: "All Graph requests carry `Prefer: IdType=\"ImmutableId\"` to prevent ID rotation on folder moves."
3. § "Schema implications introduced in this section" — `emails` row updated to mention `change_marker` stores `changeKey` (with a sentence: "Despite the column name, the stored value is Graph's `changeKey` field — `@odata.etag` does not exist on the message resource") and to add `removed_reason TEXT NULL`.
4. § "Sync ↔ Actions (D4 + D5 + D9)" write-back retry contract — add a new bullet: "Delta-token invalidation (`410 Gone`, `404 syncStateNotFound`) clears `sync_state.delta_link` and triggers a one-shot urgent notification; the next worker tick performs a full resync."
5. New § "Access model" (insert near the top of "Sync ↔ Actions" or as its own subsection) documenting: delegated access via OAuth 2.0 Authorization Code flow + `offline_access` scope; personal Outlook → tenant=`consumers`; work/school → tenant GUID; mixed-mode → tenant=`common`; app-only access was ruled out because the design uses the `/me` alias throughout.
6. New appendix "Reference Material" pointing at `docs/external/learn-microsoft-azure/` as the canonical archived reference for Graph/Outlook semantics; SITE-MAP.md is the entry point.

**AC-8.** All gates green: ruff, mypy --strict, boundary checker, pytest (existing 84 tests still pass; new tests for AC-1 + AC-6 add to total).

## Tasks / Subtasks

- [ ] **Task 1** — `graph_client.py`: add `Prefer: IdType="ImmutableId"` header (AC: #1)
- [ ] **Task 2** — `db/migrations/00X_emails_removed_reason.sql` migration (AC: #3)
- [ ] **Task 3** — `sync_worker.py`: read `changeKey` with `@odata.etag` fallback + structured log (AC: #2)
- [ ] **Task 4** — `sync_worker.py`: write `removed_reason` on `@removed` branch (AC: #3)
- [ ] **Task 5** — `sync_worker.py`: `_handle_delta_token_invalidation` helper + 410 branch + 404+syncStateNotFound branch + debounced notification (AC: #4, #5)
- [ ] **Task 6** — `db/queries.py`: add `SYNC_STATE_UPSERT_NULL_LINK` constant (AC: #4)
- [ ] **Task 7** — Integration test for 410 → delta_link cleared (AC: #4)
- [ ] **Task 8** — Integration test for 404+syncStateNotFound → delta_link cleared (AC: #5)
- [ ] **Task 9** — Integration test for single-page duplicate replay (AC: #6)
- [ ] **Task 10** — Unit test for `Prefer` header presence on `GraphClient` requests (AC: #1)
- [ ] **Task 11** — Architecture document patches × 6 (AC: #7)
- [ ] **Task 12** — All gates green (AC: #8)

## Dev Notes

### Why we keep the `change_marker` column name

Renaming would force a destructive schema migration on a column that already has live data (84 tests, plus any real-tenant data after Story 1-9 runs). The column name is a Rule-A naming choice (PRD's terminology) while the value is a Graph protocol detail. Decoupling the two via a docstring is cheaper and clearer than a renaming churn that the boundary checker would have to relearn.

### Why a single helper for 410 and 404+syncStateNotFound

Both are "delta token is dead, restart from scratch" signals. Microsoft's docs treat them as distinct error surfaces ([delta-query-overview.md § Synchronization reset](../../docs/external/learn-microsoft-azure/pages/graph/delta-query-overview.md), § Token duration), but the recovery is identical. Centralizing into `_handle_delta_token_invalidation(reason)` lets observability tell them apart (different `reason` strings in the log line) while keeping the action one-place-to-change-if-Microsoft-adds-a-third.

### Why debounce the resync notification

Without debounce, a malformed delta endpoint that 410'd persistently would spam `notifications_pending.jsonl`. Story 1-8's sync-health alarm is the right escalation path for "sync stuck in a loop"; this notification is for "sync had to reset, expect a brief inbox-state re-sync." One per episode is the right cardinality.

### Why we don't switch to `msgraph-sdk` here

The SDK would handle delta pagination, `@removed`, `@odata.nextLink`/`@odata.deltaLink`, and 410-resume automatically. We retain hand-rolled httpx because the `httpx.MockTransport` integration test pattern is load-bearing for Middleware-Real-Bootstrap; the SDK's request-builder API doesn't expose a clean mock seam. This story brings hand-rolled to parity with SDK behavior for the four documented edge cases.

### Why `removed_reason` is additive (no backfill)

Existing rows with `deleted_at NOT NULL AND removed_reason IS NULL` represent emails removed before this story shipped. We don't know retroactively whether they were `changed` (recoverable) or `deleted` (permanent). Epic 4's Tier-1 reverter must treat NULL `removed_reason` as "unknown → don't attempt restoration without confirming via Graph first." That's a one-line check in the reverter; doesn't belong here.

### References

- [docs/external/learn-microsoft-azure/pages/graph/api/resources/message.md](../../docs/external/learn-microsoft-azure/pages/graph/api/resources/message.md) — message resource: `id` rotation, `changeKey`, `immutable_id` Prefer header
- [docs/external/learn-microsoft-azure/pages/graph/api/resources/mail-api-overview.md](../../docs/external/learn-microsoft-azure/pages/graph/api/resources/mail-api-overview.md) — "do not assume that message and mailfolder IDs are unique and always remain the same"
- [docs/external/learn-microsoft-azure/pages/graph/delta-query-overview.md](../../docs/external/learn-microsoft-azure/pages/graph/delta-query-overview.md) — `@removed.reason` (changed vs deleted), `410 Gone` sync reset, token-duration / cache-eviction, replays
- Story 1-7 — current sync worker implementation (the one being patched)
- Story 1-9 — the bootstrap-token story (sequentially-prior; story 1-9 must complete before this one is testable against real Graph)
