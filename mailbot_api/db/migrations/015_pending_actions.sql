-- 015_pending_actions.sql — Story 4-2 AC-1.
--
-- pending_actions: queue table for all Tier-1/2/3 action proposals.
--
-- CHECK(action_type IN (...)) deliberately mirrors mailbot_api.actions.types
-- Tier-1/2/3 enum members (Tier-0 deliberately excluded — Tier-0 verbs never
-- enter pending_actions per Story 4-2 propose_action verb-boundary refusal).
-- Drift caught by tests/integration/test_action_schema.py
-- ::test_check_constraint_in_sync_with_enum.
--
-- CHECK(tier IN (1, 2, 3)) is a second-layer defense for FR-5.6 — a future
-- buggy direct SQL insert with tier=0 is caught by the schema even if the
-- producer's tier_for() call slipped.
--
-- CHECK(status IN (...)) pins the 7-state lifecycle: a row starts in one of
-- {pending, cooling_off, pending_grant}, transitions to draining, then
-- terminates in {applied, failed, cancelled}.
--
-- Append-only per AR-D14-1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NULL,
    action_type TEXT NOT NULL CHECK(action_type IN (
        'mark_read', 'mark_unread', 'add_local_category', 'remove_local_category', 'move_to_triage_folder',
        'archive', 'mark_junk', 'move_to_user_folder', 'unsubscribe', 'move_to_inbox',
        'delete', 'send_reply', 'send_new_email', 'send_forward', 'reply_to_inactive_thread',
        'modify_inbox_rule', 'modify_outlook_filter', 'touch_delegated_mailbox'
    )),
    tier INTEGER NOT NULL CHECK(tier IN (1, 2, 3)),
    payload TEXT NOT NULL,
    proposed_at TEXT NOT NULL,
    proposed_by_grant_id INTEGER NULL,
    change_marker_at_propose TEXT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'cooling_off', 'pending_grant', 'draining', 'applied', 'failed', 'cancelled'
    )),
    retry_count INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT NULL,
    terminal_at TEXT NULL,
    budget_consumed INTEGER NOT NULL DEFAULT 0 CHECK(budget_consumed IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_pending_actions_status_proposed_at
    ON pending_actions (status, proposed_at);
CREATE INDEX IF NOT EXISTS ix_pending_actions_email_id
    ON pending_actions (email_id);
CREATE INDEX IF NOT EXISTS ix_pending_actions_action_type
    ON pending_actions (action_type);
