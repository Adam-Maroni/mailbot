"""cancel_action verb — Story 4-6.

Atomically transitions a Tier-3 SEND row from `cooling_off` → `cancelled`
if and only if it's still in the cooling_off state. Race-safe vs the
cooling-off ticker via the `AND status='cooling_off'` guard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.db.connection import execute_write
from mailbot_api.db.queries import PENDING_ACTION_CANCEL_FROM_COOLING_OFF

_logger = logging.getLogger(__name__)


class CancelActionOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    cancelled: bool
    action_id: int | None = None
    reason: Literal["action_not_in_cooling_off"] | None = None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def cancel_action(action_id: int, *, db_path: str) -> CancelActionOut:
    """Atomically cancel a cooling_off action.

    Returns ok=True regardless of whether the row was actually cancelled —
    the `cancelled` boolean tells the caller. ok=False would imply a real
    error (DB unreachable, etc.); that's left to the connection layer's
    exception handling.
    """
    rowcount = await execute_write(
        db_path,
        PENDING_ACTION_CANCEL_FROM_COOLING_OFF,
        (_iso_now(), action_id),
    )
    if rowcount == 1:
        _logger.info(
            "action cancelled",
            extra={"event": "action.cancelled", "action_id": action_id},
        )
        return CancelActionOut(ok=True, cancelled=True, action_id=action_id)
    _logger.info(
        "action cancel no-op",
        extra={
            "event": "action.cancel.noop",
            "action_id": action_id,
            "reason": "action_not_in_cooling_off",
        },
    )
    return CancelActionOut(
        ok=True,
        cancelled=False,
        action_id=action_id,
        reason="action_not_in_cooling_off",
    )


__all__ = ["CancelActionOut", "cancel_action"]
