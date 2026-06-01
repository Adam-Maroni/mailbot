"""Cost-breakdown verb per Story 2-10.

``cost_breakdown(period)`` returns a Pydantic ``CostBreakdownOut`` sourced
entirely from ``router_calls`` via raw SQL (no pandas — AR-BOOT-2 deferral).
The verb is exposed via MCP in Epic 5; for Story 2-10 it ships as a callable
function tested directly.

Per-task / per-model / per-caller-origin breakdowns are aggregated SQL
GROUP BY queries. Cache hit rate is `SUM(cached_tokens_in) / SUM(tokens_in)`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from mailbot_api.db import connection, queries
from mailbot_api.router.budget import MONTHLY_HARD_CAP_USD, get_guard


class CostBreakdownOut(BaseModel):
    """Result of cost_breakdown(period). All monetary values are USD."""

    period: Literal["today", "month"]
    total_usd: float
    cap_usd: float | None
    per_task: dict[str, float]
    per_model: dict[str, float]
    per_caller_origin: dict[str, float]
    cache_hit_rate: float
    call_count: int
    degraded_mode_active: bool


def _period_start_iso(period: Literal["today", "month"]) -> str:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.strftime("%Y-%m-%dT00:00:00Z")
    return now.strftime("%Y-%m-01T00:00:00Z")


async def cost_breakdown(period: Literal["today", "month"], *, db_path: str) -> CostBreakdownOut:
    """Aggregate router_calls over the given period and return the breakdown."""
    since = _period_start_iso(period)

    totals_row = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_TOTALS_SINCE, (since,)
    )
    if totals_row is None:
        call_count = 0
        total_usd = 0.0
        sum_cached = 0
        sum_in = 0
    else:
        call_count = int(totals_row[0])
        total_usd = float(totals_row[1])
        sum_cached = int(totals_row[2])
        sum_in = int(totals_row[3])

    per_task_rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_BY_TASK_SINCE, (since,)
    )
    per_model_rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_BY_MODEL_SINCE, (since,)
    )
    per_origin_rows = await connection.fetchall(
        db_path, queries.ROUTER_CALLS_BY_CALLER_ORIGIN_SINCE, (since,)
    )

    cache_hit_rate = (sum_cached / sum_in) if sum_in > 0 else 0.0
    cap_usd = MONTHLY_HARD_CAP_USD if period == "month" else None

    return CostBreakdownOut(
        period=period,
        total_usd=total_usd,
        cap_usd=cap_usd,
        per_task={row[0]: float(row[1]) for row in per_task_rows},
        per_model={row[0]: float(row[1]) for row in per_model_rows},
        per_caller_origin={row[0]: float(row[1]) for row in per_origin_rows},
        cache_hit_rate=cache_hit_rate,
        call_count=call_count,
        degraded_mode_active=get_guard().is_degraded(),
    )


__all__ = ["CostBreakdownOut", "cost_breakdown"]
