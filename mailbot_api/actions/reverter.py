"""Tier-1 24-hour reverter — Story 4-8 (+ Story 10-2 move-family support).

`revert_action(action_id)` consults the action_history row + inverse-action
map, constructs an inverse pending_actions row, and re-queues it for the
drainer. Refuses cases:
  - non-existent action
  - tier != 1 (higher tiers require fresh propose + grant)
  - status != 'applied' (only applied actions are revertible)
  - terminal_at + 24h < now() (revert window closed)
  - action_history.reverted_at IS NOT NULL (already reverted)
  - move-family action with missing/legacy-empty pre_state (PRE_STATE_MISSING
    — legacy rows drained before Story 10-2 have pre_state='{}'; never guess
    a destination)

Two inverse strategies:
  - Static map (Story 4-8): MARK_READ↔MARK_UNREAD, ADD↔REMOVE_LOCAL_CATEGORY.
  - State-dependent (Story 10-2): a Tier-1 move reverts as another
    MOVE_TO_TRIAGE_FOLDER row (the Tier-1 move primitive — same Graph seam)
    targeting pre_state.source_folder_id, payload-marked with the reserved
    REVERT_OF_ACTION_ID_KEY so the drainer bypasses the target_deleted gate
    (the original move soft-deleted the local row, 10-1 walk F5) and repairs
    the local soft-delete on applied.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.types import (
    REVERT_OF_ACTION_ID_KEY,
    ActionType,
    is_move_family,
    tier_for,
)
from mailbot_api.db.connection import (
    execute_insert_returning_id,
    execute_write,
    fetchone,
)
from mailbot_api.db.queries import (
    ACTION_HISTORY_INSERT_IF_ABSENT,
    ACTION_HISTORY_MARK_REVERTED,
    ACTION_HISTORY_SELECT_BY_ACTION_ID,
    PENDING_ACTION_INSERT,
    PENDING_ACTION_SELECT_BY_ID,
)

_logger = logging.getLogger(__name__)

REVERT_WINDOW = timedelta(hours=24)


# Tier-1 static inverse-action map (Story 4-8). Move-family inverses are
# state-dependent and handled by the Story 10-2 pre_state branch instead.
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
    "PRE_STATE_MISSING",
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


def _extract_source_folder_id(pre_state_json: str | None) -> str | None:
    """Story 10-2: parse action_history.pre_state and return source_folder_id,
    or None for missing/legacy-empty/malformed pre_state (→ PRE_STATE_MISSING).
    """
    if not pre_state_json:
        return None
    try:
        pre_state = json.loads(pre_state_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(pre_state, dict):
        return None
    source_folder_id = pre_state.get("source_folder_id")
    if not isinstance(source_folder_id, str) or not source_folder_id:
        return None
    return source_folder_id


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

    # Resolve inverse. Move-family (Story 10-2): state-dependent — re-move the
    # email back to pre_state.source_folder_id via another Tier-1 move row.
    # Any move-family action reaching this point is Tier-1 (the tier gate
    # above already refused everything else), i.e. MOVE_TO_TRIAGE_FOLDER.
    action_type = ActionType(action_type_str)
    inverse_payload_json: str
    if is_move_family(action_type):
        source_folder_id = _extract_source_folder_id(
            history_row[0] if history_row is not None else None,
        )
        if source_folder_id is None:
            return RevertOut(
                ok=False,
                error=RevertError(
                    code="PRE_STATE_MISSING",
                    message=f"action_id {action_id} has no usable pre_state "
                            "(source_folder_id) — rows drained before Story 10-2 "
                            "recorded pre_state='{}'; refusing to guess a "
                            "destination folder",
                ),
            )
        inverse = action_type  # the Tier-1 move primitive, same Graph seam
        inverse_payload_json = json.dumps(
            {
                "destination_folder_id": source_folder_id,
                REVERT_OF_ACTION_ID_KEY: action_id,
            },
            sort_keys=True,
        )
    else:
        maybe_inverse = _INVERSE_ACTION.get(action_type)
        if maybe_inverse is None:
            return RevertOut(
                ok=False,
                error=RevertError(
                    code="INVERSE_UNAVAILABLE",
                    message=f"no Tier-1 inverse available for {action_type.value!r}",
                ),
            )
        inverse = maybe_inverse
        inverse_payload_json = payload_json or "{}"

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

    # CR-10-2-1: atomically CLAIM the revert BEFORE queueing the inverse row.
    # Every fetchone/execute_write in this function is its own transaction, so
    # two concurrent revert_action calls can both pass the ALREADY_REVERTED
    # gate read above. ACTION_HISTORY_MARK_REVERTED is guarded by
    # `AND reverted_at IS NULL`, so exactly one racer's UPDATE hits a row —
    # the loser sees rowcount 0 and refuses here instead of queueing a
    # duplicate inverse (for a move, a second real Graph dispatch). If the
    # insert below then fails, the row is marked reverted with no inverse
    # queued — recoverable and strictly safer than the duplicate dispatch.
    #
    # CR-10-2-D1 closure (Story 10.5.4): action_history may not exist for this
    # action_id (Story 4-4 writes it during drain; legacy pre-4-4 rows may lack
    # one). Previously the revert proceeded UNCLAIMED for such rows, so two
    # concurrent reverts of a legacy static-map row could both queue an inverse.
    # We now INSERT OR IGNORE a placeholder history row first (action_id is the
    # PK → serialized), making the subsequent MARK_REVERTED claim uniform for
    # legacy rows too. Move-family rows never reach here without history — they
    # refuse PRE_STATE_MISSING above — so this placeholder only ever backs a
    # static-map (mark/category) inverse, whose pre_state is unused.
    if history_row is None:
        await execute_write(
            db_path,
            ACTION_HISTORY_INSERT_IF_ABSENT,
            (action_id, "{}", proposed_at),
        )
    claimed = await execute_write(
        db_path, ACTION_HISTORY_MARK_REVERTED, (proposed_at, action_id),
    )
    if claimed == 0:
        return RevertOut(
            ok=False,
            error=RevertError(
                code="ALREADY_REVERTED",
                message=f"action_id {action_id} was already reverted by a "
                        "concurrent revert call",
            ),
        )

    revert_action_id = await execute_insert_returning_id(
        db_path,
        PENDING_ACTION_INSERT,
        (
            email_id,
            inverse.value,
            inverse_tier,
            inverse_payload_json,
            proposed_at,
            None,  # proposed_by_grant_id — Tier-1 doesn't need a grant
            None,  # change_marker_at_propose — Tier-1 doesn't capture
            "pending",
        ),
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
