-- 014_thread_continuity.sql — Story 3-7 AC-1.
--
-- Adds thread_continuity_note + 4 companion columns to threads.
--
-- Disposition: senders.sender_reputation_summary* columns already shipped in
-- 001_init.sql (lines 25-29). The epic spec (3-7) called for a parallel
-- 014_sender_reputation migration which is N/A by disposition. This file
-- ships the threads side only.
--
-- Append-only per AR-D14-1.

PRAGMA foreign_keys = ON;

ALTER TABLE threads ADD COLUMN thread_continuity_note TEXT;
ALTER TABLE threads ADD COLUMN thread_continuity_note_prompt_v TEXT;
ALTER TABLE threads ADD COLUMN thread_continuity_note_conf REAL;
ALTER TABLE threads ADD COLUMN thread_continuity_note_model TEXT;
ALTER TABLE threads ADD COLUMN thread_continuity_note_at TEXT;

CREATE INDEX IF NOT EXISTS ix_threads_thread_continuity_note_at
    ON threads (thread_continuity_note_at);
