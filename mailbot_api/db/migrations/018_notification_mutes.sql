-- 018_notification_mutes.sql — Story 5-6 AC-1.
--
-- notification_mutes: persists Adam's intent to mute outgoing notification
-- categories. Written by /mute slash command (Story 5-6's mute_category verb);
-- read by Epic 6's notification tier dispatcher (Story 6-3) when classifying
-- outgoing notifications.
--
-- category is free-form for now; Story 6-3 may add a CHECK constraint when a
-- closed taxonomy emerges (e.g., 'newsletters', 'low_importance_human',
-- 'transactional').
--
-- muted_until NULL means indefinite — the dispatcher silences the category
-- until the row is deleted (no /unmute slash command in v1; deletion is via
-- manual SQL or a future /unmute command).
--
-- muted_at exists for forensics — knowing WHEN Adam muted a category helps
-- the retro discussion on why a notification class isn't reaching him.
--
-- Append-only per AR-D14-1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS notification_mutes (
    category TEXT PRIMARY KEY,
    muted_until TEXT NULL,
    muted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_notification_mutes_muted_until
    ON notification_mutes (muted_until);
