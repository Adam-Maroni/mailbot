-- 020_posture_state.sql — Story 6-4.
--
-- Single-row table tracking the urgent-only notification posture
-- (FR-7.4 + Story 6-4). Mirrors Story 2-8's degraded_mode_state pattern:
-- always id=1; UPDATE-only after the initial seed.
--
-- urgent_only=1 means: only `tier='urgent'` notifications deliver.
-- `tier='important'` + `tier='informational'` calls are dropped at
-- dispatch time. Set via `notifications.posture.set_urgent_only`; lifted
-- via `notifications.posture.lift_urgent_only` (called from the resume
-- verb so `/resume` is the de-facto "talk to me" trigger).

CREATE TABLE posture_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    urgent_only INTEGER NOT NULL DEFAULT 0 CHECK (urgent_only IN (0, 1)),
    set_at TEXT,
    reason TEXT
);

INSERT INTO posture_state (id, urgent_only) VALUES (1, 0);
