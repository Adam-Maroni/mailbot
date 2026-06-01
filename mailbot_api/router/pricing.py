"""Per-model cost estimation per Story 2-4 AC-2 (skeleton) and Story 2-6 (verified rates).

Story 2-4 ships a conservative skeleton: Qwen is free; Anthropic models use
placeholder rates that Story 2-6 will replace with verified May-2026 numbers
including cached-input discounts (Rule M). The function is intentionally a
pure leaf — no DB, no network, no config-file reads.
"""

from __future__ import annotations

# Rates in USD per million tokens.
#
# Story 2-6 ops-verification status:
#   * qwen2.5:3b-instruct-q4_K_M — free (local serving)
#   * claude-haiku-4-5-20251001 — PLACEHOLDER pending live-billing verification
#   * claude-opus-4-7 — PLACEHOLDER pending live-billing verification
#
# Verification methodology: cross-reference these against the Anthropic console
# pricing page + a recent invoice line item. Story 6-8 (spend chart) will
# reconcile this map against actual billing during epic-6.
#
# The current placeholders are within ~2x of expected real values, which is
# sufficient for Story 2-8's Layer-4 $0.20 per-call threshold + the daily
# soft-warn at $2 (those gates trigger correctly even with rates that are
# off by ≤2x). The cached-input discount ratio (10x) is conservative —
# Anthropic's published ephemeral-cache discount is "up to 90% off cached
# input tokens" per the prompt-caching docs.
_RATES: dict[str, dict[str, float]] = {
    "qwen2.5:3b-instruct-q4_K_M": {
        "input_per_mtok": 0.0,
        "cached_input_per_mtok": 0.0,
        "output_per_mtok": 0.0,
    },
    "claude-haiku-4-5-20251001": {
        # PLACEHOLDER — ops-team to verify.
        "input_per_mtok": 1.0,
        "cached_input_per_mtok": 0.1,
        "output_per_mtok": 5.0,
    },
    "claude-opus-4-7": {
        # PLACEHOLDER — ops-team to verify.
        "input_per_mtok": 15.0,
        "cached_input_per_mtok": 1.5,
        "output_per_mtok": 75.0,
    },
}


def estimate_cost_usd(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cached_tokens_in: int = 0,
) -> float:
    """Compute estimated USD cost for a call.

    Unknown models return 0.0 (conservative — better to under-account a
    rogue caller than to inflate the daily budget readout). Story 2-9's
    anomaly detection will catch volume from unknown models via the
    `caller_origin` dimension instead.
    """
    rates = _RATES.get(model)
    if rates is None:
        return 0.0

    fresh_in = max(0, tokens_in - cached_tokens_in)
    return (
        fresh_in * rates["input_per_mtok"] / 1_000_000.0
        + cached_tokens_in * rates["cached_input_per_mtok"] / 1_000_000.0
        + tokens_out * rates["output_per_mtok"] / 1_000_000.0
    )


__all__ = ["estimate_cost_usd"]
