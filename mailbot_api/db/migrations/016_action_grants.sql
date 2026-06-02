-- 016_action_grants.sql — Story 4-2 AC-2.
--
-- action_grants: scoped time-bounded grants per FR-5.2.
-- Story 4-3 implements mint_grant + is_grant_valid; this story ships the schema.
--
-- CHECK(action_type IN (...)) mirrors 015's list (Tier-1/2/3 only) — mint_grant
-- in Story 4-3 refuses to mint for Tier-1 (Tier-1 is auto-approved per FR-5.1),
-- so the actually-used subset is Tier-2/3, but the CHECK simplification accepts
-- the full Tier-1/2/3 set.
--
-- email_ids is a JSON array (TEXT) — empty [] permitted for email-less actions
-- like MODIFY_INBOX_RULE that grant by action_type alone.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS action_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL CHECK(action_type IN (
        'mark_read', 'mark_unread', 'add_local_category', 'remove_local_category', 'move_to_triage_folder',
        'archive', 'mark_junk', 'move_to_user_folder', 'unsubscribe', 'move_to_inbox',
        'delete', 'send_reply', 'send_new_email', 'send_forward', 'reply_to_inactive_thread',
        'modify_inbox_rule', 'modify_outlook_filter', 'touch_delegated_mailbox'
    )),
    email_ids TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    minted_at TEXT NOT NULL,
    revoked_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS ix_action_grants_action_type_expires_at
    ON action_grants (action_type, expires_at);
