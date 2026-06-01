"""Summary-short prompt v1 — Story 3-2.

Twitter-length defender brevity: ≤ 280 chars. The summary is computed once at
ingest time per Rule A and stored in `emails.summary_short` for chat-time
display in Hermes-rendered digests; it is NEVER recomputed at chat time.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You write a one-line summary of an email in 280 characters or fewer. "
    "Defender tone: factual, no fluff, no opinions, no recommendations. "
    "The summary will be cached and shown to the recipient in a daily digest, "
    "so it must capture the gist (sender intent + key data point if any) in "
    "one scannable sentence.\n"
    "Examples of good summaries:\n"
    "  'Sarah confirms Friday 3pm meeting moved to Tuesday 2pm.'\n"
    "  'Bank statement attached — Sept balance $3,418, due Oct 15.'\n"
    "  'GitHub: 3 failing tests on PR #482; review requested.'\n"
    "Do NOT add commentary, urgency framing, or suggested replies. Just the gist."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class SummaryShortOutput(BaseModel):
    """One-line summary of an email; ≤ 280 chars."""

    summary: str = Field(max_length=280)


OUTPUT_SCHEMA: type[BaseModel] = SummaryShortOutput

__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA", "SummaryShortOutput"]
