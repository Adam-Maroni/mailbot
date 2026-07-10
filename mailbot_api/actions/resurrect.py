"""Story 10.5.4 (F5/F6) — operator move-family resurrection primitive.

A `MOVE_TO_TRIAGE_FOLDER` (and every move-family action) soft-deletes the local
`emails` row via the delta-sync `@removed` path (10-1 walk F5: the move out of
the synced folder set arrives as a removal), and `EMAIL_UPSERT` never resurrects
a soft-deleted row (F6, FILED). The 10-2 revert path already un-soft-deletes on
apply (`drainer.py` clears the soft-delete for a `_is_revert_row`), but that only
covers rows still inside the 24h revert window. For rows OUTSIDE the window
(e.g. the retained 10-1 walk subject, deliberately left soft-deleted as live F6
evidence per retro B5), there was no recovery path at all — the email is
physically fine in the mailbox, but every MailBot read verb filters
`deleted_at IS NULL`, so it is invisible forever.

`resurrect_email(graph_id)` is a LOCAL-DB-ONLY repair: it clears
`deleted_at` / `removed_reason` via `EMAIL_CLEAR_SOFT_DELETE`. It issues NO Graph
write — the physical message already lives where it should; only the stale local
row needs repair. It refuses:
  - the row doesn't exist (EMAIL_NOT_FOUND)
  - the row is already live / not soft-deleted (NOT_SOFT_DELETED) — never a
    silent no-op that masquerades as a repair; idempotent-success is signalled
    explicitly via `already_live`.

Guarded on the default path by TWO conditions (CR-10-5-4-1): the row's
`removed_reason` must be `'deleted'` (the move-out signature) AND a move-family
`pending_actions` row must exist for the email — structural corroboration that a
MOVE, not a permanent Graph delete, caused the soft-delete. This matters because
the delta-sync `@removed.reason` field writes `'deleted'` for BOTH a move-out
AND a permanent mailbox delete; the reason string alone cannot distinguish them,
and resurrecting a genuinely-deleted email would make a phantom row visible to
every read verb even though the physical message is gone. `--force` (the
`allow_any_reason` flag) bypasses BOTH conditions for the rare manual case,
recorded by the caller.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.types import MOVE_FAMILY
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_CLEAR_SOFT_DELETE,
    EMAIL_HAS_MOVE_FAMILY_ACTION_COUNT,
    EMAIL_SOFT_DELETE_STATE_SELECT,
)

_logger = logging.getLogger(__name__)

# The delta-sync @removed.reason a move-out produces (Story 1-10 AC-3). The
# resurrection primitive is scoped to this by default — a 'changed' removal is a
# different case and a live row (removed_reason NULL) is not soft-deleted at all.
MOVE_SOFT_DELETE_REASON = "deleted"


ResurrectErrorCode = Literal[
    "EMAIL_NOT_FOUND",
    "NOT_SOFT_DELETED",
    "REASON_NOT_MOVE_DELETE",
    "NO_MOVE_FAMILY_ACTION",
]


class ResurrectError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: ResurrectErrorCode
    message: str


class ResurrectResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    graph_id: str | None = None
    already_live: bool = False
    error: ResurrectError | None = None


async def resurrect_email(
    graph_id: str,
    *,
    db_path: str,
    allow_any_reason: bool = False,
) -> ResurrectResult:
    """Clear a move-family soft-delete on the local `emails` row (no Graph write).

    Returns a structured result so the CLI can map to exit codes (0 success,
    2 refused). Idempotent: resurrecting a row that isn't soft-deleted is NOT an
    error the operator must recover from — it is reported as `already_live=True`
    with ok=False + NOT_SOFT_DELETED so the caller can distinguish "I repaired
    it" from "nothing to repair" without treating the latter as a hard failure.
    """
    row = await fetchone(db_path, EMAIL_SOFT_DELETE_STATE_SELECT, (graph_id,))
    if row is None:
        return ResurrectResult(
            ok=False,
            graph_id=graph_id,
            error=ResurrectError(
                code="EMAIL_NOT_FOUND",
                message=f"graph_id {graph_id!r} not found in emails",
            ),
        )

    deleted_at, removed_reason = row
    if deleted_at is None:
        return ResurrectResult(
            ok=False,
            graph_id=graph_id,
            already_live=True,
            error=ResurrectError(
                code="NOT_SOFT_DELETED",
                message=f"graph_id {graph_id!r} is not soft-deleted "
                        "(deleted_at IS NULL) — nothing to resurrect",
            ),
        )

    if not allow_any_reason:
        if removed_reason != MOVE_SOFT_DELETE_REASON:
            return ResurrectResult(
                ok=False,
                graph_id=graph_id,
                error=ResurrectError(
                    code="REASON_NOT_MOVE_DELETE",
                    message=f"graph_id {graph_id!r} was soft-deleted with "
                            f"removed_reason={removed_reason!r}, not "
                            f"{MOVE_SOFT_DELETE_REASON!r} — pass allow_any_reason to "
                            "resurrect a non-move-delete removal",
                ),
            )

        # CR-10-5-4-1: `removed_reason='deleted'` is written for BOTH a move-out
        # AND a permanent Graph delete. Require structural corroboration that a
        # MOVE happened (a move-family pending_actions row for this email) before
        # resurrecting on the default path — otherwise `resurrect` could revive a
        # phantom row for a genuinely-deleted message. `--force` bypasses this.
        move_family_values = tuple(a.value for a in MOVE_FAMILY)
        placeholders = ",".join("?" * len(move_family_values))
        count_row = await fetchone(
            db_path,
            EMAIL_HAS_MOVE_FAMILY_ACTION_COUNT.format(placeholders=placeholders),
            (graph_id, *move_family_values),
        )
        if count_row is None or int(count_row[0]) == 0:
            return ResurrectResult(
                ok=False,
                graph_id=graph_id,
                error=ResurrectError(
                    code="NO_MOVE_FAMILY_ACTION",
                    message=f"graph_id {graph_id!r} is soft-deleted "
                            f"(removed_reason={removed_reason!r}) but has NO "
                            "move-family action on record — the removal may be a "
                            "permanent Graph delete, not a move. Resurrecting would "
                            "revive a row for a message that no longer exists. Pass "
                            "allow_any_reason (--force) if you are certain the "
                            "message is still in the mailbox.",
                ),
            )

    await execute_write(db_path, EMAIL_CLEAR_SOFT_DELETE, (graph_id,))

    _logger.info(
        "email resurrected",
        extra={
            "event": "email.resurrected",
            "graph_id": graph_id,
            "prior_removed_reason": removed_reason,
        },
    )
    return ResurrectResult(ok=True, graph_id=graph_id)


__all__ = [
    "MOVE_SOFT_DELETE_REASON",
    "ResurrectError",
    "ResurrectResult",
    "resurrect_email",
]
