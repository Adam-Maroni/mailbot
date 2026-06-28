"""Story 9.9 Task 3 — DEMOTE/PROMOTE verdict engine tests.

5-value closed set: ``"PROMOTE-needed"`` | ``"DEMOTE-valid"`` |
``"DEMOTE-invalid"`` | ``"hold-steady"`` | ``"INSUFFICIENT_DATA"``.
"""

from __future__ import annotations

from benchmark.stats import ParetoPoint
from benchmark.verdict import compute_verdict


def _pt(model: str, cost: float, quality: float, n: int = 100) -> ParetoPoint:
    return ParetoPoint(
        model=model,
        prompt_version="v1",
        cost_per_100_calls=cost,
        quality=quality,
        sample_count=n,
    )


class TestComputeVerdict:
    def test_insufficient_data_when_sample_count_below_gate(self) -> None:
        current = _pt("haiku", cost=0.20, quality=0.85, n=14)  # below n=15 gate
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[current],
            current_metrics=current,
        )
        assert verdict == "INSUFFICIENT_DATA"

    def test_promote_needed_when_below_threshold(self) -> None:
        # Threshold for coarse_class is 0.85. current quality 0.75 < 0.85.
        current = _pt("qwen", cost=0.05, quality=0.75)
        better = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="qwen",
            frontier=[current, better],
            current_metrics=current,
        )
        assert verdict == "PROMOTE-needed"

    def test_demote_valid_when_cheaper_meets_threshold(self) -> None:
        # current = haiku at $0.20 / 0.92 quality. cheap qwen also meets threshold.
        cheap_alt = _pt("qwen", cost=0.05, quality=0.90)
        current = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[cheap_alt, current],
            current_metrics=current,
        )
        assert verdict == "DEMOTE-valid"

    def test_demote_invalid_when_no_cheaper_meets_threshold(self) -> None:
        # current = haiku at $0.20 / 0.92 quality. qwen is cheaper but below
        # threshold (0.75 < 0.85) → demoting loses quality.
        cheap_loser = _pt("qwen", cost=0.05, quality=0.75)
        current = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[cheap_loser, current],
            current_metrics=current,
        )
        assert verdict == "DEMOTE-invalid"

    def test_hold_steady_when_already_cheapest_threshold_meeting(self) -> None:
        # current is the only point meeting threshold; nothing cheaper exists.
        current = _pt("haiku", cost=0.20, quality=0.92)
        expensive_alt = _pt("opus", cost=2.50, quality=0.95)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[current, expensive_alt],
            current_metrics=current,
        )
        assert verdict == "hold-steady"

    def test_per_task_thresholds_override_used_when_provided(self) -> None:
        # Override coarse_class threshold to 0.95; current quality 0.92 < 0.95
        # → PROMOTE-needed despite default threshold being 0.85.
        current = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[current],
            current_metrics=current,
            per_task_thresholds={"coarse_class": 0.95},
        )
        assert verdict == "PROMOTE-needed"

    def test_unknown_task_returns_hold_steady(self) -> None:
        # Defensive: unknown task with no threshold defined → hold steady.
        current = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="unknown_task_xyz",
            current_model="haiku",
            frontier=[current],
            current_metrics=current,
        )
        assert verdict == "hold-steady"

    def test_cheaper_alternative_with_insufficient_samples_does_not_trigger_demote(
        self,
    ) -> None:
        # Edge case: qwen is cheaper AND meets threshold but only has n=10 — not
        # eligible to gate a DEMOTE decision; renderer should hold-steady.
        cheap_low_n = _pt("qwen", cost=0.05, quality=0.90, n=10)
        current = _pt("haiku", cost=0.20, quality=0.92)
        verdict = compute_verdict(
            task="coarse_class",
            current_model="haiku",
            frontier=[cheap_low_n, current],
            current_metrics=current,
        )
        # Should NOT be DEMOTE-valid because qwen's sample_count is below gate.
        assert verdict == "hold-steady"
