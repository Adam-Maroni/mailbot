"""MailBot benchmark runner + scorer package (Story 9.6 + Story 9.7).

Top-level sibling of ``evals/`` (the corpus authoring package from Story 9.5).
This package owns:

* the **benchmark dispatch** surface (Story 9.6) — enumerate the
  ``(corpus_item × task × model × prompt_version)`` grid, dispatch each cell
  through ``ask_router(force_model=...)`` per Rule I, record one row per
  dispatch into the ``benchmark_runs`` table via the single writer in
  ``benchmark.db``, and produce a stable ``cohort_key`` per Adam-decision
  2026-06-27 (A5 default 4-tuple).
* the **benchmark scoring** surface (Story 9.7) — read ``benchmark_runs``
  rows, dispatch per-task scoring (objective: classification + extraction;
  subjective: anchor-calibrated auto-eval via Opus + optional secondary
  evaluator), compute Krippendorff α agreement, and write rows into the
  ``benchmark_scores`` table via the single writer in
  ``benchmark.scorer_db``.

Public API (re-exported via ``__all__``):

Story 9-6:
  * ``compute_cohort_key``       — pure leaf; SHA-256[:16] over the 4-tuple
  * ``BenchmarkCell``            — pre-dispatch (corpus_item × task × model × pv) shape
  * ``BenchmarkRunRow``          — per-row shape mirroring migration 024
  * ``record_benchmark_run``     — Rule C single writer (boundary-enforced)
  * ``read_completed_cells``     — ``--resume`` dedup helper
  * ``read_run_grid``            — ``--resume`` grid-mismatch validator

Story 9-7:
  * ``BenchmarkScoreRow``        — per-row shape mirroring migration 025
  * ``record_benchmark_score``   — Rule C single writer for ``benchmark_scores``
  * ``read_run_runs``            — Pydantic-typed read of ``benchmark_runs``
  * ``read_run_scores``          — Pydantic-typed read of ``benchmark_scores``
  * ``krippendorff_alpha_ordinal`` — pure-leaf cross-evaluator α
"""

from __future__ import annotations

from benchmark.agreement import krippendorff_alpha_ordinal
from benchmark.anchor_baselines import (
    BaselineComparison,
    BaselineSnapshot,
    PerAnchorDiff,
    PerAnchorScore,
    compare_against_current,
    load_baseline,
)
from benchmark.cohort import compute_cohort_key
from benchmark.db import (
    read_completed_cells,
    read_run_grid,
    record_benchmark_run,
)
from benchmark.report import render_report
from benchmark.schemas import (
    BenchmarkCell,
    BenchmarkRunRow,
    BenchmarkScoreRow,
    EvaluatorRoleLiteral,
    OutcomeLiteral,
    ScoreOutcomeLiteral,
    StatusLiteral,
)
from benchmark.scorer_db import (
    encode_extra_json,
    read_run_runs,
    read_run_scores,
    record_benchmark_score,
)
from benchmark.stats import (
    ParetoPoint,
    bootstrap_ci,
    compute_pareto_frontier,
    wilson_score_interval,
)
from benchmark.verdict import VerdictLiteral, compute_verdict

__all__ = [
    "BaselineComparison",
    "BaselineSnapshot",
    "BenchmarkCell",
    "BenchmarkRunRow",
    "BenchmarkScoreRow",
    "EvaluatorRoleLiteral",
    "OutcomeLiteral",
    "ParetoPoint",
    "PerAnchorDiff",
    "PerAnchorScore",
    "ScoreOutcomeLiteral",
    "StatusLiteral",
    "VerdictLiteral",
    "bootstrap_ci",
    "compare_against_current",
    "compute_cohort_key",
    "compute_pareto_frontier",
    "compute_verdict",
    "encode_extra_json",
    "krippendorff_alpha_ordinal",
    "load_baseline",
    "read_completed_cells",
    "read_run_grid",
    "read_run_runs",
    "read_run_scores",
    "record_benchmark_run",
    "record_benchmark_score",
    "render_report",
    "wilson_score_interval",
]
