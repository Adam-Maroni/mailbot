"""Grant authorization layer — Story 4-3.

mint_grant + is_grant_valid + revoke_grant: the Tier-2/3 grant infrastructure
that Story 4-4's drainer consults at its second-auth-check.

Defender-bias rules:
  - Grants are short by design (max 24h window from now).
  - Grants are bounded (max 200 email_ids per grant — bulk operations beyond
    this require a fresh grant; prevents one-grant-rules-them-all anti-pattern).
  - Tier-0 / Tier-1 actions can't be granted — they don't need a grant per
    FR-5.1 (Tier-1 auto-approved + revertible) and Story 4-2's verb boundary
    (Tier-0 never queues). Refusing the mint surfaces redundant operations.

References:
  - FR-5.2 — Tier 2 batched approval (grant-gated)
  - FR-5.3 — Tier 3 explicit approval (grant-gated + ETag + cooling-off)
  - AR-D6-1..4 — grant scope/expiry/revocation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.types import ActionType, tier_for
from mailbot_api.db.connection import (
    execute_insert_returning_id,
    execute_write,
    fetchall,
)
from mailbot_api.db.queries import (
    ACTION_GRANT_FIND_VALID,
    ACTION_GRANT_INSERT,
    ACTION_GRANT_REVOKE,
    PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE,
)

_logger = logging.getLogger(__name__)

MAX_GRANT_WINDOW = timedelta(hours=24)
MAX_BATCH_SIZE = 200


MintGrantErrorCode = Literal[
    "INVALID_ACTION_TYPE",
    "EXPIRES_AT_IN_PAST",
    "GRANT_WINDOW_TOO_LARGE",
    "BATCH_TOO_LARGE",
    "GRANT_NOT_NEEDED",
]

RevokeGrantErrorCode = Literal["GRANT_NOT_FOUND"]


class MintGrantError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: MintGrantErrorCode
    message: str


class MintGrantOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    grant_id: int | None = None
    expires_at: str | None = None
    email_count: int | None = None
    error: MintGrantError | None = None


class RevokeGrantError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: RevokeGrantErrorCode
    message: str


class RevokeGrantOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    grant_id: int | None = None
    revoked_at: str | None = None
    error: RevokeGrantError | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def mint_grant(
    action_type: ActionType,
    email_ids: list[str],
    expires_at: datetime,
    *,
    db_path: str,
) -> MintGrantOut:
    """Mint a scoped time-bounded grant for a Tier-2/3 action.

    Validates expires_at, window size, batch size, and tier eligibility BEFORE
    any DB write. Returns the new grant's id + minted/expires timestamps on
    success.
    """
    # Tier check first — fastest refusal, no DB read needed.
    tier = tier_for(action_type)
    if tier < 2:
        return _refuse_mint(
            "GRANT_NOT_NEEDED",
            f"action_type {action_type.value!r} (tier {tier}) does not require a grant "
            "(Tier 0 verbs are never queued; Tier 1 is auto-approved per FR-5.1)",
            action_type=action_type,
        )

    # Normalize expires_at to UTC if naive.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = _utc_now()

    if expires_at <= now:
        return _refuse_mint(
            "EXPIRES_AT_IN_PAST",
            f"expires_at {_iso(expires_at)} is not strictly in the future",
            action_type=action_type,
        )

    if expires_at > now + MAX_GRANT_WINDOW:
        return _refuse_mint(
            "GRANT_WINDOW_TOO_LARGE",
            f"expires_at {_iso(expires_at)} exceeds the {MAX_GRANT_WINDOW} max window "
            "(defender bias: grants are short by design)",
            action_type=action_type,
        )

    if len(email_ids) > MAX_BATCH_SIZE:
        return _refuse_mint(
            "BATCH_TOO_LARGE",
            f"email_ids batch size {len(email_ids)} exceeds the {MAX_BATCH_SIZE} max "
            "(bulk operations beyond this require a fresh grant)",
            action_type=action_type,
        )

    email_ids_json = json.dumps(email_ids)
    minted_at_iso = _iso(now)
    expires_at_iso = _iso(expires_at)

    grant_id = await execute_insert_returning_id(
        db_path,
        ACTION_GRANT_INSERT,
        (action_type.value, email_ids_json, expires_at_iso, minted_at_iso),
    )

    # F22 (Story 6-6.5 walk, 2026-06-04): wake pending_grant rows waiting on
    # this action_type. Filters by action_type only — is_grant_valid() at
    # drain time re-checks email_id membership against the JSON list.
    promoted = await execute_write(
        db_path, PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE, (action_type.value,),
    )

    _logger.info(
        "action grant minted",
        extra={
            "event": "action.grant.minted",
            "grant_id": grant_id,
            "action_type": action_type.value,
            "email_count": len(email_ids),
            "expires_at": expires_at_iso,
            "pending_grant_promoted": promoted,
        },
    )
    return MintGrantOut(
        ok=True,
        grant_id=grant_id,
        expires_at=expires_at_iso,
        email_count=len(email_ids),
        error=None,
    )


def _refuse_mint(
    code: MintGrantErrorCode,
    message: str,
    *,
    action_type: ActionType | None = None,
) -> MintGrantOut:
    _logger.warning(
        "mint_grant refused",
        extra={
            "event": "action.grant.mint_refused",
            "code": code,
            "action_type": action_type.value if action_type is not None else None,
        },
    )
    return MintGrantOut(ok=False, error=MintGrantError(code=code, message=message))


async def is_grant_valid(
    action_type: ActionType,
    email_id: str | None,
    *,
    db_path: str,
) -> tuple[bool, int | None]:
    """Return (True, grant_id) iff a valid unrevoked unexpired grant covers
    (action_type, email_id). Return (False, None) otherwise.

    Tier-1 callers shouldn't invoke this (Tier-1 doesn't need a grant per
    FR-5.1). If they do, returns (False, None) — defensive no-op.

    An action_grants row with an empty email_ids list (`[]`) matches ANY
    target email_id — that's the email-less-grant case (e.g.,
    MODIFY_INBOX_RULE) where the grant scopes by action_type alone.
    """
    if tier_for(action_type) < 2:
        # Defensive — Tier-0/1 never need grants. Drainer should branch
        # before calling this. Returning (False, None) is the safe no-op.
        return (False, None)

    now_iso = _iso(_utc_now())
    rows = await fetchall(db_path, ACTION_GRANT_FIND_VALID, (action_type.value, now_iso))

    for grant_id, email_ids_blob in rows:
        try:
            email_ids_list = json.loads(email_ids_blob)
        except (TypeError, json.JSONDecodeError):
            continue  # corrupted row — skip rather than crash
        if not isinstance(email_ids_list, list):
            continue
        # Empty list = email-less grant — matches any email_id (or None).
        if len(email_ids_list) == 0:
            return (True, int(grant_id))
        # Non-empty list — must contain the target email_id.
        if email_id is not None and email_id in email_ids_list:
            return (True, int(grant_id))

    return (False, None)


async def revoke_grant(grant_id: int, *, db_path: str) -> RevokeGrantOut:
    """Revoke a grant by setting revoked_at = now. Refuses if the row doesn't
    exist OR is already revoked (defensive — surfaces the no-op rather than
    silently succeeding)."""
    now_iso = _iso(_utc_now())
    rowcount = await execute_write(db_path, ACTION_GRANT_REVOKE, (now_iso, grant_id))
    if rowcount != 1:
        _logger.warning(
            "revoke_grant refused",
            extra={
                "event": "action.grant.revoke_refused",
                "code": "GRANT_NOT_FOUND",
                "grant_id": grant_id,
            },
        )
        return RevokeGrantOut(
            ok=False,
            error=RevokeGrantError(
                code="GRANT_NOT_FOUND",
                message=f"grant_id {grant_id} not found or already revoked",
            ),
        )

    _logger.info(
        "action grant revoked",
        extra={
            "event": "action.grant.revoked",
            "grant_id": grant_id,
        },
    )
    return RevokeGrantOut(ok=True, grant_id=grant_id, revoked_at=now_iso, error=None)


__all__ = [
    "MAX_BATCH_SIZE",
    "MAX_GRANT_WINDOW",
    "MintGrantError",
    "MintGrantOut",
    "RevokeGrantError",
    "RevokeGrantOut",
    "is_grant_valid",
    "mint_grant",
    "revoke_grant",
]
