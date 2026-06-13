"""4-layer budget guard per Story 2-8 and FR-6.

Layer 1 — per-call ``max_tokens_out`` cap (policy-defined; enforced by passing
  to adapter.call). Adapter rejects/truncates server-side.
Layer 2 — $2 daily soft warn. Single-fire per UTC day; subsequent calls
  proceed normally.
Layer 3 — $30 monthly hard cap entering DEGRADED MODE. Demotion chain
  opus→haiku→qwen; force_model="claude-opus-4-7" blocked without
  confirmation token (token mint flow Epic 5). Persisted via
  ``degraded_mode_state`` SQLite singleton row.
Layer 4 — $0.20 per-call refusal threshold (before dispatch, on estimated
  cost). Override via ``force=True`` kwarg on ``ask_router``; the override
  is logged with ``model_chosen_reason=ModelChosenReason.OVERRIDE_API`` per
  Story 9.2's vocabulary consolidation (force=True and force=False both
  collapse to OVERRIDE_API; the audit row no longer distinguishes them).

Architecture: BudgetGuard is a module-level singleton with in-memory cache of
(today_spend, this_month_spend) rolled forward from ``router_calls`` on
startup. Each successful call adds to the cache atomically with the
``router_calls`` row write. Counts are UTC-day / UTC-month bounded.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

_log = logging.getLogger(__name__)


# Budget thresholds — architecture constants from FR-6.
DAILY_SOFT_WARN_USD = 2.0
MONTHLY_HARD_CAP_USD = 30.0
PER_CALL_REFUSAL_THRESHOLD_USD = 0.20


# Demotion chain (inverse of escalation): top-of-chain → bottom-of-chain.
_DEMOTION_CHAIN_NEXT: dict[str, str] = {
    "claude-opus-4-7": "claude-haiku-4-5-20251001",
    "claude-haiku-4-5-20251001": "qwen2.5:3b-instruct-q4_K_M",
}


def demote_model(current_model: str) -> str:
    """Return the demoted model id, or `current_model` unchanged if it's
    already at the bottom of the chain (Qwen) or off-chain (unknown)."""
    return _DEMOTION_CHAIN_NEXT.get(current_model, current_model)


def _utc_day_start_iso(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT00:00:00Z")


def _utc_month_start_iso(now: datetime | None = None) -> str:
    n = now or datetime.now(timezone.utc)
    return n.strftime("%Y-%m-01T00:00:00Z")


class BudgetGuard:
    """Process-wide singleton tracking daily + monthly spend.

    Layer 2 soft-warn flag persists for the calendar day (UTC). Layer 3
    degraded-mode flag is durable via SQLite. The in-memory spend counters
    are seeded from ``router_calls`` on initialization.
    """

    def __init__(self) -> None:
        self.today_spend_usd: float = 0.0
        self.this_month_spend_usd: float = 0.0
        self._soft_warn_fired_for_day: str | None = None  # YYYY-MM-DD when fired
        self._degraded_mode_active: bool = False
        self._lock = asyncio.Lock()

    async def initialize(self, db_path: str) -> None:
        """Roll the in-memory spend counters forward from router_calls and
        read the persisted degraded-mode flag from the singleton row."""
        today_start = _utc_day_start_iso()
        month_start = _utc_month_start_iso()
        today = await connection.fetchone(
            db_path, queries.ROUTER_CALLS_SPEND_SINCE, (today_start,)
        )
        month = await connection.fetchone(
            db_path, queries.ROUTER_CALLS_SPEND_SINCE, (month_start,)
        )
        self.today_spend_usd = float(today[0]) if today else 0.0
        self.this_month_spend_usd = float(month[0]) if month else 0.0

        row = await connection.fetchone(db_path, queries.DEGRADED_MODE_SELECT, ())
        self._degraded_mode_active = bool(row[0]) if row else False

    def is_degraded(self) -> bool:
        return self._degraded_mode_active

    async def add_spend(self, db_path: str, cost_usd: float) -> None:
        """Add a successful call's cost to both counters; trigger Layer 2
        warning + Layer 3 entry on threshold crossings."""
        async with self._lock:
            prev_today = self.today_spend_usd
            prev_month = self.this_month_spend_usd
            self.today_spend_usd += cost_usd
            self.this_month_spend_usd += cost_usd

            # Layer 2 — daily soft warn.
            today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if (
                prev_today < DAILY_SOFT_WARN_USD
                and self.today_spend_usd >= DAILY_SOFT_WARN_USD
                and self._soft_warn_fired_for_day != today_key
            ):
                self._soft_warn_fired_for_day = today_key
                _log.warning(
                    "daily soft-warn breached",
                    extra={
                        "event": "budget.daily.soft_warn",
                        "today_spend_usd": self.today_spend_usd,
                        "monthly_cap_usd": MONTHLY_HARD_CAP_USD,
                    },
                )

            # Layer 3 — monthly hard cap entry.
            if (
                prev_month < MONTHLY_HARD_CAP_USD
                and self.this_month_spend_usd >= MONTHLY_HARD_CAP_USD
                and not self._degraded_mode_active
            ):
                await self._enter_degraded_mode(db_path)

    async def _enter_degraded_mode(self, db_path: str) -> None:
        now_iso = utc_z_now()
        await connection.execute_write(db_path, queries.DEGRADED_MODE_ENTER, (now_iso,))
        self._degraded_mode_active = True
        _log.error(
            "monthly budget breached — entering degraded mode",
            extra={
                "event": "budget.degraded.entered",
                "monthly_spend_usd": self.this_month_spend_usd,
                "cap_usd": MONTHLY_HARD_CAP_USD,
            },
        )

    async def exit_degraded_mode(self, db_path: str, *, reason: str) -> None:
        async with self._lock:
            if not self._degraded_mode_active:
                return
            now_iso = utc_z_now()
            await connection.execute_write(db_path, queries.DEGRADED_MODE_EXIT, (now_iso,))
            self._degraded_mode_active = False
            _log.info(
                "degraded mode exited",
                extra={"event": "budget.degraded.exited", "reason": reason},
            )

    def reset_for_test(self) -> None:
        self.today_spend_usd = 0.0
        self.this_month_spend_usd = 0.0
        self._soft_warn_fired_for_day = None
        self._degraded_mode_active = False


_GUARD = BudgetGuard()


def get_guard() -> BudgetGuard:
    return _GUARD


def _reset_guard_for_test() -> None:
    _GUARD.reset_for_test()


__all__ = [
    "DAILY_SOFT_WARN_USD",
    "MONTHLY_HARD_CAP_USD",
    "PER_CALL_REFUSAL_THRESHOLD_USD",
    "BudgetGuard",
    "demote_model",
    "get_guard",
]
