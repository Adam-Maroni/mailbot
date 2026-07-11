"""Story 10.5.5 (AC-3, B8) — unit tests for build_answer_footer + pricing_is_fresh."""

from __future__ import annotations

from typing import Any

import pytest

from mailbot_api.observability.answer_footer import build_answer_footer
from mailbot_api.router import pricing

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


def test_paid_fresh_exact_format_string() -> None:
    footer = build_answer_footer(
        model_used=_OPUS,
        tokens_in=1200,
        tokens_out=340,
        cost_usd=0.0145,
        month_spend_usd=26.31,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert footer == (
        "🤖 opus (Anthropic API) · this reply: $0.0145 "
        "(1200 in / 340 out) · July: $26.31 of $30.00"
    )


def test_paid_fresh_haiku_short_name() -> None:
    footer = build_answer_footer(
        model_used=_HAIKU,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.0035,
        month_spend_usd=1.0,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert footer.startswith(
        "🤖 haiku (Anthropic API) · this reply: $0.0035 (100 in / 50 out) · July:"
    )


def test_free_local_qwen_no_dollar() -> None:
    footer = build_answer_footer(
        model_used=_QWEN,
        tokens_in=500,
        tokens_out=120,
        cost_usd=0.0,
        month_spend_usd=26.31,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert footer == "🤖 qwen (local, free)"
    assert "$" not in footer
    assert "Anthropic API" not in footer  # free/local never carries the paid marker


def test_paid_marks_anthropic_api_free_does_not() -> None:
    """Story 10.5.5 walk (Adam Q2 2026-07-11): a user must be able to tell a
    billed Anthropic API turn (haiku/opus) from a free/local one (qwen) at a
    glance. Paid footers carry '(Anthropic API)'; the free line does not."""
    paid = build_answer_footer(
        model_used=_HAIKU,
        tokens_in=327,
        tokens_out=22,
        cost_usd=0.0030,
        month_spend_usd=26.51,
        month_cap_usd=30.0,
        month_label="July",
    )
    free = build_answer_footer(
        model_used=_QWEN,
        tokens_in=327,
        tokens_out=22,
        cost_usd=0.0,
        month_spend_usd=26.51,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert "(Anthropic API)" in paid
    assert "(Anthropic API)" not in free
    assert "(local, free)" in free


def test_paid_qwen_nonzero_cost_is_not_free_line() -> None:
    """Defensive: if a local model somehow carries a nonzero cost, it is NOT
    rendered as the free line (the free branch requires cost==0)."""
    footer = build_answer_footer(
        model_used=_QWEN,
        tokens_in=500,
        tokens_out=120,
        cost_usd=0.01,
        month_spend_usd=26.31,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert footer != "🤖 qwen (local, free)"


def test_stale_pricing_degrades_to_tokens_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-3 code invariant: when the freshness marker is placeholder, the footer
    withholds the dollar figure entirely."""
    monkeypatch.setattr(pricing, "PRICING_PLACEHOLDER", True)
    footer = build_answer_footer(
        model_used=_OPUS,
        tokens_in=1200,
        tokens_out=340,
        cost_usd=0.0145,
        month_spend_usd=26.31,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert "$" not in footer
    assert "1200 in / 340 out" in footer
    assert "unverified" in footer


def test_missing_verified_on_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pricing, "PRICING_VERIFIED_ON", "")
    footer = build_answer_footer(
        model_used=_OPUS,
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.001,
        month_spend_usd=1.0,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert "$" not in footer
    assert "unverified" in footer


# ---- pricing_is_fresh predicate ----


def test_pricing_is_fresh_default_true() -> None:
    assert pricing.pricing_is_fresh() is True


def test_pricing_is_fresh_false_when_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pricing, "PRICING_PLACEHOLDER", True)
    assert pricing.pricing_is_fresh() is False


def test_pricing_is_fresh_false_when_verified_on_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pricing, "PRICING_VERIFIED_ON", "")
    assert pricing.pricing_is_fresh() is False


def test_pricing_is_fresh_false_when_verified_on_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pricing, "PRICING_VERIFIED_ON", "not-a-date")
    assert pricing.pricing_is_fresh() is False


def test_unknown_model_falls_back_to_raw_id() -> None:
    footer: Any = build_answer_footer(
        model_used="some-future-model",
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.001,
        month_spend_usd=1.0,
        month_cap_usd=30.0,
        month_label="July",
    )
    assert "some-future-model" in footer
