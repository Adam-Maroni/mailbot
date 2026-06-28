"""Story 9.6: Pydantic shapes for the benchmark runner.

* ``BenchmarkCell`` — one (corpus_item_id, task_type, model, prompt_version)
  tuple BEFORE dispatch. Pure value type; carries no result data.
* ``BenchmarkRunRow`` — full row shape mirroring the ``benchmark_runs``
  SQL columns from migration 024. Written via ``benchmark.db.record_benchmark_run``.

Both shapes use ``model_config = ConfigDict(extra="forbid")`` so accidental
new fields fail loudly at validation time rather than silently dropping into
``output_json``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

OutcomeLiteral = Literal[
    "ok",
    "schema_failed",
    "timeout",
    "provider_error",
    "budget_blocked",
]

StatusLiteral = Literal[
    "completed",
    "aborted_cost_cap",
    "interrupted",
]


class BenchmarkCell(BaseModel):
    """One (corpus_item_id, task_type, model, prompt_version) tuple BEFORE dispatch.

    Used by the runner's grid enumeration + resume dedup pathway. Carries no
    result data; the dispatch produces a ``BenchmarkRunRow`` from this cell.
    """

    model_config = ConfigDict(extra="forbid")

    corpus_item_id: str
    task_type: str
    model: str
    prompt_version: str


class BenchmarkRunRow(BaseModel):
    """One row of the ``benchmark_runs`` table.

    Mirrors migration 024_benchmark_runs.sql column-for-column. The
    Pydantic ``extra="forbid"`` config + the closed-set Literals for
    ``outcome`` and ``status`` make this the authoritative application-side
    contract for the schema.

    Conventions:
      * ``output_json`` is the serialized prompt-module output on success;
        ``None`` on any failure.
      * ``cohort_key`` is per-row (Story 9-6 design — single-row queries
        don't need to JOIN to a run_metadata table).
      * ``scorer_model`` + ``anchors_version`` + ``router_policy_version``
        are frozen at run-start; they compose the cohort_key.
      * ``ran_at`` is UTC ISO-8601 with ``Z`` suffix.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    corpus_item_id: str
    task_type: str
    model: str
    prompt_version: str
    cohort_key: str
    output_json: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens_in: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    outcome: OutcomeLiteral
    status: StatusLiteral = "completed"
    scorer_model: str
    anchors_version: str
    router_policy_version: str
    ran_at: str


__all__ = [
    "BenchmarkCell",
    "BenchmarkRunRow",
    "OutcomeLiteral",
    "StatusLiteral",
]
