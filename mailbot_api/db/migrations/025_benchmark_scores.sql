-- 025_benchmark_scores.sql — Benchmark scoring audit table per Story 9-7.
--
-- One row per (run_id × task × model × prompt_version × scorer_model ×
-- evaluator_role × metric_name) score computed by benchmark/scorer.py.
-- Written via benchmark/scorer_db.py's record_benchmark_score() — the
-- ONLY writer to this table per Rule C (boundary-check enforced at
-- scripts/check_boundaries.py, same pattern as Story 9-6's
-- INSERT INTO benchmark_runs monopoly and Story 2-1's router_calls).
--
-- Schema notes:
-- * cohort_key is COPIED from the benchmark_runs row that was scored.
--   Story 9-9's report renderer joins on cohort_key without re-computing.
-- * scorer_model is the strong-model evaluator id for subjective tasks
--   (e.g., 'claude-opus-4-7-20251220'); for objective tasks it is the
--   literal string 'objective:mechanical' (no LLM in the loop).
-- * evaluator_role is plain TEXT NOT NULL — closed set ('primary' /
--   'secondary') enforced application-side on the BenchmarkScoreRow
--   Pydantic model.
-- * outcome is closed set ('ok' / 'calibration_warning' /
--   'insufficient_data' / 'scorer_error') enforced application-side.
-- * extra_json carries non-tabular metric data (confusion matrices,
--   per-axis subjective breakdowns, per-anchor α disagreements);
--   shape documented in benchmark/scorer_db.py module docstring.
-- * UNIQUE constraint on (run_id, task_type, model, prompt_version,
--   scorer_model, evaluator_role, metric_name) enforces idempotent
--   re-scoring at the SQL layer. The writer uses INSERT OR REPLACE
--   semantics so re-running the scorer overwrites prior values.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS benchmark_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,                          -- matches benchmark_runs.run_id
    cohort_key TEXT NOT NULL,                      -- copied from benchmark_runs row
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,                           -- the model that produced the scored output
    prompt_version TEXT NOT NULL,
    scorer_model TEXT NOT NULL,                    -- evaluator id; 'objective:mechanical' for objective tasks
    evaluator_role TEXT NOT NULL,                  -- 'primary' / 'secondary'
    metric_name TEXT NOT NULL,                     -- e.g., 'accuracy', 'subjective_overall', 'cross_evaluator_alpha'
    metric_value REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    outcome TEXT NOT NULL,                         -- 'ok' / 'calibration_warning' / 'insufficient_data' / 'scorer_error'
    extra_json TEXT NULL,                          -- JSON blob for non-tabular metric data
    computed_at TEXT NOT NULL,                     -- UTC ISO-8601 with Z suffix
    UNIQUE(run_id, task_type, model, prompt_version, scorer_model, evaluator_role, metric_name)
);

CREATE INDEX IF NOT EXISTS ix_benchmark_scores_run_id
    ON benchmark_scores (run_id);

CREATE INDEX IF NOT EXISTS ix_benchmark_scores_cohort_key
    ON benchmark_scores (cohort_key);

CREATE INDEX IF NOT EXISTS ix_benchmark_scores_task_model
    ON benchmark_scores (task_type, model);
