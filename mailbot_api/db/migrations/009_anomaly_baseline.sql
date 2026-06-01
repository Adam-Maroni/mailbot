-- 009_anomaly_baseline.sql — rolling 7-day per-hour call-volume baseline
-- per Story 2-9 AC for hourly anomaly detection.
--
-- One row per (caller_origin, hour_of_day) pair. Updated on each hourly
-- tick: count last-hour calls per origin → upsert into this table with
-- a rolling 7-day window calculation.
--
-- Numbering: epic spec said 008; renumbered to 009 due to 008 being
-- consumed by Story 2-8's degraded_mode_state.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS call_volume_baseline (
    caller_origin TEXT NOT NULL,
    hour_of_day INTEGER NOT NULL,        -- 0..23
    mean_volume REAL NOT NULL DEFAULT 0,
    stddev_volume REAL NOT NULL DEFAULT 0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (caller_origin, hour_of_day)
);

CREATE INDEX IF NOT EXISTS ix_call_volume_baseline_last_updated
    ON call_volume_baseline (last_updated);
