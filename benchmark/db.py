"""Story 9.6: single-writer monopoly for ``benchmark_runs`` (Rule C).

This module is the ONLY place ``INSERT INTO benchmark_runs`` may appear.
Enforced by ``scripts/check_boundaries.py`` extension (Story 2-1 precedent).
Any other module attempting an ``INSERT INTO benchmark_runs`` literal will
fail the boundary check at CI time.

Two functions:

* ``record_benchmark_run(db_path, row) -> int`` — writes a single row,
  returns the inserted ``id``. Goes through ``execute_insert_returning_id``
  for BEGIN IMMEDIATE / COMMIT semantics (per AR-D8-1).
* ``read_completed_cells(db_path, run_id) -> set[tuple[...]]`` — reads the
  set of ``(corpus_item_id, task_type, model, prompt_version)`` tuples
  already present for a given ``run_id``. Used by ``runner.py`` to skip
  cells on ``--resume``.

The unique constraint on the SQL side enforces resume idempotency as
belt-and-braces beyond this layer.
"""

from __future__ import annotations

from benchmark.schemas import BenchmarkRunRow
from mailbot_api.db.connection import execute_insert_returning_id, fetchall

_INSERT_BENCHMARK_RUN_SQL = """
INSERT INTO benchmark_runs (
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
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""".strip()

_READ_COMPLETED_CELLS_SQL = """
SELECT corpus_item_id, task_type, model, prompt_version
FROM benchmark_runs
WHERE run_id = ?
""".strip()

_READ_RUN_GRID_SQL = """
SELECT DISTINCT task_type, model
FROM benchmark_runs
WHERE run_id = ?
""".strip()


async def record_benchmark_run(db_path: str, row: BenchmarkRunRow) -> int:
    """Insert a single ``benchmark_runs`` row; return the new ``id``.

    Rule C single-writer: this is the ONLY function that emits
    ``INSERT INTO benchmark_runs``. Boundary-check enforced.

    Atomicity: ``execute_insert_returning_id`` runs the statement inside
    BEGIN IMMEDIATE / COMMIT (per ``mailbot_api/db/connection.py``).

    Raises:
        sqlite3.IntegrityError: if the row violates the
            ``UNIQUE(run_id, corpus_item_id, task_type, model, prompt_version)``
            constraint. Callers in ``runner.py`` deduplicate via
            ``read_completed_cells`` BEFORE dispatch; an IntegrityError here
            indicates a programming bug or a concurrent runner — both fail
            loudly.
    """
    params: tuple[
        str, str, str, str, str, str, str | None,
        int, int, int, float, int,
        str, str, str, str, str, str,
    ] = (
        row.run_id,
        row.corpus_item_id,
        row.task_type,
        row.model,
        row.prompt_version,
        row.cohort_key,
        row.output_json,
        row.tokens_in,
        row.tokens_out,
        row.cached_tokens_in,
        row.cost_usd,
        row.latency_ms,
        row.outcome,
        row.status,
        row.scorer_model,
        row.anchors_version,
        row.router_policy_version,
        row.ran_at,
    )
    return await execute_insert_returning_id(db_path, _INSERT_BENCHMARK_RUN_SQL, params)


async def read_completed_cells(
    db_path: str, run_id: str
) -> set[tuple[str, str, str, str]]:
    """Return the set of completed (corpus_item_id, task_type, model, prompt_version) tuples.

    Used by ``runner.py`` for ``--resume`` dedup. Empty set if no rows match
    (fresh run_id). Includes rows with ANY status (``completed`` +
    ``aborted_cost_cap`` + ``interrupted``) — the runner does not re-dispatch
    a cell that already has any row, even an interrupted one (the user's
    intent is to skip already-attempted work).
    """
    rows = await fetchall(db_path, _READ_COMPLETED_CELLS_SQL, (run_id,))
    return {(corpus_id, task, model, pv) for corpus_id, task, model, pv in rows}


async def read_run_grid(db_path: str, run_id: str) -> set[tuple[str, str]]:
    """Return the set of (task_type, model) tuples present in a run.

    Used by ``runner.py`` to validate that ``--resume`` is invoked with the
    same ``--tasks`` and ``--models`` as the original run. A mismatched
    resume would silently expand the grid; refusing it is the safer default.
    Empty set if no rows match (fresh run_id, callers should fall through
    to the new-run pathway).
    """
    rows = await fetchall(db_path, _READ_RUN_GRID_SQL, (run_id,))
    return {(task, model) for task, model in rows}


__all__ = [
    "record_benchmark_run",
    "read_completed_cells",
    "read_run_grid",
]
