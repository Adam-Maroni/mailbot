"""Daily-digest intro prompt v1 — Story 6-5 (AR-PAT-5).

The intro paragraph that opens the 08:00 digest. Defender-toned, terse,
≤ 200 characters. Qwen-served via policy.yaml's ``daily_digest_intro`` task
entry. Response-cached (TTL 600s) so a digest retry within 10 minutes
re-uses the same intro.

The agent receives a structured summary of the digest payload (counts +
top categories — NOT email bodies, per Rule J) and writes a short opener
acknowledging the day. The Hermes-cron-skill assembles the final message
as: intro + unread groups + pending Tier-2 batches + queued important
notifications.

Rule M discipline: SYSTEM is byte-stable across calls. No interpolation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You are MailBot, a defender of Adam's attention. You write the intro "
    "paragraph for the 08:00 daily digest.\n"
    "Style: terse, observational, no marketing, no exclamation points. "
    "Reference the day-of-week and one or two salient signals from the "
    "input summary (high-importance unread count, pending action batches, "
    "or queued important notifications). If the input shows a clean inbox "
    "with nothing pending, say so plainly.\n"
    "Constraints: intro MUST be a single paragraph, ≤ 200 characters, no "
    "newlines. Example tone: 'Tuesday morning. 3 important things and a "
    "quiet inbox otherwise.' — observational, not chipper."
)

USER_TEMPLATE = (
    "Day: {day_of_week}\n"
    "Unread (high importance): {unread_high}\n"
    "Unread (medium): {unread_medium}\n"
    "Unread (low): {unread_low}\n"
    "Pending Tier-2 batches: {pending_tier2_count}\n"
    "Queued important notifications: {queued_important_count}\n"
    "Weekly artifacts present: {weekly_present}\n"
)


class DailyDigestIntroOutput(BaseModel):
    """Single-paragraph defender-toned intro for the 08:00 digest."""

    intro: str = Field(
        max_length=200,
        description=(
            "Single-paragraph defender-toned intro acknowledging the "
            "day-of-week + 1-2 salient signals. ≤ 200 chars; no newlines."
        ),
    )


OUTPUT_SCHEMA: type[BaseModel] = DailyDigestIntroOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "DailyDigestIntroOutput",
]
