-- 006_router_calls.sql — Router audit log per Story 2-1 and architecture
-- §"Rule W" + §"Errors as data".
--
-- One row per ask_router() invocation, written via observability/audit.py's
-- record_router_call() function (the ONLY writer to this table per Rule C).
-- Direct INSERT INTO router_calls outside that module fails the boundary
-- check at scripts/check_boundaries.py.
--
-- Numbering variance: epic spec said `005_router_calls.sql`, but prefix 005
-- was consumed by 005_emails_removed_reason.sql in Story 1-10. The migration
-- runner's duplicate-prefix detector (CR-6) would refuse both at startup.
-- Bumped to 006 here; downstream Epic-2 migrations renumber accordingly
-- (see epic-run-flags.md).
--
-- Schema notes:
-- * `model_chosen_reason` is plain TEXT NOT NULL — no SQL CHECK constraint.
--   The closed set ('policy' / 'override' / 'degraded' / 'response_cache_hit'
--   / 'force_override' / 'escalated_from_<X>') is enforced application-side
--   on the RouterCallRow Pydantic model. Downstream stories 2-7 and 2-8 add
--   new reasons without a schema migration.
-- * `caller_origin` defaults to 'unknown' (placeholder per AR-D2-2 until
--   Story 2-10 wires real values).
-- * `sensitivity_grant_id` and `sensitivity_grant_minted_at` are NULL-able
--   from day one; Epic 4 populates them when sensitivity-grant minting ships.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS router_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,                              -- UTC ISO-8601 with Z suffix
    task_type TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_chosen TEXT NOT NULL,
    model_chosen_reason TEXT NOT NULL,             -- enforced on RouterCallRow
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cached_tokens_in INTEGER NOT NULL DEFAULT 0,
    cost_usd_estimated REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL,                         -- ok / retry_recovered / escalated / failed
    caller_verb TEXT NULL,
    caller_origin TEXT NOT NULL DEFAULT 'unknown', -- AR-D2-2: real values from Story 2-10
    email_id TEXT NULL,
    sensitivity_grant_id TEXT NULL,                -- Epic 4 populates
    sensitivity_grant_minted_at TEXT NULL          -- Epic 4 populates
);

CREATE INDEX IF NOT EXISTS ix_router_calls_ts
    ON router_calls (ts);

CREATE INDEX IF NOT EXISTS ix_router_calls_task_type_model_chosen
    ON router_calls (task_type, model_chosen);

CREATE INDEX IF NOT EXISTS ix_router_calls_email_id
    ON router_calls (email_id);
