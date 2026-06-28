"""Story 9.9 — pure-leaf statistical helpers for the report renderer.

Three responsibilities live here:

* :func:`wilson_score_interval` — Wilson 1927 score interval for binomial
  proportions at 95% confidence. Pure-numpy implementation; scipy is not
  installed in this repo and Story 9-7's Krippendorff α set the
  pure-numpy precedent.
* :func:`bootstrap_ci` — deterministic bootstrap CI for non-proportion
  samples (latency_ms, cost_usd). Uses ``numpy.random.default_rng(seed=42)``
  by default for reproducible CI bounds across re-runs of the renderer.
* :func:`compute_pareto_frontier` (+ :class:`ParetoPoint`) — strict-weak
  dominance Pareto frontier on (cost, quality) pairs. A point ``a``
  dominates ``b`` iff ``a.cost <= b.cost AND a.quality >= b.quality AND
  (a.cost < b.cost OR a.quality > b.quality)``. Ties on both axes
  retain both points.

Boundary discipline: this module imports only the standard library and
numpy. It has no I/O, no database access, no environment-variable reads.
Tested via ``tests/unit/benchmark/test_report_stats.py`` and
``tests/unit/benchmark/test_report_pareto.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 95% confidence z-score (two-sided normal). Centralized so the Wilson and
# bootstrap helpers agree on the confidence level by default.
_Z_95: float = 1.959963984540054


def _z_for_confidence(confidence: float) -> float:
    """Two-sided normal z-score for the given confidence level.

    Only the 95% case is exact (the centralized ``_Z_95`` constant); other
    levels go through ``numpy``'s inverse-normal via the polynomial-tail
    Beasley-Springer-Moro approximation. The renderer's call sites only
    use 95% so a slow path here is irrelevant.
    """
    if confidence == 0.95:
        return _Z_95
    alpha = 1.0 - confidence
    # Two-sided: tail probability per side is alpha/2.
    # numpy doesn't expose an inverse-CDF directly; use the well-known
    # rational approximation via Beasley-Springer-Moro through scipy if
    # available, otherwise fall back to a coarse value (callers don't use
    # non-95% in practice).
    # Defensive: clamp to a reasonable range.
    if alpha <= 0.0 or alpha >= 1.0:
        raise ValueError(
            f"confidence must be strictly between 0 and 1; got {confidence}"
        )
    # Hand-rolled inverse-normal via the standard rational approximation
    # (Beasley-Springer-Moro coefficients). Accurate to ~1e-7 over the
    # working range. Adapted from Acklam (2003) public-domain version.
    p = 1.0 - alpha / 2.0
    # Constants
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = float(np.sqrt(-2.0 * np.log(p)))
        z = (
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        z = (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    else:
        q = float(np.sqrt(-2.0 * np.log(1.0 - p)))
        z = -(
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )
    return float(z)


def wilson_score_interval(
    successes: int, trials: int, z: float = _Z_95
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion at the given z-level.

    The formula::

        (p̂ + z²/2n ± z·sqrt((p̂(1-p̂) + z²/4n)/n)) / (1 + z²/n)

    Numerically stable for small ``trials`` and extreme ``p̂`` (0 or 1) —
    unlike the normal-approximation interval which produces bounds outside
    [0, 1]. Default z=1.96 → 95% confidence.

    Edge cases:
      * ``trials == 0`` returns ``(0.0, 1.0)`` (maximally uncertain — no data).
      * ``successes == 0`` returns ``(0.0, upper)``.
      * ``successes == trials`` returns ``(lower, 1.0)``.

    Raises ``ValueError`` if ``successes < 0``, ``trials < 0``, or
    ``successes > trials``.
    """
    if trials < 0:
        raise ValueError(f"trials must be ≥ 0; got {trials}")
    if successes < 0 or successes > trials:
        raise ValueError(
            f"successes must satisfy 0 ≤ successes ≤ trials; "
            f"got successes={successes}, trials={trials}"
        )
    if trials == 0:
        # No data → maximum uncertainty.
        return (0.0, 1.0)
    n = float(trials)
    p_hat = successes / n
    z_sq = z * z
    denominator = 1.0 + z_sq / n
    center = (p_hat + z_sq / (2.0 * n)) / denominator
    radius = (
        z
        * float(np.sqrt((p_hat * (1.0 - p_hat) + z_sq / (4.0 * n)) / n))
        / denominator
    )
    # Clamp + snap-to-zero for FP-noise residuals when p̂ = 0 or 1.
    # Without the snap, p̂ = 0 produces lower ≈ 3.5e-18 (not exactly 0)
    # because the radius and the half-width term don't cancel cleanly.
    lower = max(0.0, center - radius)
    upper = min(1.0, center + radius)
    if successes == 0:
        lower = 0.0
    if successes == trials:
        upper = 1.0
    return (lower, upper)


def bootstrap_ci(
    samples: list[float],
    n_resamples: int = 1000,
    confidence: float = 0.95,
    random_seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap CI on the sample mean.

    Resamples ``len(samples)`` observations with replacement ``n_resamples``
    times, computes the mean of each resample, then returns the
    ``(alpha/2, 1 - alpha/2)`` percentiles of the resample-mean distribution.

    Uses ``numpy.random.default_rng(seed=random_seed)`` so bounds are
    reproducible across re-runs. Default ``random_seed=42``.

    Edge cases:
      * Empty samples → ``ValueError``.
      * Single sample → degenerate ``(x, x)`` CI (every resample is x).
      * All-identical samples → degenerate ``(x, x)`` CI.

    Raises ``ValueError`` on empty samples, non-positive ``n_resamples``,
    or ``confidence`` outside ``(0, 1)``.
    """
    if not samples:
        raise ValueError("bootstrap_ci received empty samples list")
    if n_resamples <= 0:
        raise ValueError(f"n_resamples must be > 0; got {n_resamples}")
    if not (0.0 < confidence < 1.0):
        raise ValueError(
            f"confidence must be strictly between 0 and 1; got {confidence}"
        )
    rng = np.random.default_rng(seed=random_seed)
    arr = np.asarray(samples, dtype=np.float64)
    # Single-value optimization: every resample-mean is the value itself.
    if arr.size == 1 or float(arr.min()) == float(arr.max()):
        v = float(arr[0])
        return (v, v)
    indices = rng.integers(low=0, high=arr.size, size=(n_resamples, arr.size))
    resample_means = arr[indices].mean(axis=1)
    alpha = 1.0 - confidence
    lower_pct = 100.0 * (alpha / 2.0)
    upper_pct = 100.0 * (1.0 - alpha / 2.0)
    lower = float(np.percentile(resample_means, lower_pct))
    upper = float(np.percentile(resample_means, upper_pct))
    return (lower, upper)


@dataclass(frozen=True)
class ParetoPoint:
    """A single point on the cost-quality plane for Pareto-frontier analysis.

    ``cost_per_100_calls`` is the running per-call cost normalized to
    100 calls (so the unit is dollars; for $0.002/call this is $0.20).
    ``quality`` is the task's headline metric (accuracy / f1 / subjective
    overall) — higher is better. ``sample_count`` is propagated so the
    n≥15 sample-size gate can filter ineligible points before the frontier
    computation.
    """

    model: str
    prompt_version: str
    cost_per_100_calls: float
    quality: float
    sample_count: int


def _dominates(a: ParetoPoint, b: ParetoPoint) -> bool:
    """``a`` strictly dominates ``b`` iff a is no-worse on both axes AND
    strictly better on at least one. Ties on both axes → no domination.
    """
    no_worse = a.cost_per_100_calls <= b.cost_per_100_calls and a.quality >= b.quality
    strictly_better = (
        a.cost_per_100_calls < b.cost_per_100_calls or a.quality > b.quality
    )
    return no_worse and strictly_better


def compute_pareto_frontier(points: list[ParetoPoint]) -> list[ParetoPoint]:
    """Return the strict-weak Pareto frontier of the input points.

    A point is on the frontier iff NO other point strictly dominates it.
    Tied points (same cost AND same quality) are all retained.

    Empty input → empty frontier. Single point → single-element frontier.
    Sort order of output: ascending cost_per_100_calls, then ascending
    quality (deterministic for golden-value tests).
    """
    frontier: list[ParetoPoint] = []
    for candidate in points:
        dominated = any(
            _dominates(other, candidate)
            for other in points
            if other is not candidate
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(
        frontier, key=lambda p: (p.cost_per_100_calls, p.quality, p.model)
    )


__all__ = [
    "ParetoPoint",
    "bootstrap_ci",
    "compute_pareto_frontier",
    "wilson_score_interval",
]
