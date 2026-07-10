"""mint_sensitivity_token verb — Story 4-7.

Tier-0 verb. Refuses confidential emails (unconditionally per NFR-PRIV-2).
Refuses normal emails (don't need a token). Mints for sensitive emails.

The returned `token` is the secret value the agent passes back to
`ask_router(..., confirmation_token=<value>)`. The `grant_id` is a short
hash for audit linkage — appears in logs + router_calls rows.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.sensitivity_tokens import mint
from mailbot_api.actions.user_confirmation import consume_sensitivity_confirmation
from mailbot_api.db.connection import fetchone
from mailbot_api.db.queries import EMAIL_SENSITIVITY_SELECT

_logger = logging.getLogger(__name__)


MintSensitivityTokenErrorCode = Literal[
    "EMAIL_NOT_FOUND",
    "EMAIL_NOT_SENSITIVE",
    "SENSITIVITY_BLOCKS_API",
    "SENSITIVITY_NOT_CLASSIFIED",
    "NEEDS_USER_CONFIRMATION",
]


class MintSensitivityTokenError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: MintSensitivityTokenErrorCode
    message: str


class MintSensitivityTokenOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    token: str | None = None
    expires_at: str | None = None
    grant_id: str | None = None
    error: MintSensitivityTokenError | None = None


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


async def mint_sensitivity_token(
    email_id: str, task_type: str, *, db_path: str,
) -> MintSensitivityTokenOut:
    row = await fetchone(db_path, EMAIL_SENSITIVITY_SELECT, (email_id,))
    if row is None:
        return MintSensitivityTokenOut(
            ok=False,
            error=MintSensitivityTokenError(
                code="EMAIL_NOT_FOUND",
                message=f"email_id {email_id!r} not found",
            ),
        )
    sensitivity_value = row[0]
    if sensitivity_value == "confidential":
        return MintSensitivityTokenOut(
            ok=False,
            error=MintSensitivityTokenError(
                code="SENSITIVITY_BLOCKS_API",
                message="confidential emails admit no API override",
            ),
        )
    if sensitivity_value == "normal":
        return MintSensitivityTokenOut(
            ok=False,
            error=MintSensitivityTokenError(
                code="EMAIL_NOT_SENSITIVE",
                message="email is not sensitive; no confirmation token required",
            ),
        )
    if sensitivity_value != "sensitive":
        # CR-4-7-7: distinguish "not yet classified" (NULL) from "unknown
        # future label". The previous EMAIL_NOT_FOUND code conflated this
        # with "row missing" and caused callers to give up rather than wait
        # for the ingest pipeline's sensitivity step to finish.
        return MintSensitivityTokenOut(
            ok=False,
            error=MintSensitivityTokenError(
                code="SENSITIVITY_NOT_CLASSIFIED",
                message=(
                    "email sensitivity not yet classified; run the ingest "
                    "pipeline's sensitivity_class step first"
                    if sensitivity_value is None
                    else f"unexpected sensitivity value {sensitivity_value!r}"
                ),
            ),
        )

    # Story 10.5.2 (F-10-5-5): minting is NOT agent-assertable. A genuine
    # user-gated confirmation record — created only at the chat boundary on a
    # real user-role "yes, escalate" — must exist and is consumed single-use
    # here. An agent that only issues verb calls cannot manufacture it, so it
    # cannot self-authorize the escalation.
    confirmed = await consume_sensitivity_confirmation(
        db_path, email_id=email_id, task_type=task_type,
    )
    if not confirmed:
        # Live-walk fix (F-10-5-2-W1): in the real Discord flow the persona
        # self-refuses and the agent's mint attempt lands in the SAME turn as
        # the user's "yes, escalate", so the boundary couldn't pre-record a
        # confirmation for this exact (email, task). If the caller armed an
        # escalation this turn, consume it here — the mint verb IS where the
        # concrete (email_id, task_type) is known — and proceed. The arm is
        # still a genuine user-gated event (only the boundary sets it on a real
        # user-role phrase); the agent cannot arm itself.
        from mailbot_api.actions.user_confirmation import (  # noqa: PLC0415
            consume_escalation_arm,
        )
        confirmed = await consume_escalation_arm(
            db_path, email_id=email_id, task_type=task_type,
        )
    if not confirmed:
        # CR-7 (Story 10.5.2): audit the refused-mint path so self-mint attempts
        # are observable (the security-relevant event is "an agent tried to mint
        # without a user confirmation").
        _logger.info(
            "sensitivity token mint refused — no user confirmation",
            extra={
                "event": "sensitivity.token.mint_refused",
                "reason": "needs_user_confirmation",
                "email_id": email_id,
                "task_type": task_type,
            },
        )
        return MintSensitivityTokenOut(
            ok=False,
            error=MintSensitivityTokenError(
                code="NEEDS_USER_CONFIRMATION",
                message=(
                    "sensitivity escalation requires a user confirmation "
                    "(reply 'yes, escalate' in chat); the agent cannot "
                    "self-authorize this mint"
                ),
            ),
        )

    token = mint(email_id, task_type)
    _logger.info(
        "sensitivity token minted",
        extra={
            "event": "sensitivity.token.minted",
            "email_id": email_id,
            "task_type": task_type,
            "grant_id": token.grant_id,  # short hash, NOT the token value
            "expires_at": _iso(token.expires_at),
        },
    )
    return MintSensitivityTokenOut(
        ok=True,
        token=token.token_value,
        expires_at=_iso(token.expires_at),
        grant_id=token.grant_id,
    )


__all__ = [
    "MintSensitivityTokenError",
    "MintSensitivityTokenOut",
    "mint_sensitivity_token",
]
