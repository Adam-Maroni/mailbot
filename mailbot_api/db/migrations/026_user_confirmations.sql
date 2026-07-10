-- 026_user_confirmations.sql — Story 10.5.2 (Epic 10.5 Cluster B).
--
-- The API-layer user-confirmation record that makes token/grant minting a
-- genuinely user-gated event (fixes F-10-5-5 self-mint sensitivity token +
-- F-10-5-8 Tier-2 grant minted with no user "yes").
--
-- Root problem: `mint_sensitivity_token` and `mint_grant` had only STRUCTURAL
-- gates (sensitivity label / tier / window / batch). Nothing recorded a user
-- approval, so an agent that only issues verb calls could self-authorize.
--
-- The invariant this table enforces: a confirmation row is created ONLY by the
-- /v1/chat/completions boundary when a genuine USER-ROLE message carries an
-- explicit confirmation phrase ("yes, escalate" / "yes, archive ...") — NEVER
-- by an MCP verb call. The mint verbs consume a matching un-consumed row
-- single-use. An agent cannot manufacture the row because it does not control
-- the user-role message stream.
--
-- scope: 'sensitivity_token' (keyed by email_id + task) OR 'grant' (keyed by
--        action_type; email scope carried in email_ids JSON, may be []).
-- Single-use: consumed by deleting the row (mirrors the sensitivity-token
--             registry's remove-on-consume semantics).
-- TTL: short window (created_at + a few minutes) so a stale "yes" cannot be
--      replayed much later; enforced in code at consume time.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(scope IN ('sensitivity_token', 'grant')),
    -- For 'sensitivity_token': the target email + task. For 'grant': email_id
    -- is NULL and action_type carries the grant scope.
    email_id TEXT NULL,
    task_type TEXT NULL,
    action_type TEXT NULL,
    email_ids TEXT NULL,          -- JSON array for grant scope; NULL otherwise
    created_at TEXT NOT NULL,     -- ISO-8601 UTC; TTL window enforced in code
    consumed_at TEXT NULL         -- set (row removed) on single-use consume
);

CREATE INDEX IF NOT EXISTS ix_user_confirmations_sensitivity
    ON user_confirmations (scope, email_id, task_type);

CREATE INDEX IF NOT EXISTS ix_user_confirmations_grant
    ON user_confirmations (scope, action_type);


-- pending_sensitive_refusal: the most-recent sensitive-refusal per caller so a
-- bare "yes, escalate" reply (which carries no email id) can be correlated back
-- to the (email_id, task) the user is escalating. Fixes F-10-5-7's binding
-- divergence WITHOUT a session id: the correlation key is the Discord caller
-- (caller_origin), stable across the separate HTTP requests that chat turns
-- become. Only 'sensitive' refusals are recorded here (confidential offers no
-- escalation; not_classified has nothing to escalate). One row per caller,
-- upserted on each new sensitive refusal, cleared on consume.
CREATE TABLE IF NOT EXISTS pending_sensitive_refusal (
    caller_origin TEXT PRIMARY KEY,
    email_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);


-- pending_grant_approval: the Tier-2 analog of pending_sensitive_refusal
-- (Story 10.5.2, CR-3/CR-4). When a Tier-2 action is queued as pending_grant,
-- the boundary records what a user "yes"/"approve" would authorize — the exact
-- (action_type, email_ids) — keyed by caller_origin. On the user's approval
-- phrase the boundary records a scoped grant confirmation for those EXACT
-- email_ids (not an agent-chosen batch), then clears the row. Without this,
-- record_grant_confirmation has no production caller and every Tier-2 grant is
-- permanently blocked (CR-3); with the email_ids carried through, the blast
-- radius is the user-approved set, not agent-controlled (CR-4).
CREATE TABLE IF NOT EXISTS pending_grant_approval (
    caller_origin TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    email_ids TEXT NOT NULL,
    created_at TEXT NOT NULL
);
