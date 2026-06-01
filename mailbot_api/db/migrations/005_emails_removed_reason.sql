-- 005_emails_removed_reason.sql — additive column for Graph @removed.reason
-- distinction (Story 1-10 AC-3).
--
-- When the sync worker sees a delta page row annotated @removed, the reason
-- field distinguishes 'changed' (item moved out of the synced folder set —
-- recoverable, may reappear) from 'deleted' (item permanently removed —
-- not recoverable from delta replay). Epic 4's Tier-1 reverter consults this
-- to decide whether restoration is even possible.
--
-- Additive only: existing soft-deleted rows (deleted_at NOT NULL AND
-- removed_reason IS NULL) are left untouched. The reverter must treat NULL
-- as "unknown → confirm via Graph before attempting restoration."

ALTER TABLE emails ADD COLUMN removed_reason TEXT NULL;
