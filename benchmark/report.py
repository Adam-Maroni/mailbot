"""Story 9.9: full report renderer (upgrades Story 9-8 stub).

This module produces the per-task benchmark report at
``<output_dir>/<run_id>.md`` for a single ``run_id``. Section ordering:

1. ``# Benchmark Report``
2. ``## Run metadata``
3. ``## Per-task scores`` — tables of (model, prompt_version, metric)
   rows with Wilson-CI confidence intervals on classification metrics
   and bootstrap CIs on latency/cost. Cells with ``sample_count < 15``
   render ``INSUFFICIENT DATA — n=<count>, gate=15``.
4. ``## Pareto Frontier`` — strict-weak dominance frontier per task with
   cost-vs-quality plotting. Excludes points with sample_count < 15.
5. ``## DEMOTE/PROMOTE Suggestions`` — verdict per (task, current_model)
   with copy-pasteable ``policy.yaml`` snippet on actionable verdicts.
6. ``## Scorer calibration`` — present ONLY when ``cross_evaluator_alpha``
   rows exist; surfaces α + per-anchor breakdown + verdict.
7. ``## Cross-cohort drift comparison`` — present ONLY when multiple
   ``cohort_key`` values exist in the run; warning header + per-cohort
   headline metrics; informational only (verdicts above never cross cohorts).

CR-F3 contract from Story 9-8 preserved verbatim: ``run_id`` MUST match
``^[A-Za-z0-9_-]+$`` before path construction; ``ValueError`` otherwise.

CLI entry: ``python -m benchmark.report --run-id <id> --db-path <path>
--output-dir <path> [--thresholds-override '{"task": float}']``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from benchmark.schemas import BenchmarkRunRow, BenchmarkScoreRow
from benchmark.scorer_db import read_run_runs, read_run_scores
from benchmark.stats import (
    ParetoPoint,
    bootstrap_ci,
    compute_pareto_frontier,
    wilson_score_interval,
)
from benchmark.verdict import VerdictLiteral, compute_verdict

_SAMPLE_SIZE_GATE: int = 15

_INSUFFICIENT_DATA_FMT: str = "INSUFFICIENT DATA — n={count}, gate={gate}"

# CR-F3 (sonnet-4-6 review, Story 9-8): allow only filesystem-safe
# characters in run_id before composing the output path. Production
# run_ids are UUID4 (from benchmark.runner) and test run_ids are
# alphanumeric+hyphen — both safe. Preserved verbatim for Story 9.9.
_RUN_ID_SAFE_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]+$")

# Headline metric per task. Used by the Pareto + DEMOTE/PROMOTE sections
# to pick which row's ``metric_value`` is the "quality" axis.
_HEADLINE_METRIC: dict[str, str] = {
    "coarse_class": "accuracy",
    "sensitivity_class": "accuracy",
    "fine_class": "accuracy",
    "summary_short": "subjective_overall",
    "action_extraction": "f1_extraction_action_type",
    "draft_reply": "subjective_overall",
    "reference_resolution": "accuracy",
}

# Wilson-CI eligible metrics. CR-F6 (deferred):
# Two classes of members here, with DIFFERENT statistical interpretations:
#   * Proper proportions (Wilson CI is rigorous):
#       accuracy, precision_macro, recall_macro, ok_rate
#   * Derived metrics (Wilson CI is approximate — see Story 9-9 deferred items):
#       f1_macro, f1_extraction_action_type, f1_extraction_summary_similarity,
#       f1_extraction_deadline_match
# For the derived members, `successes = round(value * n)` synthesizes a
# trial-count without strict frequentist meaning; the CI bounds are
# directional indicators of sample-size-driven uncertainty rather than
# strict frequentist intervals. Future story may replace with bootstrap CIs.
_WILSON_METRICS: frozenset[str] = frozenset(
    {
        "accuracy",
        "precision_macro",
        "recall_macro",
        "f1_macro",
        "f1_extraction_action_type",
        "f1_extraction_summary_similarity",
        "f1_extraction_deadline_match",
        "ok_rate",
    }
)


def _insufficient_data(count: int) -> str:
    return _INSUFFICIENT_DATA_FMT.format(count=count, gate=_SAMPLE_SIZE_GATE)


def _format_metric_value_with_ci(row: BenchmarkScoreRow) -> str:
    """Render a metric value with Wilson CI when eligible, otherwise plain."""
    if row.sample_count < _SAMPLE_SIZE_GATE:
        return _insufficient_data(row.sample_count)
    if row.metric_name in _WILSON_METRICS and 0.0 <= row.metric_value <= 1.0:
        successes = int(round(row.metric_value * row.sample_count))
        lower, upper = wilson_score_interval(
            successes=successes, trials=row.sample_count
        )
        return (
            f"{row.metric_value:.4f} "
            f"[95% CI: {lower:.4f}–{upper:.4f}]"
        )
    return f"{row.metric_value:.4f}"


def _group_by_task(
    rows: list[BenchmarkScoreRow],
) -> dict[str, list[BenchmarkScoreRow]]:
    by_task: dict[str, list[BenchmarkScoreRow]] = defaultdict(list)
    for row in rows:
        by_task[row.task_type].append(row)
    return by_task


def _group_runs_by_model_task(
    runs: list[BenchmarkRunRow],
) -> dict[tuple[str, str], list[BenchmarkRunRow]]:
    grouped: dict[tuple[str, str], list[BenchmarkRunRow]] = defaultdict(list)
    for run in runs:
        grouped[(run.task_type, run.model)].append(run)
    return grouped


def _latency_cost_stats(
    runs: list[BenchmarkRunRow],
) -> tuple[tuple[float, float, float, float] | None, int]:
    """Return ((mean_latency, mean_cost, latency_ci_upper, cost_ci_upper), excluded_count).

    Filters to outcome == "ok" rows only. The excluded count surfaces in
    the per-task table footnote. Returns ``None`` for the stats tuple if
    no ok rows remain (caller renders an absence note).
    """
    ok_rows = [r for r in runs if r.outcome == "ok"]
    excluded = len(runs) - len(ok_rows)
    if not ok_rows:
        return (None, excluded)
    latencies = [float(r.latency_ms) for r in ok_rows]
    costs = [float(r.cost_usd) for r in ok_rows]
    mean_latency = sum(latencies) / len(latencies)
    mean_cost = sum(costs) / len(costs)
    _, latency_upper = bootstrap_ci(latencies)
    _, cost_upper = bootstrap_ci(costs)
    return ((mean_latency, mean_cost, latency_upper, cost_upper), excluded)


def _render_task_table(
    task: str, rows: list[BenchmarkScoreRow], runs_by_task_model: dict[tuple[str, str], list[BenchmarkRunRow]]
) -> str:
    """Render one per-task table. Cells with sample_count < gate render
    INSUFFICIENT DATA. Wilson CIs on proportion metrics; bootstrap CIs on
    latency/cost summary row appended below.
    """
    lines: list[str] = []
    lines.append(f"### Task: `{task}`")
    lines.append("")
    lines.append("| model | prompt_version | metric | value | n | outcome |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in sorted(rows, key=lambda r: (r.model, r.prompt_version, r.metric_name)):
        value_cell = _format_metric_value_with_ci(row)
        lines.append(
            f"| `{row.model}` "
            f"| `{row.prompt_version}` "
            f"| `{row.metric_name}` "
            f"| {value_cell} "
            f"| {row.sample_count} "
            f"| {row.outcome} |"
        )
    lines.append("")
    # Latency / cost summary per (task, model) — CR-F2: render bootstrap CI bounds.
    models_for_task = sorted(
        {row.model for row in rows if row.evaluator_role == "primary"}
    )
    if models_for_task:
        lines.append(f"**Latency / cost summary for `{task}`:**")
        lines.append("")
        lines.append(
            "| model | n_ok | mean_latency_ms [95% CI upper] | "
            "mean_cost_usd [95% CI upper] | excluded (outcome≠ok) |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for model in models_for_task:
            runs_for_pair = runs_by_task_model.get((task, model), [])
            stats, excluded = _latency_cost_stats(runs_for_pair)
            if stats is None:
                lines.append(
                    f"| `{model}` | 0 | N/A | N/A | {excluded} |"
                )
            else:
                mean_latency, mean_cost, lat_upper, cost_upper = stats
                ok_n = len(runs_for_pair) - excluded
                lines.append(
                    f"| `{model}` | {ok_n} "
                    f"| {mean_latency:.0f} [{lat_upper:.0f}] "
                    f"| {mean_cost:.6f} [{cost_upper:.6f}] "
                    f"| {excluded} |"
                )
        lines.append("")
    return "\n".join(lines)


def _extract_pareto_points_for_task(
    task: str,
    rows: list[BenchmarkScoreRow],
    runs_by_task_model: dict[tuple[str, str], list[BenchmarkRunRow]],
) -> list[ParetoPoint]:
    """Build ParetoPoint list from (model, prompt_version) rows for one task."""
    headline = _HEADLINE_METRIC.get(task)
    if headline is None:
        return []
    points: list[ParetoPoint] = []
    headline_rows = [
        r
        for r in rows
        if r.metric_name == headline and r.evaluator_role == "primary"
    ]
    for row in headline_rows:
        runs_for_pair = runs_by_task_model.get((task, row.model), [])
        ok_runs = [r for r in runs_for_pair if r.outcome == "ok"]
        if ok_runs:
            mean_cost_per_call = sum(r.cost_usd for r in ok_runs) / len(ok_runs)
        else:
            mean_cost_per_call = 0.0
        points.append(
            ParetoPoint(
                model=row.model,
                prompt_version=row.prompt_version,
                cost_per_100_calls=mean_cost_per_call * 100.0,
                quality=row.metric_value,
                sample_count=row.sample_count,
            )
        )
    return points


def _render_pareto_section(
    rows: list[BenchmarkScoreRow],
    runs_by_task_model: dict[tuple[str, str], list[BenchmarkRunRow]],
) -> str:
    """Render the Pareto Frontier section.

    Per (task, cohort_key) subsection — AC-7 mandates the frontier ONLY
    combines rows within the same cohort_key. CR-F1: enforced here by
    nesting an inner cohort_key loop inside the per-task loop.

    Drops sample_count < 15 points before frontier computation. Renders
    INSUFFICIENT POINTS when fewer than 2 eligible (model, prompt_version)
    combinations remain. CR-F3: shows both frontier and dominated points
    with on_frontier ∈ {yes, no} — iterating `eligible` (not `frontier`)
    so dominated rows are visible.
    """
    lines: list[str] = []
    lines.append("## Pareto Frontier")
    lines.append("")
    by_task = _group_by_task(rows)
    if not by_task:
        lines.append("_No scored rows for this run; no frontier to compute._")
        lines.append("")
        return "\n".join(lines)
    for task in sorted(by_task.keys()):
        task_rows = by_task[task]
        cohort_keys = sorted({r.cohort_key for r in task_rows})
        lines.append(f"### Task: `{task}`")
        lines.append("")
        for ck in cohort_keys:
            ck_rows = [r for r in task_rows if r.cohort_key == ck]
            points = _extract_pareto_points_for_task(
                task, ck_rows, runs_by_task_model
            )
            # Filter to sample-size-gate-eligible points BEFORE frontier computation.
            eligible = [p for p in points if p.sample_count >= _SAMPLE_SIZE_GATE]
            if len(cohort_keys) > 1:
                lines.append(f"#### cohort_key: `{ck}`")
                lines.append("")
            distinct_combos = len({(p.model, p.prompt_version) for p in eligible})
            if distinct_combos < 2:
                lines.append(
                    f"INSUFFICIENT POINTS — need ≥2 distinct (model, prompt_version) "
                    f"combinations to compute a frontier, found {distinct_combos}"
                )
                lines.append("")
                continue
            frontier = compute_pareto_frontier(eligible)
            frontier_keys = {(p.model, p.prompt_version) for p in frontier}
            lines.append(
                "| model | prompt_version | cost_per_100_calls | quality | on_frontier |"
            )
            lines.append("| --- | --- | --- | --- | --- |")
            for p in sorted(
                eligible, key=lambda x: (x.cost_per_100_calls, x.quality, x.model)
            ):
                on_frontier = (
                    "yes" if (p.model, p.prompt_version) in frontier_keys else "no"
                )
                lines.append(
                    f"| `{p.model}` "
                    f"| `{p.prompt_version}` "
                    f"| ${p.cost_per_100_calls:.4f} "
                    f"| {p.quality:.4f} "
                    f"| {on_frontier} |"
                )
            lines.append("")
    return "\n".join(lines)


def _policy_yaml_snippet(task: str, target_model: str, run_id: str, evidence: str) -> str:
    """Return a copy-pasteable ``policy.yaml`` snippet for the verdict.

    Mirrors Story 7.4 AC text — yaml-block with notes referencing the
    benchmark run_id + one-line stat.
    """
    return (
        f"```yaml\n"
        f"# Apply to router/policy.yaml under tasks.{task}:\n"
        f"{task}:\n"
        f"  default_model: {target_model}\n"
        f"  notes: benchmark run_id {run_id}, evidence: {evidence}\n"
        f"```"
    )


def _render_demote_promote_section(
    rows: list[BenchmarkScoreRow],
    runs_by_task_model: dict[tuple[str, str], list[BenchmarkRunRow]],
    run_id: str,
    thresholds: dict[str, float] | None,
) -> str:
    """Render the DEMOTE/PROMOTE Suggestions section.

    CR-F1: verdicts ONLY combine rows within the same cohort_key
    (AC-7 mandate). Per-task subsection nests an inner cohort_key loop;
    each (task, cohort_key) computes its own frontier + verdict set.
    """
    lines: list[str] = []
    lines.append("## DEMOTE/PROMOTE Suggestions")
    lines.append("")
    by_task = _group_by_task(rows)
    if not by_task:
        lines.append("_No scored rows for this run; no verdicts to emit._")
        lines.append("")
        return "\n".join(lines)
    # CR-F4: distinguish "no override" (None) from "explicit empty override" ({}).
    if thresholds is None:
        threshold_map: dict[str, float] = {}
    else:
        threshold_map = thresholds
    for task in sorted(by_task.keys()):
        task_rows = by_task[task]
        cohort_keys = sorted({r.cohort_key for r in task_rows})
        lines.append(f"### Task: `{task}`")
        lines.append("")
        for ck in cohort_keys:
            ck_rows = [r for r in task_rows if r.cohort_key == ck]
            points = _extract_pareto_points_for_task(
                task, ck_rows, runs_by_task_model
            )
            eligible = [p for p in points if p.sample_count >= _SAMPLE_SIZE_GATE]
            if len(cohort_keys) > 1:
                lines.append(f"#### cohort_key: `{ck}`")
                lines.append("")
            if not points:
                lines.append("_No headline metric rows for this task._")
                lines.append("")
                continue
            frontier = compute_pareto_frontier(eligible)
            for current in sorted(
                points, key=lambda p: (p.cost_per_100_calls, p.model)
            ):
                verdict: VerdictLiteral = compute_verdict(
                    task=task,
                    current_model=current.model,
                    frontier=frontier,
                    current_metrics=current,
                    per_task_thresholds=thresholds,
                )
                if verdict == "INSUFFICIENT_DATA":
                    lines.append(
                        f"- `{current.model}` (n={current.sample_count}): "
                        f"{_insufficient_data(current.sample_count)}"
                    )
                    continue
                lines.append(
                    f"- `{current.model}` (quality={current.quality:.4f}, "
                    f"cost_per_100={current.cost_per_100_calls:.4f}): "
                    f"**{verdict}**"
                )
                if verdict == "DEMOTE-valid":
                    threshold = threshold_map.get(task, 0.0)
                    candidates = [
                        p
                        for p in frontier
                        if p.cost_per_100_calls < current.cost_per_100_calls
                        and p.quality >= threshold
                    ]
                    if candidates:
                        cheapest = min(
                            candidates, key=lambda p: p.cost_per_100_calls
                        )
                        evidence = (
                            f"{cheapest.model} quality "
                            f"{cheapest.quality:.4f} ≥ threshold; cheaper "
                            f"than current {current.model}"
                        )
                        lines.append("")
                        lines.append(
                            _policy_yaml_snippet(
                                task, cheapest.model, run_id, evidence
                            )
                        )
                elif verdict == "PROMOTE-needed":
                    threshold = threshold_map.get(task, 0.0)
                    meeting = [p for p in frontier if p.quality >= threshold]
                    if meeting:
                        target = min(meeting, key=lambda p: p.cost_per_100_calls)
                        evidence = (
                            f"current quality {current.quality:.4f} < "
                            f"threshold {threshold}; promote to "
                            f"{target.model} (quality {target.quality:.4f})"
                        )
                        lines.append("")
                        lines.append(
                            _policy_yaml_snippet(
                                task, target.model, run_id, evidence
                            )
                        )
            lines.append("")
    return "\n".join(lines)


def _render_scorer_calibration_section(rows: list[BenchmarkScoreRow]) -> str | None:
    """Return the Scorer calibration section markdown, or ``None`` to OMIT.

    Triggered by the presence of ``cross_evaluator_alpha`` rows from the
    Story 9-7 secondary-evaluator pathway.
    """
    alpha_rows = [
        r
        for r in rows
        if r.metric_name == "cross_evaluator_alpha"
        and r.evaluator_role == "secondary"
    ]
    if not alpha_rows:
        return None
    lines: list[str] = []
    lines.append("## Scorer calibration")
    lines.append("")
    for row in alpha_rows:
        alpha = row.metric_value
        if alpha >= 0.8:
            verdict = "scorer trusted"
        elif alpha >= 0.6:
            verdict = "scorer uncertain — α<0.8 boundary"
        else:
            verdict = "scorer untrusted — blocks routing decisions until reconciled"
        lines.append(f"### Task: `{row.task_type}` — `{row.model}`")
        lines.append("")
        lines.append(f"- **Krippendorff α:** {alpha:.4f}")
        lines.append(f"- **Verdict:** {verdict}")
        lines.append("")
        # Per-anchor breakdown table from extra_json.
        per_anchor: list[dict[str, object]] = []
        if row.extra_json:
            try:
                payload = json.loads(row.extra_json)
                if isinstance(payload, dict):
                    raw_anchors = payload.get("per_anchor", [])
                    if isinstance(raw_anchors, list):
                        per_anchor = [
                            a for a in raw_anchors if isinstance(a, dict)
                        ]
            except (json.JSONDecodeError, TypeError):
                per_anchor = []
        if per_anchor:
            lines.append("| anchor_id | primary_score | secondary_score | delta |")
            lines.append("| --- | --- | --- | --- |")
            for anchor in per_anchor:
                anchor_id = anchor.get("anchor_id", "?")
                primary_score = anchor.get("primary_score", "?")
                secondary_score = anchor.get("secondary_score", "?")
                delta = anchor.get("delta", "?")
                lines.append(
                    f"| {anchor_id} "
                    f"| {primary_score} "
                    f"| {secondary_score} "
                    f"| {delta} |"
                )
            lines.append("")
    return "\n".join(lines)


def _render_cross_cohort_drift_section(
    rows: list[BenchmarkScoreRow],
) -> str | None:
    """Return the Cross-cohort drift comparison section, or ``None`` to OMIT.

    Only fires when ``rows`` spans 2+ distinct ``cohort_key`` values.
    """
    cohort_keys = sorted({row.cohort_key for row in rows})
    if len(cohort_keys) < 2:
        return None
    lines: list[str] = []
    lines.append("## Cross-cohort drift comparison")
    lines.append("")
    # CR-F5: post CR-F1 fix, verdicts above ARE cohort-clean (Pareto and
    # DEMOTE/PROMOTE sections render one sub-subsection per cohort_key).
    # The warning now correctly states the contract.
    lines.append(
        "> WARNING: Rows below span MULTIPLE cohort_keys — prompt/scorer/anchors/policy "
        "evolved between rows. Each verdict in the DEMOTE/PROMOTE section above is "
        "scoped to a single cohort_key; this section is informational only and lets "
        "you spot drift across cohort boundaries."
    )
    lines.append("")
    # Per cohort, headline metric per (task, model).
    for ck in cohort_keys:
        ck_rows = [r for r in rows if r.cohort_key == ck]
        lines.append(f"### cohort_key: `{ck}`")
        lines.append("")
        lines.append("| task | model | metric | value | n |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in sorted(
            ck_rows,
            key=lambda r: (r.task_type, r.model, r.metric_name),
        ):
            headline = _HEADLINE_METRIC.get(row.task_type)
            if headline and row.metric_name != headline:
                continue
            lines.append(
                f"| `{row.task_type}` "
                f"| `{row.model}` "
                f"| `{row.metric_name}` "
                f"| {row.metric_value:.4f} "
                f"| {row.sample_count} |"
            )
        lines.append("")
    return "\n".join(lines)


def _render_report_body(
    run_id: str,
    rows: list[BenchmarkScoreRow],
    runs: list[BenchmarkRunRow],
    thresholds: dict[str, float] | None,
) -> str:
    """Compose the full Markdown body."""
    lines: list[str] = []
    lines.append(f"# Benchmark Report — `{run_id}`")
    lines.append("")
    lines.append(
        "_Generated by Story 9-9 full renderer (Wilson CIs + bootstrap CIs + "
        "Pareto frontier + DEMOTE/PROMOTE verdicts + sample-size gate + "
        "cohort_key primary slice)._"
    )
    lines.append("")

    total_rows = len(rows)
    cohort_keys = sorted({row.cohort_key for row in rows})

    lines.append("## Run metadata")
    lines.append("")
    lines.append(f"- **run_id:** `{run_id}`")
    lines.append(f"- **total scored rows:** {total_rows}")
    lines.append(f"- **total dispatch rows:** {len(runs)}")
    lines.append(f"- **distinct cohort_keys:** {len(cohort_keys)}")
    for ck in cohort_keys:
        lines.append(f"  - `{ck}`")
    lines.append("")

    runs_by_task_model = _group_runs_by_model_task(runs)

    lines.append("## Per-task scores")
    lines.append("")
    if not rows:
        lines.append("_No scored rows found for this run._")
        lines.append("")
    else:
        by_task = _group_by_task(rows)
        for task in sorted(by_task.keys()):
            lines.append(
                _render_task_table(task, by_task[task], runs_by_task_model)
            )

    lines.append(_render_pareto_section(rows, runs_by_task_model))
    lines.append(
        _render_demote_promote_section(
            rows, runs_by_task_model, run_id, thresholds
        )
    )

    calibration = _render_scorer_calibration_section(rows)
    if calibration is not None:
        lines.append(calibration)

    drift = _render_cross_cohort_drift_section(rows)
    if drift is not None:
        lines.append(drift)

    return "\n".join(lines)


def render_report(
    db_path: str,
    run_id: str,
    output_dir: Path,
    thresholds_override: dict[str, float] | None = None,
) -> Path:
    """Render the benchmark report for ``run_id`` to ``output_dir/<run_id>.md``.

    Returns the path to the written file. Creates ``output_dir`` if absent.

    Raises ``ValueError`` if ``run_id`` contains characters that could
    escape ``output_dir`` (path separators, parent-directory references,
    anything outside ``[A-Za-z0-9_-]``) — CR-F3 guard from Story 9-8.

    ``thresholds_override`` (optional) replaces the per-task thresholds
    used by the DEMOTE/PROMOTE verdict engine. When ``None``, defaults
    from :func:`benchmark.verdict._default_per_task_thresholds` apply.
    """
    if not _RUN_ID_SAFE_PATTERN.match(run_id):
        raise ValueError(
            f"run_id {run_id!r} contains unsafe characters; expected "
            f"pattern {_RUN_ID_SAFE_PATTERN.pattern}"
        )
    rows = asyncio.run(read_run_scores(db_path, run_id))
    runs = asyncio.run(read_run_runs(db_path, run_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    # Resolve thresholds: explicit override OR defaults from verdict module.
    # CR-F4: distinguish None (no override) from {} (explicit empty override).
    from benchmark.verdict import _default_per_task_thresholds
    if thresholds_override is None:
        thresholds = _default_per_task_thresholds()
    else:
        thresholds = thresholds_override
    body = _render_report_body(run_id, rows, runs, thresholds)
    target = output_dir / f"{run_id}.md"
    target.write_text(body, encoding="utf-8")
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark.report",
        description=(
            "Render a benchmark report for a single run_id. "
            "Reads benchmark_runs + benchmark_scores tables from the "
            "given SQLite DB; writes Markdown to <output_dir>/<run_id>.md."
        ),
    )
    parser.add_argument("--run-id", required=True, help="Benchmark run identifier (UUID4 or alphanumeric+hyphen).")
    parser.add_argument("--db-path", required=True, help="Path to the MailBot SQLite database file.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write the report into. Created if absent.",
    )
    parser.add_argument(
        "--thresholds-override",
        default=None,
        help=(
            "Optional JSON dict overriding per-task quality thresholds "
            'for the verdict engine, e.g. \'{"coarse_class": 0.90}\'. '
            "When absent, defaults from benchmark.verdict apply."
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point. Returns process exit code.

    Exit codes:
      * 0 — success; prints the absolute path of the written report.
      * 1 — malformed ``run_id`` (path-traversal guard).
      * 2 — database access failure.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    thresholds_override: dict[str, float] | None = None
    if args.thresholds_override:
        try:
            parsed = json.loads(args.thresholds_override)
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"--thresholds-override is not valid JSON: {exc}\n"
            )
            return 1
        if not isinstance(parsed, dict):
            sys.stderr.write("--thresholds-override must be a JSON object.\n")
            return 1
        thresholds_override = {str(k): float(v) for k, v in parsed.items()}
    # Validate db file exists before SQLite auto-creates it as an empty file.
    if not Path(args.db_path).is_file():
        sys.stderr.write(f"Database file not found: {args.db_path}\n")
        return 2
    try:
        out = render_report(
            db_path=args.db_path,
            run_id=args.run_id,
            output_dir=Path(args.output_dir),
            thresholds_override=thresholds_override,
        )
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"Database file not found: {exc}\n")
        return 2
    print(str(out.resolve()))
    return 0


__all__ = ["main", "render_report"]


if __name__ == "__main__":
    raise SystemExit(main())
