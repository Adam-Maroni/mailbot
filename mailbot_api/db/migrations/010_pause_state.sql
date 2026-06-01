-- 010_pause_state.sql — pause/resume kill-switch singleton per Story 2-9.
--
-- Persists across restarts. `paused=1` short-circuits every ask_router
-- call with RouterError(code=PROVIDER_ERROR, message="router paused",
-- retryable=True) before the call enters the queue.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pause_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    paused INTEGER NOT NULL DEFAULT 0,
    reason TEXT NULL,
    paused_at TEXT NULL,
    resumed_at TEXT NULL
);

INSERT INTO pause_state (id, paused) VALUES (1, 0)
    ON CONFLICT(id) DO NOTHING;
