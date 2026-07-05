"""Per-model cost estimation per Story 2-4 AC-2 (skeleton) and Story 2-6 (verified rates).

Rates verified 2026-07-05 (Epic 9.5 retro action A2, closing F-PLACEHOLDER-3X-DRIFT):
cross-referenced against the Anthropic pricing docs and reconciled against real
Console billing observed during the Epic 9.5 real-spend walks (placeholder-billed
figures ran ~2.7x over Console truth — driver was the 3x-overstated Opus rows).
The function is intentionally a pure leaf — no DB, no network, no config-file reads.
"""

from __future__ import annotations

# Rates in USD per million tokens.
#
# Verification status (2026-07-05):
#   * qwen2.5:3b-instruct-q4_K_M — free (local serving)
#   * claude-haiku-4-5-20251001 — VERIFIED $1.00 in / $5.00 out (the former
#     placeholder happened to match the published rate)
#   * claude-opus-4-7 — VERIFIED $5.00 in / $25.00 out (former placeholder was
#     $15/$75 — exactly 3x overstated; the F-PLACEHOLDER-3X-DRIFT root cause)
#
# Cached-input rows use Anthropic's published ephemeral-cache read rate of
# ~0.1x the base input price. Cache WRITES bill at 1.25x base input (5-min TTL);
# this map models reads only, so estimates for cache-writing calls are slightly
# conservative-low by the 0.25x write premium on the cached span.
_RATES: dict[str, dict[str, float]] = {
    "qwen2.5:3b-instruct-q4_K_M": {
        "input_per_mtok": 0.0,
        "cached_input_per_mtok": 0.0,
        "output_per_mtok": 0.0,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_mtok": 1.0,
        "cached_input_per_mtok": 0.1,
        "output_per_mtok": 5.0,
    },
    "claude-opus-4-7": {
        "input_per_mtok": 5.0,
        "cached_input_per_mtok": 0.5,
        "output_per_mtok": 25.0,
    },
}


class UnknownModelPricingError(LookupError):
    """Raised when a cost estimate is requested for a model with no pricing row.

    Epic 9.5 retro action A2 (F-UNKNOWN-MODEL-COST-GATE): an unknown model
    silently estimating $0.00 let a real-spend pre-flight gate print "$0.00"
    and approve a 322-call Opus dispatch (Story 9.5.3, ~$3.43 overshoot).
    Unknown models must fail the estimate loudly unless the caller explicitly
    opts into the lenient under-account behavior.
    """


def estimate_cost_usd(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cached_tokens_in: int = 0,
    *,
    strict: bool = True,
) -> float:
    """Compute estimated USD cost for a call.

    Unknown models raise :class:`UnknownModelPricingError` by default — a
    spend gate estimating $0.00 for a model it cannot price is false-safe
    (F-UNKNOWN-MODEL-COST-GATE). Pass ``strict=False`` to restore the legacy
    return-0.0 behavior; that mode is reserved for post-call audit accounting
    and pre-dispatch refusal estimates inside the Router hot path, where a
    raise would fail calls that policy/registry already vetted and where test
    fixtures register fake model names (Story 2-9's anomaly detection catches
    unknown-model volume via ``caller_origin`` there instead).
    """
    rates = _RATES.get(model)
    if rates is None:
        if strict:
            raise UnknownModelPricingError(
                f"no pricing row for model {model!r}; refusing to estimate "
                "(an unknown model estimating $0.00 is false-safe — register "
                "the model in mailbot_api/router/pricing.py or pass "
                "strict=False for lenient under-accounting)"
            )
        return 0.0

    fresh_in = max(0, tokens_in - cached_tokens_in)
    return (
        fresh_in * rates["input_per_mtok"] / 1_000_000.0
        + cached_tokens_in * rates["cached_input_per_mtok"] / 1_000_000.0
        + tokens_out * rates["output_per_mtok"] / 1_000_000.0
    )


__all__ = ["UnknownModelPricingError", "estimate_cost_usd"]
