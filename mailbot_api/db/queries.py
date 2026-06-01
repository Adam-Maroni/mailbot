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


# --- emails (Story 1-7) ---

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
    "UPDATE emails SET deleted_at = ? WHERE graph_id = ? AND deleted_at IS NULL"
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
