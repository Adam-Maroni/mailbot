"""Story 9-11: anchor stability audit — one-shot cross-evaluator calibration.

Runs the 20 hand-anchored subjective items per task (40 total: 20
summary_short + 20 draft_reply) through BOTH the primary evaluator (Opus
by default) and a secondary evaluator (Sonnet by default), computes
Krippendorff α agreement coefficient (ordinal δ² metric) on the
overall_score values, and persists the result as the baseline at
``evals/anchor_baselines/v{N}.json``.

CLI surface:

    python -m benchmark.anchor_stability_audit \\
        --evaluators primary,secondary \\
        --secondary-model claude-sonnet-4-5 \\
        [--primary-model claude-opus-4-7-20251220] \\
        [--output evals/anchor_baselines/v1.json] \\
        [--db-path <path>] \\
        [--anchors-dir evals/anchors] \\
        [--tasks summary_short,draft_reply] \\
        [--cost-mock] [--yes]

Verdict thresholds (Story 9-11 AC-5):
  * α ≥ 0.8        → ``trusted``
  * 0.6 ≤ α < 0.8  → ``uncertain`` (acceptable but flagged)
  * α < 0.6        → ``untrusted`` (BLOCKS Epic 9 done-flip clause #9)

On ``untrusted``: the script EXITS WITH NON-ZERO status, writes the
payload to ``<output-dir>/<output-stem>-FAILED-CALIBRATION.json`` rather
than the canonical ``--output`` path, and prints a per-anchor
disagreement table to stderr ordered by ``abs(delta)`` desc.

Per Rule I every evaluator call goes through ``ask_router(task_type=
"anchor_calibrated_eval", force_model=<scorer>, force=True,
caller_origin="benchmark-scorer", email_id=None)`` — note that the audit
INHERITS the ``caller_origin="benchmark-scorer"`` attribution from Story
9-7's ``benchmark/scoring/subjective.py::_dispatch_eval`` rather than
declaring its own ``"benchmark-anchor-stability-audit"`` origin. This is
the deliberate trade-off of AC-2 (one dispatch path of truth) — the
audit re-uses the already-CR'd subjective scorer's dispatch helper
rather than duplicating it. Operators auditing ``router_calls`` for
anchor-stability-audit provenance should grep by time-range + the
``anchor_calibrated_eval`` task_type rather than by ``caller_origin``;
a follow-up story can thread an explicit override through
``_dispatch_eval`` if origin attribution becomes a hard requirement
(see Story 9-11 CR-F2 note for context).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from benchmark.anchor_baselines import (
    BaselineSnapshot,
    PerAnchorScore,
    VerdictLiteral,
)
from benchmark.scoring.subjective import (
    _AnchorCalibrationResult,
    _run_anchor_calibration,
    build_anchors_block,
    load_anchors,
)
from evals.corpus_schema import AnchorItem

_logger = logging.getLogger(__name__)

_DEFAULT_PRIMARY_MODEL: str = "claude-opus-4-7-20251220"
_DEFAULT_SECONDARY_MODEL: str = "claude-sonnet-4-5"
_DEFAULT_OUTPUT_PATH: str = "evals/anchor_baselines/v1.json"
_DEFAULT_ANCHORS_DIR: str = "evals/anchors"
_DEFAULT_DB_PATH_ENV: str = "MAILBOT_DB_PATH"
_DEFAULT_TASKS: tuple[str, ...] = ("summary_short", "draft_reply")

_COST_GATE_THRESHOLD_USD: float = 5.00
_COST_MOCK_ENV: str = "BENCHMARK_COST_MOCK"

_ALPHA_TRUSTED_THRESHOLD: float = 0.8
_ALPHA_UNCERTAIN_THRESHOLD: float = 0.6


def _utc_today() -> str:
    """ISO-8601 date (YYYY-MM-DD) in UTC."""
    return datetime.now(timezone.utc).date().isoformat()


def _classify_alpha(alpha: float) -> VerdictLiteral:
    """Map Krippendorff α to a verdict band per Story 9-11 AC-5."""
    if alpha >= _ALPHA_TRUSTED_THRESHOLD:
        return "trusted"
    if alpha >= _ALPHA_UNCERTAIN_THRESHOLD:
        return "uncertain"
    return "untrusted"


def _resolve_db_path(cli_db_path: str | None) -> str:
    """CLI arg → env-var fallback; SystemExit if neither resolves.

    Mirrors ``benchmark/scorer.py::_resolve_db_path`` so the operator
    experience is consistent across the runner / scorer / audit triad.
    """
    if cli_db_path:
        return cli_db_path
    env_path = os.environ.get(_DEFAULT_DB_PATH_ENV, "")
    if not env_path:
        raise SystemExit(
            f"{_DEFAULT_DB_PATH_ENV} unset and --db-path not provided; refusing to dispatch"
        )
    return env_path


def _confirm_proceed(prompt: str) -> bool:
    """Read y/N from stdin; non-TTY → False (refuse)."""
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def _estimate_audit_cost(
    n_anchors_per_task: int,
    n_tasks: int,
    primary_model: str,
    secondary_model: str,
    anchors_block_chars: int,
    per_row_chars: int = 600,
    sample_output_tokens: int = 256,
) -> float:
    """Rough USD cost estimate for the full audit dispatch.

    For each (task, evaluator) we run ``n_anchors_per_task`` calibration
    dispatches; both evaluators run on every anchor so the call count
    is ``n_anchors_per_task * n_tasks * 2``. Per-call token volume is
    the rendered anchors block + the item-under-test block, chunked at
    4 chars/token (same heuristic as Story 9-7 scorer).
    """
    from mailbot_api.router.pricing import estimate_cost_usd

    total_input_chars = anchors_block_chars + per_row_chars
    tokens_in_per_call = max(1, total_input_chars // 4)
    n_calls_per_eval = n_anchors_per_task * n_tasks
    primary_cost = n_calls_per_eval * estimate_cost_usd(
        primary_model, tokens_in_per_call, sample_output_tokens
    )
    secondary_cost = n_calls_per_eval * estimate_cost_usd(
        secondary_model, tokens_in_per_call, sample_output_tokens
    )
    return primary_cost + secondary_cost


def _failed_calibration_path(output_path: Path) -> Path:
    """Derive the FAILED-CALIBRATION sibling path for an `untrusted` verdict.

    e.g., ``evals/anchor_baselines/v1.json``
       → ``evals/anchor_baselines/v1-FAILED-CALIBRATION.json``.
    """
    return output_path.with_name(f"{output_path.stem}-FAILED-CALIBRATION{output_path.suffix}")


def _compose_per_anchor_scores(
    primary: _AnchorCalibrationResult,
    secondary: _AnchorCalibrationResult,
    task: str,
) -> list[PerAnchorScore]:
    """Build the per-anchor PerAnchorScore list aligned by anchor_id.

    Only anchors scored by BOTH evaluators contribute (alignment by id
    rather than positional index — defends against one evaluator failing
    on a specific anchor while the other succeeded). The result is
    sorted by anchor_id for diff-friendliness (AC-9).
    """
    primary_by_id = {
        aid: score
        for aid, score in zip(
            primary.per_anchor_ids, primary.per_anchor_auto_scores, strict=True
        )
    }
    secondary_by_id = {
        aid: score
        for aid, score in zip(
            secondary.per_anchor_ids, secondary.per_anchor_auto_scores, strict=True
        )
    }
    paired_ids = sorted(set(primary_by_id) & set(secondary_by_id))
    rows: list[PerAnchorScore] = []
    for aid in paired_ids:
        p_score = primary_by_id[aid]
        s_score = secondary_by_id[aid]
        rows.append(
            PerAnchorScore(
                anchor_id=aid,
                task=task,  # type: ignore[arg-type]
                primary_score=int(p_score),
                secondary_score=int(s_score),
                delta=int(abs(p_score - s_score)),
            )
        )
    return rows


def _compose_baseline(
    primary_evaluator: str,
    secondary_evaluator: str,
    anchors_version: str,
    per_anchor_scores: list[PerAnchorScore],
    alpha: float,
    verdict: VerdictLiteral,
    baseline_date: str | None = None,
) -> BaselineSnapshot:
    """Build the BaselineSnapshot with deterministic per-anchor ordering.

    Per-anchor list is sorted by anchor_id (AC-9 diff-friendliness
    invariant). ``baseline_date`` defaults to today's UTC date; tests can
    override for byte-identical fixtures.
    """
    sorted_rows = sorted(per_anchor_scores, key=lambda r: r.anchor_id)
    return BaselineSnapshot(
        baseline_date=baseline_date if baseline_date is not None else _utc_today(),
        primary_evaluator=primary_evaluator,
        secondary_evaluator=secondary_evaluator,
        anchors_version=anchors_version,
        per_anchor_scores=sorted_rows,
        krippendorff_alpha=alpha,
        verdict=verdict,
    )


def _serialize_baseline(snapshot: BaselineSnapshot) -> str:
    """Render the BaselineSnapshot to a stable JSON string.

    Uses ``sort_keys=True`` for top-level keys and a 2-space indent.
    The per_anchor_scores list is already pre-sorted by anchor_id (see
    ``_compose_baseline``) and Pydantic preserves insertion order on
    serialize, so the resulting bytes are deterministic for a fixed
    input.
    """
    return json.dumps(
        snapshot.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def _write_baseline_atomic(payload: str, path: Path) -> None:
    """Write the baseline JSON via tmp-file + os.replace (atomic on Windows + POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _print_disagreement_table(
    per_anchor: list[PerAnchorScore], file: Literal["stderr", "stdout"] = "stderr"
) -> None:
    """Print per-anchor delta table sorted by abs(delta) desc.

    Lines are tab-separated for easy operator paste-into-spreadsheet.
    """
    stream = sys.stderr if file == "stderr" else sys.stdout
    sorted_rows = sorted(per_anchor, key=lambda r: (-r.delta, r.anchor_id))
    print("anchor_id\ttask\tprimary\tsecondary\tdelta", file=stream)
    for row in sorted_rows:
        print(
            f"{row.anchor_id}\t{row.task}\t{row.primary_score}"
            f"\t{row.secondary_score}\t{row.delta}",
            file=stream,
        )


async def _audit_all_tasks(
    tasks: list[str],
    anchors_by_task: dict[str, list[AnchorItem]],
    db_path: str,
    primary_model: str,
    secondary_model: str,
) -> tuple[list[PerAnchorScore], float]:
    """Run the audit for every task; return aggregated per-anchor + α."""
    from benchmark.agreement import krippendorff_alpha_ordinal

    all_pairs: list[PerAnchorScore] = []
    primary_aligned_all: list[float | None] = []
    secondary_aligned_all: list[float | None] = []

    for task in tasks:
        anchors = anchors_by_task[task]
        anchors_block = build_anchors_block(anchors)
        primary_result = await _run_anchor_calibration(
            anchors, db_path, primary_model, anchors_block
        )
        secondary_result = await _run_anchor_calibration(
            anchors, db_path, secondary_model, anchors_block
        )
        pairs = _compose_per_anchor_scores(primary_result, secondary_result, task)
        all_pairs.extend(pairs)

        # Build per-task aligned lists for the global α computation.
        primary_by_id = {
            aid: score
            for aid, score in zip(
                primary_result.per_anchor_ids,
                primary_result.per_anchor_auto_scores,
                strict=True,
            )
        }
        secondary_by_id = {
            aid: score
            for aid, score in zip(
                secondary_result.per_anchor_ids,
                secondary_result.per_anchor_auto_scores,
                strict=True,
            )
        }
        ids = sorted(set(primary_by_id) | set(secondary_by_id))
        for aid in ids:
            primary_aligned_all.append(
                float(primary_by_id[aid]) if aid in primary_by_id else None
            )
            secondary_aligned_all.append(
                float(secondary_by_id[aid]) if aid in secondary_by_id else None
            )

    if not all_pairs:
        # No anchor was scored by both evaluators on any task; α is
        # mathematically undefined. Mark as untrusted via -1.0 sentinel
        # so the caller writes the FAILED-CALIBRATION path.
        return [], -1.0

    try:
        alpha = krippendorff_alpha_ordinal(
            {"primary": primary_aligned_all, "secondary": secondary_aligned_all}
        )
    except ValueError:
        # Too few pairable observations across all tasks → untrusted.
        alpha = -1.0
    return all_pairs, alpha


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="benchmark.anchor_stability_audit",
        description=(
            "Story 9.11: one-shot cross-evaluator anchor calibration audit. "
            "Dispatches primary + secondary evaluators against the 20 anchored "
            "items per task and persists the Krippendorff alpha baseline."
        ),
    )
    parser.add_argument(
        "--evaluators",
        type=str,
        default="primary,secondary",
        help=(
            "Comma-separated evaluator roles to run; must include both "
            "'primary' and 'secondary' for a meaningful alpha (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--primary-model",
        type=str,
        default=_DEFAULT_PRIMARY_MODEL,
        help="Primary evaluator model id (default: %(default)s).",
    )
    parser.add_argument(
        "--secondary-model",
        type=str,
        default=_DEFAULT_SECONDARY_MODEL,
        help="Secondary evaluator model id (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=_DEFAULT_OUTPUT_PATH,
        help="Canonical baseline JSON output path (default: %(default)s).",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="SQLite path; defaults to $MAILBOT_DB_PATH.",
    )
    parser.add_argument(
        "--anchors-dir",
        type=str,
        default=_DEFAULT_ANCHORS_DIR,
        help="Anchors directory (default: %(default)s).",
    )
    parser.add_argument(
        "--tasks",
        type=str,
        default=",".join(_DEFAULT_TASKS),
        help="Comma-separated subjective tasks to audit (default: %(default)s).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm cost gate (non-TTY contexts).",
    )
    parser.add_argument(
        "--cost-mock",
        action="store_true",
        help=f"Set ${_COST_MOCK_ENV}=1 for the adapter layer (Story 9-8 hook).",
    )
    return parser.parse_args(argv)


async def _run_async(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)

    if args.cost_mock:
        os.environ[_COST_MOCK_ENV] = "1"
        _logger.info("cost-mock mode requested; %s=1", _COST_MOCK_ENV)

    evaluator_roles = {r.strip() for r in args.evaluators.split(",") if r.strip()}
    if not {"primary", "secondary"}.issubset(evaluator_roles):
        raise SystemExit(
            "--evaluators must include both 'primary' and 'secondary' for a "
            "meaningful cross-evaluator alpha; got: "
            f"{sorted(evaluator_roles)}"
        )

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if not tasks:
        raise SystemExit("--tasks must be a non-empty comma-separated list")

    anchors_dir = Path(args.anchors_dir)
    anchors_by_task: dict[str, list[AnchorItem]] = {}
    for task in tasks:
        anchors_by_task[task] = load_anchors(anchors_dir, task)

    n_anchors_per_task = max(
        (len(v) for v in anchors_by_task.values()), default=0
    )
    if n_anchors_per_task == 0:
        raise SystemExit("No anchors loaded; refusing to dispatch")

    largest_block_chars = max(
        len(build_anchors_block(v)) for v in anchors_by_task.values()
    )
    total_cost = _estimate_audit_cost(
        n_anchors_per_task=n_anchors_per_task,
        n_tasks=len(tasks),
        primary_model=args.primary_model,
        secondary_model=args.secondary_model,
        anchors_block_chars=largest_block_chars,
    )
    print(f"Estimated audit dispatch cost: ${total_cost:.2f}")
    if total_cost > _COST_GATE_THRESHOLD_USD and not args.yes:
        if not _confirm_proceed("Proceed? [y/N]: "):
            # CR-F3 (MEDIUM): user-abort returns exit code 1 so CI
            # pipelines can distinguish "user aborted the cost gate" from
            # "baseline written successfully (exit 0)" and from
            # "untrusted verdict, FAILED-CALIBRATION written (exit 2)".
            print("Aborted by user; no baseline written.")
            return 1
    elif args.yes and total_cost > _COST_GATE_THRESHOLD_USD:
        _logger.info(
            "cost_gate.bypassed_via_yes_flag estimated_total_usd=%.2f", total_cost
        )

    per_anchor_scores, alpha = await _audit_all_tasks(
        tasks=tasks,
        anchors_by_task=anchors_by_task,
        db_path=db_path,
        primary_model=args.primary_model,
        secondary_model=args.secondary_model,
    )
    verdict = _classify_alpha(alpha)

    output_path = Path(args.output)

    # CR-F1 (HIGH): zero-pairs guard. If every dispatch failed on both
    # evaluators, `per_anchor_scores` is empty and `_compose_baseline`
    # would raise Pydantic ValidationError (BaselineSnapshot.per_anchor_scores
    # has min_length=1) BEFORE the FAILED-CALIBRATION write path runs —
    # defeating the AC-6 contract that the audit always lands on a JSON
    # file we can grep later. Short-circuit here: write a stderr error,
    # do NOT call _compose_baseline, exit 2 (untrusted-shaped failure).
    if not per_anchor_scores:
        print(
            f"VERDICT=untrusted alpha={alpha:.4f} but ZERO anchors were paired "
            f"by both evaluators. Likely cause: every dispatch on at least "
            f"one evaluator returned None (rate-limit / provider-error / "
            f"schema-rejection chain). No baseline written. "
            f"Canonical path NOT updated and FAILED-CALIBRATION sibling NOT "
            f"written (no valid payload to persist). Re-run after triaging "
            f"the dispatch failures (check router_calls audit for the "
            f"affected run_id).",
            file=sys.stderr,
        )
        return 2

    anchors_version_file = anchors_dir / "VERSION"
    if not anchors_version_file.is_file():
        raise SystemExit(
            f"anchors VERSION file not found at {anchors_version_file}; "
            "Story 9-5 AC-11 requires this to be tracked"
        )
    anchors_version = anchors_version_file.read_text(encoding="utf-8").strip()

    snapshot = _compose_baseline(
        primary_evaluator=args.primary_model,
        secondary_evaluator=args.secondary_model,
        anchors_version=anchors_version,
        per_anchor_scores=per_anchor_scores,
        alpha=alpha,
        verdict=verdict,
    )

    if verdict == "untrusted":
        fail_path = _failed_calibration_path(output_path)
        _write_baseline_atomic(_serialize_baseline(snapshot), fail_path)
        print(
            f"VERDICT=untrusted alpha={alpha:.4f} (threshold < {_ALPHA_UNCERTAIN_THRESHOLD:.2f}). "
            f"Wrote FAILED-CALIBRATION payload to {fail_path}. Canonical baseline NOT updated.",
            file=sys.stderr,
        )
        print("Per-anchor disagreements (sorted by abs(delta) desc):", file=sys.stderr)
        _print_disagreement_table(per_anchor_scores, file="stderr")
        return 2

    _write_baseline_atomic(_serialize_baseline(snapshot), output_path)
    print(
        f"VERDICT={verdict} alpha={alpha:.4f} n_anchors_paired={len(per_anchor_scores)}. "
        f"Wrote baseline to {output_path}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "main",
]
