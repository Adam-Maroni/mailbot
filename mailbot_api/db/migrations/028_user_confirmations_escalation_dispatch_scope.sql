-- 028_user_confirmations_escalation_dispatch_scope.sql — Story 10-5-6 refinement.
--
-- Widen user_confirmations.scope CHECK to admit a third scope value,
-- 'escalation_dispatch': a TTL-windowed, RE-READABLE grant scoped to
-- (email_id, task_type), recorded at the router dispatch seam on the first
-- authorization off a genuine user "yes, escalate", and PEEKED (not consumed)
-- by the several same-(email, task) sensitive dispatches the persona fans out
-- in one escalation turn (hydrate -> propose -> draft). Without it, a strictly
-- single-use arm authorized only the FIRST dispatch and the 2nd/3rd re-refused
-- mid-flow (the residual W3 symptom the 10-5-6 re-walk surfaced). A different
-- email still finds no grant + no live arm/confirmation and refuses, so the
-- blast-radius invariant is preserved.
--
-- SQLite cannot ALTER a CHECK constraint in place, so this rebuilds the table
-- (create -> copy -> drop -> rename) preserving all columns, data, and indexes.
-- Ships as a NEW migration (028) — the applied 026 file is never edited
-- (migration-content-stability discipline, F-10-5-2-W3).
--
-- FK note (CR-10-5-6-2, 2026-07-11 MANDATORY-CR): no `PRAGMA foreign_keys`
-- toggle is used here. The runner wraps every migration body in an outer
-- `BEGIN; ... COMMIT;` (migrations_runner.py), and SQLite ignores
-- `PRAGMA foreign_keys` writes while a transaction is open — so a mid-body
-- toggle is dead code. It is moot for this rebuild anyway: `user_confirmations`
-- declares no `REFERENCES` and nothing else references it, so the DROP+rename
-- has no FK to violate. A future FK-bearing rebuild that genuinely needs FK
-- suppression must issue the pragma on a separate connection BEFORE the
-- migration transaction begins, not inside the body.

CREATE TABLE user_confirmations_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL CHECK(
        scope IN ('sensitivity_token', 'grant', 'escalation_dispatch')
    ),
    email_id TEXT NULL,
    task_type TEXT NULL,
    action_type TEXT NULL,
    email_ids TEXT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT NULL
);

INSERT INTO user_confirmations_new
    (id, scope, email_id, task_type, action_type, email_ids, created_at, consumed_at)
SELECT id, scope, email_id, task_type, action_type, email_ids, created_at, consumed_at
FROM user_confirmations;

DROP TABLE user_confirmations;

ALTER TABLE user_confirmations_new RENAME TO user_confirmations;

CREATE INDEX IF NOT EXISTS ix_user_confirmations_sensitivity
    ON user_confirmations (scope, email_id, task_type);

CREATE INDEX IF NOT EXISTS ix_user_confirmations_grant
    ON user_confirmations (scope, action_type);
