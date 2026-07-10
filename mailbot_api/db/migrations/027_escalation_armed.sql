-- 027_escalation_armed.sql — Story 10.5.2 (live-walk finding F-10-5-2-W1).
--
-- Fixes a turn-ordering bug the Task 5 live walk surfaced: the "yes, escalate"
-- boundary handshake checked for a pending_sensitive_refusal row at the START
-- of the request, but in the real Discord flow the persona self-refuses and
-- asks for confirmation, so the agent's mint_sensitivity_token attempt (and the
-- refusal that records the pending row) happen LATER in the SAME turn than the
-- confirm-check runs → the escalation never attached.
--
-- New model: on "yes, escalate" the boundary ARMS an escalation (this table).
-- The mint_sensitivity_token verb — which is where the concrete (email_id,
-- task_type) is actually known — consumes the arm and records a real
-- single-use user_confirmation for that exact scope, then mints. Ordering-
-- independent and matches the real agent flow (agent calls mint after the
-- user's yes).
--
-- Single active arm (id=1 singleton): the mint verb has no caller_origin
-- (MCP transport is separate from the HTTP boundary), and per the CR-8 finding
-- caller_origin arrives as the shared default 'unknown-external' in the current
-- Hermes topology anyway — so a single active arm is the honest scope here.
-- Short-TTL (reuses CONFIRMATION_TTL, enforced in code), consumed on first
-- matching mint. The arm is only ever SET by the chat boundary on a genuine
-- user-role phrase; the agent's verb surface cannot arm it (non-agent-assertable
-- invariant preserved).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS escalation_armed (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    armed_at TEXT NOT NULL
);
