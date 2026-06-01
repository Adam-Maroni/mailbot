-- 008_degraded_mode.sql — degraded-mode singleton row per Story 2-8 Layer 3.
--
-- One row. active=1 means the Router is demoting opus→haiku→qwen on every
-- call (logged with model_chosen_reason="degraded") until either /budget
-- reset is invoked or the calendar month rolls over (UTC midnight on the
-- 1st of the next month).
--
-- Numbering: epic spec said 007; Story 2-7 took 007_response_cache.sql.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS degraded_mode_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- enforce singleton row
    active INTEGER NOT NULL DEFAULT 0,
    entered_at TEXT NULL,
    exited_at TEXT NULL
);

-- Seed the singleton row (inactive on first boot).
INSERT INTO degraded_mode_state (id, active) VALUES (1, 0)
    ON CONFLICT(id) DO NOTHING;
