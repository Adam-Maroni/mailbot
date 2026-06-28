"""Story 9-7 AC-2/AC-9/AC-11/AC-12: benchmark scorer CLI.

Reads ``benchmark_runs`` rows for a given ``--run-id``, dispatches per-task
scoring (objective via ``benchmark/scoring/objective.py``; subjective via
``benchmark/scoring/subjective.py``), and writes ``benchmark_scores`` rows
via ``benchmark/scorer_db.py``.

CLI surface (full spec in story file AC-2):

    python -m benchmark.scorer \\
        --run-id <uuid> \\
        [--secondary-evaluator <model-id>] \\
        [--scorer-model <model-id>] \\
        [--db-path <path>] \\
        [--tasks <comma-separated>] [--models <comma-separated>] \\
        [--cost-mock] [--yes] [--anchors-dir <path>] [--corpus <path>]

Three load-bearing safety features mirror the runner (Story 9-6):

* ``$5 confirmation gate`` (AC-11) — estimates total subjective dispatch
  cost; prompts above $5; ``--yes`` bypasses.
* ``MAILBOT_DB_PATH`` env-var fallback when ``--db-path`` is absent.
* ``BENCHMARK_COST_MOCK=1`` env-var carrier for Story 9-8.

All subjective dispatches go through ``ask_router(task_type=
"anchor_calibrated_eval", force_model=<scorer>, force=True,
caller_origin="benchmark-scorer", email_id=None)`` per Rule I.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import (
    encode_extra_json,
    read_run_runs,
    read_run_scores,
    record_benchmark_score,
)
from benchmark.scoring.objective import (
    ClassificationMetrics,
    ExtractionMetrics,
    score_classification,
    score_extraction,
)
from benchmark.scoring.subjective import (
    SubjectiveMetrics,
    load_anchors,
    score_subjective,
)
from evals.corpus_schema import CorpusItem, load_corpus

_logger = logging.getLogger(__name__)

_DEFAULT_SCORER_MODEL: str = "claude-opus-4-7-20251220"
_DEFAULT_DB_PATH_ENV: str = "MAILBOT_DB_PATH"
_DEFAULT_CORPUS_PATH: str = "evals/email_corpus_v1.jsonl"
_DEFAULT_ANCHORS_DIR: str = "evals/anchors"

_COST_GATE_THRESHOLD_USD: float = 5.00

_COST_MOCK_ENV: str = "BENCHMARK_COST_MOCK"

# Classification task → (output_field_name, ground_truth_attr) on CorpusLabels.
_CLASSIFICATION_TASKS: dict[str, tuple[str, str]] = {
    "coarse_class": ("class_coarse", "class_coarse"),
    "sensitivity_class": ("sensitivity", "sensitivity"),
    "fine_class": ("class_fine", "class_fine"),
}

_SUBJECTIVE_TASKS: frozenset[str] = frozenset({"draft_reply", "summary_short"})

_EXTRACTION_TASK: str = "action_extraction"


def _utc_now_z() -> str:
    """UTC ISO-8601 with Z suffix; matches runner's `_utc_now_z`."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _group_rows_by_task_model(
    rows: list[BenchmarkRunRow],
    task_filter: set[str] | None,
    model_filter: set[str] | None,
) -> dict[tuple[str, str], list[BenchmarkRunRow]]:
    """Bucket the rows into (task_type, model) batches honoring optional filters."""
    by_pair: dict[tuple[str, str], list[BenchmarkRunRow]] = {}
    for row in rows:
        if task_filter is not None and row.task_type not in task_filter:
            continue
        if model_filter is not None and row.model not in model_filter:
            continue
        key = (row.task_type, row.model)
        by_pair.setdefault(key, []).append(row)
    return by_pair


def _classification_extra_json(metrics: ClassificationMetrics) -> str:
    return encode_extra_json(
        {
            "confusion_matrix": metrics.confusion_matrix,
            "per_class": metrics.per_class,
        }
    )


def _extraction_extra_json(metrics: ExtractionMetrics) -> str:
    return encode_extra_json({"per_action_type": metrics.per_action_type})


def _ok_rate_extra_json(ok_count: int, total_count: int) -> str:
    return encode_extra_json({"ok_count": ok_count, "total_count": total_count})


def _calibration_extra_json(metrics: SubjectiveMetrics) -> str:
    return encode_extra_json(
        {
            "per_anchor": metrics.calibration_per_anchor,
            "n_anchors": len(metrics.calibration_per_anchor),
        }
    )


def _alpha_extra_json(metrics: SubjectiveMetrics) -> str:
    return encode_extra_json(
        {
            "per_anchor": metrics.cross_evaluator_per_anchor,
            "n_anchors": len(metrics.cross_evaluator_per_anchor),
        }
    )


def _per_axis_extra_json(metrics: SubjectiveMetrics, axis: str) -> str:
    values = [
        p.per_axis_scores.get(axis)
        for p in metrics.per_row_scores
        if axis in p.per_axis_scores
    ]
    return encode_extra_json({"per_row_scores": values, "n_rows": len(values)})


def _overall_extra_json(metrics: SubjectiveMetrics) -> str:
    return encode_extra_json(
        {
            "per_row_scores": [p.overall_score for p in metrics.per_row_scores],
            "n_rows": len(metrics.per_row_scores),
        }
    )


async def _write_classification_scores(
    db_path: str,
    pair_rows: list[BenchmarkRunRow],
    metrics: ClassificationMetrics,
    cohort_key: str,
    prompt_version: str,
    task_type: str,
    model: str,
) -> None:
    common = {
        "run_id": pair_rows[0].run_id,
        "cohort_key": cohort_key,
        "task_type": task_type,
        "model": model,
        "prompt_version": prompt_version,
        "scorer_model": "objective:mechanical",
        "evaluator_role": "primary",
        "computed_at": _utc_now_z(),
    }

    if metrics.ok_count == 0:
        # Insufficient data: still write a metric row so the report sees the gap.
        await record_benchmark_score(
            db_path,
            BenchmarkScoreRow.model_validate(
                {
                    **common,
                    "metric_name": "accuracy",
                    "metric_value": 0.0,
                    "sample_count": 0,
                    "outcome": "insufficient_data",
                    "extra_json": None,
                }
            ),
        )
    else:
        extra_json = _classification_extra_json(metrics)
        for metric_name, value in (
            ("accuracy", metrics.accuracy),
            ("precision_macro", metrics.precision_macro),
            ("recall_macro", metrics.recall_macro),
            ("f1_macro", metrics.f1_macro),
        ):
            await record_benchmark_score(
                db_path,
                BenchmarkScoreRow.model_validate(
                    {
                        **common,
                        "metric_name": metric_name,
                        "metric_value": value,
                        "sample_count": metrics.ok_count,
                        "outcome": "ok",
                        "extra_json": extra_json,
                    }
                ),
            )

    # ok_rate row (always written so report has visibility into failure rate).
    await record_benchmark_score(
        db_path,
        BenchmarkScoreRow.model_validate(
            {
                **common,
                "metric_name": "ok_rate",
                "metric_value": (
                    metrics.ok_count / metrics.total_count
                    if metrics.total_count > 0
                    else 0.0
                ),
                "sample_count": metrics.total_count,
                "outcome": "ok",
                "extra_json": _ok_rate_extra_json(metrics.ok_count, metrics.total_count),
            }
        ),
    )


async def _write_extraction_scores(
    db_path: str,
    pair_rows: list[BenchmarkRunRow],
    metrics: ExtractionMetrics,
    cohort_key: str,
    prompt_version: str,
    model: str,
) -> None:
    common = {
        "run_id": pair_rows[0].run_id,
        "cohort_key": cohort_key,
        "task_type": _EXTRACTION_TASK,
        "model": model,
        "prompt_version": prompt_version,
        "scorer_model": "objective:mechanical",
        "evaluator_role": "primary",
        "computed_at": _utc_now_z(),
    }

    if metrics.ok_count == 0:
        await record_benchmark_score(
            db_path,
            BenchmarkScoreRow.model_validate(
                {
                    **common,
                    "metric_name": "f1_action_type",
                    "metric_value": 0.0,
                    "sample_count": 0,
                    "outcome": "insufficient_data",
                    "extra_json": None,
                }
            ),
        )
    else:
        extra_json = _extraction_extra_json(metrics)
        for metric_name, value in (
            ("f1_action_type", metrics.f1_action_type),
            ("f1_summary_similarity", metrics.f1_summary_similarity),
            ("f1_deadline_match", metrics.f1_deadline_match),
        ):
            await record_benchmark_score(
                db_path,
                BenchmarkScoreRow.model_validate(
                    {
                        **common,
                        "metric_name": metric_name,
                        "metric_value": value,
                        "sample_count": metrics.ok_count,
                        "outcome": "ok",
                        "extra_json": extra_json,
                    }
                ),
            )

    await record_benchmark_score(
        db_path,
        BenchmarkScoreRow.model_validate(
            {
                **common,
                "metric_name": "ok_rate",
                "metric_value": (
                    metrics.ok_count / metrics.total_count
                    if metrics.total_count > 0
                    else 0.0
                ),
                "sample_count": metrics.total_count,
                "outcome": "ok",
                "extra_json": _ok_rate_extra_json(metrics.ok_count, metrics.total_count),
            }
        ),
    )


async def _write_subjective_scores(
    db_path: str,
    pair_rows: list[BenchmarkRunRow],
    metrics: SubjectiveMetrics,
    cohort_key: str,
    prompt_version: str,
    task_type: str,
    model: str,
    scorer_model: str,
    secondary_evaluator: str | None,
) -> None:
    common = {
        "run_id": pair_rows[0].run_id,
        "cohort_key": cohort_key,
        "task_type": task_type,
        "model": model,
        "prompt_version": prompt_version,
        "scorer_model": scorer_model,
        "evaluator_role": "primary",
        "computed_at": _utc_now_z(),
    }

    # MAE row — always written.
    await record_benchmark_score(
        db_path,
        BenchmarkScoreRow.model_validate(
            {
                **common,
                "metric_name": "calibration_mae",
                # CR-F5 (LOW): when all 20 calibration anchors failed to
                # dispatch (calibration_mae == inf), use a -1.0 sentinel
                # (out of the normal [0, 4] MAE range) and set
                # outcome=scorer_error so Story 9-9's report renderer can
                # distinguish "all anchors failed" from "perfect calibration
                # (MAE=0.0)" — the prior implementation silently coerced
                # inf to 0.0, making the two indistinguishable.
                "metric_value": (
                    metrics.calibration_mae
                    if metrics.calibration_mae != float("inf")
                    else -1.0
                ),
                "sample_count": len(metrics.calibration_per_anchor),
                "outcome": (
                    "scorer_error"
                    if metrics.calibration_mae == float("inf")
                    else (
                        "calibration_warning"
                        if metrics.outcome == "calibration_warning"
                        else "ok"
                    )
                ),
                "extra_json": _calibration_extra_json(metrics),
            }
        ),
    )

    if metrics.ok_count == 0:
        await record_benchmark_score(
            db_path,
            BenchmarkScoreRow.model_validate(
                {
                    **common,
                    "metric_name": "subjective_overall",
                    "metric_value": 0.0,
                    "sample_count": 0,
                    "outcome": "insufficient_data",
                    "extra_json": None,
                }
            ),
        )
    else:
        await record_benchmark_score(
            db_path,
            BenchmarkScoreRow.model_validate(
                {
                    **common,
                    "metric_name": "subjective_overall",
                    "metric_value": metrics.mean_overall,
                    "sample_count": metrics.ok_count,
                    "outcome": metrics.outcome,
                    "extra_json": _overall_extra_json(metrics),
                }
            ),
        )
        for axis, mean_val in sorted(metrics.mean_per_axis.items()):
            await record_benchmark_score(
                db_path,
                BenchmarkScoreRow.model_validate(
                    {
                        **common,
                        "metric_name": f"subjective_{axis}",
                        "metric_value": mean_val,
                        "sample_count": metrics.ok_count,
                        "outcome": metrics.outcome,
                        "extra_json": _per_axis_extra_json(metrics, axis),
                    }
                ),
            )

    # Cross-evaluator α (when applicable).
    if metrics.cross_evaluator_alpha is not None and secondary_evaluator is not None:
        await record_benchmark_score(
            db_path,
            BenchmarkScoreRow.model_validate(
                {
                    **common,
                    "metric_name": "cross_evaluator_alpha",
                    "metric_value": metrics.cross_evaluator_alpha,
                    "sample_count": len(metrics.cross_evaluator_per_anchor),
                    "outcome": (
                        "calibration_warning"
                        if metrics.cross_evaluator_alpha < 0.6
                        else "ok"
                    ),
                    "extra_json": _alpha_extra_json(metrics),
                }
            ),
        )

    # ok_rate row.
    await record_benchmark_score(
        db_path,
        BenchmarkScoreRow.model_validate(
            {
                **common,
                "metric_name": "ok_rate",
                "metric_value": (
                    metrics.ok_count / metrics.total_count
                    if metrics.total_count > 0
                    else 0.0
                ),
                "sample_count": metrics.total_count,
                "outcome": "ok",
                "extra_json": _ok_rate_extra_json(metrics.ok_count, metrics.total_count),
            }
        ),
    )


def _estimate_subjective_cost(
    by_pair: dict[tuple[str, str], list[BenchmarkRunRow]],
    n_anchors: int,
    scorer_model: str,
    secondary_evaluator: str | None,
    anchors_block_chars: int | None = None,
    per_row_chars: int = 600,
    sample_output_tokens: int = 256,
) -> float:
    """Rough estimate of total subjective-evaluator cost in USD.

    Per subjective (task, model) pair we run: ``n_anchors`` calibration
    dispatches + ``len(pair_rows)`` per-row dispatches. If a secondary
    evaluator is configured we add another ``n_anchors`` calls for it.

    CR-F3 (MEDIUM) 2026-06-28: the prior implementation used a fixed
    ``sample_input_chars=2000`` constant that was ~5× below the actual
    anchors-block input size (20 anchors × ~450 chars avg = ~9 000 chars
    + ~600 chars per item-under-test). The caller now passes the
    pre-rendered ``anchors_block_chars`` (already computed during anchor
    loading) so the $5 pre-flight gate reflects realistic dispatch cost.
    Fallback: when no block size is known, use a conservative
    ``9000 + per_row_chars`` estimate rather than the prior 2000-char
    under-count.
    """
    from mailbot_api.router.pricing import estimate_cost_usd

    block_chars = anchors_block_chars if anchors_block_chars is not None else 9000
    total_input_chars = block_chars + per_row_chars
    tokens_in_per_call = max(1, total_input_chars // 4)
    total = 0.0
    for (task_type, _model), pair_rows in by_pair.items():
        if task_type not in _SUBJECTIVE_TASKS:
            continue
        primary_calls = n_anchors + len(pair_rows)
        total += primary_calls * estimate_cost_usd(
            scorer_model, tokens_in_per_call, sample_output_tokens
        )
        if secondary_evaluator is not None:
            total += n_anchors * estimate_cost_usd(
                secondary_evaluator, tokens_in_per_call, sample_output_tokens
            )
    return total


def _resolve_db_path(cli_db_path: str | None) -> str:
    if cli_db_path:
        return cli_db_path
    env_path = os.environ.get(_DEFAULT_DB_PATH_ENV, "")
    if not env_path:
        raise SystemExit(
            f"{_DEFAULT_DB_PATH_ENV} unset and --db-path not provided; refusing to dispatch"
        )
    return env_path


def _confirm_proceed(prompt: str) -> bool:
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="benchmark.scorer",
        description="Story 9.7: benchmark scorer (Rule I — dispatches via ask_router force_model)",
    )
    parser.add_argument("--run-id", type=str, required=True, help="run_id to score")
    parser.add_argument(
        "--secondary-evaluator",
        type=str,
        default=None,
        help="Optional cross-evaluator model id for Krippendorff α (Story 9-7 AC-7)",
    )
    parser.add_argument(
        "--scorer-model",
        type=str,
        default=_DEFAULT_SCORER_MODEL,
        help="Primary evaluator model id",
    )
    parser.add_argument(
        "--corpus",
        type=str,
        default=_DEFAULT_CORPUS_PATH,
        help="Path to email_corpus_v1.jsonl",
    )
    parser.add_argument(
        "--anchors-dir",
        type=str,
        default=_DEFAULT_ANCHORS_DIR,
        help="Path to evals/anchors directory",
    )
    parser.add_argument(
        "--tasks", type=str, default=None, help="Optional comma-separated task filter"
    )
    parser.add_argument(
        "--models", type=str, default=None, help="Optional comma-separated model filter"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm cost gate (non-TTY contexts)",
    )
    parser.add_argument(
        "--cost-mock",
        action="store_true",
        help=f"Set ${_COST_MOCK_ENV}=1 for the adapter layer (Story 9-8 hook)",
    )
    parser.add_argument("--db-path", type=str, default=None, help="SQLite path; defaults to $MAILBOT_DB_PATH")
    return parser.parse_args(argv)


async def _run_async(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)

    if args.cost_mock:
        os.environ[_COST_MOCK_ENV] = "1"
        _logger.info("cost-mock mode requested; %s=1", _COST_MOCK_ENV)

    rows = await read_run_runs(db_path, args.run_id)
    if not rows:
        raise SystemExit(f"no benchmark_runs rows found for run_id={args.run_id}")

    items = load_corpus(Path(args.corpus))
    items_by_id: dict[str, CorpusItem] = {it.id: it for it in items}

    task_filter = set(args.tasks.split(",")) if args.tasks else None
    model_filter = set(args.models.split(",")) if args.models else None
    by_pair = _group_rows_by_task_model(rows, task_filter, model_filter)
    if not by_pair:
        print("No (task, model) pairs match the requested filters; nothing to score.")
        return 0

    print(f"Scoring run_id={args.run_id}; {len(by_pair)} (task, model) pairs.")

    # Pre-load anchors per subjective task so we know n_anchors for cost estimate.
    anchors_by_task = {}
    needed_tasks = {t for (t, _m) in by_pair if t in _SUBJECTIVE_TASKS}
    for task in needed_tasks:
        anchors_by_task[task] = load_anchors(Path(args.anchors_dir), task)

    # Cost gate (AC-11). CR-F3 (MEDIUM): pass the actual anchors-block size
    # rather than a 2000-char constant — pre-render the largest anchors
    # block across the requested subjective tasks (worst-case bias) so the
    # estimate doesn't silently under-count and let runs slip past the $5
    # gate that should have prompted for confirmation.
    n_anchors = max((len(v) for v in anchors_by_task.values()), default=0)
    if anchors_by_task:
        from benchmark.scoring.subjective import build_anchors_block as _build_block
        anchors_block_chars = max(
            len(_build_block(anchors)) for anchors in anchors_by_task.values()
        )
    else:
        anchors_block_chars = None
    total_cost = _estimate_subjective_cost(
        by_pair,
        n_anchors=n_anchors,
        scorer_model=args.scorer_model,
        secondary_evaluator=args.secondary_evaluator,
        anchors_block_chars=anchors_block_chars,
    )
    print(f"Estimated subjective-dispatch cost: ${total_cost:.2f}")
    if total_cost > _COST_GATE_THRESHOLD_USD and not args.yes:
        if not _confirm_proceed("Proceed? [y/N]: "):
            print("Aborted by user; no scores written.")
            return 0
    elif args.yes and total_cost > _COST_GATE_THRESHOLD_USD:
        _logger.info(
            "cost_gate.bypassed_via_yes_flag run_id=%s estimated_total_usd=%.2f",
            args.run_id,
            total_cost,
        )

    # Per-pair scoring.
    for (task_type, model), pair_rows in by_pair.items():
        cohort_key = pair_rows[0].cohort_key
        prompt_version = pair_rows[0].prompt_version

        if task_type in _CLASSIFICATION_TASKS:
            output_field, ground_truth_attr = _CLASSIFICATION_TASKS[task_type]
            metrics_c = score_classification(
                pair_rows,
                items_by_id,
                task_type=task_type,
                output_field_name=output_field,
                ground_truth_attr=ground_truth_attr,
            )
            await _write_classification_scores(
                db_path, pair_rows, metrics_c, cohort_key, prompt_version, task_type, model
            )
        elif task_type == _EXTRACTION_TASK:
            metrics_e = score_extraction(pair_rows, items_by_id)
            await _write_extraction_scores(
                db_path, pair_rows, metrics_e, cohort_key, prompt_version, model
            )
        elif task_type in _SUBJECTIVE_TASKS:
            metrics_s = await score_subjective(
                rows=pair_rows,
                items_by_id=items_by_id,
                anchors=anchors_by_task[task_type],
                db_path=db_path,
                scorer_model=args.scorer_model,
                task_type=task_type,
                secondary_evaluator=args.secondary_evaluator,
            )
            await _write_subjective_scores(
                db_path,
                pair_rows,
                metrics_s,
                cohort_key,
                prompt_version,
                task_type,
                model,
                args.scorer_model,
                args.secondary_evaluator,
            )
        else:
            _logger.warning("scorer.unknown_task_type task=%s; skipping pair", task_type)

    # Read-back summary so the operator sees what landed.
    scores = await read_run_scores(db_path, args.run_id)
    print(f"Wrote {len(scores)} benchmark_scores rows for run_id={args.run_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    sys.exit(main())
