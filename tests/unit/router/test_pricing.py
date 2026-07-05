"""Unit tests for mailbot_api/router/pricing.py.

Story 2-4 AC-2 skeleton, updated 2026-07-05 by Epic 9.5 retro action A2:
verified rates (F-PLACEHOLDER-3X-DRIFT) + strict unknown-model raise
(F-UNKNOWN-MODEL-COST-GATE).
"""

from __future__ import annotations

import pytest

from mailbot_api.router.pricing import UnknownModelPricingError, estimate_cost_usd


def test_qwen_is_free() -> None:
    assert estimate_cost_usd("qwen2.5:3b-instruct-q4_K_M", 1000, 500) == 0.0


def test_unknown_model_raises_by_default() -> None:
    """F-UNKNOWN-MODEL-COST-GATE: a $0 estimate for an unpriceable model is
    false-safe — the strict default must refuse loudly."""
    with pytest.raises(UnknownModelPricingError, match="totally-unknown-model"):
        estimate_cost_usd("totally-unknown-model", 1_000_000, 500_000)


def test_unknown_model_dated_opus_id_raises() -> None:
    """Regression pin on the exact ID that caused the Story 9.5.3 overshoot:
    the dated scorer default estimated $0.00 then dispatched real Opus."""
    with pytest.raises(UnknownModelPricingError):
        estimate_cost_usd("claude-opus-4-7-20251220", 100_000, 50_000)


def test_unknown_model_lenient_optout_returns_zero() -> None:
    """strict=False preserves the legacy under-account behavior for post-call
    audit accounting (Story 2-9 anomaly detection owns rogue-caller volume)."""
    assert (
        estimate_cost_usd("totally-unknown-model", 1_000_000, 500_000, strict=False)
        == 0.0
    )


def test_haiku_verified_rates_exact() -> None:
    """Verified 2026-07-05: Haiku 4.5 is $1.00/MTok in, $5.00/MTok out."""
    cost = estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.0 + 5.0)


def test_opus_verified_rates_exact() -> None:
    """Verified 2026-07-05: Opus 4.7 is $5.00/MTok in, $25.00/MTok out — the
    former $15/$75 placeholder was exactly 3x overstated (F-PLACEHOLDER-3X-DRIFT).
    This pin fails if placeholders ever drift back in."""
    cost = estimate_cost_usd("claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == pytest.approx(5.0 + 25.0)


def test_cached_input_is_one_tenth_of_fresh() -> None:
    """Cache reads bill at ~0.1x the base input rate (Anthropic ephemeral cache)."""
    fresh = estimate_cost_usd("claude-opus-4-7", 1_000_000, 0, cached_tokens_in=0)
    cached = estimate_cost_usd(
        "claude-opus-4-7", 1_000_000, 0, cached_tokens_in=1_000_000
    )
    assert cached == pytest.approx(fresh / 10)
    assert 0 < cached < fresh


def test_haiku_cached_input_discount_applied() -> None:
    """Cached input must cost less than fresh input for the same model."""
    fresh = estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0, cached_tokens_in=0)
    cached = estimate_cost_usd(
        "claude-haiku-4-5-20251001", 1_000_000, 0, cached_tokens_in=1_000_000
    )
    assert cached < fresh
    assert cached > 0


def test_opus_more_expensive_than_haiku() -> None:
    haiku = estimate_cost_usd("claude-haiku-4-5-20251001", 100_000, 50_000)
    opus = estimate_cost_usd("claude-opus-4-7", 100_000, 50_000)
    assert opus > haiku


def test_opus_to_haiku_ratio_is_5x() -> None:
    """Both verified rate cards are 5x apart on input AND output; the estimate
    ratio must therefore be exactly 5x for identical token mixes."""
    haiku = estimate_cost_usd("claude-haiku-4-5-20251001", 100_000, 50_000)
    opus = estimate_cost_usd("claude-opus-4-7", 100_000, 50_000)
    assert opus == pytest.approx(5 * haiku)


@pytest.mark.parametrize("tokens_in", [0, 1, 1000, 1_000_000])
def test_estimate_cost_nonnegative(tokens_in: int) -> None:
    assert estimate_cost_usd("claude-opus-4-7", tokens_in, tokens_in) >= 0
