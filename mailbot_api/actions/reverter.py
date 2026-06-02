"""Tier-1 24-hour reverter — Story 4-8.

`revert_action(action_id)` consults the action_history row + inverse-action
map, constructs an inverse pending_actions row, and re-queues it for the
drainer. Refuses cases:
  - non-existent action
  - tier != 1 (higher tiers require fresh propose + grant)
  - status != 'applied' (only applied actions are revertible)
  - terminal_at + 24h < now() (revert window closed)
  - action_history.reverted_at IS NOT NULL (already reverted)
  - MOVE_TO_TRIAGE_FOLDER (no Tier-1 inverse available — pre_state path not yet filled)

Per Story 4-4's design note: pre_state is `{}` for every action today. Story 4-8
uses a hardcoded inverse-action map keyed on action_type, sidestepping the
pre_state gap. A future story that fills pre_state can support state-dependent
inverses (e.g., MOVE_TO_TRIAGE_FOLDER → MOVE_TO_<previous_folder>).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.types import ActionType, tier_for
from mailbot_api.db.connection import (
    execute_insert_returning_id,
    execute_write,
    fetchone,
)
from mailbot_api.db.queries import (
    ACTION_HISTORY_MARK_REVERTED,
    ACTION_HISTORY_SELECT_BY_ACTION_ID,
    PENDING_ACTION_INSERT,
    PENDING_ACTION_SELECT_BY_ID,
)

_logger = logging.getLogger(__name__)

REVERT_WINDOW = timedelta(hours=24)


# Tier-1 inverse-action map. Excludes MOVE_TO_TRIAGE_FOLDER (no Tier-1 inverse).
_INVERSE_ACTION: dict[ActionType, ActionType] = {
    ActionType.MARK_READ: ActionType.MARK_UNREAD,
    ActionType.MARK_UNREAD: ActionType.MARK_READ,
    ActionType.ADD_LOCAL_CATEGORY: ActionType.REMOVE_LOCAL_CATEGORY,
    ActionType.REMOVE_LOCAL_CATEGORY: ActionType.ADD_LOCAL_CATEGORY,
}


RevertErrorCode = Literal[
    "ACTION_NOT_FOUND",
    "ONLY_TIER_1_REVERTIBLE",
    "NOT_APPLIED",
    "REVERT_WINDOW_EXPIRED",
    "ALREADY_REVERTED",
    "INVERSE_UNAVAILABLE",
]


class RevertError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: RevertErrorCode
    message: str


class RevertOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    original_action_id: int | None = None
    revert_action_id: int | None = None
    error: RevertError | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def revert_action(action_id: int, *, db_path: str) -> RevertOut:
    row = await fetchone(db_path, PENDING_ACTION_SELECT_BY_ID, (action_id,))
    if row is None:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="ACTION_NOT_FOUND",
                message=f"action_id {action_id} not found",
            ),
        )

    (
        _row_id, email_id, action_type_str, tier, payload_json, _proposed_at,
        _proposed_by_grant_id, _change_marker_at_propose, status,
        _retry_count, _failure_reason, terminal_at, _budget_consumed,
    ) = row

    if tier != 1:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="ONLY_TIER_1_REVERTIBLE",
                message=f"action_id {action_id} is tier {tier}; only Tier-1 is "
                        "auto-revertible (higher tiers require a fresh action proposal)",
            ),
        )

    if status != "applied":
        return RevertOut(
            ok=False,
            error=RevertError(
                code="NOT_APPLIED",
                message=f"action_id {action_id} is in status {status!r}; "
                        "only 'applied' actions can be reverted",
            ),
        )

    if terminal_at is None:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="REVERT_WINDOW_EXPIRED",
                message=f"action_id {action_id} has no terminal_at — cannot revert",
            ),
        )

    elapsed = _utc_now() - _parse_iso(terminal_at)
    if elapsed > REVERT_WINDOW:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="REVERT_WINDOW_EXPIRED",
                message=f"action_id {action_id} terminal_at is older than "
                        f"{REVERT_WINDOW} — revert window expired",
            ),
        )

    # Check action_history for prior revert.
    history_row = await fetchone(
        db_path, ACTION_HISTORY_SELECT_BY_ACTION_ID, (action_id,),
    )
    if history_row is not None and history_row[2] is not None:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="ALREADY_REVERTED",
                message=f"action_id {action_id} was already reverted at {history_row[2]}",
            ),
        )

    # Resolve inverse.
    action_type = ActionType(action_type_str)
    inverse = _INVERSE_ACTION.get(action_type)
    if inverse is None:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="INVERSE_UNAVAILABLE",
                message=f"no Tier-1 inverse available for {action_type.value!r} "
                        "(MOVE_TO_TRIAGE_FOLDER and similar require pre_state which is not yet populated)",
            ),
        )

    # Construct the inverse pending_actions row.
    inverse_tier = tier_for(inverse)
    # Defensive — every inverse should also be Tier-1, but the map could
    # in theory drift if a future story extends it.
    if inverse_tier != 1:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="INVERSE_UNAVAILABLE",
                message=f"inverse {inverse.value!r} is tier {inverse_tier}; "
                        "reverter only constructs Tier-1 inverses",
            ),
        )

    proposed_at = _iso(_utc_now())
    revert_action_id = await execute_insert_returning_id(
        db_path,
        PENDING_ACTION_INSERT,
        (
            email_id,
            inverse.value,
            inverse_tier,
            payload_json or "{}",
            proposed_at,
            None,  # proposed_by_grant_id — Tier-1 doesn't need a grant
            None,  # change_marker_at_propose — Tier-1 doesn't capture
            "pending",
        ),
    )

    # Mark the original action_history row reverted_at. action_history row
    # may not exist for this action_id (Story 4-4 writes it during drain, but
    # only on the success path) — if absent, the revert still proceeds (we
    # already verified status='applied' which implies dispatch succeeded).
    if history_row is not None:
        await execute_write(
            db_path, ACTION_HISTORY_MARK_REVERTED, (proposed_at, action_id),
        )

    _logger.info(
        "action reverted",
        extra={
            "event": "action.reverted",
            "original_action_id": action_id,
            "revert_action_id": revert_action_id,
            "original_action_type": action_type.value,
            "inverse_action_type": inverse.value,
        },
    )
    return RevertOut(
        ok=True,
        original_action_id=action_id,
        revert_action_id=revert_action_id,
    )


__all__ = [
    "REVERT_WINDOW",
    "RevertError",
    "RevertOut",
    "revert_action",
]
