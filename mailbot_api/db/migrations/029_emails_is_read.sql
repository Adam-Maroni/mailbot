-- 029_emails_is_read.sql — Story 10.7.7 AC-1.
--
-- Adds a truthful read/unread signal to the emails table so "find my unread
-- emails" has a backing query. Microsoft Graph exposes `isRead` on every
-- message resource by default; the sync worker simply never persisted it
-- (schema-completeness gap flagged for the Epic 10.7 retro — sender/subject/
-- date were captured but the read flag Graph provides was dropped). Without
-- this column, the local qwen lane calls find_emails({}) for "unread", gets
-- recent-all, can't reconcile it with the intent, and loops (F-10-7-6-R2).
--
-- Semantics:
--   * is_read = 0  → genuinely unread (Graph isRead=false)
--   * is_read = 1  → read (Graph isRead=true)
--   * is_read NULL → UNKNOWN. Rows synced before this migration carry NULL
--     until their next delta-sync upsert repopulates the flag. `unread_only`
--     filtering uses `is_read = 0`, which (by SQLite three-valued logic)
--     EXCLUDES NULL rows — an honest posture: we only claim a row is unread
--     when Graph actually told us so, never guess for un-resynced history.
--
-- No backfill of existing rows: their true read-state is only knowable from
-- Graph, and the next delta sync repopulates it. Leaving them NULL is the
-- honest default (the alternative — defaulting every historical row to 0 —
-- would falsely surface long-read mail as "unread").
ALTER TABLE emails ADD COLUMN is_read INTEGER;

-- Partial index supporting the `WHERE is_read = 0 AND deleted_at IS NULL`
-- unread query (find_emails unread_only path). Indexes only the unread rows,
-- keeping it small and skipping the NULL/read majority.
CREATE INDEX IF NOT EXISTS ix_emails_is_read ON emails (is_read) WHERE is_read = 0;
