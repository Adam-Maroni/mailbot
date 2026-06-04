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

OAUTH_STATE_INSERT_SEED = "INSERT INTO oauth_state (provider, refresh_token, rotation_count) VALUES (?, ?, 0)"

# Story 6-6: worker's drainer-side access-token cache refresher reads just
# the access_token column on every refresh (cheaper than the full SELECT).
OAUTH_STATE_ACCESS_TOKEN_SELECT = "SELECT access_token FROM oauth_state WHERE provider = ?"  # noqa: S105

OAUTH_STATE_UPDATE_AFTER_EXCHANGE = (
    "UPDATE oauth_state SET refresh_token = ?, access_token = ?, "
    "access_expires_at = ?, last_rotated_at = ?, rotation_count = ? "
    "WHERE provider = ?"
)


# --- sync_state (Story 1-7) ---

SYNC_STATE_SELECT = (
    "SELECT provider, delta_link, last_sync_at, last_sync_messages_seen FROM sync_state WHERE provider = ?"
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
    "UPDATE emails SET deleted_at = ?, removed_reason = ? WHERE graph_id = ? AND deleted_at IS NULL"
)

EMAIL_EXISTS_WITH_MARKER = "SELECT 1 FROM emails WHERE graph_id = ? AND change_marker = ?"


# --- emails: sensitivity (Story 3-3) ---
#
# Three constants supporting the sensitivity classifier (AC-1) and the Router
# precondition layer (AC-5):
#   1. EMAIL_BODY_FOR_SENSITIVITY_SELECT — reads (subject, from_address,
#      body_preview) for a single graph_id. Used by classify_sensitivity to
#      populate the prompt's USER_TEMPLATE placeholders.
#   2. EMAIL_SENSITIVITY_SELECT — reads (sensitivity, sensitivity_at) for a
#      single graph_id. Used by the Router precondition layer to decide
#      whether to refuse with SENSITIVITY_NOT_CLASSIFIED / SENSITIVITY_BLOCKS_API.
#   3. EMAIL_SENSITIVITY_UPDATE — atomic write of sensitivity + all 4
#      companion fields + override_reason in a single execute_write.

EMAIL_BODY_FOR_SENSITIVITY_SELECT = "SELECT subject, from_address, body_preview FROM emails WHERE graph_id = ?"

EMAIL_SENSITIVITY_SELECT = "SELECT sensitivity, sensitivity_at FROM emails WHERE graph_id = ?"

EMAIL_SENSITIVITY_UPDATE = (
    "UPDATE emails SET "
    "  sensitivity = ?, "
    "  sensitivity_prompt_v = ?, "
    "  sensitivity_conf = ?, "
    "  sensitivity_model = ?, "
    "  sensitivity_at = ?, "
    "  sensitivity_override_reason = ? "
    "WHERE graph_id = ?"
)


# --- emails: per-task derived field updates (Story 3-5) ---
#
# Five atomic UPDATE constants for the pipeline's per-step writes. Each
# writes the derived value column + its 4 standard companions
# (*_prompt_v / _conf / _model / _at) in a single execute_write.
#
# Sensitivity (Story 3-3 EMAIL_SENSITIVITY_UPDATE) and embedding (Story 3-4
# EMAIL_EMBEDDING_UPDATE) are NOT here — those modules own their writes
# per the writer-monopoly contracts. These constants serve the remaining
# 5 ingest tasks: class_coarse, class_fine, summary_short, importance_score,
# action_extraction.

EMAIL_CLASS_COARSE_UPDATE = (
    "UPDATE emails SET "
    "  class_coarse = ?, "
    "  class_coarse_prompt_v = ?, "
    "  class_coarse_conf = ?, "
    "  class_coarse_model = ?, "
    "  class_coarse_at = ? "
    "WHERE graph_id = ?"
)

EMAIL_CLASS_FINE_UPDATE = (
    "UPDATE emails SET "
    "  class_fine = ?, "
    "  class_fine_prompt_v = ?, "
    "  class_fine_conf = ?, "
    "  class_fine_model = ?, "
    "  class_fine_at = ? "
    "WHERE graph_id = ?"
)

EMAIL_SUMMARY_SHORT_UPDATE = (
    "UPDATE emails SET "
    "  summary_short = ?, "
    "  summary_short_prompt_v = ?, "
    "  summary_short_conf = ?, "
    "  summary_short_model = ?, "
    "  summary_short_at = ? "
    "WHERE graph_id = ?"
)

EMAIL_IMPORTANCE_SCORE_UPDATE = (
    "UPDATE emails SET "
    "  importance_score = ?, "
    "  importance_score_prompt_v = ?, "
    "  importance_score_conf = ?, "
    "  importance_score_model = ?, "
    "  importance_score_at = ? "
    "WHERE graph_id = ?"
)

EMAIL_ACTION_EXTRACTION_UPDATE = (
    "UPDATE emails SET "
    "  action_extraction = ?, "
    "  action_extraction_prompt_v = ?, "
    "  action_extraction_conf = ?, "
    "  action_extraction_model = ?, "
    "  action_extraction_at = ? "
    "WHERE graph_id = ?"
)


# --- emails: sensitivity override re-write (Story 3-5 AC-3 + Dev Notes) ---
#
# After classify_sensitivity (Story 3-3) writes the raw classifier result, the
# pipeline orchestrator runs apply_pattern_override and may need to re-write
# just the sensitivity + sensitivity_override_reason columns (preserving the
# original prompt_v/conf/model/at from the classifier run).

EMAIL_SENSITIVITY_OVERRIDE_REWRITE = (
    "UPDATE emails SET sensitivity = ?, sensitivity_override_reason = ? WHERE graph_id = ?"
)

# Story 3-5: hot-path read used by pipeline._run_sensitivity_step to detect
# a previously-classified email (short-circuit step 1).
EMAIL_SENSITIVITY_DETAIL_SELECT = (
    "SELECT sensitivity, sensitivity_at, sensitivity_conf, sensitivity_model FROM emails WHERE graph_id = ?"
)

# Story 3-5: hot-path read used by pipeline after a class_coarse idempotency
# short-circuit so the fine_class conditional gate still resolves correctly.
EMAIL_CLASS_COARSE_SELECT = "SELECT class_coarse FROM emails WHERE graph_id = ?"


# --- derivations_idempotency (Story 3-5) ---

DERIVATIONS_IDEMPOTENCY_SELECT = (
    "SELECT idempotency_key FROM derivations_idempotency WHERE email_id = ? AND task_type = ?"
)

DERIVATIONS_IDEMPOTENCY_UPSERT = (
    "INSERT INTO derivations_idempotency (email_id, task_type, idempotency_key, applied_at) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT (email_id, task_type) DO UPDATE SET "
    "  idempotency_key = excluded.idempotency_key, "
    "  applied_at = excluded.applied_at"
)


# --- emails: embedding (Story 3-4) ---
#
# Two constants for the embedding writer-monopoly contract:
#   1. EMAIL_EMBEDDING_UPDATE — atomic write of all 6 embedding columns:
#      embedding (BLOB), embedding_dtype (TEXT), embedding_shape (TEXT),
#      embedding_prompt_v (TEXT — sentinel "v1"; embeddings have no prompts),
#      embedding_model (TEXT), embedding_at (TEXT). embedding_conf stays NULL
#      by contract (no confidence concept for embeddings).
#   2. EMAIL_EMBEDDING_SELECT — hot-path read for read_embedding: just the
#      blob + the two W-5 companion columns. Story 3-1's
#      EMAIL_DERIVED_FIELDS_SELECT also returns these, but EMAIL_EMBEDDING_SELECT
#      is narrower for the embed-read inner loop.

EMAIL_EMBEDDING_UPDATE = (
    "UPDATE emails SET "
    "  embedding = ?, "
    "  embedding_dtype = ?, "
    "  embedding_shape = ?, "
    "  embedding_prompt_v = ?, "
    "  embedding_model = ?, "
    "  embedding_at = ? "
    "WHERE graph_id = ?"
)

EMAIL_EMBEDDING_SELECT = "SELECT embedding, embedding_dtype, embedding_shape FROM emails WHERE graph_id = ?"


# --- emails: derived fields (Story 3-1) ---
#
# Selects every derived-value column and its companion metadata
# (*_prompt_v / _conf / _model / _at) for a single email row keyed by graph_id.
# Used by Stories 3-3 through 3-8 to inspect what has and hasn't been derived
# yet, and by integration tests verifying migration 011 applies the W-5
# companion columns (embedding_dtype, embedding_shape) cleanly. Listed
# explicitly (no SELECT *) per AR-PAT-1 producer-boundary discipline.

EMAIL_DERIVED_FIELDS_SELECT = (
    "SELECT "
    "  sensitivity, sensitivity_prompt_v, sensitivity_conf, "
    "  sensitivity_model, sensitivity_at, "
    "  class_coarse, class_coarse_prompt_v, class_coarse_conf, "
    "  class_coarse_model, class_coarse_at, "
    "  class_fine, class_fine_prompt_v, class_fine_conf, "
    "  class_fine_model, class_fine_at, "
    "  summary_short, summary_short_prompt_v, summary_short_conf, "
    "  summary_short_model, summary_short_at, "
    "  importance_score, importance_score_prompt_v, importance_score_conf, "
    "  importance_score_model, importance_score_at, "
    "  action_extraction, action_extraction_prompt_v, action_extraction_conf, "
    "  action_extraction_model, action_extraction_at, "
    "  embedding, embedding_prompt_v, embedding_conf, "
    "  embedding_model, embedding_at, "
    "  embedding_dtype, embedding_shape "
    "FROM emails WHERE graph_id = ?"
)


# --- senders + threads: enrichment (Story 3-7) ---
#
# Read + write constants for sender_reputation_summary and thread_continuity_note.
# Cross-email synthesis stays Qwen-local per Rule F.1 and is cached forever
# per Rule A.

SENDER_REPUTATION_SELECT = "SELECT sender_reputation_summary FROM senders WHERE id = ?"

EMAILS_RECENT_BY_SENDER_SELECT = (
    "SELECT graph_id, subject, received_at, body_preview, sensitivity "
    "FROM emails "
    "WHERE sender_id = ? AND deleted_at IS NULL "
    "ORDER BY received_at DESC "
    "LIMIT 5"
)

SENDER_REPUTATION_UPDATE = (
    "UPDATE senders SET "
    "  sender_reputation_summary = ?, "
    "  sender_reputation_summary_prompt_v = ?, "
    "  sender_reputation_summary_conf = ?, "
    "  sender_reputation_summary_model = ?, "
    "  sender_reputation_summary_at = ? "
    "WHERE id = ?"
)

THREAD_CONTINUITY_SELECT = "SELECT message_count, thread_continuity_note FROM threads WHERE id = ?"

EMAILS_BY_THREAD_SELECT = (
    "SELECT graph_id, subject, received_at, body_preview, sensitivity "
    "FROM emails "
    "WHERE thread_id = ? AND deleted_at IS NULL "
    "ORDER BY received_at ASC "
    "LIMIT 20"
)

THREAD_CONTINUITY_UPDATE = (
    "UPDATE threads SET "
    "  thread_continuity_note = ?, "
    "  thread_continuity_note_prompt_v = ?, "
    "  thread_continuity_note_conf = ?, "
    "  thread_continuity_note_model = ?, "
    "  thread_continuity_note_at = ? "
    "WHERE id = ?"
)


# --- emails: re-derivation queries (Story 3-8) ---
#
# Per-task "rows needing re-derivation since DATE" queries. Each follows the
# pattern: graph_id rows where received_at >= ? AND (<task>_at IS NULL OR
# <task>_prompt_v != ?) AND deleted_at IS NULL ORDER BY received_at DESC.
#
# Sensitivity is its own column family (no `class_` prefix); embedding has
# the W-5 dtype/shape companion columns. Each query has the same parameter
# shape: (since_iso, target_prompt_v).

EMAILS_NEEDING_REDERIVATION_SENSITIVITY = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (sensitivity_at IS NULL OR sensitivity_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_COARSE_CLASS = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (class_coarse_at IS NULL OR class_coarse_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_FINE_CLASS = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (class_fine_at IS NULL OR class_fine_prompt_v != ?) "
    "AND class_coarse = 'human' "  # fine_class only applies after human gate
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_SUMMARY_SHORT = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (summary_short_at IS NULL OR summary_short_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_IMPORTANCE_SCORING = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (importance_score_at IS NULL OR importance_score_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_ACTION_EXTRACTION = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (action_extraction_at IS NULL OR action_extraction_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

EMAILS_NEEDING_REDERIVATION_EMBEDDING = (
    "SELECT graph_id FROM emails "
    "WHERE received_at >= ? AND deleted_at IS NULL "
    "AND (embedding_at IS NULL OR embedding_prompt_v != ?) "
    "ORDER BY received_at DESC"
)

# Count of selected rows that ALSO have sensitivity_at IS NULL — used by
# AC-4 to refuse non-sensitivity re-derivation when any row is unclassified.
EMAILS_REDERIVATION_UNCLASSIFIED_COUNT = (
    "SELECT COUNT(*) FROM emails "
    "WHERE graph_id IN ({placeholders}) AND sensitivity_at IS NULL"
)

# AC-5: clear ALL downstream derived fields when re-deriving sensitivity_class.
# Wipes 6 column families × 5–7 columns each. The atomic UPDATE keeps the row
# in a consistent state — either all downstream cleared or none.
EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS = (
    "UPDATE emails SET "
    "  class_coarse = NULL, class_coarse_prompt_v = NULL, class_coarse_conf = NULL, "
    "  class_coarse_model = NULL, class_coarse_at = NULL, "
    "  class_fine = NULL, class_fine_prompt_v = NULL, class_fine_conf = NULL, "
    "  class_fine_model = NULL, class_fine_at = NULL, "
    "  summary_short = NULL, summary_short_prompt_v = NULL, summary_short_conf = NULL, "
    "  summary_short_model = NULL, summary_short_at = NULL, "
    "  importance_score = NULL, importance_score_prompt_v = NULL, importance_score_conf = NULL, "
    "  importance_score_model = NULL, importance_score_at = NULL, "
    "  action_extraction = NULL, action_extraction_prompt_v = NULL, action_extraction_conf = NULL, "
    "  action_extraction_model = NULL, action_extraction_at = NULL, "
    "  embedding = NULL, embedding_prompt_v = NULL, embedding_conf = NULL, "
    "  embedding_model = NULL, embedding_at = NULL, "
    "  embedding_dtype = NULL, embedding_shape = NULL "
    "WHERE graph_id = ?"
)

# AC-5: delete derivations_idempotency rows for an email_id so subsequent
# pipeline runs re-derive the downstream tasks.
DERIVATIONS_IDEMPOTENCY_DELETE_FOR_EMAIL = (
    "DELETE FROM derivations_idempotency WHERE email_id = ?"
)

# Story 3-8 re-derive embedding: clear the existing blob so embed_email's
# read_embedding != None short-circuit doesn't fire on the re-derive path.
EMAIL_EMBEDDING_CLEAR = "UPDATE emails SET embedding = NULL WHERE graph_id = ?"


# --- emails: unprocessed queue (Story 3-6) ---
#
# Backpressure-aware drain queries. The "unprocessed" condition is
# `sensitivity_at IS NULL AND deleted_at IS NULL` — the FR-2.3 hard invariant
# treats sensitivity as the entry gate to the pipeline. Soft-deleted rows
# (Story 1-10) are skipped — they shouldn't be derived for. Ordering is
# `received_at DESC` per epic spec rationale.

EMAIL_UNPROCESSED_COUNT_SELECT = "SELECT COUNT(*) FROM emails WHERE sensitivity_at IS NULL AND deleted_at IS NULL"

EMAIL_UNPROCESSED_BATCH_SELECT = (
    "SELECT graph_id FROM emails WHERE sensitivity_at IS NULL AND deleted_at IS NULL ORDER BY received_at DESC LIMIT ?"
)


# --- worker_health (Story 1-8) ---

WORKER_HEALTH_SELECT = (
    "SELECT component, last_heartbeat_at, last_outcome, last_error FROM worker_health WHERE component = ?"
)

WORKER_HEALTH_UPSERT = (
    "INSERT INTO worker_health (component, last_heartbeat_at, last_outcome, last_error) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(component) DO UPDATE SET "
    "  last_heartbeat_at = excluded.last_heartbeat_at, "
    "  last_outcome = excluded.last_outcome, "
    "  last_error = excluded.last_error"
)


# --- Story 6-1: status assembler reads (mailbot_api/observability/status.py) ---
#
# All 5 queries below land in the status board read-path; collectively they
# must execute in < 1s on 100k router_calls (per AC perf budget). Each one
# either hits an existing index (router_calls.ts, pending_actions.status) or
# does a small COUNT(*) — verified via `EXPLAIN QUERY PLAN` during dev.

PENDING_ACTIONS_COUNT_BY_TIER = (
    "SELECT tier, COUNT(*) FROM pending_actions "
    "WHERE status IN ('pending', 'pending_grant', 'cooling_off') "
    "GROUP BY tier"
)

PENDING_ACTIONS_AWAITING_GRANT_COUNT = (
    "SELECT COUNT(*) FROM pending_actions WHERE status = 'pending_grant'"
)

PENDING_ACTIONS_FAILED_LAST_24H = (
    "SELECT COUNT(*) FROM pending_actions "
    "WHERE status = 'failed' AND terminal_at >= ?"
)

ROUTER_CALLS_CACHE_HIT_RATE_LAST_7D = (
    "SELECT COALESCE(SUM(cached_tokens_in), 0), COALESCE(SUM(tokens_in), 0) "
    "FROM router_calls WHERE ts >= ?"
)

ROUTER_CALLS_LAST_N_ERRORS = (
    "SELECT id, ts, task_type, model_chosen, outcome, caller_origin "
    "FROM router_calls WHERE outcome IN ('failed', 'retry_recovered') "
    "ORDER BY ts DESC LIMIT ?"
)

ROUTER_CALLS_HERMES_AUX_COUNT_LAST_24H = (
    # Story 6-1 CR-1: post-Story-6-0 reality is that Hermes's real config
    # schema has no `headers:` key on auxiliary entries (see RECONCILIATION-NOTES
    # §1.6), so production auxiliary calls land with caller_origin = 'hermes_aux'
    # (single value, underscore). The legacy 'hermes-aux-*' pattern is what
    # Story 2-10's test fixtures + the original chat-completions header-propagation
    # path produce. Match BOTH so the query stays correct across the corrective.
    "SELECT COUNT(*) FROM router_calls "
    "WHERE (caller_origin = 'hermes_aux' OR caller_origin LIKE 'hermes-aux%') "
    "AND ts >= ?"
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
    "  sensitivity_grant_id, sensitivity_grant_minted_at, "
    "  tool_calls_count, tool_calls_summary"
    ") VALUES ("
    "  ?, ?, ?, ?, ?, "
    "  ?, ?, ?, ?, ?, "
    "  ?, ?, ?, ?, "
    "  ?, ?, "
    "  ?, ?"
    ")"
)


# --- response_cache (Story 2-7) ---

RESPONSE_CACHE_SELECT = (
    "SELECT result_json, cost_usd, cached_at, ttl_seconds, hit_count FROM response_cache WHERE cache_key = ?"
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

RESPONSE_CACHE_INCREMENT_HIT = "UPDATE response_cache SET hit_count = hit_count + 1 WHERE cache_key = ?"


# --- degraded_mode_state (Story 2-8) ---

DEGRADED_MODE_SELECT = "SELECT active, entered_at, exited_at FROM degraded_mode_state WHERE id = 1"

DEGRADED_MODE_ENTER = "UPDATE degraded_mode_state SET active = 1, entered_at = ?, exited_at = NULL WHERE id = 1"

DEGRADED_MODE_EXIT = "UPDATE degraded_mode_state SET active = 0, exited_at = ? WHERE id = 1"


# --- router_calls aggregations (Story 2-8) ---

ROUTER_CALLS_SPEND_SINCE = "SELECT COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ?"


# --- pause_state (Story 2-9) ---

PAUSE_STATE_SELECT = "SELECT paused, reason, paused_at, resumed_at FROM pause_state WHERE id = 1"

PAUSE_STATE_PAUSE = "UPDATE pause_state SET paused = 1, reason = ?, paused_at = ?, resumed_at = NULL WHERE id = 1"

PAUSE_STATE_RESUME = "UPDATE pause_state SET paused = 0, resumed_at = ? WHERE id = 1"


# --- call_volume_baseline (Story 2-9) ---

CALL_VOLUME_LAST_HOUR_BY_ORIGIN = (
    "SELECT caller_origin, COUNT(*) FROM router_calls WHERE ts >= ? GROUP BY caller_origin"
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
    "SELECT task_type, COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ? GROUP BY task_type"
)

ROUTER_CALLS_BY_MODEL_SINCE = (
    "SELECT model_chosen, COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ? GROUP BY model_chosen"
)

ROUTER_CALLS_BY_CALLER_ORIGIN_SINCE = (
    "SELECT caller_origin, COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ? GROUP BY caller_origin"
)

# Hermes aux drift detection (Story 2-10 AC).
ROUTER_CALLS_HERMES_AUX_SINCE = (
    # Story 6-1 CR-1 coordination fix: post-Story-6-0 real Hermes config has no
    # `headers:` key on auxiliary entries, so production lands `caller_origin =
    # 'hermes_aux'` (underscore). Legacy header-propagation path stays as the
    # 'hermes-aux-*' family. Match BOTH so the count is correct across stacks.
    "SELECT COUNT(*) FROM router_calls "
    "WHERE ts >= ? AND (caller_origin = 'hermes_aux' OR caller_origin LIKE 'hermes-aux-%')"
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


# --- pending_actions (Story 4-2) ---

PENDING_ACTION_INSERT = (
    "INSERT INTO pending_actions ("
    "  email_id, action_type, tier, payload, proposed_at, "
    "  proposed_by_grant_id, change_marker_at_propose, status"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

PENDING_ACTION_SELECT_BY_ID = (
    "SELECT id, email_id, action_type, tier, payload, proposed_at, "
    "proposed_by_grant_id, change_marker_at_propose, status, retry_count, "
    "failure_reason, terminal_at, budget_consumed "
    "FROM pending_actions WHERE id = ?"
)

# Read-only lookup of change_marker + deleted_at for propose-time capture.
# Returns (change_marker, deleted_at) or None if the email_id doesn't exist.
EMAIL_MARKER_AND_DELETED_AT_SELECT = (
    "SELECT change_marker, deleted_at FROM emails WHERE graph_id = ?"
)


# --- action_grants (Story 4-3) ---

ACTION_GRANT_INSERT = (
    "INSERT INTO action_grants (action_type, email_ids, expires_at, minted_at) "
    "VALUES (?, ?, ?, ?)"
)

# Returns (id, email_ids JSON) rows for grants matching the action_type that
# haven't expired and aren't revoked. The caller (is_grant_valid) parses
# email_ids and checks whether the target email_id is in the list (or whether
# the list is empty, for email-less grants).
ACTION_GRANT_FIND_VALID = (
    "SELECT id, email_ids FROM action_grants "
    "WHERE action_type = ? AND expires_at > ? AND revoked_at IS NULL "
    "ORDER BY id ASC"
)

ACTION_GRANT_REVOKE = (
    "UPDATE action_grants SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL"
)


# --- drainer (Story 4-4) ---

# Select up to N pending-status rows in priority order (tier ASC = Tier-1 first;
# proposed_at ASC = FIFO within tier).
PENDING_ACTIONS_SELECT_DRAINABLE = (
    "SELECT id, email_id, action_type, tier, payload, proposed_at, "
    "proposed_by_grant_id, change_marker_at_propose, status, retry_count, "
    "failure_reason, terminal_at, budget_consumed "
    "FROM pending_actions WHERE status = 'pending' "
    "ORDER BY tier ASC, proposed_at ASC LIMIT ?"
)

# Atomic claim: flip pending → draining only if still pending. rowcount=1 means
# we own the row; rowcount=0 means a concurrent drainer beat us to it.
PENDING_ACTION_CLAIM_DRAINING = (
    "UPDATE pending_actions SET status = 'draining' "
    "WHERE id = ? AND status = 'pending'"
)

PENDING_ACTION_MARK_APPLIED = (
    "UPDATE pending_actions SET status = 'applied', terminal_at = ?, budget_consumed = ? "
    "WHERE id = ?"
)

# Identical to MARK_APPLIED but also writes proposed_by_grant_id — used on the
# Tier-2/3 success path when the drainer resolved a valid grant before dispatch.
PENDING_ACTION_MARK_APPLIED_WITH_GRANT = (
    "UPDATE pending_actions SET status = 'applied', terminal_at = ?, "
    "budget_consumed = ?, proposed_by_grant_id = ? WHERE id = ?"
)

PENDING_ACTION_MARK_FAILED = (
    "UPDATE pending_actions SET status = 'failed', failure_reason = ?, "
    "terminal_at = ?, budget_consumed = ? WHERE id = ?"
)

# Used when a Tier-2/3 row is being drained but the grant isn't yet valid —
# revert to pending_grant so the cooling-off/grant flow can complete it later.
PENDING_ACTION_REVERT_TO_PENDING_GRANT = (
    "UPDATE pending_actions SET status = 'pending_grant', "
    "proposed_by_grant_id = ? WHERE id = ?"
)

# F22 (Story 6-6.5 walk, 2026-06-04): promote pending_grant rows back to
# pending after a matching grant is minted. Filters by action_type only;
# email_id matching happens in is_grant_valid() at drain time (handles the
# JSON-list email_ids semantics including the empty-list = all-emails case).
PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE = (
    "UPDATE pending_actions SET status = 'pending' "
    "WHERE status = 'pending_grant' AND action_type = ?"
)

# Pre-state snapshot for revert (Story 4-8 consumes). For Story 4-4 the
# pre_state JSON is empty `{}` for every action_type — the emails table
# doesn't carry the per-action fields (is_read, folder_id, categories) that
# revert would need. Story 4-8 will either (a) add those columns to emails
# via a migration, OR (b) re-read the field from the live Graph row at
# revert time. Either path is the reverter's choice.
ACTION_HISTORY_INSERT = (
    "INSERT INTO action_history (action_id, pre_state, applied_at) VALUES (?, ?, ?)"
)


# --- replay (Story 4-5 mailbot replay CLI) ---

# Resets a terminal-failed row back to pending for re-drain by the worker.
# Conditional WHERE clause ensures we only replay rows that ARE failed (not
# applied or already pending).
PENDING_ACTION_REPLAY_RESET = (
    "UPDATE pending_actions SET status = 'pending', retry_count = 0, "
    "terminal_at = NULL, failure_reason = NULL "
    "WHERE id = ? AND status = 'failed'"
)


# --- cooling-off + cancel (Story 4-6) ---

# Promotes cooling_off rows whose proposed_at is older than the window.
# Per AC-1: atomic UPDATE with status='cooling_off' guard is race-safe vs cancel.
COOLING_OFF_PROMOTE_DUE = (
    "UPDATE pending_actions SET status = 'pending' "
    "WHERE status = 'cooling_off' AND proposed_at <= ?"
)

# Atomic cancel: only flips if still in cooling_off (race with promote).
PENDING_ACTION_CANCEL_FROM_COOLING_OFF = (
    "UPDATE pending_actions SET status = 'cancelled', terminal_at = ? "
    "WHERE id = ? AND status = 'cooling_off'"
)

# Count of SEND-family rows that consumed budget since today's UTC midnight.
# Used by Story 4-6's hard 20-send/day cap enforcement.
SEND_FAMILY_BUDGET_CONSUMED_TODAY_COUNT = (
    "SELECT COUNT(*) FROM pending_actions WHERE budget_consumed = 1 "
    "AND action_type IN ('send_reply', 'send_new_email', 'send_forward', 'reply_to_inactive_thread') "
    "AND terminal_at >= ?"
)


# --- revert (Story 4-8) ---

ACTION_HISTORY_SELECT_BY_ACTION_ID = (
    "SELECT pre_state, applied_at, reverted_at FROM action_history WHERE action_id = ?"
)

ACTION_HISTORY_MARK_REVERTED = (
    "UPDATE action_history SET reverted_at = ? WHERE action_id = ? AND reverted_at IS NULL"
)


# --- read-side verbs (Story 5-1) ---

# Projection field list (Rule J — no body fields). Kept as a string fragment so
# both FIND_EMAILS_PROJECTION_SELECT and GET_THREAD_PROJECTION_SELECT pull the
# same column shape — staying parallel matters because the Python verbs map
# both to the same EmailProjection Pydantic model.
EMAIL_PROJECTION_COLUMNS = (
    "graph_id, received_at, from_address, from_display_name, subject, "
    "summary_short, class_coarse, importance_score, sensitivity, has_attachments"
)

# Base SELECT for find_emails — WHERE clause is built dynamically by the verb,
# always parameterized via ? placeholders. The verb starts from
# FIND_EMAILS_SELECT_BASE and appends `AND col = ?` clauses + ORDER BY + LIMIT.
# noqa S608: the f-string only interpolates the fixed-string EMAIL_PROJECTION_COLUMNS
# constant defined above. No user input is concatenated here; user input only
# enters via parameterized `?` placeholders at the verb call site.
FIND_EMAILS_SELECT_BASE = (
    f"SELECT {EMAIL_PROJECTION_COLUMNS} FROM emails WHERE deleted_at IS NULL"  # noqa: S608
)

# Base SELECT for count_emails — parallel to FIND_EMAILS_SELECT_BASE but counts.
COUNT_EMAILS_SELECT_BASE = "SELECT COUNT(*) FROM emails WHERE deleted_at IS NULL"

# hydrate_email — single-row SELECT by graph_id. Returns the full hydration shape.
HYDRATE_EMAIL_SELECT = (
    "SELECT graph_id, received_at, from_address, from_display_name, subject, "
    "body_preview, summary_short, summary_short_at, class_coarse, class_coarse_at, "
    "class_fine, class_fine_at, importance_score, importance_score_at, "
    "sensitivity, sensitivity_at, action_extraction, action_extraction_at, "
    "has_attachments, thread_id, deleted_at "
    "FROM emails WHERE graph_id = ?"
)

# get_thread — projections for every email in a thread, ordered ASC.
# Same noqa rationale as FIND_EMAILS_SELECT_BASE above.
GET_THREAD_PROJECTION_SELECT = (
    f"SELECT {EMAIL_PROJECTION_COLUMNS} FROM emails "  # noqa: S608
    "WHERE thread_id = ? AND deleted_at IS NULL ORDER BY received_at ASC"
)

# Threads metadata for get_thread (continuity note only).
# CR finding 7: threads.message_count is intentionally NOT selected here — the
# get_thread verb returns a LIVE count of non-soft-deleted emails computed at
# the verb boundary. The cached threads.message_count includes soft-deleted
# rows, so the two would diverge. Co-locating the divergence here prevents a
# future reader from re-introducing the cached value silently.
GET_THREAD_META_SELECT = (
    "SELECT thread_continuity_note FROM threads WHERE id = ?"
)

# get_sender_summary — exact-match by sender_address against senders + an
# aggregate of message_count / last_seen_at from emails. The senders table is
# keyed by lowercased address (per 001_init).
GET_SENDER_BASE_SELECT = (
    "SELECT id, display_name, sender_reputation_summary FROM senders WHERE id = ?"
)

GET_SENDER_AGGREGATE_SELECT = (
    "SELECT COUNT(*), MAX(received_at) FROM emails "
    "WHERE LOWER(from_address) = ? AND deleted_at IS NULL"
)


# --- chat orchestrator (Story 5-9) ---

# Story 5-9 AC-2: orchestrator-side sensitivity check before dispatching
# tone_style_mirror / draft_reply. The Router precondition layer (Story 3-3)
# would catch sensitivity violations anyway, but the orchestrator short-circuits
# at the chat surface to avoid even the cache-warmed Opus call.
EMAIL_SENSITIVITY_BY_GRAPH_ID = (
    "SELECT sensitivity, subject, body_preview, from_address "
    "FROM emails WHERE graph_id = ? AND deleted_at IS NULL"
)


# --- notification_mutes (Story 5-6) ---

# Pre-write read used to determine `previously_muted` for the verb response.
NOTIFICATION_MUTES_SELECT_BY_CATEGORY = (
    "SELECT category, muted_until, muted_at FROM notification_mutes WHERE category = ?"
)

# UPSERT: insert new row or overwrite the existing one's muted_until + muted_at.
# Story 5-6 AC-2: calling /mute on an already-muted category overwrites the
# previous muted_until value with the new one (so Adam can extend or shorten
# the window without manually unmuting first).
NOTIFICATION_MUTES_UPSERT = (
    "INSERT INTO notification_mutes (category, muted_until, muted_at) "
    "VALUES (?, ?, ?) "
    "ON CONFLICT(category) DO UPDATE SET "
    "muted_until = excluded.muted_until, "
    "muted_at = excluded.muted_at"
)


# --- notifications_outbox (Story 6-3) ---

# Enqueue. tier is 'urgent' or 'important'; informational/silent never reach
# the DB.
NOTIFICATIONS_OUTBOX_INSERT = (
    "INSERT INTO notifications_outbox "
    "(tier, category, message, enqueued_at) "
    "VALUES (?, ?, ?, ?)"
)

# Hermes-polled pull. Urgent-tier only; important rows belong to Story 6-5's
# 08:00 digest. ORDER BY enqueued_at ASC for FIFO; LIMIT respects the caller's
# batch cap (default 10 in the verb wrapper).
NOTIFICATIONS_OUTBOX_PULL_PENDING_URGENT = (
    "SELECT id, tier, category, message, enqueued_at, attempt_count "
    "FROM notifications_outbox "
    "WHERE delivery_status='pending' AND tier='urgent' "
    "ORDER BY enqueued_at ASC LIMIT ?"
)

# Atomic claim — runs in the same transaction as the pull. The
# `delivery_status='pending'` predicate makes concurrent claims race-safe:
# if another Hermes poller already flipped the row to 'delivering', this
# UPDATE matches 0 rows and the verb skips the claim. The IN(?) shape is
# expanded at call time via parameterized placeholders.
NOTIFICATIONS_OUTBOX_CLAIM_ONE_FOR_DELIVERY = (
    "UPDATE notifications_outbox "
    "SET delivery_status='delivering', "
    "    attempt_count = attempt_count + 1, "
    "    last_attempt_at = ? "
    "WHERE id = ? AND delivery_status='pending'"
)

# Ack: success. delivered_at gets the wall-clock ts; status transitions to
# the terminal 'ok' state.
NOTIFICATIONS_OUTBOX_ACK_OK = (
    "UPDATE notifications_outbox "
    "SET delivery_status='ok', delivered_at = ? "
    "WHERE id = ? AND delivery_status='delivering'"
)

# Ack: failure under the 5-attempt cap. Returns to 'pending' for re-pull;
# records last_error for the operator to inspect.
NOTIFICATIONS_OUTBOX_ACK_FAILED_RETRY = (
    "UPDATE notifications_outbox "
    "SET delivery_status='pending', last_error = ? "
    "WHERE id = ? AND delivery_status='delivering' AND attempt_count < 5"
)

# Ack: failure at or past the 5-attempt cap. Terminal failed_max_retries
# state — no further pulls; manual intervention required.
NOTIFICATIONS_OUTBOX_ACK_FAILED_MAX = (
    "UPDATE notifications_outbox "
    "SET delivery_status='failed_max_retries', last_error = ? "
    "WHERE id = ? AND delivery_status='delivering' AND attempt_count >= 5"
)

# Recovery sweep — re-claims rows stuck in 'delivering' state for > 60s.
# The cutoff is computed in Python (`now - 60s`) and passed as the bound
# parameter. Rows that come back to 'pending' get re-pulled on the next
# Hermes poll; attempt_count is preserved (recovery is NOT a fresh attempt
# from the cap-counting perspective).
NOTIFICATIONS_OUTBOX_RECOVERY_RECLAIM = (
    "UPDATE notifications_outbox "
    "SET delivery_status='pending' "
    "WHERE delivery_status='delivering' AND last_attempt_at < ?"
)

# Fetch one row by id — used by ack_notification to inspect attempt_count
# before deciding the retry-vs-terminal path.
NOTIFICATIONS_OUTBOX_FETCH_BY_ID = (
    "SELECT id, tier, category, message, enqueued_at, "
    "  delivery_status, attempt_count, last_attempt_at, last_error, delivered_at "
    "FROM notifications_outbox WHERE id = ?"
)

# Test helper / observability — count all rows in the outbox.
NOTIFICATIONS_OUTBOX_COUNT_ALL = "SELECT COUNT(*) FROM notifications_outbox"

# Test helper — list all messages (used by tests to assert what was enqueued
# during a flow). Ordered by enqueued_at ASC so tests can pattern-match by
# index.
NOTIFICATIONS_OUTBOX_LIST_ALL = (
    "SELECT id, tier, category, message FROM notifications_outbox "
    "ORDER BY enqueued_at ASC"
)


# --- anti-fatigue (Story 6-4) ---

# Dedup: count + max-id of same-category-same-tier rows within the last
# hour. Used by the dispatcher to decide collapse vs new insert at the
# 5-in-1h threshold per AC-2.
#
# CR HIGH-1 fix: filter on `delivery_status='pending'` so already-delivered
# rows do NOT count toward dedup. Without this filter, 5 acked rows + a
# 6th call would target an `ok`-state row for UPDATE (predicate fails),
# silently dropping the 6th notification with no INSERT.
NOTIFICATIONS_OUTBOX_COUNT_SAME_CATEGORY_LAST_HOUR = (
    "SELECT COUNT(*), MAX(id) FROM notifications_outbox "
    "WHERE category = ? AND tier = ? AND enqueued_at >= ? "
    "AND delivery_status = 'pending'"
)

# Dedup collapse: rewrite the latest row's message body to the summary
# form. Only touches pending rows (a delivered row should not have its
# message rewritten — the recipient already saw it).
NOTIFICATIONS_OUTBOX_UPDATE_LATEST_MESSAGE = (
    "UPDATE notifications_outbox SET message = ? "
    "WHERE id = ? AND delivery_status = 'pending'"
)

# Story 6-4 unmute verb companion to Story 5-6's NOTIFICATION_MUTES_UPSERT.
# Returns rowcount > 0 iff a mute was actually cleared (used to populate
# UnmuteCategoryOut.was_muted).
NOTIFICATION_MUTES_DELETE_BY_CATEGORY = (
    "DELETE FROM notification_mutes WHERE category = ?"
)

# Posture state (Story 6-4 single-row table; id always 1).
POSTURE_STATE_SELECT = (
    "SELECT urgent_only, set_at, reason FROM posture_state WHERE id = 1"
)
POSTURE_STATE_SET_URGENT_ONLY = (
    "UPDATE posture_state SET urgent_only = 1, set_at = ?, reason = ? WHERE id = 1"
)
POSTURE_STATE_LIFT_URGENT_ONLY = (
    "UPDATE posture_state SET urgent_only = 0, set_at = NULL, reason = NULL WHERE id = 1"
)


# --- daily digest (Story 6-5) ---

# Recent non-deleted projection rows ordered by importance DESC. The verb
# buckets the rows in Python (high ≥ 70, medium 40-69, low < 40).
#
# Schema-reality note (Story 5-1 § precedent): `emails.is_read` is NOT
# captured in the local schema — Microsoft Graph has `isRead` but the
# sync worker doesn't persist it. Without is_read, this query approximates
# "unread" as "all non-deleted emails received in the last 24h" so the
# digest stays useful. A future story will capture is_read; for now the
# 24h window is the pragmatic proxy. Story 5-1's `find_emails` documented
# the same gap.
EMAILS_UNREAD_BUCKETED = (
    "SELECT graph_id, subject, from_address, received_at, "
    "  importance_score, summary_short, class_coarse, sensitivity "
    "FROM emails "
    "WHERE deleted_at IS NULL AND received_at >= ? "
    "ORDER BY importance_score DESC NULLS LAST, received_at DESC "
    "LIMIT 100"
)

# Tier-2 pending batches grouped by action_type. The composer renders one
# line per action_type with the count + oldest proposal timestamp.
PENDING_ACTIONS_TIER2_GROUPED = (
    "SELECT action_type, COUNT(*), MIN(proposed_at) "
    "FROM pending_actions "
    "WHERE tier = 2 AND status = 'pending' "
    "GROUP BY action_type "
    "ORDER BY COUNT(*) DESC"
)

# Queued important notifications since the last digest (i.e., still pending).
# Story 6-3 enqueues important rows with delivery_status='pending'; this
# story's finalize sweep flips them to 'ok_via_digest' after the digest
# posts.
NOTIFICATIONS_OUTBOX_IMPORTANT_PENDING = (
    "SELECT id, category, message, enqueued_at "
    "FROM notifications_outbox "
    "WHERE tier = 'important' AND delivery_status = 'pending' "
    "ORDER BY enqueued_at ASC"
)

# Finalize sweep — flips every queued important row to ok_via_digest in
# one transaction. Returns rowcount via execute_write.
NOTIFICATIONS_OUTBOX_FINALIZE_DIGEST_DELIVERY = (
    "UPDATE notifications_outbox "
    "SET delivered_at = ?, delivery_status = 'ok_via_digest' "
    "WHERE tier = 'important' AND delivery_status = 'pending'"
)
