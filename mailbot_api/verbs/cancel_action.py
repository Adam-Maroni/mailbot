"""cancel_action verb shim — Story 4-6.

Pass-through to actions.cancel.cancel_action.
"""

from __future__ import annotations

from mailbot_api.actions.cancel import (
    CancelActionOut,
)
from mailbot_api.actions.cancel import (
    cancel_action as _cancel_impl,
)


async def cancel_action(action_id: int, *, db_path: str) -> CancelActionOut:
    return await _cancel_impl(action_id, db_path=db_path)


__all__ = ["cancel_action"]
