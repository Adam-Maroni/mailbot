-- 001_init.sql — initial schema per architecture §2 and FR-2.1 derived-field design.
-- Tables: emails, threads, senders, sync_state.
-- All timestamps are TEXT UTC ISO-8601 with Z suffix (AR-PAT-3).
-- Names are plural snake_case (AR-PAT-2).
-- Indexes follow ix_<table>_<col> convention.

PRAGMA foreign_keys = ON;

-- Threads: one per Outlook conversation_id.
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,                       -- Graph conversationId
    subject_normalized TEXT,
    last_message_at TEXT,                      -- UTC ISO-8601 Z
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_threads_last_message_at ON threads (last_message_at);

-- Senders: one per from-address (lowercased).
CREATE TABLE IF NOT EXISTS senders (
    id TEXT PRIMARY KEY,                       -- lowercased email address
    display_name TEXT,
    domain TEXT,
    first_seen_at TEXT NOT NULL,
    sender_reputation_summary TEXT,            -- nullable; populated in epic 3 via Qwen
    sender_reputation_summary_prompt_v TEXT,
    sender_reputation_summary_conf REAL,
    sender_reputation_summary_model TEXT,
    sender_reputation_summary_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_senders_domain ON senders (domain);

-- Emails: the primary table.
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id TEXT NOT NULL UNIQUE,             -- Microsoft Graph message id
    change_marker TEXT,                        -- @odata.etag equivalent per AR-SCHEMA-2
    thread_id TEXT,
    sender_id TEXT,
    received_at TEXT NOT NULL,                 -- UTC ISO-8601 Z
    from_address TEXT,
    from_display_name TEXT,
    subject TEXT,
    body_preview TEXT,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,                           -- soft-delete per FR-1.3
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    -- Derived field: sensitivity (Qwen-only per Rule Q; FR-2.3 hard invariant — must
    -- be set before any other derived-field Router call on this row)
    sensitivity TEXT,                          -- one of 'normal', 'sensitive', 'confidential'
    sensitivity_prompt_v TEXT,
    sensitivity_conf REAL,
    sensitivity_model TEXT,
    sensitivity_at TEXT,
    -- Derived field: class_coarse
    class_coarse TEXT,
    class_coarse_prompt_v TEXT,
    class_coarse_conf REAL,
    class_coarse_model TEXT,
    class_coarse_at TEXT,
    -- Derived field: class_fine (only for class_coarse='human')
    class_fine TEXT,
    class_fine_prompt_v TEXT,
    class_fine_conf REAL,
    class_fine_model TEXT,
    class_fine_at TEXT,
    -- Derived field: summary_short
    summary_short TEXT,
    summary_short_prompt_v TEXT,
    summary_short_conf REAL,
    summary_short_model TEXT,
    summary_short_at TEXT,
    -- Derived field: importance_score
    importance_score REAL,
    importance_score_prompt_v TEXT,
    importance_score_conf REAL,
    importance_score_model TEXT,
    importance_score_at TEXT,
    -- Derived field: action_extraction (JSON of suggested actions)
    action_extraction TEXT,
    action_extraction_prompt_v TEXT,
    action_extraction_conf REAL,
    action_extraction_model TEXT,
    action_extraction_at TEXT,
    -- Derived field: embedding (raw bytes; cosine search uses numpy in verbs)
    embedding BLOB,
    embedding_prompt_v TEXT,
    embedding_conf REAL,
    embedding_model TEXT,
    embedding_at TEXT,
    FOREIGN KEY (thread_id) REFERENCES threads (id),
    FOREIGN KEY (sender_id) REFERENCES senders (id)
);

CREATE INDEX IF NOT EXISTS ix_emails_graph_id ON emails (graph_id);
CREATE INDEX IF NOT EXISTS ix_emails_received_at ON emails (received_at);
CREATE INDEX IF NOT EXISTS ix_emails_thread_id ON emails (thread_id);
CREATE INDEX IF NOT EXISTS ix_emails_sender_id ON emails (sender_id);
CREATE INDEX IF NOT EXISTS ix_emails_deleted_at ON emails (deleted_at);
CREATE INDEX IF NOT EXISTS ix_emails_sensitivity ON emails (sensitivity);
CREATE INDEX IF NOT EXISTS ix_emails_class_coarse ON emails (class_coarse);

-- Sync state: single row keyed by provider.
CREATE TABLE IF NOT EXISTS sync_state (
    provider TEXT PRIMARY KEY,                 -- e.g., 'microsoft_graph'
    delta_link TEXT,                           -- Graph delta link for next sync
    last_sync_at TEXT,                         -- UTC ISO-8601 Z
    last_sync_messages_seen INTEGER NOT NULL DEFAULT 0
);
