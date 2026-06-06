"""propose_action verb shim — Story 4-2 AC-11.

Agent-facing MCP entry point. The agent passes `action_type` as a string
(JSON); this shim converts to ActionType and surfaces a clean error if the
string is unknown. All other validation lives in mailbot_api.actions.propose.

Story 6-19 (F29 closure): the INVALID_ACTION_TYPE error path carries the
canonical 23 ActionType values as a recovery hint — both in the error
message (for agents reading only the message field) AND as a structured
``valid_action_types`` list (for agents that parse the error correctly).
The discoverable MCP resource ``mailbot://action-types`` is the
discovery-time companion (Story 6-19 AC-2).
"""

from __future__ import annotations

from typing import Any, Final

from mailbot_api.actions.propose import (
    ProposeActionError,
    ProposeActionOut,
)
from mailbot_api.actions.propose import (
    propose_action as _propose_action_impl,
)
from mailbot_api.actions.types import ActionType

# Story 6-19 (F29 closure): the canonical 23 ActionType values as a sorted
# snake_case tuple. Computed once at module import; immutable.
#
# CR-1 (2026-06-06, sonnet-4-6 review): tuple defense-in-depth — `Final`
# annotates name-binding only; `Final[list[str]]` would allow a caller to
# do `from .propose_action import _VALID_ACTION_TYPES;
# _VALID_ACTION_TYPES.append('hacked')` and contaminate ALL subsequent
# ProposeActionError responses. Using `tuple[str, ...]` makes the same
# mutation a TypeError. Used by the INVALID_ACTION_TYPE error path to
# populate the recovery hint (both in the error message and as the
# structured ``valid_action_types`` field on ProposeActionError).
_VALID_ACTION_TYPES: Final[tuple[str, ...]] = tuple(sorted(at.value for at in ActionType))


async def propose_action(
    email_id: str | None,
    action_type: str,
    payload: dict[str, Any] | None = None,
    *,
    db_path: str,
) -> ProposeActionOut:
    """MCP-facing wrapper around mailbot_api.actions.propose.propose_action.

    Converts the agent's JSON-string `action_type` to an ActionType enum
    member; returns INVALID_ACTION_TYPE on any unknown string. The error
    response carries the canonical 23 action_type values both inline in
    the error message AND as the structured ``valid_action_types`` field,
    so an agent that hallucinated a synonym (e.g., ``SEND_EMAIL`` instead
    of ``send_reply``) can self-correct in a single turn. F29 closure.
    """
    try:
        at = ActionType(action_type)
    except ValueError:
        return ProposeActionOut(
            ok=False,
            error=ProposeActionError(
                code="INVALID_ACTION_TYPE",
                message=(
                    f"unknown action_type {action_type!r}; "
                    f"must be one of {list(_VALID_ACTION_TYPES)}"
                ),
                # CR-1 (2026-06-06): pass the tuple as-is; ProposeActionError's
                # valid_action_types field is `tuple[str, ...] | None` per
                # CR-2 (sibling defense-in-depth). Pydantic accepts the tuple
                # at model construction and preserves immutability.
                valid_action_types=_VALID_ACTION_TYPES,
            ),
        )

    return await _propose_action_impl(
        email_id,
        at,
        payload=payload,
        db_path=db_path,
    )


__all__ = ["propose_action"]
