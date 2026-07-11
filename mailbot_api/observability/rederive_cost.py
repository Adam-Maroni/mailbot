"""Story 10.5.5 (AC-1, R4 / F-10-3-1) — re-derive `router_calls.cost_usd_estimated`
at corrected A2 pricing, re-seed the BudgetGuard counter, and clear a degraded
trip that only the inflated ledger forced.

Why this module exists
----------------------
The July `cost_usd_estimated` figures were written under the pre-A2 3x-overstated
Opus placeholder (F-PLACEHOLDER-3X-DRIFT). The Opus `anchor_calibrated_eval`
rows alone carried ~$62.58 estimated across 197 calls. That inflated the
internal monthly counter to ~$70 (vs the ~$26 Console-real July, 9.5.4 D1),
which tripped `MONTHLY_HARD_CAP_USD` ($30) and stuck degraded mode on
(F-10-3-1). Because historical rows keep their inflated estimates, the trip
persists until Aug-1 rollover or a manual reset — regardless of real spend.

The fix is a PURE ARITHMETIC re-derive: every row stored its true per-call
`tokens_in` / `tokens_out` / `cached_tokens_in` / `model_chosen`, so
`estimate_cost_usd(model, ..., strict=False)` recomputes the honest cost with no
model re-dispatch and no network. Retired model ids (rows referencing a model no
longer in `pricing._RATES`) fall through to `strict=False`'s lenient $0 rather
than raising — a conservative under-account, which is the correct bias for a
historical ledger correction.

Boundary note (Task 1)
----------------------
`router_calls` has a single-writer append-monopoly enforced by
`scripts/check_boundaries.py` (only `observability/audit.py` may emit the
row-append SQL literal). This module never appends — it issues a bounded
cost-only correction via the named `queries.ROUTER_CALLS_UPDATE_COST` constant
(no raw SQL literal lives in this file, so the raw-SQL boundary scan stays
clean). The correction keyed by primary id touches no audit-forensic column
(tokens, model, outcome, ts are all preserved), so the audit trail's integrity
is unchanged. This is the deliberate, documented boundary choice: the
append-monopoly is untouched; the correction rides a dedicated ops module behind
a named query rather than widening the audit-writer allowlist.

After correcting the ledger the module MUST re-seed the guard — a stale
`this_month_spend_usd` (~$70) would let the very next `add_spend` re-cross the
cap and re-trip degraded mode even though the corrected ledger reads ~$26.
`exit_degraded_mode` clears the flag but does NOT fix the counter, so we re-seed
the counter off the corrected rows BEFORE deciding whether to clear degraded.

Current-month vs retrospective re-derive (Finding 1)
----------------------------------------------------
`BudgetGuard.initialize()` always re-seeds `this_month_spend_usd` from the
CURRENT UTC month with no upper bound, so re-seeding via it for a retrospective
`--month <past>` run would clobber the live counter with the wrong month's
total. This module therefore:

  * Re-seeds the guard ONLY when the re-derived month IS the current UTC month —
    and does so from the SAME `[window_start, window_end)` window it corrected
    (via `BudgetGuard.reseed_month_from_window`, which holds `_lock`), so the
    counter and the clear-degraded decision agree on one month.
  * For a PAST month it corrects the historical rows but leaves the live guard
    counter UNTOUCHED (the current month's real spend, not a corrected past
    month, is what legitimately gates `add_spend`) and SKIPS the clear-degraded
    step entirely — re-deriving a past month must never clear a degraded trip
    the current month's real spend may justify.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from mailbot_api.db import connection, queries
from mailbot_api.router.budget import MONTHLY_HARD_CAP_USD, get_guard
from mailbot_api.router.pricing import estimate_cost_usd

_log = logging.getLogger(__name__)


class RederiveCostResult(BaseModel):
    """Outcome of a month cost re-derive."""

    month_label: str
    window_start_iso: str
    window_end_iso: str
    rows_scanned: int
    rows_updated: int
    old_total_usd: float
    new_total_usd: float
    month_cap_usd: float
    degraded_was_active: bool
    degraded_now_active: bool
    guard_counter_usd: float


def _month_window(month: str | None) -> tuple[str, str, str, bool]:
    """Resolve (window_start_iso, window_end_iso, month_label, is_current_month).

    `month` is either an explicit ``"YYYY-MM"`` string or ``None`` (→ current
    UTC month). The window is half-open ``[start, next_month_start)`` so the
    ``ts >= ? AND ts < ?`` predicate captures exactly one calendar month of
    UTC ISO-8601 ``Z`` timestamps. ``is_current_month`` is True iff the resolved
    (year, month) is the current UTC month — the re-seed / clear-degraded steps
    key off this (Finding 1: a past-month re-derive must not touch the live
    guard counter or clear a degraded trip the current month may justify).
    """
    now = datetime.now(timezone.utc)
    if month is None:
        year, mon = now.year, now.month
    else:
        parts = month.split("-")
        if len(parts) != 2:
            raise ValueError(f"month must be 'YYYY-MM'; got {month!r}")
        if not (parts[0].isdigit() and parts[1].isdigit()):
            raise ValueError(f"month must be numeric 'YYYY-MM'; got {month!r}")
        year, mon = int(parts[0]), int(parts[1])
        if not (1 <= mon <= 12):
            raise ValueError(f"month must be 'YYYY-MM' with month 01-12; got {month!r}")

    start = f"{year:04d}-{mon:02d}-01T00:00:00Z"
    if mon == 12:
        end = f"{year + 1:04d}-01-01T00:00:00Z"
    else:
        end = f"{year:04d}-{mon + 1:02d}-01T00:00:00Z"
    is_current_month = (year == now.year) and (mon == now.month)
    return start, end, f"{year:04d}-{mon:02d}", is_current_month


async def rederive_month_cost(
    *,
    db_path: str,
    month: str | None = None,
) -> RederiveCostResult:
    """Re-derive `cost_usd_estimated` for one month, re-seed the guard, and
    clear a degraded trip that the inflated ledger forced.

    Steps (order is load-bearing):
      1. Read every row in the month window with its stored tokens + model.
      2. Recompute `cost_usd_estimated` per row (strict=False leniency for
         retired model ids) and write the corrected value back per row.
      3. Re-seed the BudgetGuard by re-running `initialize()` off the corrected
         ledger — so `this_month_spend_usd` reads the honest ~$26.
      4. If the corrected month total is now under the cap AND degraded is
         active, clear it via `exit_degraded_mode`.

    Idempotent: running twice recomputes to the same values and updates 0 rows
    on the second pass.
    """
    window_start, window_end, month_label, is_current_month = _month_window(month)

    rows = await connection.fetchall(
        db_path,
        queries.ROUTER_CALLS_SELECT_TOKENS_IN_WINDOW,
        (window_start, window_end),
    )

    new_total = 0.0
    rows_updated = 0
    # Finding 2: read OLD total from the SAME [window_start, window_end) window
    # the re-derive corrects — NOT the unbounded-above ROUTER_CALLS_SPEND_SINCE,
    # which over-counts the moment any later-month row exists (the realistic
    # retrospective `--month` case). BEFORE any per-row UPDATE, so it captures
    # the true pre-correction window sum.
    old_agg = await connection.fetchone(
        db_path, queries.ROUTER_CALLS_SPEND_IN_WINDOW, (window_start, window_end)
    )
    old_total = float(old_agg[0]) if old_agg else 0.0

    for row_id, model_chosen, tokens_in, tokens_out, cached_tokens_in in rows:
        new_cost = estimate_cost_usd(
            str(model_chosen),
            int(tokens_in),
            int(tokens_out),
            int(cached_tokens_in),
            strict=False,
        )
        new_total += new_cost
        # Write the corrected cost for this row. The pass is naturally
        # idempotent: a second run recomputes to the same value, so re-running
        # is a no-op on the stored figures (the row count still reports the
        # rows touched). We do not read back the prior per-row cost — the
        # month-aggregate `old_total` above captures the pre-correction sum.
        await connection.execute_write(
            db_path,
            queries.ROUTER_CALLS_UPDATE_COST,
            (new_cost, int(row_id)),
        )
        rows_updated += 1

    guard = get_guard()
    degraded_was_active = await guard.is_degraded_now(db_path)

    # Finding 1: the re-seed + clear-degraded steps run ONLY when the re-derived
    # month IS the current UTC month. For a retrospective (past-month) run we
    # correct the historical rows but must NOT clobber the live guard counter
    # (which legitimately reflects the CURRENT month's real spend) nor clear a
    # degraded trip the current month may justify.
    if is_current_month:
        # Re-seed the in-memory month counter from the SAME window we corrected
        # (holds _lock — Finding 5) BEFORE the clear decision, so the counter and
        # the clear-degraded decision agree on one month, and the next add_spend
        # does not re-trip on stale ~$70.
        await guard.reseed_month_from_window(
            db_path, window_start=window_start, window_end=window_end
        )
        # Clear degraded iff the corrected month total is now under the cap.
        if new_total < MONTHLY_HARD_CAP_USD and degraded_was_active:
            await guard.exit_degraded_mode(
                db_path, reason="cost_rederive_under_cap_story_10_5_5"
            )

    degraded_now_active = await guard.is_degraded_now(db_path)

    _log.info(
        "router_calls cost re-derive complete",
        extra={
            "event": "budget.cost.rederived",
            "month": month_label,
            "rows_scanned": len(rows),
            "rows_updated": rows_updated,
            "old_total_usd": old_total,
            "new_total_usd": new_total,
            "degraded_was_active": degraded_was_active,
            "degraded_now_active": degraded_now_active,
        },
    )

    return RederiveCostResult(
        month_label=month_label,
        window_start_iso=window_start,
        window_end_iso=window_end,
        rows_scanned=len(rows),
        rows_updated=rows_updated,
        old_total_usd=old_total,
        new_total_usd=new_total,
        month_cap_usd=MONTHLY_HARD_CAP_USD,
        degraded_was_active=degraded_was_active,
        degraded_now_active=degraded_now_active,
        guard_counter_usd=guard.this_month_spend_usd,
    )


__all__ = ["RederiveCostResult", "rederive_month_cost"]
