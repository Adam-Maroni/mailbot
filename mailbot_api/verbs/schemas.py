"""Read-side verb schemas — Story 5-1.

Pydantic models for the projection-first agent data window (Rule J — hydration
discipline). All models are frozen. Optional fields use ``T | None = None`` per
PEP 604 (Python 3.12). Lists default to ``Field(default_factory=list)``.

Field descriptions propagate to MCP tool schemas via Story 5-2; populate them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- shared error carrier ---


VerbErrorCode = Literal[
    # find_emails
    "LIMIT_EXCEEDED",
    "LIMIT_INVALID",
    # hydrate_email
    "HYDRATE_EMAIL_NOT_FOUND",
    "HYDRATE_EMAIL_DELETED",
    "HYDRATE_NOT_CLASSIFIED",
    "CONFIDENTIAL_HYDRATION_BLOCKED",
    "HYDRATE_RATE_LIMITED",
    # get_thread
    "THREAD_NOT_FOUND",
    # get_sender_summary
    "SENDER_NOT_FOUND",
]


class VerbError(BaseModel):
    """Refusal carrier returned inside <Verb>Out.error.

    Mirrors mailbot_api.actions.propose.ProposeActionError (Story 4-2). Verbs
    never raise to the agent — every refusal is data per AR-PAT-4.
    """

    model_config = ConfigDict(frozen=True)

    code: VerbErrorCode = Field(description="Machine-readable refusal code.")
    message: str = Field(description="Human-readable refusal explanation for the agent.")


# --- shared row shape ---


class EmailProjection(BaseModel):
    """The agent-visible row (Rule J — projection-only, no body bytes).

    Used by find_emails, get_thread (per-message), and any list-style read verb.
    Bodies require a separate hydrate_email call (rate-limited 5/turn).
    """

    model_config = ConfigDict(frozen=True)

    email_id: str = Field(description="Stable Graph message id (emails.graph_id).")
    received_at: str = Field(description="UTC ISO-8601 with Z suffix.")
    from_address: str | None = Field(default=None, description="Sender email address.")
    from_display_name: str | None = Field(default=None, description="Sender display name if known.")
    subject: str | None = Field(default=None, description="Email subject line.")
    summary_short: str | None = Field(
        default=None,
        description="Short LLM-generated summary; populated by ingest pipeline (Story 3-x).",
    )
    class_coarse: str | None = Field(
        default=None,
        description="Coarse classification (e.g., human, automated). Story 3-2 prompt.",
    )
    importance_score: float | None = Field(
        default=None,
        description="Importance 0.0-100.0 (REAL); populated by ingest pipeline.",
    )
    sensitivity: str | None = Field(
        default=None,
        description="One of normal / sensitive / confidential. Story 3-3 classifier.",
    )
    has_attachments: bool = Field(default=False, description="Whether the email has attachments.")
    thread_id: str | None = Field(
        default=None,
        description=(
            "Stable Graph conversation/thread id (emails.thread_id). Pass this "
            "to get_thread to retrieve every message in the thread. Story 10.5.3 "
            "(F-10-4-3) — surfaced so get_thread is reachable from chat."
        ),
    )


# --- find_emails ---


class FindEmailsFilter(BaseModel):
    """Filter spec for find_emails / count_emails. Frozen, all fields optional.

    NOTE: `unread_only` is intentionally absent — emails.is_read is not captured
    today. Filed as a deferred follow-up; see story 5-1 §schema-reality reframe.
    """

    model_config = ConfigDict(frozen=True)

    sender_address: str | None = Field(default=None, description="Exact-match from_address.")
    sender_domain: str | None = Field(default=None, description="Domain suffix match (e.g., example.com).")
    class_coarse: str | None = Field(default=None, description="Exact-match coarse class.")
    importance_min: float | None = Field(
        default=None,
        description="Minimum importance_score (inclusive). REAL column.",
    )
    since: str | None = Field(default=None, description="received_at >= since (UTC ISO-8601 Z).")
    until: str | None = Field(default=None, description="received_at <= until (UTC ISO-8601 Z).")
    query: str | None = Field(
        default=None,
        description="Substring match on subject + summary_short (parameterized LIKE).",
    )


class FindEmailsOut(BaseModel):
    """Result of find_emails. ok=True with projections, or ok=False with error."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: VerbError | None = None
    projections: list[EmailProjection] = Field(default_factory=list)


class CountEmailsOut(BaseModel):
    """Result of count_emails. ok=True with count, or ok=False with error."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: VerbError | None = None
    count: int = 0


# --- hydrate_email ---


class HydratedEmail(BaseModel):
    """The full row exposed to the agent on a successful hydrate_email call.

    body_text/body_html/to_addresses/cc_addresses are deferred until the
    sync-side capture story lands; today we expose body_preview only.
    """

    model_config = ConfigDict(frozen=True)

    email_id: str = Field(description="Stable Graph message id.")
    received_at: str = Field(description="UTC ISO-8601 Z.")
    from_address: str | None = None
    from_display_name: str | None = None
    subject: str | None = None
    body_preview: str | None = Field(
        default=None,
        description="The body preview captured during Graph sync. Full body deferred (see story 5-1 reframe).",
    )
    summary_short: str | None = None
    summary_short_at: str | None = None
    class_coarse: str | None = None
    class_coarse_at: str | None = None
    class_fine: str | None = None
    class_fine_at: str | None = None
    importance_score: float | None = None
    importance_score_at: str | None = None
    sensitivity: str | None = None
    sensitivity_at: str | None = None
    action_extraction: str | None = Field(
        default=None,
        description="JSON of extracted action items (column emails.action_extraction).",
    )
    action_extraction_at: str | None = None
    has_attachments: bool = False
    thread_id: str | None = None


class HydrateEmailOut(BaseModel):
    """Result of hydrate_email."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: VerbError | None = None
    email: HydratedEmail | None = None


# --- get_thread ---


class GetThreadOut(BaseModel):
    """Result of get_thread. Ordered ASC by received_at, projections only."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: VerbError | None = None
    thread_id: str | None = None
    projections: list[EmailProjection] = Field(default_factory=list)
    thread_continuity_note: str | None = Field(
        default=None,
        description="Cached cross-message summary from Story 3-7 (threads.thread_continuity_note).",
    )
    message_count: int = 0


# --- get_sender_summary ---


class SenderSummary(BaseModel):
    """Per-sender enrichment surface."""

    model_config = ConfigDict(frozen=True)

    sender_address: str
    display_name: str | None = None
    message_count: int = 0
    last_seen_at: str | None = None
    sender_reputation_summary: str | None = Field(
        default=None,
        description="Cached LLM-generated sender reputation summary (Story 3-7).",
    )


class GetSenderSummaryOut(BaseModel):
    """Result of get_sender_summary."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: VerbError | None = None
    sender: SenderSummary | None = None


__all__ = [
    "VerbError",
    "VerbErrorCode",
    "EmailProjection",
    "FindEmailsFilter",
    "FindEmailsOut",
    "CountEmailsOut",
    "HydratedEmail",
    "HydrateEmailOut",
    "GetThreadOut",
    "SenderSummary",
    "GetSenderSummaryOut",
]
