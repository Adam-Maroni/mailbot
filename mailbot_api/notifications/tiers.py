"""Four-tier notification dispatcher — Story 6-3 (FR-7.4).

Replaces the Story 1-8 JSONL placeholder (`mailbot_api/notifications/__init__.py`)
with a tiered dispatch surface:

  - ``send_urgent(message, category, *, db_path)`` — enqueue in
    ``notifications_outbox`` with ``tier='urgent'``. Hermes pulls via
    ``pull_pending_notifications`` MCP tool every ~10s and posts to Discord.
    Worst-case delivery SLA: ~30s (10s pull cadence + 5s Discord API + buffer).
  - ``send_important(message, category, *, db_path)`` — enqueue with
    ``tier='important'``. Held until Story 6-5's 08:00 digest sweeper.
  - ``send_informational(message, category)`` — no DB write. Pure log line.
    Slash commands like ``/status`` / ``/cost`` query underlying data
    on-demand; this tier is a marker for code that wants to record an event
    without delivering anything.
  - ``send_silent(message, category)`` — log line only. No DB row, no
    Discord delivery. Used for ambient ops events.

Schema-reality reframe (vs Epic 6 spec):

    The epic spec proposed *"Hermes exposes an internal HTTP endpoint for
    'post this message to Adam's DM' that the worker calls."* Real Hermes
    does NOT accept inbound HTTP for outbound message dispatch — Hermes
    runs the Discord gateway and posts when its agent loop decides. The
    schema-reality path is pull-based: mailbot-api enqueues; Hermes polls
    via MCP (the F6-closed transport from Story 6-6.6) + acks.

    This keeps the bot token in Hermes only (mailbot-api never holds it)
    and uses the existing 17→19 MCP tool surface — no new transport, no
    new container, no Hermes-side HTTP server.

The OLD ``mailbot_api/notifications.send_urgent`` JSONL writer remains
callable as a deprecation stub (one-epic backwards compat). CR-clarified
2026-06-03: the stub does NOT forward into ``tiers.send_urgent`` — it still
writes JSONL directly, because the legacy callers were sync and threading
``db_path`` through that surface would have required API-breaking changes.
All production call sites in Story 6-3 were migrated to call
``tiers.send_<tier>`` directly with an explicit category. The JSONL stub
is exercised by exactly one test
(``test_worker_health_alarm.py::test_send_urgent_writes_jsonl``) which
validates the deprecated surface still works.

``category`` is load-bearing — Story 6-4's anti-fatigue (mute / dedup /
quiet hours) reads it. Use stable category names: ``'health'``, ``'sync'``,
``'router_anomaly'``, ``'action_escalation'``, etc.
"""

from __future__ import annotations

import logging
from datetime import datetime

from mailbot_api.db import connection, queries
from mailbot_api.notifications import fatigue, posture
from mailbot_api.observability.timestamps import utc_z_now

logger = logging.getLogger(__name__)


__all__ = [
    "send_urgent",
    "send_important",
    "send_informational",
    "send_silent",
]


def _log_suppressed(event: str, tier: str, category: str, message: str) -> None:
    """One-liner for the "dropped" logs that Story 6-4 introduces. Carries
    a preview of the dropped message so an operator can trace why their
    notification never arrived (Story 6-3 CR HIGH-2 observability lesson).

    CR MED-2: WARNING level (was INFO) so suppressed notifications show up
    in the operator's default `journalctl -p warning` view. Operationally
    significant — explains why Adam didn't receive an alert.
    """
    logger.warning(
        f"notification {tier} dropped",
        extra={
            "event": event,
            "tier": tier,
            "category": category,
            "dropped_message_preview": message[:120],
        },
    )


async def _check_mute(category: str, tier: str, message: str, *, db_path: str) -> bool:
    """Return True iff the category is muted (caller should drop the call)."""
    if await fatigue.is_muted(category, db_path=db_path):
        _log_suppressed("notification.muted", tier, category, message)
        return True
    return False


async def send_urgent(message: str, category: str, *, db_path: str) -> None:
    """Enqueue an urgent-tier notification for Hermes pull-based delivery.

    Story 6-4: urgent BYPASSES quiet hours + posture (FR-7.4 — urgent
    means urgent). ONLY the mute gate applies.

    **SHARP EDGE — urgent honors mute.** A muted category SILENCES even
    urgent notifications. This is intentional (Adam's call, mirrors the
    Story 4-1 CR-2 belt-and-suspenders defender posture) but operationally
    risky: a muted ``health`` or ``sync`` category means Adam goes blind
    to real emergencies until ``/unmute <category>``. Default Story 6-3
    categories (``health``, ``sync``, ``router_anomaly``, ``action_escalation``)
    should generally NOT be muted indefinitely.

    The row lands in ``notifications_outbox`` with ``delivery_status='pending'``;
    Hermes's MCP poller (~10s cadence) picks it up via ``pull_pending_notifications``.
    """
    if await _check_mute(category, "urgent", message, db_path=db_path):
        return
    # Dedup applies even to urgent — 5 health alarms in an hour is still noise.
    collapsed, latest_id = await fatigue.should_dedup(
        category, "urgent", db_path=db_path
    )
    if collapsed and latest_id is not None:
        summary = (
            f"5 {category} alerts in the last hour; latest: {message}"
        )
        rowcount = await connection.execute_write(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_UPDATE_LATEST_MESSAGE,
            (summary, latest_id),
        )
        if rowcount > 0:
            # CR MED-2: WARNING level for the collapse so the suppression
            # is visible alongside the other anti-fatigue events.
            logger.warning(
                "notification dedup collapsed",
                extra={
                    "event": "notification.dedup.collapsed",
                    "tier": "urgent",
                    "category": category,
                    "collapsed_into_id": latest_id,
                },
            )
            return
        # CR HIGH-1 defensive fallback: the collapse target raced from
        # `pending` to `delivering`/`ok` between the count and this UPDATE.
        # Without this branch the alert would be silently dropped. Fall
        # through to the normal INSERT path below.
        logger.warning(
            "notification dedup collapse missed — falling through to INSERT",
            extra={
                "event": "notification.dedup.collapse_missed",
                "tier": "urgent",
                "category": category,
                "intended_target_id": latest_id,
            },
        )

    notification_id = await connection.execute_insert_returning_id(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_INSERT,
        ("urgent", category, message, utc_z_now()),
    )
    logger.info(
        "notification enqueued",
        extra={
            "event": "notification.enqueued",
            "tier": "urgent",
            "category": category,
            "notification_id": notification_id,
        },
    )


async def send_important(message: str, category: str, *, db_path: str) -> None:
    """Enqueue an important-tier notification for the 08:00 digest (Story 6-5).

    Story 6-4 gating layers:

      1. urgent-only posture → drop (only urgent delivers under noisy episode)
      2. mute → drop
      3. dedup → collapse into the latest matching row instead of inserting
      4. quiet hours → still enqueue (the row waits for the digest sweeper
         anyway, so quiet hours add no extra hold)

    The row sits in ``notifications_outbox`` with ``tier='important'``.
    Story 6-5's digest composer sweeps it; ``pull_pending_notifications``
    does NOT return important rows.
    """
    if await posture.is_urgent_only_active(db_path):
        _log_suppressed(
            "notification.posture.suppressed", "important", category, message
        )
        return
    if await _check_mute(category, "important", message, db_path=db_path):
        return
    collapsed, latest_id = await fatigue.should_dedup(
        category, "important", db_path=db_path
    )
    if collapsed and latest_id is not None:
        summary = (
            f"5 {category} alerts in the last hour; latest: {message}"
        )
        rowcount = await connection.execute_write(
            db_path,
            queries.NOTIFICATIONS_OUTBOX_UPDATE_LATEST_MESSAGE,
            (summary, latest_id),
        )
        if rowcount > 0:
            # CR MED-2: WARNING level (was INFO) so suppressions surface in
            # the operator's default warning view.
            logger.warning(
                "notification dedup collapsed",
                extra={
                    "event": "notification.dedup.collapsed",
                    "tier": "important",
                    "category": category,
                    "collapsed_into_id": latest_id,
                },
            )
            return
        # CR HIGH-1 defensive fallback (same as send_urgent's branch).
        logger.warning(
            "notification dedup collapse missed — falling through to INSERT",
            extra={
                "event": "notification.dedup.collapse_missed",
                "tier": "important",
                "category": category,
                "intended_target_id": latest_id,
            },
        )

    notification_id = await connection.execute_insert_returning_id(
        db_path,
        queries.NOTIFICATIONS_OUTBOX_INSERT,
        ("important", category, message, utc_z_now()),
    )
    logger.info(
        "notification enqueued",
        extra={
            "event": "notification.enqueued",
            "tier": "important",
            "category": category,
            "notification_id": notification_id,
        },
    )


async def send_informational(
    message: str,
    category: str,
    *,
    db_path: str | None = None,
    _now: datetime | None = None,
) -> None:
    """Mark an informational event without enqueuing or delivering.

    Story 6-4 gating layers:

      1. urgent-only posture → drop
      2. mute → drop
      3. quiet hours → drop (informational is pull-only anyway; no
         delivery loss — slash commands like /status query data on demand)

    No DB write on the deliver path; only the gates touch DB. ``db_path``
    is optional so legacy sync call sites can opt out of the gates by
    passing ``None``; production paths should always thread it through.
    """
    if db_path is not None:
        if await posture.is_urgent_only_active(db_path):
            _log_suppressed(
                "notification.posture.suppressed",
                "informational", category, message,
            )
            return
        if await _check_mute(category, "informational", message, db_path=db_path):
            return
        if fatigue.is_quiet_hours(_now):
            _log_suppressed(
                "notification.quiet_hours.dropped",
                "informational", category, message,
            )
            return

    logger.info(
        "notification informational",
        extra={
            "event": "notification.informational",
            "tier": "informational",
            "category": category,
            "log_message": message,
        },
    )


def send_silent(message: str, category: str) -> None:
    """Log-only notification — no DB row, no Discord delivery.

    Used for ambient ops events that should be searchable in logs but
    never reach Adam in any channel.
    """
    logger.info(
        "notification silent",
        extra={
            "event": "notification.silent",
            "tier": "silent",
            "category": category,
            "log_message": message,
        },
    )
