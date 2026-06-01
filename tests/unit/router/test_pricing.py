"""Unit tests for mailbot_api/router/pricing.py (Story 2-4 AC-2 skeleton)."""

from __future__ import annotations

import pytest

from mailbot_api.router.pricing import estimate_cost_usd


def test_qwen_is_free() -> None:
    assert estimate_cost_usd("qwen2.5:3b-instruct-q4_K_M", 1000, 500) == 0.0


def test_unknown_model_returns_zero() -> None:
    """Per Story 2-4 pricing.py: unknown models return 0.0; Story 2-9's
    anomaly detection catches rogue callers via caller_origin instead."""
    assert estimate_cost_usd("totally-unknown-model", 1_000_000, 500_000) == 0.0


def test_haiku_input_output_costs_nonzero() -> None:
    cost = estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost > 0


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


@pytest.mark.parametrize("tokens_in", [0, 1, 1000, 1_000_000])
def test_estimate_cost_nonnegative(tokens_in: int) -> None:
    assert estimate_cost_usd("claude-opus-4-7", tokens_in, tokens_in) >= 0
