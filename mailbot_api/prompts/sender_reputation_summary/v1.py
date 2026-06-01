"""Sender-reputation-summary prompt v1 — Story 3-7.

Generates a one-line ≤ 140-char summary describing how a sender typically
interacts with the recipient — used at chat time to answer queries like
"anything from the lawyer" without re-paying for synthesis.

Local Qwen-only per Rule F.1 (cross-email aggregation never escapes to
Anthropic). Cached forever per Rule A.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

VERSION: str = "v1"

SYSTEM = (
    "You summarize how an email sender typically interacts with the "
    "recipient, given 5 of their most-recent messages. Reply with valid "
    "JSON matching the schema; no preamble. The summary is one line, ≤ 140 "
    "characters, defender-tone factual.\n"
    "Capture the relationship + typical content (e.g., 'Family — weekly "
    "personal updates', 'Vendor — monthly billing statements', 'Recruiter — "
    "cold outreach'). Do NOT speculate; only describe what the messages "
    "literally show. Confidential email bodies are excluded from the digest; "
    "sensitive bodies are also excluded but subjects remain — work with what "
    "is provided."
)

USER_TEMPLATE = "Sender: {sender_address}\n\nRecent emails digest:\n{recent_emails_digest}\n"


class SenderReputationSummaryOutput(BaseModel):
    """One-line ≤ 140-char defender-tone sender description."""

    summary: str = Field(max_length=140)


OUTPUT_SCHEMA: type[BaseModel] = SenderReputationSummaryOutput

__all__ = [
    "OUTPUT_SCHEMA",
    "SYSTEM",
    "USER_TEMPLATE",
    "VERSION",
    "SenderReputationSummaryOutput",
]
