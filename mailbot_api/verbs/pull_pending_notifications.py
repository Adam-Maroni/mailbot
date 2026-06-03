"""``pull_pending_notifications`` verb — Story 6-3 AC-2.

Hermes-side pull surface. Atomically claims up to ``limit`` urgent-tier
pending rows from ``notifications_outbox``, transitioning each to
``delivering`` + bumping ``attempt_count``. Returns the claimed rows so
Hermes can post each to Discord and ack via ``ack_notification``.

Concurrency: SQLite's BEGIN IMMEDIATE provides row-level isolation; the
``WHERE delivery_status='pending'`` predicate on the UPDATE makes the
claim race-safe. Two concurrent pulls cannot return the same row.

Limit cap: hard-coded at 25 — Discord's per-channel posting cadence makes
larger batches unnecessary and risks rate-limit. Hermes typically asks for
~10 per poll.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, model_validator

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)

_MAX_LIMIT = 25


class PendingNotification(BaseModel):
    """One urgent-tier notification claimed for delivery."""

    id: int
    tier: str
    category: str
    message: str
    enqueued_at: str
    attempt_count: int


class PullPendingNotificationsOut(BaseModel):
    """Result of pull_pending_notifications. ``count`` is surfaced explicitly
    so wire-decoded JSON callers don't have to inspect the list length, but
    a ``model_validator`` enforces ``count == len(notifications)`` so the
    two cannot drift (CR HIGH-1 fix: previously an independent field with
    default 0; constructing with only ``notifications=`` left ``count=0``)."""

    notifications: list[PendingNotification] = Field(default_factory=list)
    count: int = Field(default=0)

    @model_validator(mode="after")
    def _sync_count_to_list(self) -> "PullPendingNotificationsOut":
        # The validator runs on EVERY model construction including JSON
        # decode round-trips, so an incoming payload with a wrong `count`
        # is corrected to match the list — no desync possible.
        self.count = len(self.notifications)
        return self


async def pull_pending_notifications(
    limit: int = 10, *, db_path: str
) -> PullPendingNotificationsOut:
    """Atomically claim up to ``limit`` pending urgent-tier rows.

    ``limit`` is clamped to ``[1, 25]`` — the upper bound prevents
    rate-limit pressure on Discord; the lower bound prevents accidental
    zero-pull on bad input.
    """
    capped_limit = max(1, min(limit, _MAX_LIMIT))

    candidate_rows = await connection.fetchall(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_PULL_PENDING_URGENT,
        (capped_limit,),
    )

    claimed: list[PendingNotification] = []
    now_iso = utc_z_now()
    # Claim each row individually with the atomic predicate. A row that
    # races with another puller (already claimed) returns rowcount=0 and
    # is skipped. Pre-bumped attempt_count is read AFTER the claim.
    for row in candidate_rows:
        row_id = int(row[0])
        rowcount = await connection.execute_write(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_CLAIM_ONE_FOR_DELIVERY,
            (now_iso, row_id),
        )
        if rowcount == 0:
            # Lost the race — another Hermes pull claimed it first. Skip.
            continue
        # Re-fetch the post-claim attempt_count for the returned shape.
        post_row = await connection.fetchone(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_FETCH_BY_ID,
            (row_id,),
        )
        if post_row is None:
            continue
        claimed.append(
            PendingNotification(
                id=int(post_row[0]),
                tier=str(post_row[1]),
                category=str(post_row[2]),
                message=str(post_row[3]),
                enqueued_at=str(post_row[4]),
                attempt_count=int(post_row[6]),
            )
        )

    logger.info(
        "notifications pulled",
        extra={
            "event": "notification.pulled",
            "requested_limit": limit,
            "capped_limit": capped_limit,
            "returned_count": len(claimed),
        },
    )

    return PullPendingNotificationsOut(
        notifications=claimed, count=len(claimed)
    )


__all__ = [
    "PendingNotification",
    "PullPendingNotificationsOut",
    "pull_pending_notifications",
]
