"""``compose_digest`` verb — Story 6-5.

Assembles the 08:00 digest payload from cached projections only — no LLM
calls, no body bytes (Rule J + Rule A). Hermes's cron-with-agent job
fetches this payload, makes ONE Qwen call for a persona-voiced intro,
and posts the assembled message to Discord.

Empty-payload detection lives on Hermes-side: if all 4 sections are empty,
Hermes posts the terse fallback ("Inbox is clean. Nothing pending. Have a
good day.") instead of an empty digest. The verb returns the
collections-as-is.

The digest delivery is finalized by ``finalize_digest_delivery`` (the
companion verb that flips queued `tier='important'` rows to
`delivery_status='ok_via_digest'`).

Schema-reality note: ``emails.is_read`` is NOT captured (Story 5-1 § same
gap). The unread bucket uses "received in the last 24h" as a pragmatic
proxy — defensible for a daily digest, since anything older than 24h was
either already in yesterday's digest or has been triaged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from mailbot_api.db import connection, queries
from mailbot_api.verbs.schemas import EmailProjection

_UNREAD_WINDOW_HOURS = 24

logger = logging.getLogger(__name__)


class PendingBatchSummary(BaseModel):
    """One Tier-2 action_type pending Adam's approval. ``count`` is the
    number of pending rows; ``oldest_proposed_at`` is the earliest
    proposal still waiting (so Adam knows how stale the request is)."""

    action_type: str
    count: int
    oldest_proposed_at: str


class NotificationSummary(BaseModel):
    """One queued `tier='important'` notification from Story 6-3 that
    arrived since the last digest. ``message`` is the original
    `send_important` message body (not the dedup summary form — the
    dispatcher's dedup collapse already happened upstream)."""

    id: int
    category: str
    message: str
    enqueued_at: str


class WeeklyArtifacts(BaseModel):
    """Story 6-5 placeholder — Epic 7 (eval + calibration) will populate
    weekly KL-divergence drift reports + Sunday sampling DMs. Returned as
    ``None`` from compose_digest until Epic 7 ships."""

    placeholder: bool = True


class ComposeDigestOut(BaseModel):
    """Result of compose_digest. The Hermes-side renderer assembles a
    Discord message in section order: intro (Qwen-generated) → unread
    groups → pending Tier-2 batches → queued important notifications →
    weekly artifacts (when present).

    Empty-payload detection lives on Hermes-side (not here): if every
    collection is empty, Hermes posts the terse fallback instead.
    """

    unread_by_importance: dict[
        Literal["high", "medium", "low"], list[EmailProjection]
    ] = Field(
        default_factory=lambda: {  # type: ignore[arg-type]
            "high": [],
            "medium": [],
            "low": [],
        }
    )
    pending_tier2_batches: list[PendingBatchSummary] = Field(default_factory=list)
    queued_important_notifications: list[NotificationSummary] = Field(
        default_factory=list
    )
    weekly_artifacts: WeeklyArtifacts | None = None


def _bucket_importance(score: float | None) -> Literal["high", "medium", "low"]:
    """Map importance_score → bucket. NULL scores fall into low (defensive
    — emails missing the derived score haven't been processed by the
    ingest pipeline yet, so the operator likely cares less)."""
    if score is None:
        return "low"
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


async def compose_digest(*, db_path: str) -> ComposeDigestOut:
    """Read the 4 digest sections from cached projections + return the
    payload. No LLM calls; no body bytes (Rule J + Rule A).
    """
    # Section 1 — recent non-deleted emails (last 24h) bucketed by
    # importance. Documented as the is_read-less proxy in module docstring.
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=_UNREAD_WINDOW_HOURS)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    unread_rows = await connection.fetchall(
        db_path, queries.EMAILS_UNREAD_BUCKETED, (cutoff,)
    )
    buckets: dict[Literal["high", "medium", "low"], list[EmailProjection]] = {
        "high": [],
        "medium": [],
        "low": [],
    }
    for row in unread_rows:
        proj = EmailProjection(
            email_id=str(row[0]),
            subject=row[1],
            from_address=row[2],
            received_at=str(row[3]) if row[3] is not None else "",
            importance_score=row[4],
            summary_short=row[5],
            class_coarse=row[6],
            sensitivity=row[7],
        )
        buckets[_bucket_importance(proj.importance_score)].append(proj)

    # Section 2 — Tier-2 batches grouped by action_type.
    batch_rows = await connection.fetchall(
        db_path, queries.PENDING_ACTIONS_TIER2_GROUPED, ()
    )
    pending_tier2_batches = [
        PendingBatchSummary(
            action_type=str(r[0]),
            count=int(r[1]),
            oldest_proposed_at=str(r[2]),
        )
        for r in batch_rows
    ]

    # Section 3 — queued tier='important' notifications still pending.
    notif_rows = await connection.fetchall(
        db_path, queries.NOTIFICATIONS_OUTBOX_IMPORTANT_PENDING, ()
    )
    queued_important_notifications = [
        NotificationSummary(
            id=int(r[0]),
            category=str(r[1]),
            message=str(r[2]),
            enqueued_at=str(r[3]),
        )
        for r in notif_rows
    ]

    # Section 4 — weekly artifacts (Epic 7 will populate; None for now).
    weekly_artifacts: WeeklyArtifacts | None = None

    logger.info(
        "digest composed",
        extra={
            "event": "digest.composed",
            "unread_high": len(buckets["high"]),
            "unread_medium": len(buckets["medium"]),
            "unread_low": len(buckets["low"]),
            "pending_tier2_count": len(pending_tier2_batches),
            "queued_important_count": len(queued_important_notifications),
        },
    )

    return ComposeDigestOut(
        unread_by_importance=buckets,
        pending_tier2_batches=pending_tier2_batches,
        queued_important_notifications=queued_important_notifications,
        weekly_artifacts=weekly_artifacts,
    )


__all__ = [
    "ComposeDigestOut",
    "NotificationSummary",
    "PendingBatchSummary",
    "WeeklyArtifacts",
    "compose_digest",
]
