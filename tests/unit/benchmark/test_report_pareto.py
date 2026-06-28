"""Story 9.9 Task 2 — Pareto frontier algorithm tests.

Strict-weak dominance: ``a`` dominates ``b`` iff
``a.cost <= b.cost AND a.quality >= b.quality AND
(a.cost < b.cost OR a.quality > b.quality)``. Ties on both axes retain
both points (neither strictly dominates).
"""

from __future__ import annotations

from benchmark.stats import ParetoPoint, compute_pareto_frontier


def _pt(model: str, cost: float, quality: float, n: int = 100) -> ParetoPoint:
    """Test helper — construct a ParetoPoint with reasonable defaults."""
    return ParetoPoint(
        model=model,
        prompt_version="v1",
        cost_per_100_calls=cost,
        quality=quality,
        sample_count=n,
    )


class TestComputeParetoFrontier:
    def test_empty_input_returns_empty_frontier(self) -> None:
        assert compute_pareto_frontier([]) == []

    def test_single_point_is_on_frontier(self) -> None:
        only = _pt("solo", cost=0.50, quality=0.80)
        frontier = compute_pareto_frontier([only])
        assert frontier == [only]

    def test_two_points_one_dominates_drops_dominated(self) -> None:
        # cheap_winner is cheaper AND higher-quality than expensive_loser.
        cheap_winner = _pt("haiku", cost=0.10, quality=0.85)
        expensive_loser = _pt("loser", cost=0.50, quality=0.80)
        frontier = compute_pareto_frontier([cheap_winner, expensive_loser])
        assert frontier == [cheap_winner]

    def test_three_non_dominating_points_all_on_frontier(self) -> None:
        # cheap-low-quality / mid-cost-mid-quality / expensive-high-quality.
        # No point strictly dominates the others.
        cheap_low = _pt("qwen", cost=0.05, quality=0.70)
        mid_mid = _pt("haiku", cost=0.20, quality=0.85)
        expensive_high = _pt("opus", cost=2.50, quality=0.95)
        frontier = compute_pareto_frontier([cheap_low, mid_mid, expensive_high])
        # All 3 on frontier; sorted by ascending cost.
        assert frontier == [cheap_low, mid_mid, expensive_high]

    def test_identical_cost_and_quality_ties_retained(self) -> None:
        # Two points with EXACTLY the same (cost, quality) → neither strictly
        # dominates → both retained.
        twin_a = _pt("a", cost=0.20, quality=0.85)
        twin_b = _pt("b", cost=0.20, quality=0.85)
        frontier = compute_pareto_frontier([twin_a, twin_b])
        assert len(frontier) == 2
        assert twin_a in frontier and twin_b in frontier

    def test_strict_dominance_drops_equal_cost_lower_quality(self) -> None:
        # Same cost, but b has lower quality → b dominated.
        winner = _pt("good", cost=0.20, quality=0.90)
        loser = _pt("bad", cost=0.20, quality=0.80)
        frontier = compute_pareto_frontier([winner, loser])
        assert frontier == [winner]

    def test_strict_dominance_drops_equal_quality_higher_cost(self) -> None:
        # Same quality, but b is more expensive → b dominated.
        winner = _pt("cheaper", cost=0.10, quality=0.85)
        loser = _pt("pricier", cost=0.30, quality=0.85)
        frontier = compute_pareto_frontier([winner, loser])
        assert frontier == [winner]

    def test_frontier_output_sorted_by_ascending_cost(self) -> None:
        # Property: output ordering is deterministic for golden-value tests.
        a = _pt("a", cost=2.50, quality=0.95)
        b = _pt("b", cost=0.05, quality=0.70)
        c = _pt("c", cost=0.20, quality=0.85)
        frontier = compute_pareto_frontier([a, b, c])
        # All non-dominating → all retained, sorted by ascending cost.
        assert [p.model for p in frontier] == ["b", "c", "a"]
