"""revoke_grant verb shim — Story 4-3.

Pass-through to authorization.revoke_grant — no string conversion needed
(grant_id is already an int from the agent's JSON payload).
"""

from __future__ import annotations

from mailbot_api.actions.authorization import (
    RevokeGrantOut,
)
from mailbot_api.actions.authorization import (
    revoke_grant as _revoke_grant_impl,
)


async def revoke_grant(grant_id: int, *, db_path: str) -> RevokeGrantOut:
    return await _revoke_grant_impl(grant_id, db_path=db_path)


__all__ = ["revoke_grant"]
