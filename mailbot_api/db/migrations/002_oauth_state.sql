-- 002_oauth_state.sql — single-row OAuth state per provider per architecture AR-D9-1.

CREATE TABLE IF NOT EXISTS oauth_state (
    provider TEXT PRIMARY KEY,                 -- e.g., 'microsoft_graph'
    refresh_token TEXT NOT NULL,
    access_token TEXT,                         -- nullable; refreshed on demand
    access_expires_at TEXT,                    -- UTC ISO-8601 Z, nullable
    last_rotated_at TEXT,                      -- UTC ISO-8601 Z, nullable
    rotation_count INTEGER NOT NULL DEFAULT 0
);
