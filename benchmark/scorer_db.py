"""Story 9-7: single-writer monopoly for ``benchmark_scores`` (Rule C).

This module is the ONLY place ``INSERT INTO benchmark_scores`` may appear
(or ``INSERT OR REPLACE INTO benchmark_scores`` for the idempotent
re-scoring path). Enforced by ``scripts/check_boundaries.py`` extension
(Story 9-6 / Story 2-1 precedent). Any other module attempting an
``INSERT INTO benchmark_scores`` literal will fail the boundary check at
CI time.

Three functions:

* ``record_benchmark_score(db_path, row) -> int`` — writes (or overwrites
  on UNIQUE conflict) a single row; returns the inserted ``id``. Uses
  ``INSERT OR REPLACE`` semantics so re-running the scorer for the same
  (run, task, model, prompt_version, scorer_model, evaluator_role,
  metric_name) replaces the prior value cleanly.
* ``read_run_runs(db_path, run_id) -> list[BenchmarkRunRow]`` — reads
  ``benchmark_runs`` rows for the scorer's input. Lives here (not in
  ``benchmark/db.py``) so the scorer pulls all its boundary-crossing
  reads through one module without depending on the runner's writer.
* ``read_run_scores(db_path, run_id) -> list[BenchmarkScoreRow]`` —
  reads back ``benchmark_scores`` rows. Used by Story 9-9's report
  renderer + integration tests.

``extra_json`` shape conventions (per metric_name):

* ``accuracy`` / ``precision_macro`` / ``recall_macro`` / ``f1_macro`` —
  ``{"confusion_matrix": {true: {pred: count, ...}}, "per_class":
  {label: {precision: x, recall: y, f1: z, support: n}}}``
* ``f1_extraction_action_type`` / ``f1_extraction_summary_similarity`` /
  ``f1_extraction_deadline_match`` — ``{"per_action_type":
  {type_str: {precision, recall, f1, support}}}``
* ``subjective_overall`` / ``subjective_<axis>`` —
  ``{"per_row_scores": [int, ...], "n_rows": int}``
* ``calibration_mae`` —
  ``{"per_anchor": [{anchor_id, auto_score, adam_score, abs_error},
  ...], "n_anchors": int}``
* ``cross_evaluator_alpha`` —
  ``{"per_anchor": [{anchor_id, primary_score, secondary_score, delta},
  ...], "n_anchors": int}``
* ``ok_rate`` — ``{"ok_count": int, "total_count": int}``

The ``extra_json`` column may be NULL when no auxiliary payload applies.
"""

from __future__ import annotations

import json

from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from mailbot_api.db.connection import execute_insert_returning_id, fetchall

# INSERT OR REPLACE so re-running the scorer for the same
# (run_id, task_type, model, prompt_version, scorer_model,
# evaluator_role, metric_name) tuple overwrites the prior row cleanly
# (instead of raising IntegrityError on the UNIQUE constraint). The
# 7-column UNIQUE constraint from migration 025 is the key target.
_UPSERT_BENCHMARK_SCORE_SQL = """
INSERT OR REPLACE INTO benchmark_scores (
    run_id,
    cohort_key,
    task_type,
    model,
    prompt_version,
    scorer_model,
    evaluator_role,
    metric_name,
    metric_value,
    sample_count,
    outcome,
    extra_json,
    computed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""".strip()

_READ_RUN_RUNS_SQL = """
SELECT
    run_id,
    corpus_item_id,
    task_type,
    model,
    prompt_version,
    cohort_key,
    output_json,
    tokens_in,
    tokens_out,
    cached_tokens_in,
    cost_usd,
    latency_ms,
    outcome,
    status,
    scorer_model,
    anchors_version,
    router_policy_version,
    ran_at
FROM benchmark_runs
WHERE run_id = ?
ORDER BY id
""".strip()

_READ_RUN_SCORES_SQL = """
SELECT
    run_id,
    cohort_key,
    task_type,
    model,
    prompt_version,
    scorer_model,
    evaluator_role,
    metric_name,
    metric_value,
    sample_count,
    outcome,
    extra_json,
    computed_at
FROM benchmark_scores
WHERE run_id = ?
ORDER BY id
""".strip()


async def record_benchmark_score(db_path: str, row: BenchmarkScoreRow) -> int:
    """Insert or replace a single ``benchmark_scores`` row; return the new ``id``.

    Rule C single-writer: this is the ONLY function that emits
    ``INSERT INTO benchmark_scores`` (or the ``INSERT OR REPLACE``
    variant). Boundary-check enforced.

    Atomicity: ``execute_insert_returning_id`` runs the statement inside
    BEGIN IMMEDIATE / COMMIT (per ``mailbot_api/db/connection.py``).

    The 7-column UNIQUE constraint from migration 025 keys the upsert.
    If the constraint matches, the existing row is REPLACED (REPLACE in
    SQLite deletes + inserts atomically, so the row gets a new ``id``).
    Callers that need to track the persistent identity of a metric
    should key off the UNIQUE tuple, not the ``id``.
    """
    params: tuple[
        str, str, str, str, str, str, str, str,
        float, int, str, str | None, str,
    ] = (
        row.run_id,
        row.cohort_key,
        row.task_type,
        row.model,
        row.prompt_version,
        row.scorer_model,
        row.evaluator_role,
        row.metric_name,
        row.metric_value,
        row.sample_count,
        row.outcome,
        row.extra_json,
        row.computed_at,
    )
    return await execute_insert_returning_id(db_path, _UPSERT_BENCHMARK_SCORE_SQL, params)


async def read_run_runs(db_path: str, run_id: str) -> list[BenchmarkRunRow]:
    """Read all ``benchmark_runs`` rows for ``run_id`` as Pydantic shapes.

    Re-validates every row through ``BenchmarkRunRow.model_validate(...)``
    so callers get full type-safety + the closed-set Literal enforcement.
    Empty list if no rows match (fresh / unknown run_id).
    """
    raw = await fetchall(db_path, _READ_RUN_RUNS_SQL, (run_id,))
    rows: list[BenchmarkRunRow] = []
    for r in raw:
        rows.append(
            BenchmarkRunRow.model_validate(
                {
                    "run_id": r[0],
                    "corpus_item_id": r[1],
                    "task_type": r[2],
                    "model": r[3],
                    "prompt_version": r[4],
                    "cohort_key": r[5],
                    "output_json": r[6],
                    "tokens_in": r[7],
                    "tokens_out": r[8],
                    "cached_tokens_in": r[9],
                    "cost_usd": r[10],
                    "latency_ms": r[11],
                    "outcome": r[12],
                    "status": r[13],
                    "scorer_model": r[14],
                    "anchors_version": r[15],
                    "router_policy_version": r[16],
                    "ran_at": r[17],
                }
            )
        )
    return rows


async def read_run_scores(db_path: str, run_id: str) -> list[BenchmarkScoreRow]:
    """Read all ``benchmark_scores`` rows for ``run_id`` as Pydantic shapes.

    Used by Story 9-9's report renderer + integration tests.
    """
    raw = await fetchall(db_path, _READ_RUN_SCORES_SQL, (run_id,))
    rows: list[BenchmarkScoreRow] = []
    for r in raw:
        rows.append(
            BenchmarkScoreRow.model_validate(
                {
                    "run_id": r[0],
                    "cohort_key": r[1],
                    "task_type": r[2],
                    "model": r[3],
                    "prompt_version": r[4],
                    "scorer_model": r[5],
                    "evaluator_role": r[6],
                    "metric_name": r[7],
                    "metric_value": r[8],
                    "sample_count": r[9],
                    "outcome": r[10],
                    "extra_json": r[11],
                    "computed_at": r[12],
                }
            )
        )
    return rows


def encode_extra_json(payload: dict[str, object]) -> str:
    """Serialize an ``extra_json`` payload dict to its TEXT-column form.

    Centralized so callers don't drift from the encoding contract
    (``sort_keys=True`` for stable diffs across re-runs; ``ensure_ascii=False``
    so unicode in confusion matrices / per-axis labels stays readable).
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


__all__ = [
    "encode_extra_json",
    "read_run_runs",
    "read_run_scores",
    "record_benchmark_score",
]
