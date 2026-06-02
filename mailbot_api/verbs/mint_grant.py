"""mint_grant verb shim — Story 4-3.

Agent-facing MCP entry point. Converts the JSON-string `action_type` and
ISO-8601 `expires_at` to typed values; delegates to authorization.mint_grant.
"""

from __future__ import annotations

from datetime import datetime

from mailbot_api.actions.authorization import (
    MintGrantError,
    MintGrantOut,
)
from mailbot_api.actions.authorization import (
    mint_grant as _mint_grant_impl,
)
from mailbot_api.actions.types import ActionType


async def mint_grant(
    action_type: str,
    email_ids: list[str],
    expires_at: str,
    *,
    db_path: str,
) -> MintGrantOut:
    try:
        at = ActionType(action_type)
    except ValueError:
        return MintGrantOut(
            ok=False,
            error=MintGrantError(
                code="INVALID_ACTION_TYPE",
                message=f"unknown action_type {action_type!r}",
            ),
        )

    try:
        # fromisoformat accepts "Z" suffix in Python 3.11+; for 3.10 strip it.
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return MintGrantOut(
            ok=False,
            error=MintGrantError(
                code="EXPIRES_AT_IN_PAST",  # closest existing code; treats unparseable as past
                message=f"expires_at {expires_at!r} is not a valid ISO-8601 datetime",
            ),
        )

    return await _mint_grant_impl(at, email_ids, expires_dt, db_path=db_path)


__all__ = ["mint_grant"]
