"""Importance-scoring prompt v1 — Story 3-2.

0..100 integer importance score plus ≤ 5 short signal tags explaining the
score. The score is computed once at ingest and cached per Rule A; Epic 5's
read-side projections rank by `importance_score` to surface the inbox top-N.

The Pydantic schema declares `importance: int` even though the underlying
`emails.importance_score` column is declared REAL in 001_init.sql — SQLite
type affinity makes the round-trip lossless (Story 3-1 Disposition note).

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You score the importance of an email on a 0–100 scale and name the "
    "specific signals that drove the score. Reply with valid JSON matching "
    "the schema; no preamble.\n"
    "Anchors:\n"
    "  0–10: explicit unsubscribe-worthy content, pure marketing broadcast\n"
    "  11–30: low-priority informational content, newsletters skimmed at leisure\n"
    "  31–50: routine personal/professional communication needing eventual reply\n"
    "  51–70: time-sensitive request from a known contact\n"
    "  71–85: urgent personal matter or business deadline within 48h\n"
    "  86–100: crisis, safety, or money-loss-imminent content; act today\n"
    "Signal tags (≤ 5, short snake_case strings): name the specific reasons "
    "the score lands where it does. Examples: 'explicit_deadline_24h', "
    "'sender_is_partner', 'unsubscribe_link_present', 'follows_up_existing_thread'.\n"
    "Defender tone: be honest about uncertainty. A clearly-routine email is 35–40, "
    "not 50. A clearly-urgent crisis is 90+, not 70."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class ImportanceScoringOutput(BaseModel):
    """0..100 importance score + ≤ 5 signal tags."""

    importance: int = Field(ge=0, le=100)
    signals: list[str] = Field(max_length=5)


OUTPUT_SCHEMA: type[BaseModel] = ImportanceScoringOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "ImportanceScoringOutput",
]
