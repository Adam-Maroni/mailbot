"""Story 4-5 — `mailbot replay <action_id>` implementation.

Re-queues a terminal-failed pending_actions row for re-drain by the worker.
Refuses if:
  - the row doesn't exist
  - the row's terminal_at is older than 7 days
  - the row's action_type is Tier-2/3 AND no valid grant currently covers
    (action_type, email_id)

Returns a structured ReplayResult so the CLI can map to exit codes (0 success,
2 refused, 1 generic error).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.authorization import is_grant_valid
from mailbot_api.actions.types import ActionType, is_move_family, tier_for
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_SOFT_DELETE_STATE_SELECT,
    PENDING_ACTION_REPLAY_RESET,
    PENDING_ACTION_SELECT_BY_ID,
)

_logger = logging.getLogger(__name__)

REPLAY_WINDOW = timedelta(days=7)


ReplayErrorCode = Literal[
    "ACTION_NOT_FOUND",
    "ACTION_NOT_FAILED",
    "REPLAY_WINDOW_EXPIRED",
    "GRANT_INVALID",
    "REPLAY_MOVE_TARGET_DELETED",
]


class ReplayError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: ReplayErrorCode
    message: str


class ReplayResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    action_id: int | None = None
    error: ReplayError | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def replay_action(action_id: int, *, db_path: str) -> ReplayResult:
    row = await fetchone(db_path, PENDING_ACTION_SELECT_BY_ID, (action_id,))
    if row is None:
        return ReplayResult(
            ok=False,
            error=ReplayError(
                code="ACTION_NOT_FOUND",
                message=f"action_id {action_id} not found in pending_actions",
            ),
        )

    (
        row_id, email_id, action_type_str, _tier, _payload, _proposed_at,
        _proposed_by_grant_id, _change_marker_at_propose, status,
        _retry_count, _failure_reason, terminal_at, _budget_consumed,
    ) = row

    if status != "failed":
        return ReplayResult(
            ok=False,
            error=ReplayError(
                code="ACTION_NOT_FAILED",
                message=f"action_id {action_id} is in status {status!r}; "
                        "only 'failed' actions can be replayed",
            ),
        )

    if terminal_at is None:
        # Defensive — a failed row should always have terminal_at; if not, treat
        # as still-active and refuse.
        return ReplayResult(
            ok=False,
            error=ReplayError(
                code="REPLAY_WINDOW_EXPIRED",
                message=f"action_id {action_id} has no terminal_at — cannot replay",
            ),
        )

    elapsed = _utc_now() - _parse_iso(terminal_at)
    if elapsed > REPLAY_WINDOW:
        return ReplayResult(
            ok=False,
            error=ReplayError(
                code="REPLAY_WINDOW_EXPIRED",
                message=f"action_id {action_id} terminal_at is more than "
                        f"{REPLAY_WINDOW.days} days old — replay window expired",
            ),
        )

    action_type = ActionType(action_type_str)
    if tier_for(action_type) >= 2:
        ok_grant, _ = await is_grant_valid(action_type, email_id, db_path=db_path)
        if not ok_grant:
            return ReplayResult(
                ok=False,
                error=ReplayError(
                    code="GRANT_INVALID",
                    message=f"no valid grant covers ({action_type.value}, {email_id}); "
                            "mint a fresh grant first",
                ),
            )

    # Story 10.5.4 (F-10-6-2): a move-family action soft-deletes its local row
    # via the move-out delta (10-1 walk F5). Re-queuing it here is INERT — the
    # drainer's Tier-1 check re-reads the same `deleted_at IS NOT NULL` and
    # re-refuses `target_deleted` (only revert rows carry the bypass). Refuse
    # with a distinct, actionable code instead of a silent no-op re-queue:
    # the operator wants to UNDO a move whose target vanished, which is exactly
    # what `mailbot revert <id>` does (it re-moves to pre_state.source_folder_id
    # AND repairs the local soft-delete). Routing replay through the revert
    # bypass would re-execute the ORIGINAL move (wrong direction) or duplicate a
    # Graph dispatch — so we direct, not auto-route.
    if is_move_family(action_type) and email_id is not None:
        email_state = await fetchone(
            db_path, EMAIL_SOFT_DELETE_STATE_SELECT, (email_id,),
        )
        # CR-10-5-4-2: scope the refusal to the SOFT-DELETED case only —
        # `email_state[0]` (deleted_at) IS NOT NULL. Do NOT collapse the
        # "row entirely absent" case (`email_state is None`) into this branch:
        # for an absent local row the drainer's own `target_deleted` handling
        # (Rule 1 edge) applies and neither `revert` nor `resurrect` is a clean
        # recovery (revert would need a populated pre_state that a never-synced
        # row can't have; resurrect refuses EMAIL_NOT_FOUND). So the F-10-6-2
        # non-inert refusal + dual recovery-path hint fires only when the row is
        # genuinely soft-deleted — where BOTH `revert` and `resurrect` apply.
        if email_state is not None and email_state[0] is not None:
            return ReplayResult(
                ok=False,
                error=ReplayError(
                    code="REPLAY_MOVE_TARGET_DELETED",
                    message=f"action_id {action_id} is a move-family action whose "
                            f"target email {email_id!r} is soft-deleted (the move "
                            "removed it from the synced folder set). Replay would be "
                            "inert — the drainer re-refuses target_deleted. To undo "
                            f"the move, run `mailbot revert {action_id}` (re-moves to "
                            "the original folder and repairs the local row), or "
                            "`mailbot resurrect <graph_id>` to clear just the local "
                            "soft-delete.",
                ),
            )

    rowcount = await execute_write(db_path, PENDING_ACTION_REPLAY_RESET, (action_id,))
    if rowcount != 1:
        return ReplayResult(
            ok=False,
            error=ReplayError(
                code="ACTION_NOT_FAILED",
                message=f"action_id {action_id} was not in 'failed' status at reset",
            ),
        )

    _logger.info(
        "action replayed",
        extra={
            "event": "action.replayed",
            "original_action_id": action_id,
            "action_type": action_type.value,
        },
    )
    return ReplayResult(ok=True, action_id=action_id, error=None)


__all__ = [
    "REPLAY_WINDOW",
    "ReplayError",
    "ReplayResult",
    "replay_action",
]
