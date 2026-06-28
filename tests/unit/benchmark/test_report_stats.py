"""Story 9.9 Task 1 — pure-leaf statistical helpers for the report renderer.

Covers ``wilson_score_interval`` (Wilson score CI for binomial proportions at
95% confidence, pure-numpy implementation — scipy is not installed in this
repo and Story 9-7's Krippendorff α set the pure-numpy precedent) and
``bootstrap_ci`` (deterministic bootstrap CI for non-proportion samples like
latency/cost).
"""

from __future__ import annotations

import math

import pytest

from benchmark.stats import bootstrap_ci, wilson_score_interval


class TestWilsonScoreInterval:
    """Wilson 1927 score interval — formula:

    (p̂ + z²/2n ± z·sqrt((p̂(1-p̂) + z²/4n)/n)) / (1 + z²/n)

    with z = 1.96 for 95% confidence.
    """

    def test_zero_trials_returns_max_uncertainty(self) -> None:
        # Edge case: no data → CI is the full [0, 1] interval (maximally uncertain).
        lower, upper = wilson_score_interval(successes=0, trials=0)
        assert lower == 0.0
        assert upper == 1.0

    def test_zero_successes_has_lower_at_zero(self) -> None:
        # When p̂ = 0, the lower bound MUST clamp to 0.0 (not negative).
        lower, upper = wilson_score_interval(successes=0, trials=100)
        assert lower == 0.0
        assert 0.0 < upper < 1.0
        # Wilson upper for 0/100 at 95% confidence ≈ 0.0369.
        assert math.isclose(upper, 0.0369, abs_tol=0.001)

    def test_all_successes_has_upper_at_one(self) -> None:
        # When p̂ = 1, the upper bound MUST clamp to 1.0 (not >1).
        lower, upper = wilson_score_interval(successes=100, trials=100)
        assert upper == 1.0
        assert 0.0 < lower < 1.0
        # Wilson lower for 100/100 at 95% confidence ≈ 0.9631.
        assert math.isclose(lower, 0.9631, abs_tol=0.001)

    def test_wilson_known_value_85_of_100(self) -> None:
        """Golden value: successes=85, trials=100 should produce Wilson CI ≈ (0.7674, 0.9072)."""
        lower, upper = wilson_score_interval(successes=85, trials=100)
        # Verified against R's binom.test() and Wikipedia's Wilson score interval table.
        assert math.isclose(lower, 0.7674, abs_tol=0.001)
        assert math.isclose(upper, 0.9072, abs_tol=0.001)

    def test_wilson_known_value_5_of_10(self) -> None:
        """Small-n case: successes=5, trials=10 should produce Wilson CI ≈ (0.2366, 0.7634)."""
        lower, upper = wilson_score_interval(successes=5, trials=10)
        # Symmetric around 0.5 by construction (z² + 4·p(1-p)·n in numerator
        # symmetric in p, n fixed) — small-n width is wide as expected.
        assert math.isclose(lower, 0.2366, abs_tol=0.001)
        assert math.isclose(upper, 0.7634, abs_tol=0.001)

    def test_wilson_symmetry_around_one_half(self) -> None:
        """Property test: Wilson CI for (k/n) and ((n-k)/n) are mirror images around 0.5."""
        lower_a, upper_a = wilson_score_interval(successes=30, trials=100)
        lower_b, upper_b = wilson_score_interval(successes=70, trials=100)
        # CI for 30/100 mirrored around 0.5 should equal CI for 70/100.
        assert math.isclose(lower_a, 1.0 - upper_b, abs_tol=1e-9)
        assert math.isclose(upper_a, 1.0 - lower_b, abs_tol=1e-9)

    def test_wilson_rejects_negative_successes(self) -> None:
        with pytest.raises(ValueError, match="successes"):
            wilson_score_interval(successes=-1, trials=10)

    def test_wilson_rejects_successes_greater_than_trials(self) -> None:
        with pytest.raises(ValueError, match="successes"):
            wilson_score_interval(successes=11, trials=10)

    def test_wilson_rejects_negative_trials(self) -> None:
        with pytest.raises(ValueError, match="trials"):
            wilson_score_interval(successes=0, trials=-1)

    def test_wilson_bounds_always_within_unit_interval(self) -> None:
        """Property test: for ALL (k, n) with 0 ≤ k ≤ n, lower ≥ 0 AND upper ≤ 1."""
        for n in (1, 5, 10, 50, 100, 1000):
            for k in (0, 1, n // 2, n - 1, n):
                lower, upper = wilson_score_interval(successes=k, trials=n)
                assert 0.0 <= lower <= upper <= 1.0


class TestBootstrapCI:
    """Bootstrap CI with fixed random_seed=42 for golden-value reproducibility."""

    def test_empty_samples_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            bootstrap_ci([])

    def test_single_sample_degenerate_ci(self) -> None:
        # A single observation → bootstrap resamples are all that value → CI degenerate.
        lower, upper = bootstrap_ci([42.0])
        assert lower == 42.0
        assert upper == 42.0

    def test_two_identical_samples_degenerate_ci(self) -> None:
        lower, upper = bootstrap_ci([100.0, 100.0])
        assert lower == 100.0
        assert upper == 100.0

    def test_bootstrap_with_fixed_seed_is_deterministic(self) -> None:
        samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        lower_a, upper_a = bootstrap_ci(samples, random_seed=42)
        lower_b, upper_b = bootstrap_ci(samples, random_seed=42)
        assert lower_a == lower_b
        assert upper_a == upper_b

    def test_bootstrap_different_seeds_produce_different_bounds(self) -> None:
        # Sanity: the seed actually matters (otherwise determinism test above is vacuous).
        samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        ci_a = bootstrap_ci(samples, random_seed=42)
        ci_b = bootstrap_ci(samples, random_seed=999)
        assert ci_a != ci_b

    def test_bootstrap_ci_contains_sample_mean(self) -> None:
        """Property test: bootstrap CI of the mean should contain the observed mean."""
        samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        observed_mean = sum(samples) / len(samples)
        lower, upper = bootstrap_ci(samples, random_seed=42)
        assert lower <= observed_mean <= upper

    def test_bootstrap_rejects_negative_resamples(self) -> None:
        with pytest.raises(ValueError, match="n_resamples"):
            bootstrap_ci([1.0, 2.0], n_resamples=0)

    def test_bootstrap_rejects_confidence_outside_unit_interval(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            bootstrap_ci([1.0, 2.0], confidence=1.5)
        with pytest.raises(ValueError, match="confidence"):
            bootstrap_ci([1.0, 2.0], confidence=-0.1)
