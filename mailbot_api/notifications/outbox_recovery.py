"""Outbox recovery loop — Story 6-3 Task 6.

Re-claims rows stuck in ``delivery_status='delivering'`` for > 60 seconds.
Hermes crash mid-post, Discord rate-limit hang, or network blip can leave a
row in the intermediate ``delivering`` state forever; the recovery loop
flips them back to ``pending`` so the next Hermes poll re-pulls them.

CR MED-2 fix (was incorrect math): the 60-second threshold is chosen to
sit well above a normal Hermes pull→Discord-post→ack round-trip (typically
under ~15 seconds in the healthy path). 60 seconds tolerates transient
Discord API slowness, a Hermes restart, or a brief network blip without
triggering a spurious re-pull, but is short enough that a hard Hermes
crash doesn't leave urgent messages silently stuck for long. Story 6-4
may tune this after observing real cadence on the VPS.

Per AR-D13-1 (Story 6-6 cron split), this loop is LLM-free critical infra
and lives on the mailbot-api internal scheduler — not on Hermes's cron.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from mailbot_api.db import connection, queries

logger = logging.getLogger(__name__)

# Cutoff: a row stuck in 'delivering' for this long is considered abandoned.
# Documented in Story 6-3 Dev Notes as not-yet-configurable; Story 6-4 may
# tune after observation.
STUCK_DELIVERY_THRESHOLD_SECONDS = 60.0


async def reclaim_stuck_deliveries(db_path: str) -> int:
    """Re-claim rows stuck in ``delivering`` state for too long.

    Returns the number of rows reclaimed (for observability). Emits a
    structured log line when the count is positive.
    """
    cutoff_dt = datetime.now(timezone.utc) - timedelta(
        seconds=STUCK_DELIVERY_THRESHOLD_SECONDS
    )
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    rowcount = await connection.execute_write(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_RECOVERY_RECLAIM,
        (cutoff_iso,),
    )

    if rowcount > 0:
        logger.warning(
            "notification recovery reclaimed stuck rows",
            extra={
                "event": "notification.recovery.reclaimed",
                "count": rowcount,
                "cutoff_seconds": STUCK_DELIVERY_THRESHOLD_SECONDS,
            },
        )

    return rowcount


__all__ = ["reclaim_stuck_deliveries", "STUCK_DELIVERY_THRESHOLD_SECONDS"]
