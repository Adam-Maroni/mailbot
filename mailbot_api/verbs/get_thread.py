"""get_thread read verb — Story 5-1 AC-3.

Returns the thread's ordered projections + cached thread_continuity_note (Story 3-7)
+ message count. Bodies require separate hydrate_email calls per email_id.
"""

from __future__ import annotations

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.queries import (
    GET_THREAD_META_SELECT,
    GET_THREAD_PROJECTION_SELECT,
)
from mailbot_api.verbs.find_emails import row_to_projection
from mailbot_api.verbs.schemas import (
    GetThreadOut,
    VerbError,
)


async def get_thread(thread_id: str, *, db_path: str) -> GetThreadOut:
    """Return ordered projections for `thread_id` + thread_continuity_note."""
    meta = await fetchone(db_path, GET_THREAD_META_SELECT, (thread_id,))
    if meta is None:
        return GetThreadOut(
            ok=False,
            error=VerbError(code="THREAD_NOT_FOUND", message=f"no thread with id={thread_id!r}"),
        )

    rows = await fetchall(db_path, GET_THREAD_PROJECTION_SELECT, (thread_id,))
    return GetThreadOut(
        ok=True,
        thread_id=thread_id,
        projections=[row_to_projection(r) for r in rows],
        thread_continuity_note=meta[0],
        # Live count of non-deleted emails — intentionally NOT threads.message_count
        # (which counts pre-soft-delete; see CR finding 7 + GET_THREAD_META_SELECT
        # docstring).
        message_count=len(rows),
    )


__all__ = ["get_thread"]
