"""MailBot benchmark runner package (Story 9.6+).

Top-level sibling of ``evals/`` (the corpus authoring package from Story 9.5).
This package owns the benchmark dispatch surface: enumerate the
``(corpus_item × task × model × prompt_version)`` grid, dispatch each cell
through ``ask_router(force_model=...)`` per Rule I, record one row per
dispatch into the ``benchmark_runs`` table via the single writer in
``benchmark.db``, and produce a stable ``cohort_key`` per Adam-decision
2026-06-27 (A5 default 4-tuple).

Public API (re-exported via ``__all__``):
  * ``compute_cohort_key``       — pure leaf; SHA-256[:16] over the 4-tuple
  * ``BenchmarkCell``            — pre-dispatch (corpus_item × task × model × pv) shape
  * ``BenchmarkRunRow``          — per-row shape mirroring migration 024
  * ``record_benchmark_run``     — Rule C single writer (boundary-enforced)
  * ``read_completed_cells``     — ``--resume`` dedup helper
  * ``read_run_grid``            — ``--resume`` grid-mismatch validator
"""

from __future__ import annotations

from benchmark.cohort import compute_cohort_key
from benchmark.db import (
    read_completed_cells,
    read_run_grid,
    record_benchmark_run,
)
from benchmark.schemas import (
    BenchmarkCell,
    BenchmarkRunRow,
    OutcomeLiteral,
    StatusLiteral,
)

__all__ = [
    "BenchmarkCell",
    "BenchmarkRunRow",
    "OutcomeLiteral",
    "StatusLiteral",
    "compute_cohort_key",
    "read_completed_cells",
    "read_run_grid",
    "record_benchmark_run",
]
