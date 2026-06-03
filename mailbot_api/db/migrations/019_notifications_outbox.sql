-- 019_notifications_outbox.sql — Story 6-3.
--
-- Single outbox for the four-tier notification dispatcher (FR-7.4). Urgent
-- + important rows live here; informational + silent never land in DB.
--
-- Delivery model (schema-reality reframe of the epic spec):
--   - mailbot-api enqueues rows here via mailbot_api.notifications.tiers
--   - Hermes pulls pending urgent rows via MCP tool pull_pending_notifications,
--     posts to Discord, and calls ack_notification to finalize
--   - Important rows wait for Story 6-5's 08:00 digest sweeper
--
-- Atomic claim: the pull SQL claims via UPDATE...WHERE delivery_status='pending'
-- so concurrent Hermes pollers cannot double-deliver. SQLite BEGIN IMMEDIATE
-- provides row-level isolation here.

CREATE TABLE notifications_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL CHECK (tier IN ('urgent', 'important')),
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    delivered_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        delivery_status IN ('pending', 'delivering', 'ok', 'failed_max_retries')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error TEXT
);

-- Hot-path: Hermes-polled urgent-tier pulls. ORDER BY enqueued_at ASC after
-- this composite index → covered scan.
CREATE INDEX idx_notifications_outbox_pending_urgent
    ON notifications_outbox (delivery_status, tier, enqueued_at);

-- Recovery scan: the worker's 10s interval task re-claims rows stuck in
-- delivering state for > 60s (Hermes crash / Discord rate-limit hang).
CREATE INDEX idx_notifications_outbox_delivering
    ON notifications_outbox (delivery_status, last_attempt_at);
