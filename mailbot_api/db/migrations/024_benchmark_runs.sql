-- 024_benchmark_runs.sql — Benchmark dispatch audit table per Story 9-6.
--
-- One row per (corpus_item × task × model × prompt_version) dispatch via
-- the Story 9-6 runner. Written via benchmark/db.py's record_benchmark_run()
-- function (the ONLY writer to this table per Rule C — boundary-check
-- enforced at scripts/check_boundaries.py, same pattern as Story 2-1's
-- INSERT INTO router_calls monopoly).
--
-- Schema notes:
-- * `cohort_key` is a SHA-256[:16] of the pipe-joined 4-tuple
--   (prompt_version, scorer_model, anchors_version, router_policy_version)
--   per Adam-decision 2026-06-27 (A5 default cohort_key). Pareto plots
--   and DEMOTE/PROMOTE verdicts in Story 9-9 ONLY combine rows within
--   the same cohort_key. Cross-cohort comparison is allowed but flagged.
-- * `outcome` is plain TEXT NOT NULL — closed set
--   ('ok' / 'schema_failed' / 'timeout' / 'provider_error' / 'budget_blocked')
--   enforced application-side on the BenchmarkRunRow Pydantic model.
-- * `status` defaults to 'completed' — set to 'aborted_cost_cap' on
--   MONTHLY_BUDGET_EXCEEDED or DEGRADED_MODE_BLOCKED mid-run (AC-6), or
--   'interrupted' on SIGINT (AC-8).
-- * UNIQUE constraint on (run_id, corpus_item_id, task_type, model,
--   prompt_version) enforces idempotent resume at the SQL layer
--   (belt-and-braces beyond the runner's read_completed_cells dedup).
-- * `output_json` is NULL on failure (no parsed output to record).
-- * `scorer_model`, `anchors_version`, `router_policy_version` are
--   run-start frozen values that compose cohort_key — they live on every
--   row so single-row queries don't need to JOIN to a run_metadata table.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,                          -- UUID per full benchmark invocation
    corpus_item_id TEXT NOT NULL,                  -- links to CorpusItem.id in email_corpus_v1.jsonl
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,                           -- the force_model value passed to ask_router
    prompt_version TEXT NOT NULL,                  -- per-task PolicyEntry.prompt_version at dispatch
    cohort_key TEXT NOT NULL,                      -- SHA-256[:16] of pipe-joined 4-tuple
    output_json TEXT NULL,                         -- parsed prompt-module output JSON; NULL on failure
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cached_tokens_in INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL,                         -- ok / schema_failed / timeout / provider_error / budget_blocked
    status TEXT NOT NULL DEFAULT 'completed',      -- completed / aborted_cost_cap / interrupted
    scorer_model TEXT NOT NULL,                    -- frozen at run-start; populates cohort_key
    anchors_version TEXT NOT NULL,                 -- frozen at run-start; from evals/anchors/VERSION
    router_policy_version TEXT NOT NULL,           -- frozen at run-start; from PolicyTable.version
    ran_at TEXT NOT NULL,                          -- UTC ISO-8601 with Z suffix
    UNIQUE(run_id, corpus_item_id, task_type, model, prompt_version)
);

CREATE INDEX IF NOT EXISTS ix_benchmark_runs_run_id
    ON benchmark_runs (run_id);

CREATE INDEX IF NOT EXISTS ix_benchmark_runs_cohort_key
    ON benchmark_runs (cohort_key);

CREATE INDEX IF NOT EXISTS ix_benchmark_runs_task_type_model
    ON benchmark_runs (task_type, model);
