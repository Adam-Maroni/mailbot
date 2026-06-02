"""propose_action verb shim — Story 4-2 AC-11.

Agent-facing MCP entry point. The agent passes `action_type` as a string
(JSON); this shim converts to ActionType and surfaces a clean error if the
string is unknown. All other validation lives in mailbot_api.actions.propose.
"""

from __future__ import annotations

from typing import Any

from mailbot_api.actions.propose import (
    ProposeActionError,
    ProposeActionOut,
)
from mailbot_api.actions.propose import (
    propose_action as _propose_action_impl,
)
from mailbot_api.actions.types import ActionType


async def propose_action(
    email_id: str | None,
    action_type: str,
    payload: dict[str, Any] | None = None,
    *,
    db_path: str,
) -> ProposeActionOut:
    """MCP-facing wrapper around mailbot_api.actions.propose.propose_action.

    Converts the agent's JSON-string `action_type` to an ActionType enum
    member; returns INVALID_ACTION_TYPE on any unknown string.
    """
    try:
        at = ActionType(action_type)
    except ValueError:
        return ProposeActionOut(
            ok=False,
            error=ProposeActionError(
                code="INVALID_ACTION_TYPE",
                message=f"unknown action_type {action_type!r}",
            ),
        )

    return await _propose_action_impl(
        email_id,
        at,
        payload=payload,
        db_path=db_path,
    )


__all__ = ["propose_action"]
