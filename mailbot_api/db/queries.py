"""Centralized SQL query strings per architecture §AR-PAT-1 Rule C.

Every SELECT/INSERT/UPDATE/DELETE/CREATE that ships in production code lives
here, behind a named constant or a small helper. Modules call db.connection
async wrappers (fetchone/fetchall/execute_write) with these constants as the
`query` argument.

Why named constants instead of helper functions: helpers tend to either (a)
duplicate the async-wrapper plumbing, or (b) hide the parameter contract. Named
constants keep the SQL literal here (satisfying Rule C) without forcing a layer
of indirection.

NOTE: db/migrations_runner.py also writes raw SQL (the bookkeeping INSERT into
_migrations); that file is in the boundary checker's allowlist too because its
SQL is part of the migration mechanism itself, not the steady-state query layer.
"""

from __future__ import annotations

# --- oauth_state (Story 1-6) ---

OAUTH_STATE_SELECT = (
    "SELECT provider, refresh_token, access_token, access_expires_at, "
    "last_rotated_at, rotation_count FROM oauth_state WHERE provider = ?"
)

OAUTH_STATE_INSERT_SEED = (
    "INSERT INTO oauth_state (provider, refresh_token, rotation_count) "
    "VALUES (?, ?, 0)"
)

OAUTH_STATE_UPDATE_AFTER_EXCHANGE = (
    "UPDATE oauth_state SET refresh_token = ?, access_token = ?, "
    "access_expires_at = ?, last_rotated_at = ?, rotation_count = ? "
    "WHERE provider = ?"
)


# --- sync_state (Story 1-7) ---

SYNC_STATE_SELECT = (
    "SELECT provider, delta_link, last_sync_at, last_sync_messages_seen "
    "FROM sync_state WHERE provider = ?"
)

SYNC_STATE_UPSERT = (
    "INSERT INTO sync_state (provider, delta_link, last_sync_at, last_sync_messages_seen) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(provider) DO UPDATE SET "
    "delta_link = excluded.delta_link, "
    "last_sync_at = excluded.last_sync_at, "
    "last_sync_messages_seen = excluded.last_sync_messages_seen"
)

# Story 1-10 AC-4/5: clear the stored delta_link when Graph signals the token
# is dead (410 Gone | 404 syncStateNotFound). The next worker iteration sees
# NULL and starts a fresh delta from the default URL. `last_sync_at` is
# touched so the worker-health monitoring observes recent activity (the reset
# is itself a sync event).
SYNC_STATE_UPSERT_NULL_LINK = (
    "INSERT INTO sync_state (provider, delta_link, last_sync_at, last_sync_messages_seen) "
    "VALUES (?, NULL, ?, 0) "
    "ON CONFLICT(provider) DO UPDATE SET "
    "delta_link = NULL, "
    "last_sync_at = excluded.last_sync_at, "
    # Zero messages_seen on the reset iteration so Story 1-8's sync-health
    # alarm doesn't treat a delta-token reset as a normal successful sync —
    # the previous iteration's count would otherwise persist misleadingly.
    "last_sync_messages_seen = 0"
)


# --- senders (Story 1-7) ---

SENDER_UPSERT = (
    "INSERT INTO senders (id, display_name, domain, first_seen_at) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET "
    "display_name = COALESCE(senders.display_name, excluded.display_name)"
)


# --- threads (Story 1-7) ---

THREAD_UPSERT = (
    "INSERT INTO threads (id, subject_normalized, last_message_at, message_count) "
    "VALUES (?, ?, ?, 1) "
    "ON CONFLICT(id) DO UPDATE SET "
    "subject_normalized = COALESCE(threads.subject_normalized, excluded.subject_normalized), "
    "last_message_at = CASE "
    "  WHEN excluded.last_message_at > threads.last_message_at THEN excluded.last_message_at "
    "  ELSE threads.last_message_at END, "
    "message_count = threads.message_count + 1"
)


# --- emails (Story 1-7; Story 1-10 patches docstring + EMAIL_SOFT_DELETE) ---
#
# `change_marker` semantics (Story 1-10 AC-2): the value stored here is Graph's
# `changeKey` field on the message resource — NOT `@odata.etag` (which does not
# exist on the message resource per the Graph API docs). The column name retains
# its Rule-A naming choice (PRD terminology) to avoid a destructive schema
# migration; the docstring documents the protocol-detail mapping. The sync
# worker reads `message["changeKey"]` first and falls back to `@odata.etag` ONLY
# if the field is absent (defensive — production Graph responses always carry
# `changeKey`; the fallback emits a structured warning when it fires).

EMAIL_UPSERT = (
    "INSERT INTO emails ("
    "  graph_id, change_marker, thread_id, sender_id, received_at, "
    "  from_address, from_display_name, subject, body_preview, has_attachments"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(graph_id) DO UPDATE SET "
    "  change_marker = excluded.change_marker, "
    "  thread_id = excluded.thread_id, "
    "  sender_id = excluded.sender_id, "
    "  received_at = excluded.received_at, "
    "  from_address = excluded.from_address, "
    "  from_display_name = excluded.from_display_name, "
    "  subject = excluded.subject, "
    "  body_preview = excluded.body_preview, "
    "  has_attachments = excluded.has_attachments "
    "WHERE emails.change_marker IS NULL OR emails.change_marker != excluded.change_marker"
)

EMAIL_SOFT_DELETE = (
    # Story 1-10 AC-3: also capture the @removed.reason ('changed' | 'deleted'
    # | NULL) so Epic 4's Tier-1 reverter can distinguish recoverable removals
    # from permanent ones. The column was added by migration 005.
    "UPDATE emails SET deleted_at = ?, removed_reason = ? "
    "WHERE graph_id = ? AND deleted_at IS NULL"
)

EMAIL_EXISTS_WITH_MARKER = (
    "SELECT 1 FROM emails WHERE graph_id = ? AND change_marker = ?"
)


# --- worker_health (Story 1-8) ---

WORKER_HEALTH_SELECT = (
    "SELECT component, last_heartbeat_at, last_outcome, last_error "
    "FROM worker_health WHERE component = ?"
)

WORKER_HEALTH_UPSERT = (
    "INSERT INTO worker_health (component, last_heartbeat_at, last_outcome, last_error) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(component) DO UPDATE SET "
    "  last_heartbeat_at = excluded.last_heartbeat_at, "
    "  last_outcome = excluded.last_outcome, "
    "  last_error = excluded.last_error"
)


# --- router_calls (Story 2-1) ---
#
# The ONLY production-code INSERT into router_calls. Boundary-checked at
# scripts/check_boundaries.py; any other module attempting this literal fails
# `make lint`. Callers go through observability/audit.record_router_call().
#
# Column order is load-bearing: record_router_call() builds the parameter
# tuple in this exact order. Any column addition requires synchronizing
# (a) the migration, (b) this INSERT, (c) the param tuple in audit.py,
# (d) the RouterCallRow model.

ROUTER_CALLS_INSERT = (
    "INSERT INTO router_calls ("
    "  ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
    "  tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
    "  outcome, caller_verb, caller_origin, email_id, "
    "  sensitivity_grant_id, sensitivity_grant_minted_at"
    ") VALUES ("
    "  ?, ?, ?, ?, ?, "
    "  ?, ?, ?, ?, ?, "
    "  ?, ?, ?, ?, "
    "  ?, ?"
    ")"
)


# --- response_cache (Story 2-7) ---

RESPONSE_CACHE_SELECT = (
    "SELECT result_json, cost_usd, cached_at, ttl_seconds, hit_count "
    "FROM response_cache WHERE cache_key = ?"
)

RESPONSE_CACHE_INSERT = (
    "INSERT INTO response_cache ("
    "  cache_key, task_type, model, result_json, cost_usd, "
    "  cached_at, ttl_seconds, hit_count"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, 0) "
    "ON CONFLICT(cache_key) DO UPDATE SET "
    "  task_type = excluded.task_type, "
    "  model = excluded.model, "
    "  result_json = excluded.result_json, "
    "  cost_usd = excluded.cost_usd, "
    "  cached_at = excluded.cached_at, "
    "  ttl_seconds = excluded.ttl_seconds"
)

RESPONSE_CACHE_INCREMENT_HIT = (
    "UPDATE response_cache SET hit_count = hit_count + 1 WHERE cache_key = ?"
)


# --- degraded_mode_state (Story 2-8) ---

DEGRADED_MODE_SELECT = (
    "SELECT active, entered_at, exited_at FROM degraded_mode_state WHERE id = 1"
)

DEGRADED_MODE_ENTER = (
    "UPDATE degraded_mode_state SET active = 1, entered_at = ?, exited_at = NULL WHERE id = 1"
)

DEGRADED_MODE_EXIT = (
    "UPDATE degraded_mode_state SET active = 0, exited_at = ? WHERE id = 1"
)


# --- router_calls aggregations (Story 2-8) ---

ROUTER_CALLS_SPEND_SINCE = (
    "SELECT COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ?"
)


# --- pause_state (Story 2-9) ---

PAUSE_STATE_SELECT = (
    "SELECT paused, reason, paused_at, resumed_at FROM pause_state WHERE id = 1"
)

PAUSE_STATE_PAUSE = (
    "UPDATE pause_state SET paused = 1, reason = ?, paused_at = ?, resumed_at = NULL WHERE id = 1"
)

PAUSE_STATE_RESUME = (
    "UPDATE pause_state SET paused = 0, resumed_at = ? WHERE id = 1"
)


# --- call_volume_baseline (Story 2-9) ---

CALL_VOLUME_LAST_HOUR_BY_ORIGIN = (
    "SELECT caller_origin, COUNT(*) FROM router_calls "
    "WHERE ts >= ? GROUP BY caller_origin"
)

CALL_VOLUME_BASELINE_SELECT = (
    "SELECT mean_volume, stddev_volume, sample_count FROM call_volume_baseline "
    "WHERE caller_origin = ? AND hour_of_day = ?"
)

# --- cost breakdown aggregations (Story 2-10) ---

ROUTER_CALLS_TOTALS_SINCE = (
    "SELECT "
    "  COUNT(*), "
    "  COALESCE(SUM(cost_usd_estimated), 0), "
    "  COALESCE(SUM(cached_tokens_in), 0), "
    "  COALESCE(SUM(tokens_in), 0) "
    "FROM router_calls WHERE ts >= ?"
)

ROUTER_CALLS_BY_TASK_SINCE = (
    "SELECT task_type, COALESCE(SUM(cost_usd_estimated), 0) "
    "FROM router_calls WHERE ts >= ? GROUP BY task_type"
)

ROUTER_CALLS_BY_MODEL_SINCE = (
    "SELECT model_chosen, COALESCE(SUM(cost_usd_estimated), 0) "
    "FROM router_calls WHERE ts >= ? GROUP BY model_chosen"
)

ROUTER_CALLS_BY_CALLER_ORIGIN_SINCE = (
    "SELECT caller_origin, COALESCE(SUM(cost_usd_estimated), 0) "
    "FROM router_calls WHERE ts >= ? GROUP BY caller_origin"
)

# Hermes aux drift detection (Story 2-10 AC).
ROUTER_CALLS_HERMES_AUX_SINCE = (
    "SELECT COUNT(*) FROM router_calls "
    "WHERE ts >= ? AND caller_origin LIKE 'hermes-aux-%'"
)


CALL_VOLUME_BASELINE_UPSERT = (
    "INSERT INTO call_volume_baseline ("
    "  caller_origin, hour_of_day, mean_volume, stddev_volume, sample_count, last_updated"
    ") VALUES (?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(caller_origin, hour_of_day) DO UPDATE SET "
    "  mean_volume = excluded.mean_volume, "
    "  stddev_volume = excluded.stddev_volume, "
    "  sample_count = excluded.sample_count, "
    "  last_updated = excluded.last_updated"
)
