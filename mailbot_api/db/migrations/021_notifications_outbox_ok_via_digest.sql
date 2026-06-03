-- 021_notifications_outbox_ok_via_digest.sql — Story 6-5.
--
-- Extends the CHECK constraint on notifications_outbox.delivery_status to
-- include 'ok_via_digest'. Story 6-3's migration 019 set the constraint to
-- IN ('pending','delivering','ok','failed_max_retries'); Story 6-5's
-- finalize_digest_delivery sweep needs a distinct terminal state to
-- distinguish "delivered via Hermes urgent pull" from "delivered via
-- 08:00 digest batch."
--
-- SQLite cannot ALTER a CHECK constraint in place — the standard pattern
-- is the table-recreate dance: rename old → create new with new constraint
-- → copy → drop old. The migrations_runner executes the entire .sql file
-- as one composite executescript per Story 1-3 semantics, so the
-- intermediate _old table doesn't survive.

ALTER TABLE notifications_outbox RENAME TO notifications_outbox_old;

CREATE TABLE notifications_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL CHECK (tier IN ('urgent', 'important')),
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    delivered_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        delivery_status IN ('pending', 'delivering', 'ok', 'failed_max_retries', 'ok_via_digest')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error TEXT
);

INSERT INTO notifications_outbox
    (id, tier, category, message, enqueued_at, delivered_at, delivery_status,
     attempt_count, last_attempt_at, last_error)
SELECT
    id, tier, category, message, enqueued_at, delivered_at, delivery_status,
    attempt_count, last_attempt_at, last_error
FROM notifications_outbox_old;

DROP TABLE notifications_outbox_old;

-- Recreate the Story 6-3 indexes (DROP TABLE cascades drop on indexes).
CREATE INDEX idx_notifications_outbox_pending_urgent
    ON notifications_outbox (delivery_status, tier, enqueued_at);

CREATE INDEX idx_notifications_outbox_delivering
    ON notifications_outbox (delivery_status, last_attempt_at);
