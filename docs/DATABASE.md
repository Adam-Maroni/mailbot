# MailBot Database Reference

**Schema generation:** [`mailbot_api/db/migrations/`](../mailbot_api/db/migrations/) — 16 migration files (001–017, with 003 skipped per the migration-numbering gap-tolerance policy; see [architecture.md `### Schema implications` → "Migration numbering policy"](../_bmad-output/planning-artifacts/architecture.md)).
**Runner:** [`mailbot_api/db/migrations_runner.py`](../mailbot_api/db/migrations_runner.py) — `apply_pending_migrations(db_path)` runs at FastAPI lifespan startup + CLI init.
**Queries:** [`mailbot_api/db/queries.py`](../mailbot_api/db/queries.py) — every SQL literal in the codebase lives here (Rule C).
**Connection:** [`mailbot_api/db/connection.py`](../mailbot_api/db/connection.py) — `fetchone` / `fetchall` / `execute_write` (sync executor per AR-D8-1).

## Project conventions

- **SQLite WAL** (`PRAGMA journal_mode=WAL`) — concurrent readers, single writer, no checkpoints stalling the event loop.
- **All timestamps as TEXT UTC ISO-8601 with `Z` suffix.** Microsecond precision since 2026-06-02 (Epic 4 retro action item #3); see [`mailbot_api/observability/timestamps.py`](../mailbot_api/observability/timestamps.py).
- **Booleans as `INTEGER NOT NULL DEFAULT 0/1` with `CHECK(col IN (0, 1))`.** SQLite has no native bool.
- **Foreign keys ON.** Every migration opens with `PRAGMA foreign_keys = ON;`.
- **Indexes:** `ix_<table>_<col1>_<col2>` naming (e.g., `ix_emails_thread_id_received_at`).
- **Append-only migrations** (AR-D14-1): no `DROP TABLE`, no `ALTER COLUMN` destructive paths. New columns are `ALTER TABLE ADD COLUMN`. Renames are deferred until a backup/restore cycle is acceptable.

---

## Table inventory (10 tables across 16 migrations)

| Table | Introduced by | Purpose |
|---|---|---|
| [`threads`](#threads) | [001](#001_init) | One row per Outlook conversation_id; derived fields added in [014](#014_thread_continuity). |
| [`senders`](#senders) | [001](#001_init) | One row per from-address (lowercased); sender reputation summary populated in Epic 3. |
| [`emails`](#emails) | [001](#001_init) | The primary table. Derived-field columns + companions per Rule A (FR-2.1). Extended by [005](#005_emails_removed_reason), [011](#011_derived_fields), [012](#012_sensitivity_override). |
| [`sync_state`](#sync_state) | [001](#001_init) | Single row keyed by provider; stores Graph delta_link for next sync. |
| [`oauth_state`](#oauth_state) | [002](#002_oauth_state) | Single row keyed by provider; refresh_token + access_token rotation per AR-D9-1. |
| [`worker_health`](#worker_health) | [004](#004_worker_health) | Per-component heartbeat: `sync` / `cache_warmer` / `drainer` / `ingest_pipeline`. |
| [`router_calls`](#router_calls) | [006](#006_router_calls) | Audit log — one row per `ask_router()` invocation. Sole writer: [`observability/audit.py`](../mailbot_api/observability/audit.py). |
| [`response_cache`](#response_cache) | [007](#007_response_cache) | SQL-backed response cache, keyed on `sha256(model\|temp\|system\|user)`. |
| [`degraded_mode_state`](#degraded_mode_state) | [008](#008_degraded_mode) | Singleton row — Layer 3 of 4-layer budget guard. |
| [`call_volume_baseline`](#call_volume_baseline) | [009](#009_anomaly_baseline) | Rolling 7-day per-(origin,hour) call volume mean+stddev — hourly anomaly detection. |
| [`pause_state`](#pause_state) | [010](#010_pause_state) | Singleton row — pause/resume kill-switch persisted across restarts. |
| [`derivations_idempotency`](#derivations_idempotency) | [013](#013_derivations_idempotency) | Per-(email_id, task_type) idempotency key — short-circuits ingest-pipeline re-runs. |
| [`pending_actions`](#pending_actions) | [015](#015_pending_actions) | Action proposal queue — Tier-1/2/3 lifecycle (`pending` → `cooling_off`/`pending_grant`/`draining` → `applied`/`failed`/`cancelled`). |
| [`action_grants`](#action_grants) | [016](#016_action_grants) | Scoped time-bounded authorization grants (FR-5.2). |
| [`action_history`](#action_history) | [017](#017_action_history) | Pre-state audit snapshot written before Graph dispatch; `reverted_at` populated by Tier-1 24h reverter (Story 4-8). |

System tables:

| Table | Purpose |
|---|---|
| `_migrations` | Created by `migrations_runner.py` on first boot. Records `(prefix, applied_at)` per migration. Gap-tolerant — accepts skipped prefixes. |

---

## Migration index

| Prefix | File | Epic | Story | Adds |
|---|---|---|---|---|
| 001 | `001_init.sql` | 1 | 1-3 | `emails`, `threads`, `senders`, `sync_state` + 10 derived-field column groups on `emails` |
| 002 | `002_oauth_state.sql` | 1 | 1-6 | `oauth_state` |
| 003 | _(skipped)_ | — | — | Gap per migration-numbering gap-tolerance policy. |
| 004 | `004_worker_health.sql` | 1 | 1-8 | `worker_health` |
| 005 | `005_emails_removed_reason.sql` | 1 | 1-10 | `emails.removed_reason` column (`'changed'` / `'deleted'` per Graph `@removed.reason`) |
| 006 | `006_router_calls.sql` | 2 | 2-1 | `router_calls` (renumbered from epic spec's 005 due to 1-10's 005). Sole writer: `observability/audit.py`. |
| 007 | `007_response_cache.sql` | 2 | 2-7 | `response_cache` |
| 008 | `008_degraded_mode.sql` | 2 | 2-8 | `degraded_mode_state` (singleton) |
| 009 | `009_anomaly_baseline.sql` | 2 | 2-9 | `call_volume_baseline` |
| 010 | `010_pause_state.sql` | 2 | 2-9 | `pause_state` (singleton) |
| 011 | `011_derived_fields.sql` | 3 | 3-1 | `emails.embedding_dtype` + `embedding_shape` (W-5 resolution) + 3 missing indexes |
| 012 | `012_sensitivity_override.sql` | 3 | 3-3 | `emails.sensitivity_override_reason` |
| 013 | `013_derivations_idempotency.sql` | 3 | 3-5 | `derivations_idempotency` |
| 014 | `014_thread_continuity.sql` | 3 | 3-7 | `threads.thread_continuity_note` + 4 companion columns |
| 015 | `015_pending_actions.sql` | 4 | 4-2 | `pending_actions` + 18-action-type CHECK + tier-1/2/3 CHECK + 7-state CHECK |
| 016 | `016_action_grants.sql` | 4 | 4-2 | `action_grants` |
| 017 | `017_action_history.sql` | 4 | 4-2 | `action_history` |

**Cumulative renumber chain:** Epic 2 specs shifted by +1 (1-10 consumed 005); Epic 3 specs shifted by +1 (Epic 2's 010 was originally spec'd as 009 etc.); Epic 4's specs landed at 015–017 cleanly (no further shift). See architecture.md "Migration numbering policy" for the renumber discipline.

---

## Table reference

<a id="threads"></a>

### `threads`

One row per Outlook conversation_id. Threading is a Graph-side concept; MailBot mirrors it locally for the `get_thread()` verb + cross-email synthesis (Story 3-7 thread continuity).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | TEXT | PK | Graph `conversationId`. |
| `subject_normalized` | TEXT | YES | Subject with `Re:` / `Fwd:` / quoted-marker prefixes stripped. |
| `last_message_at` | TEXT | YES | UTC ISO-8601 Z; the latest `received_at` across emails in the thread. |
| `message_count` | INTEGER | `NOT NULL DEFAULT 0` | Count of `emails` rows joined on this thread. |
| `thread_continuity_note` | TEXT | YES | [014](#014_thread_continuity) — Story 3-7 Qwen-generated cross-email continuity summary. |
| `thread_continuity_note_prompt_v` | TEXT | YES | Companion (Rule A). |
| `thread_continuity_note_conf` | REAL | YES | Companion (Rule A). |
| `thread_continuity_note_model` | TEXT | YES | Companion (Rule A). |
| `thread_continuity_note_at` | TEXT | YES | Companion (Rule A). |

Indexes: `ix_threads_last_message_at`, `ix_threads_thread_continuity_note_at` ([014](#014_thread_continuity)).

---

<a id="senders"></a>

### `senders`

One row per lowercased from-address. Sender reputation summary populated by [`ingest/sender_enrichment.py`](../mailbot_api/ingest/sender_enrichment.py) (Story 3-7, Qwen-only per Rule Q).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | TEXT | PK | Lowercased email address. |
| `display_name` | TEXT | YES | Most-recent display name observed. |
| `domain` | TEXT | YES | Lowercased domain after `@`. |
| `first_seen_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |
| `sender_reputation_summary` | TEXT | YES | Qwen-generated one-line summary (sensitivity-aware digest filter applied — Rule Q). |
| `sender_reputation_summary_prompt_v` | TEXT | YES | Companion (Rule A). |
| `sender_reputation_summary_conf` | REAL | YES | Companion (Rule A). |
| `sender_reputation_summary_model` | TEXT | YES | Companion (Rule A). |
| `sender_reputation_summary_at` | TEXT | YES | Companion (Rule A). |

Indexes: `ix_senders_domain`.

---

<a id="emails"></a>

### `emails`

The primary table. Every email synced from Outlook lives here. Derived-field columns + companion metadata per Rule A (FR-2.1) — each derived signal carries `*_prompt_v` / `*_conf` / `*_model` / `*_at`.

#### Identity & sync

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | Internal row id. |
| `graph_id` | TEXT | `NOT NULL UNIQUE` | Microsoft Graph message id (`@odata.id` derivative). Project-wide canonical identifier. |
| `change_marker` | TEXT | YES | **Stores Graph's `changeKey` field** (NOT `@odata.etag` — that field does not exist on the message resource; Story 1-10 docs the semantic alignment without rename). Used for FR-1.4 idempotency on `(graph_id, change_marker)` AND Tier-3 ETag-strict drain (AR-D4-1). |
| `thread_id` | TEXT | YES | FK → `threads.id`. |
| `sender_id` | TEXT | YES | FK → `senders.id` (lowercased). |
| `received_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |
| `from_address` | TEXT | YES | Original case preserved; canonical lowercased form lives on `senders.id`. |
| `from_display_name` | TEXT | YES | — |
| `subject` | TEXT | YES | — |
| `body_preview` | TEXT | YES | Graph's `bodyPreview` field — first ~255 chars. Full body is not stored; `has_attachments` only at v1 per FR-1.7. |
| `has_attachments` | INTEGER | `NOT NULL DEFAULT 0` | Boolean (0/1). |
| `deleted_at` | TEXT | YES | Soft-delete (FR-1.3). |
| `created_at` | TEXT | `NOT NULL DEFAULT (strftime(...))` | When the row was inserted into the local DB. |
| `removed_reason` | TEXT | YES | [005](#005_emails_removed_reason) — Graph `@removed.reason`: `'changed'` (recoverable from deletedItems) or `'deleted'` (permanent). Used by Story 4-8 Tier-1 reverter to know whether restoration is possible. |

#### Derived fields (Rule A, FR-2.1)

Each block follows the same shape: a value column + 4 companion columns (`_prompt_v` / `_conf` / `_model` / `_at`).

| Block | Value column | Type | Pipeline step | Source |
|---|---|---|---|---|
| Sensitivity | `sensitivity` | TEXT | Step 1 (FR-2.5 Qwen-only) | `mailbot_api/sensitivity/classifier.py` |
| Coarse class | `class_coarse` | TEXT | Step 2 | `mailbot_api/router/ask_router(task_type="coarse_class")` |
| Fine class | `class_fine` | TEXT | Step 3 (gated on `class_coarse == "human"`) | `ask_router(task_type="fine_class")` |
| Summary | `summary_short` | TEXT | Step 4 | `ask_router(task_type="summary_short")` |
| Importance | `importance_score` | REAL | Step 5 | `ask_router(task_type="importance_scoring")` — note: declared REAL but writers store INTEGER 0..100 (SQLite type affinity is lossless; see [011 notes](#011_derived_fields)). |
| Action extraction | `action_extraction` | TEXT | Step 6 | `ask_router(task_type="action_extraction")` — stored as JSON array string. |
| Embedding | `embedding` | BLOB | Step 7 (Qwen-only) | `mailbot_api/ingest/embedding.py` — see W-5 contract below. |

#### Embedding storage (W-5 contract, [011](#011_derived_fields))

| Column | Type | Notes |
|---|---|---|
| `embedding` | BLOB | Raw bytes. 768-dim float32 = 3072 bytes per row. |
| `embedding_dtype` | TEXT | `"<f4"` (little-endian float32). |
| `embedding_shape` | TEXT | JSON-encoded shape tuple, e.g. `"[768]"`. |

**Sole writer:** [`mailbot_api/ingest/embedding.py`](../mailbot_api/ingest/embedding.py) via the writer-monopoly boundary (Rule G); `scripts/check_boundaries.py` `_EMBEDDING_WRITE_ALLOW` enforces this. See architecture.md `### Schema implications` → "Embedding-column binary contract" for the cross-architecture portability rationale.

#### Sensitivity override ([012](#012_sensitivity_override))

| Column | Type | Notes |
|---|---|---|
| `sensitivity_override_reason` | TEXT NULL | Populated only when `apply_pattern_override` ([`mailbot_api/sensitivity/patterns.py`](../mailbot_api/sensitivity/patterns.py)) promotes the classifier's label. Free-text audit string (e.g., `"pattern_override: force_confidential regex 'password reset confirmation'"`). |

#### Indexes

| Index | On | Introduced |
|---|---|---|
| `ix_emails_graph_id` | `(graph_id)` | [001](#001_init) |
| `ix_emails_received_at` | `(received_at)` | [001](#001_init) |
| `ix_emails_thread_id` | `(thread_id)` | [001](#001_init) |
| `ix_emails_sender_id` | `(sender_id)` | [001](#001_init) |
| `ix_emails_deleted_at` | `(deleted_at)` | [001](#001_init) |
| `ix_emails_sensitivity` | `(sensitivity)` | [001](#001_init) |
| `ix_emails_class_coarse` | `(class_coarse)` | [001](#001_init) |
| `ix_emails_importance_score` | `(importance_score)` | [011](#011_derived_fields) |
| `ix_emails_sensitivity_at` | `(sensitivity_at)` | [011](#011_derived_fields) — supports `WHERE sensitivity_at IS NULL` unprocessed-queue scan (FR-2.3 + FR-2.4). |
| `ix_emails_class_fine` | `(class_fine)` | [011](#011_derived_fields) |

---

<a id="sync_state"></a>

### `sync_state`

Single row keyed by provider. Holds the Graph delta_link for the next incremental sync.

| Column | Type | Null | Notes |
|---|---|---|---|
| `provider` | TEXT | PK | e.g., `'microsoft_graph'`. |
| `delta_link` | TEXT | YES | Graph's delta URL; opaque to MailBot — replay-only. |
| `last_sync_at` | TEXT | YES | UTC ISO-8601 Z. |
| `last_sync_messages_seen` | INTEGER | `NOT NULL DEFAULT 0` | Count from the most recent sync (FR-1.x telemetry). |

---

<a id="oauth_state"></a>

### `oauth_state`

Single row per provider; mirrors the OAuth refresh-token rotation state per AR-D9-1. `.env` `OUTLOOK_REFRESH_TOKEN` is bootstrap-seed only; subsequent rotations update this row in place.

| Column | Type | Null | Notes |
|---|---|---|---|
| `provider` | TEXT | PK | e.g., `'microsoft_graph'`. |
| `refresh_token` | TEXT | `NOT NULL` | The currently-valid refresh token. Rotated when Graph returns a new one. |
| `access_token` | TEXT | YES | Refreshed on demand by `mailbot_api/sync/oauth.py`. |
| `access_expires_at` | TEXT | YES | UTC ISO-8601 Z. Lenient parser accepts both microsecond + legacy second precision. |
| `last_rotated_at` | TEXT | YES | UTC ISO-8601 Z. |
| `rotation_count` | INTEGER | `NOT NULL DEFAULT 0` | Bumped on every refresh-token rotation. |

---

<a id="worker_health"></a>

### `worker_health`

Per-component heartbeat. `mailbot status` reads these; a `last_heartbeat_at` older than the component's threshold triggers an urgent alarm.

| Column | Type | Null | Notes |
|---|---|---|---|
| `component` | TEXT | PK | Known: `'sync'`, `'cache_warmer'`, `'drainer'`, `'ingest_pipeline'`. |
| `last_heartbeat_at` | TEXT | YES | UTC ISO-8601 Z. |
| `last_outcome` | TEXT | YES | `'ok'` or `'failed'`. |
| `last_error` | TEXT | YES | Sanitized message on `'failed'`. |

---

<a id="router_calls"></a>

### `router_calls`

Audit log — one row per `ask_router()` invocation. Ground truth for cost analysis, drift detection, routing tuning, and forensic linkage of sensitivity-token consumes.

**Sole writer:** [`mailbot_api/observability/audit.py::record_router_call()`](../mailbot_api/observability/audit.py) (Rule C). The boundary check refuses `INSERT INTO router_calls` outside this module.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | — |
| `ts` | TEXT | `NOT NULL` | UTC ISO-8601 Z. **Microsecond precision since 2026-06-02** (Epic 4 retro action item #3) — back-to-back same-second rows are strictly orderable by `ts` alone. |
| `task_type` | TEXT | `NOT NULL` | e.g., `'coarse_class'`, `'sensitivity_class'`, `'draft_reply'`. |
| `prompt_version` | TEXT | `NOT NULL` | e.g., `'v1'`. |
| `model_chosen` | TEXT | `NOT NULL` | e.g., `'qwen2.5:3b-instruct-q4_K_M'`, `'claude-haiku-4-5-20251001'`. |
| `model_chosen_reason` | TEXT | `NOT NULL` | Closed set: `'policy'` / `'override'` / `'degraded'` / `'response_cache_hit'` / `'force_override'` / `'escalated_from_<X>'`. Enforced application-side on `RouterCallRow` Pydantic model, NOT via SQL CHECK. |
| `tokens_in` | INTEGER | `NOT NULL DEFAULT 0` | — |
| `tokens_out` | INTEGER | `NOT NULL DEFAULT 0` | — |
| `cached_tokens_in` | INTEGER | `NOT NULL DEFAULT 0` | Anthropic ephemeral cache hit count. |
| `cost_usd_estimated` | REAL | `NOT NULL DEFAULT 0` | Per-call estimate. |
| `latency_ms` | INTEGER | `NOT NULL DEFAULT 0` | End-to-end wall time. |
| `outcome` | TEXT | `NOT NULL` | `'ok'` / `'retry_recovered'` / `'escalated'` / `'failed'`. |
| `caller_verb` | TEXT | YES | The verb that initiated the call (e.g., `'find_emails'`, `'draft_reply'`). |
| `caller_origin` | TEXT | `NOT NULL DEFAULT 'unknown'` | Closed-ish set: `'verb-ask-router'`, `'ingest-pipeline-sensitivity'`, `'cli-rederive'`, `'actions-drainer'`, `'confirmation-mint'`, `'hermes-aux-compression'`, `'hermes-aux-title'`, `'cache-warmer'`, `'benchmark-runner'`. |
| `email_id` | TEXT | YES | The `emails.graph_id` this call relates to, if any. |
| `sensitivity_grant_id` | TEXT | YES | Story 4-7 — 16-hex-char hash of the consumed sensitivity token. Forensic link to the mint event. NULL on non-sensitive calls. |
| `sensitivity_grant_minted_at` | TEXT | YES | Story 4-7 (with Story 4-7 retroactive CR-4-7-6 fix) — the original mint timestamp, not consume time. |

Indexes: `ix_router_calls_ts`, `ix_router_calls_task_type_model_chosen`, `ix_router_calls_email_id`.

**Row-ordering note:** escalation produces recursive `_dispatch_with_failure_chain` calls; the recursive call's `finally` block fires BEFORE the outer call's `finally`, so rows are inserted in REVERSE dispatch order (escalated tier first, original tier second). Post-2026-06-02 microsecond precision makes this orderable by `ts` alone; legacy rows additionally correlate via `email_id` + `task_type` + the `escalated_from_<X>` tag in `model_chosen_reason`.

---

<a id="response_cache"></a>

### `response_cache`

SQL-backed response cache (FR-3.7). A hit returns `cost_usd=0` and `model_used=<original>+response_cache`; per-task TTL configurable via `policy.yaml` `response_cache_ttl_seconds`.

**Sole writer/reader:** [`mailbot_api/router/response_cache.py`](../mailbot_api/router/response_cache.py).

| Column | Type | Null | Notes |
|---|---|---|---|
| `cache_key` | TEXT | PK | `sha256(model\|temperature\|system\|user)` hex. |
| `task_type` | TEXT | `NOT NULL` | For per-task cache-hit-rate accounting. |
| `model` | TEXT | `NOT NULL` | The dispatched model id (NOT `+response_cache`). |
| `result_json` | TEXT | `NOT NULL` | Serialized `RouterResult.output` (Pydantic `model_dump_json()`). |
| `cost_usd` | REAL | `NOT NULL DEFAULT 0` | Original dispatch cost (accounting only — hits return 0). |
| `cached_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |
| `ttl_seconds` | INTEGER | `NOT NULL` | Per-task TTL captured at insert time. |
| `hit_count` | INTEGER | `NOT NULL DEFAULT 0` | Atomically bumped on every cache hit. |

Indexes: `ix_response_cache_task_type_cached_at`.

**Known latent bug (Story 3-2 CR-8, guarded as of 2026-06-02):** the `hermes_aux` task must NOT enable `response_cache_ttl_seconds` in `policy.yaml` (double-wrap of cache_control). Guarded by `tests/unit/router/test_response_cache.py::test_hermes_aux_has_no_response_cache_ttl_in_policy`. See Epic 3 retro action #10.

---

<a id="degraded_mode_state"></a>

### `degraded_mode_state`

Layer 3 of the 4-layer budget guard (Story 2-8). When `active=1`, the Router demotes every API call opus→haiku→qwen until either `/budget reset` is invoked or the calendar month rolls over (UTC midnight on the 1st).

Singleton row enforced via `CHECK(id = 1)`. Seed row inserted on first migration apply.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK `CHECK(id = 1)` | Always 1. |
| `active` | INTEGER | `NOT NULL DEFAULT 0` | Boolean (0/1). |
| `entered_at` | TEXT | YES | UTC ISO-8601 Z. |
| `exited_at` | TEXT | YES | UTC ISO-8601 Z. |

---

<a id="call_volume_baseline"></a>

### `call_volume_baseline`

Rolling 7-day per-(caller_origin, hour_of_day) call-volume baseline (Story 2-9). Hourly anomaly detection: count last-hour calls per origin → upsert with rolling mean + stddev → alert if current > `mean + 3*stddev`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `caller_origin` | TEXT | `NOT NULL` (PK part 1) | Matches `router_calls.caller_origin`. |
| `hour_of_day` | INTEGER | `NOT NULL` (PK part 2) | `0..23`. |
| `mean_volume` | REAL | `NOT NULL DEFAULT 0` | Welford online mean. |
| `stddev_volume` | REAL | `NOT NULL DEFAULT 0` | Welford online stddev. |
| `sample_count` | INTEGER | `NOT NULL DEFAULT 0` | 24-sample warmup required before alarms fire. |
| `last_updated` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |

Indexes: `ix_call_volume_baseline_last_updated`.

---

<a id="pause_state"></a>

### `pause_state`

Singleton — pause/resume kill-switch persisted across restarts. When `paused=1`, `ask_router` short-circuits with `RouterError(code=PROVIDER_ERROR, message="router paused", retryable=True)` before the call enters the queue.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK `CHECK(id = 1)` | Always 1. |
| `paused` | INTEGER | `NOT NULL DEFAULT 0` | Boolean (0/1). |
| `reason` | TEXT | YES | Operator-provided pause reason. |
| `paused_at` | TEXT | YES | UTC ISO-8601 Z. |
| `resumed_at` | TEXT | YES | UTC ISO-8601 Z. |

---

<a id="derivations_idempotency"></a>

### `derivations_idempotency`

Per-(email_id, task_type) idempotency key. Short-circuits ingest-pipeline re-runs that would produce identical derived fields (FR-2.2 / Rule K).

| Column | Type | Null | Notes |
|---|---|---|---|
| `email_id` | TEXT | `NOT NULL` (PK part 1) | — |
| `task_type` | TEXT | `NOT NULL` (PK part 2) | — |
| `idempotency_key` | TEXT | `NOT NULL` | `sha256(body \| prompt_version \| model \| task_type)` per [`mailbot_api/ingest/idempotency.py::compute_idempotency_key()`](../mailbot_api/ingest/idempotency.py). |
| `applied_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |

PK: `(email_id, task_type)` — one row per email-task pair; re-derivation under a new `prompt_version` overwrites via UPSERT.
Indexes: `ix_derivations_idempotency_key`.

**Sole writer of the key formula:** [`mailbot_api/ingest/idempotency.py::compute_idempotency_key()`](../mailbot_api/ingest/idempotency.py) (Rule G writer-monopoly; `scripts/check_boundaries.py` `_IDEMPOTENCY_KEY_ALLOW` enforces).

---

<a id="pending_actions"></a>

### `pending_actions`

Action proposal queue. Every action Adam approves (or that the agent proposes for Adam's approval) lands here in `status='pending'` (Tier-1), `'cooling_off'` (Tier-3 SEND family), or `'pending_grant'` (Tier-2 batches). The drainer claims rows atomically and dispatches via [`mailbot_api/actions/drainer.py`](../mailbot_api/actions/drainer.py).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | — |
| `email_id` | TEXT | YES | `NULL` for email-less actions (`MODIFY_INBOX_RULE`, `MODIFY_OUTLOOK_FILTER`, `TOUCH_DELEGATED_MAILBOX`, `SEND_NEW_EMAIL`). |
| `action_type` | TEXT | `NOT NULL` + CHECK | 18-value Tier-1/2/3 enum mirror of `mailbot_api.actions.types.ActionType`. Tier-0 deliberately excluded (Tier-0 verbs never queue). Sync-check test in `tests/integration/test_action_schema.py` asserts CHECK-vs-enum parity. |
| `tier` | INTEGER | `NOT NULL CHECK(tier IN (1, 2, 3))` | Defense-in-depth Layer 3 for FR-5.6 (agent cannot promote tier). |
| `payload` | TEXT | `NOT NULL` | JSON-serialized verb payload. Sensitive payload fields (e.g., draft body content) are NOT logged when the audit log line fires. |
| `proposed_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z (microsecond precision since 2026-06-02). |
| `proposed_by_grant_id` | INTEGER | YES | FK → `action_grants.id` for Tier-2 actions covered by a batch grant. |
| `change_marker_at_propose` | TEXT | YES | Captured for Tier-3 ETag check at drain time (AR-D4-1). NULL for Tier-1/2 and email-less Tier-3. |
| `status` | TEXT | `NOT NULL` + CHECK | 7-state lifecycle: `'pending'` / `'cooling_off'` / `'pending_grant'` / `'draining'` / `'applied'` / `'failed'` / `'cancelled'`. |
| `retry_count` | INTEGER | `NOT NULL DEFAULT 0` | Drainer retry count (Story 4-5 retry chain). |
| `failure_reason` | TEXT | YES | Sanitized terminal-failure reason on `status='failed'`. |
| `terminal_at` | TEXT | YES | UTC ISO-8601 Z when `status` reaches `applied`/`failed`/`cancelled`. |
| `budget_consumed` | INTEGER | `NOT NULL DEFAULT 0` + `CHECK(IN (0, 1))` | Flipped on either successful leave OR terminal fail for SEND family (AR-D5-2 — the 20/day cap counts failed sends too). |

Indexes: `ix_pending_actions_status_proposed_at`, `ix_pending_actions_email_id`, `ix_pending_actions_action_type`.

**Lifecycle transitions:**

- Insert: status starts in `{pending, cooling_off, pending_grant}` per `propose_action`'s per-tier routing.
- Cooling-off ticker (Story 4-6): `cooling_off` → `pending` after the configurable window (default 60s).
- Drainer (Story 4-4): `pending` → `draining` (atomic claim) → `applied` / `failed` / `pending_grant` (revert if Tier-2 grant missing).
- `cancel_action` (Story 4-6): `cooling_off` → `cancelled` (race-safe atomic UPDATE).

---

<a id="action_grants"></a>

### `action_grants`

Scoped time-bounded grants (FR-5.2). Adam grants in chat ("you may delete the 47 spam emails from Acme; valid for 1 hour"); the drainer's second auth check at drain time consults `is_grant_valid(action_type, email_id)` which queries `expires_at > now AND revoked_at IS NULL`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | — |
| `action_type` | TEXT | `NOT NULL` + CHECK | Same 18-value CHECK as `pending_actions`. `mint_grant` refuses Tier-1 application-side (Tier-1 is auto-approved per FR-5.1). |
| `email_ids` | TEXT | `NOT NULL` | JSON array of `emails.graph_id` strings. Empty `[]` permitted for email-less actions (`MODIFY_INBOX_RULE` etc.) that grant by action_type alone. |
| `expires_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. Max 24h window per Story 4-3. |
| `minted_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z. |
| `revoked_at` | TEXT | YES | Set by `revoke_grant`. NULL = not revoked. |

Indexes: `ix_action_grants_action_type_expires_at`.

---

<a id="action_history"></a>

### `action_history`

Pre-state snapshot for Tier-1 24h reverter (Story 4-8) + forensic audit. One row per `pending_actions` row (PK = `action_id`).

**Write timing:** Story 4-4 retroactive CR-4-4-2 fix moved the INSERT to BEFORE the Graph dispatch. Failed dispatches AND adapter exceptions still leave an `action_history` row, so the reverter can recover any Tier-1 mistake within 24h regardless of dispatch outcome.

| Column | Type | Null | Notes |
|---|---|---|---|
| `action_id` | INTEGER | PK | FK → `pending_actions.id`. |
| `pre_state` | TEXT | `NOT NULL` | JSON snapshot. Empty `{}` for actions where pre-state isn't meaningful for revert (DELETE; SEND family). For Tier-1 actions, future migrations may populate `is_read` / `folder_id` / `categories` from the live email row at propose time. |
| `applied_at` | TEXT | `NOT NULL` | UTC ISO-8601 Z when the history row was inserted (immediately before dispatch). |
| `reverted_at` | TEXT | YES | Populated by `revert_action` (Story 4-8). NULL = not reverted. |

---

## Cross-cutting

### Sole-writer modules (Rule C + Rule G)

| Table | Sole writer module |
|---|---|
| `router_calls` | [`mailbot_api/observability/audit.py`](../mailbot_api/observability/audit.py) |
| `response_cache` | [`mailbot_api/router/response_cache.py`](../mailbot_api/router/response_cache.py) |
| `emails.embedding` (column) | [`mailbot_api/ingest/embedding.py`](../mailbot_api/ingest/embedding.py) |
| `derivations_idempotency` (key formula) | [`mailbot_api/ingest/idempotency.py`](../mailbot_api/ingest/idempotency.py) (formula only; the table is written by `ingest/pipeline.py`) |
| `pending_actions.action_type` bare string (lint boundary) | [`mailbot_api/actions/types.py`](../mailbot_api/actions/types.py) |

The boundary checker ([`scripts/check_boundaries.py`](../scripts/check_boundaries.py)) enforces each writer-monopoly per the canonical recipe (Rule G).

### Defense-in-depth invariants

| Invariant | Layer 1 (lint) | Layer 2 (verb) | Layer 3 (data) |
|---|---|---|---|
| FR-5.6 (no tier promotion) | bare-string `action_type` lint (Story 4-1) | `propose_action` `TIER_PROMOTION_ATTEMPT` (Story 4-2) | `pending_actions.tier CHECK(IN (1,2,3))` |
| FR-2.5 (Qwen-only sensitivity) | N/A | `classify_sensitivity` per-call assert | `assert_qwen_only(policy)` at FastAPI lifespan + CLI init |
| AR-D12-1 (sensitivity-token handshake) | N/A | `mint_sensitivity_token` refuses confidential + normal; `ask_router(confirmation_token=...)` re-validates | `router_calls.sensitivity_grant_id` audit row records every consume |

See architecture.md "Defense-in-depth pattern for invariants (Rule H)" for the canonical pattern.

### Boundary checker enforcement

[`scripts/check_boundaries.py`](../scripts/check_boundaries.py) runs as the 4th quality gate (alongside pytest, ruff, mypy --strict). Refuses:

- `INSERT INTO router_calls` outside `observability/audit.py`.
- `UPDATE emails SET embedding` outside `ingest/embedding.py` (positional + keyword + f-string forms).
- `sha256(...)` matching the idempotency-key formula shape outside `ingest/idempotency.py`.
- Bare-string Tier-1/2/3 action_type literals (`"delete"`, `"mark_read"`, etc.) outside `actions/types.py` or `tests/`.
- `yaml.safe_load` outside the documented allowlist (`policy.py`, `patterns.py`).
- `os.environ` access outside `config.py` (Rule F).

A new writer-monopoly ships with allowlist entry + violation fixture + positive-pass test + specificity test (Rule G).

---

## Related docs

- [`_bmad-output/planning-artifacts/architecture.md`](../_bmad-output/planning-artifacts/architecture.md) — Architectural decisions, rules, schema implications, defense-in-depth patterns.
- [`docs/auth-recovery.md`](auth-recovery.md) — OAuth refresh-token recovery (`oauth_state` table).
- [`docs/entra-app-registration.md`](entra-app-registration.md) — Initial Microsoft Graph app registration (one-time setup before `oauth_state` can be seeded).
- [`mailbot_api/db/migrations/`](../mailbot_api/db/migrations/) — Migration files themselves.
- [`mailbot_api/db/queries.py`](../mailbot_api/db/queries.py) — Every SQL literal in the codebase (Rule C).

---

## Document conventions

- **Anchor format:** `#NNN_short_name` for migrations, `#tablename` for tables.
- **Cross-links** use relative paths from `docs/` to the rest of the repo.
- **Update on every new migration:** add a row to the migration index + a section under the target table. If the migration introduces a new table, add an entry to the table inventory + a new dedicated section.
- **Generated:** 2026-06-02 (Epic 4 retro action item #8).
