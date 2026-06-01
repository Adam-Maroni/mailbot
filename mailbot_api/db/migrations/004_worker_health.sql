-- 004_worker_health.sql — single-row-per-component heartbeat table per AR-D7-2.
-- Components: sync (Story 1-8), cache_warmer (Epic 2), drainer (Epic 4), ingest_pipeline (Epic 3).

CREATE TABLE IF NOT EXISTS worker_health (
    component TEXT PRIMARY KEY,
    last_heartbeat_at TEXT,                    -- UTC ISO-8601 Z
    last_outcome TEXT,                         -- 'ok' | 'failed'
    last_error TEXT                            -- nullable; sanitized message on 'failed'
);
