"""Action-extraction prompt v1 — Story 3-2.

Extracts structured action items from an email body. Each ActionItem has a
type, a short summary (≤ 120 chars), and an optional UTC ISO-8601 deadline.

The strict deadline format `YYYY-MM-DDTHH:MM:SSZ` is enforced by a Pydantic
v2 `@field_validator` — the model is asked to produce that exact shape, and
non-conforming responses fail validation (which routes through the Router's
schema-fail-retry chain). This prevents ambiguous date strings ("next Tuesday")
from reaching downstream consumers.

Rule M discipline: SYSTEM is byte-stable across calls.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

VERSION: str = "v1"

_ISO_8601_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


SYSTEM = (
    "You extract structured action items from an email body. Reply with valid "
    "JSON matching the schema; no preamble.\n"
    "Action types (one per item):\n"
    "  - reply_needed: the recipient should respond in writing\n"
    "  - deadline: a date-bound obligation (with deadline_at populated)\n"
    "  - calendar_event: a meeting or event to add to the calendar\n"
    "  - payment: a charge, bill, or invoice requiring action\n"
    "  - password_reset: an account recovery flow the recipient initiated or must complete\n"
    "  - info_only: informational, no action required (use sparingly — only include "
    "when explicitly flagging the email as 'no follow-up needed')\n"
    "For each item:\n"
    "  - summary: ≤ 120 chars, defender-tone factual\n"
    "  - deadline_at: UTC ISO-8601 with strict format 'YYYY-MM-DDTHH:MM:SSZ' "
    "if a specific date/time is named; null otherwise. Do NOT guess vague "
    "dates ('next week' → null, not an interpolated date).\n"
    "If no actions are present, return an empty list. Do not invent actions."
)

USER_TEMPLATE = "Subject: {subject}\nFrom: {sender}\nBody preview: {body_preview}\n"


class ActionItem(BaseModel):
    """One extracted action with type, summary, and optional UTC deadline."""

    type: Literal[
        "reply_needed",
        "deadline",
        "calendar_event",
        "payment",
        "password_reset",
        "info_only",
    ]
    summary: str = Field(max_length=120)
    deadline_at: str | None = None

    @field_validator("deadline_at")
    @classmethod
    def _validate_iso_z(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ISO_8601_Z_RE.match(value):
            raise ValueError(f"deadline_at must match 'YYYY-MM-DDTHH:MM:SSZ' (UTC ISO-8601); got {value!r}")
        return value


class ActionExtractionOutput(BaseModel):
    """List of extracted ActionItems; empty list when no actions present."""

    actions: list[ActionItem]


OUTPUT_SCHEMA: type[BaseModel] = ActionExtractionOutput

__all__ = [
    "VERSION",
    "SYSTEM",
    "USER_TEMPLATE",
    "OUTPUT_SCHEMA",
    "ActionItem",
    "ActionExtractionOutput",
]
