"""Story 10.5.5 (AC-3, B8 retro §8.6) — per-answer cost/model footer builder.

After each chat answer, show (1) which model answered and (2) the exact cost of
that reply + month-to-date usage vs the monthly cap. Adam-decided at the Epic 10
retro:
  * cost from EXACT vendor tokens × A2-verified `pricing.py` prices (NOT the old
    estimator that burned us in 9.5.3 — "$36 estimator vs $13 Console");
  * the "credit"/"balance" line is DROPPED (no balance API exists on this org) →
    show month-to-date + cap headroom instead;
  * a footer on EVERY paid answer; free/local answers show a no-dollar line.

Freshness invariant (the 9.5.3 lesson as code): if `pricing_is_fresh()` is False
(placeholder rate or stale/missing verified-on date) the footer DEGRADES to
tokens-only and prints NO dollar figure — never a number it can't stand behind.

Naming reconciliation: the stored column is `cost_usd_estimated` but now holds
an exact-tokens × verified-price number. This footer reads per-reply cost from
the result object's `cost_usd` (RouterResult / ToolCallResult) and labels it
honestly ("this reply: $X") — it does NOT call an exact number "estimated". The
column keeps its name for migration stability; the footer text is honest.
"""

from __future__ import annotations

from mailbot_api.router.pricing import pricing_is_fresh

# Short, human display names for the footer. Falls back to the raw id if unknown.
_MODEL_SHORT: dict[str, str] = {
    "claude-opus-4-7": "opus",
    "claude-haiku-4-5-20251001": "haiku",
    "qwen2.5:3b-instruct-q4_K_M": "qwen",
    "nomic-embed-text": "nomic-embed",
}

# Local (free) models — a $0 answer from one of these renders the free line.
_LOCAL_MODELS: frozenset[str] = frozenset(
    {"qwen2.5:3b-instruct-q4_K_M", "nomic-embed-text"}
)


def _model_short(model_used: str) -> str:
    return _MODEL_SHORT.get(model_used, model_used or "unknown")


def _is_free_local(model_used: str, cost_usd: float) -> bool:
    """A free/local answer: a known local model AND zero per-reply cost."""
    return model_used in _LOCAL_MODELS and cost_usd == 0.0


def build_answer_footer(
    *,
    model_used: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    month_spend_usd: float,
    month_cap_usd: float,
    month_label: str,
) -> str:
    """Build the one-line per-answer footer.

    Branches:
      * free/local (qwen / local model at $0) →
        ``🤖 qwen (local, free)`` — no dollar noise.
      * paid + pricing FRESH →
        ``🤖 <model-short> · this reply: $X.XXXX (N in / M out) · <month>: $Y of $cap``
      * paid + pricing STALE/PLACEHOLDER →
        ``🤖 <model-short> · N in / M out · <pricing unverified — dollar figure withheld>``
        — NO dollar number (the 9.5.3 code invariant).

    All dollar amounts use the result object's exact `cost_usd` (vendor tokens ×
    verified price) and the honest month-to-date ledger — never the old estimator.
    """
    short = _model_short(model_used)

    if _is_free_local(model_used, cost_usd):
        return f"🤖 {short} (local, free)"

    # Paid branches carry an explicit `(Anthropic API)` marker so a user can
    # never mistake a billed remote call for a free/local one (Story 10.5.5
    # walk, Adam Q2 2026-07-11): "haiku" reads as small/internal, but haiku and
    # opus are Anthropic API models — every such turn is a real billed HTTP
    # request. qwen is the only local/free model (branch above). The marker
    # makes "this cost real money" unambiguous at a glance.
    if not pricing_is_fresh():
        return (
            f"🤖 {short} (Anthropic API) · {tokens_in} in / {tokens_out} out · "
            f"<pricing unverified — dollar figure withheld>"
        )

    return (
        f"🤖 {short} (Anthropic API) · this reply: ${cost_usd:.4f} "
        f"({tokens_in} in / {tokens_out} out) · "
        f"{month_label}: ${month_spend_usd:.2f} of ${month_cap_usd:.2f}"
    )


__all__ = ["build_answer_footer"]
