"""hydrate_email read verb — Story 5-1 AC-2.

Returns the full email row (modulo the deferred body_text/body_html fields —
see story 5-1 §schema-reality reframe). Rate-limited to 5 hydrations per agent
session per Rule J (hydration discipline).

Session-counter state lives in a module-level dict. Process-local + ephemeral
by design (AR-D12-1 sensitivity-token-style — restart resets are acceptable).
"""

from __future__ import annotations

from typing import Any

from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import HYDRATE_EMAIL_SELECT
from mailbot_api.verbs.schemas import (
    HydratedEmail,
    HydrateEmailOut,
    VerbError,
)

_HYDRATION_LIMIT_PER_SESSION = 5

# Process-local, in-memory. Reset on process restart by design. The MCP server
# (Story 5-2) is responsible for calling reset_hydration_count() at per-turn
# lifecycle boundaries.
_SESSION_HYDRATION_COUNTS: dict[str, int] = {}


def reset_hydration_count(session_id: str) -> None:
    """Clear the hydration counter for `session_id`. Idempotent."""
    _SESSION_HYDRATION_COUNTS.pop(session_id, None)


def _row_to_hydrated(row: tuple[Any, ...]) -> HydratedEmail:
    """Map HYDRATE_EMAIL_SELECT row to HydratedEmail. Column order matches the query."""
    return HydratedEmail(
        email_id=row[0],
        received_at=row[1],
        from_address=row[2],
        from_display_name=row[3],
        subject=row[4],
        body_preview=row[5],
        summary_short=row[6],
        summary_short_at=row[7],
        class_coarse=row[8],
        class_coarse_at=row[9],
        class_fine=row[10],
        class_fine_at=row[11],
        importance_score=row[12],
        importance_score_at=row[13],
        sensitivity=row[14],
        sensitivity_at=row[15],
        action_extraction=row[16],
        action_extraction_at=row[17],
        has_attachments=bool(row[18]),
        thread_id=row[19],
    )


async def hydrate_email(
    email_id: str,
    *,
    db_path: str,
    session_id: str,
) -> HydrateEmailOut:
    """Return the full hydration of one email for the agent.

    Rate-limited: 5 successful hydrations per session_id. Failed gates do not
    charge the counter (no body was exposed). Confidential emails refuse
    unconditionally (Rule A).
    """
    # Rate-limit check FIRST — refuse before any DB read if already at limit.
    # This avoids leaking "this email exists" via timing on rate-limited calls.
    if _SESSION_HYDRATION_COUNTS.get(session_id, 0) >= _HYDRATION_LIMIT_PER_SESSION:
        return HydrateEmailOut(
            ok=False,
            error=VerbError(
                code="HYDRATE_RATE_LIMITED",
                message="hydration limit is 5 emails per turn — narrow your filter first",
            ),
        )

    row = await fetchone(db_path, HYDRATE_EMAIL_SELECT, (email_id,))
    if row is None:
        return HydrateEmailOut(
            ok=False,
            error=VerbError(code="HYDRATE_EMAIL_NOT_FOUND", message=f"no email with id={email_id!r}"),
        )

    # row[20] = deleted_at — see HYDRATE_EMAIL_SELECT column order.
    deleted_at = row[20]
    if deleted_at is not None:
        return HydrateEmailOut(
            ok=False,
            error=VerbError(code="HYDRATE_EMAIL_DELETED", message=f"email {email_id!r} was deleted"),
        )

    # row[15] = sensitivity_at; row[14] = sensitivity.
    # CR finding 5: check confidential FIRST so a corrupt-state row
    # (sensitivity='confidential' + sensitivity_at IS NULL) surfaces the
    # privacy-block code rather than the not-classified code. Body is refused
    # in both cases — this is about correct refusal semantics + defense in
    # depth against future control-flow extensions.
    sensitivity_at = row[15]
    sensitivity = row[14]
    if sensitivity == "confidential":
        return HydrateEmailOut(
            ok=False,
            error=VerbError(
                code="CONFIDENTIAL_HYDRATION_BLOCKED",
                message="confidential emails cannot be hydrated to the agent — only metadata is available",
            ),
        )

    if sensitivity_at is None:
        return HydrateEmailOut(
            ok=False,
            error=VerbError(
                code="HYDRATE_NOT_CLASSIFIED",
                message=(
                    "email has not been classified yet — wait for the ingest pipeline. "
                    "FR-2.3 hard invariant: no body access before sensitivity classification."
                ),
            ),
        )

    # All gates passed — charge the counter and return.
    _SESSION_HYDRATION_COUNTS[session_id] = _SESSION_HYDRATION_COUNTS.get(session_id, 0) + 1
    return HydrateEmailOut(ok=True, email=_row_to_hydrated(row))


__all__ = ["hydrate_email", "reset_hydration_count"]
