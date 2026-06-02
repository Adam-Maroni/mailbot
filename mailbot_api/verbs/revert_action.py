"""revert_action verb shim — Story 4-8.

Pass-through to actions.reverter.revert_action.
"""

from __future__ import annotations

from mailbot_api.actions.reverter import (
    RevertOut,
)
from mailbot_api.actions.reverter import (
    revert_action as _revert_impl,
)


async def revert_action(action_id: int, *, db_path: str) -> RevertOut:
    return await _revert_impl(action_id, db_path=db_path)


__all__ = ["revert_action"]
