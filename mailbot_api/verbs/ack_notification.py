"""``ack_notification`` verb — Story 6-3 AC-2.

Hermes posts a pulled notification to Discord and then calls this verb to
finalize the row. Three terminal paths:

  - ``ok`` → ``delivery_status='ok'``, ``delivered_at`` set.
  - ``failed`` AND ``attempt_count < 5`` → ``delivery_status='pending'``,
    ``last_error`` set. Row re-pulls on the next Hermes poll.
  - ``failed`` AND ``attempt_count >= 5`` → ``delivery_status='failed_max_retries'``,
    ``last_error`` set. Row is terminal — manual intervention required.

The atomic predicates (``WHERE delivery_status='delivering'``) prevent ack
races: if a recovery sweep already reverted the row to ``pending`` before
the ack arrives, the ack matches 0 rows and the verb returns ``ok=False``
with ``final_status`` reflecting the actual current state.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from mailbot_api.db import connection, queries
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)


class AckNotificationOut(BaseModel):
    """Result of ack_notification.

    ``ok`` is True iff the ack landed on the row in the expected state.
    ``final_status`` reflects the row's status AFTER the ack (or its
    current status if the ack found no matching row — e.g., another
    recovery sweep flipped it back to ``pending`` first, or a concurrent
    pull re-claimed the row to ``delivering``).

    CR MED-1 fix: ``delivering`` is a distinct in-flight state from
    ``unknown`` (row deleted). Hermes uses the distinction to decide
    whether to retry vs investigate.
    """

    ok: bool
    final_status: Literal[
        "ok", "pending", "failed_max_retries", "delivering", "unknown"
    ]
    notification_id: int
    error: str | None = None


async def ack_notification(
    notification_id: int,
    delivery_status: Literal["ok", "failed"],
    error: str | None = None,
    *,
    db_path: str,
) -> AckNotificationOut:
    """Finalize a delivering row to ``ok`` or back to ``pending``/terminal-fail.

    ``delivery_status`` is the OUTCOME (what Hermes reports), not the
    row's current state. The verb maps it to one of the three terminal
    SQL paths.
    """
    if delivery_status == "ok":
        rowcount = await connection.execute_write(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_ACK_OK,
            (utc_z_now(), notification_id),
        )
        if rowcount == 0:
            # The row wasn't in 'delivering' state — surface the actual
            # current state for the caller to decide. CR MED-1: `current`
            # may now be `delivering` (someone else holds the claim) which
            # is meaningfully distinct from `unknown` (row deleted).
            current = await _fetch_status(db_path, notification_id)
            logger.warning(
                "ack ok found no delivering row",
                extra={
                    "event": "notification.ack.no_match",
                    "notification_id": notification_id,
                    "expected": "delivering",
                    "current": current,
                },
            )
            return AckNotificationOut(
                ok=False,
                final_status=current,
                notification_id=notification_id,
            )
        logger.info(
            "notification ack ok",
            extra={
                "event": "notification.ack.ok",
                "notification_id": notification_id,
            },
        )
        return AckNotificationOut(
            ok=True, final_status="ok", notification_id=notification_id
        )

    # delivery_status == "failed". Read the current row to determine if
    # this is a retry path or terminal-fail path.
    row = await connection.fetchone(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_FETCH_BY_ID,
        (notification_id,),
    )
    if row is None:
        return AckNotificationOut(
            ok=False,
            final_status="unknown",
            notification_id=notification_id,
            error="notification not found",
        )
    attempt_count = int(row[6])
    error_text = error or ""

    if attempt_count >= 5:
        rowcount = await connection.execute_write(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_ACK_FAILED_MAX,
            (error_text, notification_id),
        )
        if rowcount == 0:
            current = await _fetch_status(db_path, notification_id)
            # CR HIGH-2: error text from Hermes is operationally valuable
            # (Discord 5xx detail, rate-limit headers, etc.). The recovery
            # sweep can flip the row out of `delivering` between our fetchone
            # and this UPDATE, which discards the error silently. Surface it
            # in the log so the failure reason remains observable.
            logger.warning(
                "notification ack failed_max rowcount=0 — race loss",
                extra={
                    "event": "notification.ack.race_loss",
                    "notification_id": notification_id,
                    "intended_terminal": "failed_max_retries",
                    "discarded_error": error_text or None,
                    "current_status": current,
                },
            )
            return AckNotificationOut(
                ok=False,
                final_status=current,
                notification_id=notification_id,
                error=error_text or None,
            )
        logger.error(
            "notification ack failed_max_retries",
            extra={
                "event": "notification.ack.failed_max_retries",
                "notification_id": notification_id,
                "attempt_count": attempt_count,
            },
        )
        return AckNotificationOut(
            ok=True,
            final_status="failed_max_retries",
            notification_id=notification_id,
            error=error_text or None,
        )

    # Retry path.
    rowcount = await connection.execute_write(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_ACK_FAILED_RETRY,
        (error_text, notification_id),
    )
    if rowcount == 0:
        current = await _fetch_status(db_path, notification_id)
        # CR HIGH-2: same race-loss observability as the failed_max branch
        # — surface the discarded error text so a recovery-sweep race
        # doesn't silently swallow Hermes's failure detail.
        logger.warning(
            "notification ack failed_retry rowcount=0 — race loss",
            extra={
                "event": "notification.ack.race_loss",
                "notification_id": notification_id,
                "intended_terminal": "pending",
                "discarded_error": error_text or None,
                "current_status": current,
            },
        )
        return AckNotificationOut(
            ok=False,
            final_status=current,
            notification_id=notification_id,
            error=error_text or None,
        )
    logger.warning(
        "notification ack failed retry",
        extra={
            "event": "notification.ack.failed_retry",
            "notification_id": notification_id,
            "attempt_count": attempt_count,
        },
    )
    return AckNotificationOut(
        ok=True,
        final_status="pending",
        notification_id=notification_id,
        error=error_text or None,
    )


async def _fetch_status(
    db_path: str, notification_id: int
) -> Literal["ok", "pending", "failed_max_retries", "delivering", "unknown"]:
    row = await connection.fetchone(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_FETCH_BY_ID,
        (notification_id,),
    )
    if row is None:
        return "unknown"
    status = str(row[5])
    # CR MED-1: distinguish `delivering` (in-flight, someone else holds the
    # claim) from `unknown` (row deleted entirely). Hermes uses this to
    # decide retry vs investigate.
    if status in ("ok", "pending", "failed_max_retries", "delivering"):
        return status  # type: ignore[return-value]
    return "unknown"


__all__ = ["AckNotificationOut", "ack_notification"]
