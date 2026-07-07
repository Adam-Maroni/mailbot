"""Budget administration verbs per Story 2-8.

Currently exposes ``reset_degraded_mode`` — the verb-side handler for
``/budget reset`` (Epic 5 wires the slash-command UI to call this).
"""

from __future__ import annotations

from pydantic import BaseModel

from mailbot_api.router.budget import get_guard


class BudgetResetOut(BaseModel):
    """Result of a /budget reset invocation."""

    ok: bool
    previously_active: bool
    message: str


async def reset_degraded_mode(*, db_path: str, reason: str = "manual_reset") -> BudgetResetOut:
    """Flip the degraded_mode_state row to inactive and clear the in-memory flag.

    Returns a Pydantic shape suitable for the verb-result surface so Hermes
    can render it as chat output without parsing free-form strings.
    """
    guard = get_guard()
    # Story 10.5.1 scope: `previously_active` is a report field, not a
    # dispatch-governing read — keeps the in-memory `is_degraded()`. The
    # exit_degraded_mode call below is the authoritative DB write; the
    # cross-process degraded READ that matters is on the router dispatch gates.
    previously = guard.is_degraded()
    await guard.exit_degraded_mode(db_path, reason=reason)
    return BudgetResetOut(
        ok=True,
        previously_active=previously,
        message=(
            "degraded mode exited" if previously else "degraded mode was not active"
        ),
    )


__all__ = ["BudgetResetOut", "reset_degraded_mode"]
