-- 013_derivations_idempotency.sql — Story 3-5 AC-1.
--
-- Records each (email_id, task_type) → idempotency_key mapping so the
-- pipeline orchestrator can short-circuit re-runs of already-computed
-- derived fields. Key formula per FR-2.2 / Rule K:
--   sha256(body | prompt_version | model | task_type)
-- See mailbot_api/ingest/idempotency.py (Story 3-1) for the canonical
-- helper. The pipeline writes a row per successfully-applied step.
--
-- Primary key is (email_id, task_type) — one row per email-task pair.
-- A re-derivation under a new prompt_version (different idempotency_key)
-- OVERWRITES the row via UPSERT, capturing the latest applied state.
--
-- Append-only per AR-D14-1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS derivations_idempotency (
    email_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (email_id, task_type)
);

CREATE INDEX IF NOT EXISTS ix_derivations_idempotency_key
    ON derivations_idempotency (idempotency_key);
