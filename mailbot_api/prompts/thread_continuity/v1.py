"""Thread-continuity-note prompt v1 — Story 3-7.

Generates a one-line ≤ 200-char summary capturing what a multi-message
thread is about — used at chat time to answer queries like "where is the
project deadline thread" without re-walking every message body.

Local Qwen-only per Rule F.1. Cached forever per Rule A.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You summarize the continuity of a multi-message email thread in one "
    "line ≤ 200 characters. Reply with valid JSON matching the schema; no "
    "preamble.\n"
    "Capture the thread's topic + current state (e.g., 'Q3 budget review — "
    "awaiting CFO approval', 'Project Alpha — deadline shifted to Nov 15'). "
    "Defender-tone factual, no commentary. Confidential email bodies are "
    "excluded from the digest; work with what is provided."
)

USER_TEMPLATE = "Thread messages digest:\n{thread_digest}\n"


class ThreadContinuityOutput(BaseModel):
    """One-line ≤ 200-char defender-tone thread continuity note."""

    summary: str = Field(max_length=200)


OUTPUT_SCHEMA: type[BaseModel] = ThreadContinuityOutput

__all__ = [
    "OUTPUT_SCHEMA",
    "SYSTEM",
    "USER_TEMPLATE",
    "VERSION",
    "ThreadContinuityOutput",
]
