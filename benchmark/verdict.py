"""Story 9.9 Task 3 — DEMOTE/PROMOTE verdict engine for the report renderer.

Closed-set verdict literal:
  * ``"PROMOTE-needed"`` — current model's quality is below the per-task
    threshold; promote to a higher tier.
  * ``"DEMOTE-valid"`` — the next-cheaper tier still meets the per-task
    threshold; safe to demote in v1.
  * ``"DEMOTE-invalid"`` — the current tier is on the Pareto frontier and
    no cheaper alternative meets the threshold; demoting would lose
    quality.
  * ``"hold-steady"`` — current assignment meets the threshold AND is on
    the frontier; correct as-is.
  * ``"INSUFFICIENT_DATA"`` — sample_count gate (n < 15) refuses to emit
    a verdict.

The verdict engine is intentionally a pure leaf: callers pass the
frontier (already computed via :func:`benchmark.stats.compute_pareto_frontier`),
the current model's metrics, and the per-task threshold map. No I/O, no
database access, no environment-variable reads.

Default thresholds (overridable per render_report invocation):

  * ``coarse_class``: 0.85          (matches Epic 7 Story 7.4 threshold)
  * ``sensitivity_class``: 0.90     (higher bar — privacy critical)
  * ``fine_class``: 0.75            (granular taxonomy harder; lower bar)
  * ``summary_short``: 3.5          (out of 5 — subjective scale)
  * ``action_extraction``: 0.70     (F1 score on action types)
  * ``draft_reply``: 3.5            (subjective scale)
  * ``reference_resolution``: 0.90  (FR-4.3 contract)

The thresholds mirror Epic 7 / Story 7.4 documented values in epics.md;
they are not coerced from ``policy.yaml`` at runtime to avoid a hidden
config coupling (CR-focus item d).
"""

from __future__ import annotations

from typing import Literal

from benchmark.stats import ParetoPoint

VerdictLiteral = Literal[
    "PROMOTE-needed",
    "DEMOTE-valid",
    "DEMOTE-invalid",
    "hold-steady",
    "INSUFFICIENT_DATA",
]

_SAMPLE_SIZE_GATE: int = 15


def _default_per_task_thresholds() -> dict[str, float]:
    """Per-task quality thresholds defaulting to Epic 7 Story 7.4 values.

    Why these values: documented in epics.md and reproduced in Story
    9-9's Dev Notes — these are the historical thresholds Adam authored
    before the benchmark walk; the renderer's job is to surface
    DEMOTE/PROMOTE recommendations against them rather than discover
    new thresholds. Overridable per render_report call.
    """
    return {
        "coarse_class": 0.85,
        "sensitivity_class": 0.90,
        "fine_class": 0.75,
        "summary_short": 3.5,
        "action_extraction": 0.70,
        "draft_reply": 3.5,
        "reference_resolution": 0.90,
    }


def compute_verdict(
    task: str,
    current_model: str,
    frontier: list[ParetoPoint],
    current_metrics: ParetoPoint,
    per_task_thresholds: dict[str, float] | None = None,
) -> VerdictLiteral:
    """Return the DEMOTE/PROMOTE verdict for ``(task, current_model)``.

    Logic:
      1. ``sample_count < 15`` → ``INSUFFICIENT_DATA``.
      2. ``current_metrics.quality < threshold`` → ``PROMOTE-needed``.
      3. Otherwise (quality meets threshold), check the frontier:
         * If ``current`` is NOT on the frontier (i.e., dominated by a
           cheaper point that ALSO meets the threshold) → ``DEMOTE-valid``.
         * If there exists a cheaper point that meets the threshold
           (regardless of frontier membership) → ``DEMOTE-valid``.
         * Otherwise → ``DEMOTE-invalid`` if a strictly cheaper point
           exists that fails the threshold (demoting loses quality),
           else ``hold-steady`` (current is best by both axes).

    ``frontier`` is the result of
    :func:`benchmark.stats.compute_pareto_frontier`. ``current_metrics``
    is the row for ``(task, current_model)`` from the per-task table.
    """
    # CR-F4: distinguish None (no override) from {} (explicit empty override).
    if per_task_thresholds is None:
        thresholds = _default_per_task_thresholds()
    else:
        thresholds = per_task_thresholds
    if current_metrics.sample_count < _SAMPLE_SIZE_GATE:
        return "INSUFFICIENT_DATA"
    threshold = thresholds.get(task)
    if threshold is None:
        # No threshold configured for this task → cannot judge → hold steady.
        return "hold-steady"
    if current_metrics.quality < threshold:
        return "PROMOTE-needed"
    # Quality meets threshold. Look for a cheaper alternative that also
    # meets the threshold AND has enough samples to be eligible.
    cheaper_meets_threshold = [
        p
        for p in frontier
        if p.cost_per_100_calls < current_metrics.cost_per_100_calls
        and p.quality >= threshold
        and p.sample_count >= _SAMPLE_SIZE_GATE
        and p.model != current_model
    ]
    if cheaper_meets_threshold:
        return "DEMOTE-valid"
    # No cheaper-and-threshold-meeting alternative on the frontier.
    # If there exists a cheaper-but-below-threshold point, DEMOTE-invalid.
    # Otherwise (current is the cheapest threshold-meeting point), hold-steady.
    cheaper_below_threshold = [
        p
        for p in frontier
        if p.cost_per_100_calls < current_metrics.cost_per_100_calls
        and p.sample_count >= _SAMPLE_SIZE_GATE
        and p.model != current_model
    ]
    if cheaper_below_threshold:
        return "DEMOTE-invalid"
    return "hold-steady"


__all__ = [
    "VerdictLiteral",
    "compute_verdict",
]
