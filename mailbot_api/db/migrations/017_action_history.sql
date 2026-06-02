-- 017_action_history.sql — Story 4-2 AC-3.
--
-- action_history: pre-state snapshot written before Graph dispatch (Story 4-4
-- drainer); reverted_at populated by Story 4-8's reverter.
--
-- action_id PK enforces one history row per pending_actions row.
-- pre_state empty {} permitted for actions with no captured pre-state (DELETE).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS action_history (
    action_id INTEGER PRIMARY KEY,
    pre_state TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    reverted_at TEXT NULL
);
