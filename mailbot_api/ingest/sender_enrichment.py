"""Sender + thread enrichment per Story 3-7.

Public API:
  * `enrich_sender(*, sender_id, db_path, caller_origin)` — generate + cache
    sender_reputation_summary if not already present.
  * `enrich_thread(*, thread_id, db_path, caller_origin)` — generate + cache
    thread_continuity_note for multi-message threads.

Both functions:
  - Pass `email_id=None` to ask_router so the Story 3-3 FR-2.3 precondition
    is bypassed (these are cross-email tasks, not per-email).
  - Build their digest with sensitivity-aware filtering:
      * confidential → excluded entirely (not even subject)
      * sensitive    → subject + received_at only (body excluded)
      * normal       → subject + received_at + body_preview (truncated)
  - Are cached forever per Rule A — second call short-circuits.
  - Route via local Qwen only per Rule F.1 (cross-email synthesis never
    escapes to Anthropic — the residual digest can still be sensitive even
    after filtering).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

from pydantic import BaseModel, ConfigDict

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.queries import (
    EMAILS_BY_THREAD_SELECT,
    EMAILS_RECENT_BY_SENDER_SELECT,
    SENDER_REPUTATION_SELECT,
    SENDER_REPUTATION_UPDATE,
    THREAD_CONTINUITY_SELECT,
    THREAD_CONTINUITY_UPDATE,
)
from mailbot_api.prompts.sender_reputation_summary.v1 import (
    VERSION as SENDER_PROMPT_V,
)
from mailbot_api.prompts.sender_reputation_summary.v1 import (
    SenderReputationSummaryOutput,
)
from mailbot_api.prompts.thread_continuity.v1 import (
    VERSION as THREAD_PROMPT_V,
)
from mailbot_api.prompts.thread_continuity.v1 import (
    ThreadContinuityOutput,
)
from mailbot_api.router import ask_router
from mailbot_api.router.errors import ErrorCode, RouterError

logger = logging.getLogger(__name__)

_BODY_PREVIEW_TRUNCATE: Final[int] = 200


def _utc_iso8601_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EnrichSenderResult(BaseModel):
    """Return shape of `enrich_sender`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    sender_id: str
    was_cached: bool = False
    summary: str | None = None
    model: str | None = None
    error: RouterError | None = None


class EnrichThreadResult(BaseModel):
    """Return shape of `enrich_thread`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ok: bool
    thread_id: str
    was_cached: bool = False
    summary: str | None = None
    model: str | None = None
    error: RouterError | None = None


def _format_email_for_digest(
    *,
    subject: str | None,
    received_at: str,
    body_preview: str | None,
    sensitivity: str | None,
) -> str | None:
    """Build a one-email digest line with sensitivity-aware filtering.

    Returns None for confidential emails (excluded entirely).
    """
    if sensitivity == "confidential":
        return None
    subject_safe = subject or "(no subject)"
    if sensitivity == "sensitive":
        # Subject + received_at only; body excluded.
        return f"- [{received_at}] {subject_safe} (sensitive — body redacted)"
    body = (body_preview or "")[:_BODY_PREVIEW_TRUNCATE]
    return f"- [{received_at}] {subject_safe}: {body}"


async def enrich_sender(
    *,
    sender_id: str,
    db_path: str,
    caller_origin: str = "ingest-pipeline-sender",
) -> EnrichSenderResult:
    """Generate + cache sender_reputation_summary for this sender.

    Short-circuits if already cached (Rule A). Errors-as-data per AR-PAT-4.
    """
    # Rule A: cache check.
    row = await fetchone(db_path, SENDER_REPUTATION_SELECT, (sender_id,))
    if row is not None and row[0] is not None:
        return EnrichSenderResult(ok=True, sender_id=sender_id, was_cached=True, summary=row[0])

    # Build digest from the 5 most-recent emails from this sender.
    email_rows = await fetchall(db_path, EMAILS_RECENT_BY_SENDER_SELECT, (sender_id,))
    if not email_rows:
        return EnrichSenderResult(
            ok=False,
            sender_id=sender_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=f"no emails found for sender_id={sender_id!r}",
                retryable=False,
            ),
        )
    digest_lines: list[str] = []
    for graph_id, subject, received_at, body_preview, sensitivity in email_rows:
        line = _format_email_for_digest(
            subject=subject,
            received_at=received_at,
            body_preview=body_preview,
            sensitivity=sensitivity,
        )
        if line is not None:
            digest_lines.append(line)
    if not digest_lines:
        # All 5 emails were confidential — no digest to summarize.
        return EnrichSenderResult(
            ok=False,
            sender_id=sender_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="all recent emails are confidential; no digest possible",
                retryable=False,
            ),
        )
    digest = "\n".join(digest_lines)

    # Dispatch via Router. email_id=None bypasses FR-2.3 precondition.
    result = await ask_router(
        task_type="sender_reputation_summary",
        content={"sender_address": sender_id, "recent_emails_digest": digest},
        db_path=db_path,
        email_id=None,
        caller_origin=caller_origin,
        caller_verb="ingest.sender_enrichment",
    )
    if not result.ok or not isinstance(result.output, SenderReputationSummaryOutput):
        return EnrichSenderResult(
            ok=False,
            sender_id=sender_id,
            error=result.error,
            model=result.model_used or None,
        )

    summary = result.output.summary
    await execute_write(
        db_path,
        SENDER_REPUTATION_UPDATE,
        (
            summary,
            SENDER_PROMPT_V,
            None,  # conf — embeddings have no confidence; one-line summaries similar
            result.model_used,
            _utc_iso8601_now(),
            sender_id,
        ),
    )
    return EnrichSenderResult(
        ok=True,
        sender_id=sender_id,
        was_cached=False,
        summary=summary,
        model=result.model_used,
    )


async def enrich_thread(
    *,
    thread_id: str,
    db_path: str,
    caller_origin: str = "ingest-pipeline-thread",
) -> EnrichThreadResult:
    """Generate + cache thread_continuity_note for multi-message threads.

    Short-circuits if already cached OR if message_count <= 1 (single-message
    threads aren't really threads).
    """
    row = await fetchone(db_path, THREAD_CONTINUITY_SELECT, (thread_id,))
    if row is None:
        return EnrichThreadResult(
            ok=False,
            thread_id=thread_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message=f"thread_id={thread_id!r} not found",
                retryable=False,
            ),
        )
    message_count, existing_note = row
    if existing_note is not None:
        return EnrichThreadResult(ok=True, thread_id=thread_id, was_cached=True, summary=existing_note)
    if (message_count or 0) <= 1:
        # Not really a thread — skip silently as cached/inapplicable.
        return EnrichThreadResult(ok=True, thread_id=thread_id, was_cached=True, summary=None)

    email_rows = await fetchall(db_path, EMAILS_BY_THREAD_SELECT, (thread_id,))
    digest_lines: list[str] = []
    for graph_id, subject, received_at, body_preview, sensitivity in email_rows:
        line = _format_email_for_digest(
            subject=subject,
            received_at=received_at,
            body_preview=body_preview,
            sensitivity=sensitivity,
        )
        if line is not None:
            digest_lines.append(line)
    if not digest_lines:
        return EnrichThreadResult(
            ok=False,
            thread_id=thread_id,
            error=RouterError(
                code=ErrorCode.PROVIDER_ERROR,
                message="all thread messages are confidential; no digest possible",
                retryable=False,
            ),
        )
    digest = "\n".join(digest_lines)

    result = await ask_router(
        task_type="thread_continuity",
        content={"thread_digest": digest},
        db_path=db_path,
        email_id=None,
        caller_origin=caller_origin,
        caller_verb="ingest.thread_enrichment",
    )
    if not result.ok or not isinstance(result.output, ThreadContinuityOutput):
        return EnrichThreadResult(
            ok=False,
            thread_id=thread_id,
            error=result.error,
            model=result.model_used or None,
        )

    summary = result.output.summary
    await execute_write(
        db_path,
        THREAD_CONTINUITY_UPDATE,
        (
            summary,
            THREAD_PROMPT_V,
            None,
            result.model_used,
            _utc_iso8601_now(),
            thread_id,
        ),
    )
    return EnrichThreadResult(
        ok=True,
        thread_id=thread_id,
        was_cached=False,
        summary=summary,
        model=result.model_used,
    )


__all__ = [
    "EnrichSenderResult",
    "EnrichThreadResult",
    "enrich_sender",
    "enrich_thread",
]
