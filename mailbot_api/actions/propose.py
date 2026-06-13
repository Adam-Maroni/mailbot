"""propose_action verb — Story 4-2.

Single entry point for proposing an action. Enforces FR-5.6 (agent cannot
promote tier) at the verb boundary AND captures the Tier-3 ETag at propose
time. The schema-level CHECK constraints in migrations 015/016 are the
defense-in-depth layer.

Routing rules (per epics.md Story 4.2 AC):
  - Tier 0 → refused (TIER_0_NOT_QUEUEABLE)
  - Tier 1 → inserted as status="pending", no change_marker captured
  - Tier 2 → inserted as status="pending_grant", no change_marker captured
  - Tier 3 SEND family → status="cooling_off", change_marker captured (60s cooldown via Story 4-6)
  - Tier 3 DELETE / other non-SEND Tier 3 → status="pending", change_marker captured
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from mailbot_api.actions.recovery_action import RecoveryAction
from mailbot_api.actions.types import (
    EMAIL_LESS_ACTIONS,
    ActionType,
    is_send_family,
    requires_grant,
    tier_for,
)
from mailbot_api.db.connection import (
    execute_insert_returning_id,
    fetchone,
)
from mailbot_api.db.queries import (
    EMAIL_MARKER_AND_DELETED_AT_SELECT,
    PENDING_ACTION_INSERT,
)

_logger = logging.getLogger(__name__)


ProposeErrorCode = Literal[
    "INVALID_ACTION_TYPE",
    "TIER_PROMOTION_ATTEMPT",
    "TIER_0_NOT_QUEUEABLE",
    "EMAIL_NOT_FOUND",
    "EMAIL_NEVER_SYNCED",
    "EMAIL_DELETED",
    "INVALID_PAYLOAD",
]


class ProposeActionError(BaseModel):
    """Refusal carrier returned inside ProposeActionOut.error.

    Story 6-19 (F29 closure): added optional ``valid_action_types`` field
    populated by the verb shim on the INVALID_ACTION_TYPE path ONLY.
    Carries the canonical 23 ActionType member values (sorted snake_case
    string tuple) so an agent that hallucinated an action_type name can
    self-correct in a single turn. None for every other error code.

    CR-2 (2026-06-06, sonnet-4-6 review): the field is typed
    ``tuple[str, ...] | None`` (not ``list[str] | None``) so the recovery
    hint is immutable end-to-end. Even though Pydantic's ``frozen=True``
    forbids field reassignment, it does NOT prevent in-place mutation of
    a mutable list value. Tuple defense-in-depth signals "read-only
    recovery hint" structurally and turns mutation attempts into TypeError.
    """

    model_config = ConfigDict(frozen=True)

    code: ProposeErrorCode
    message: str
    valid_action_types: tuple[str, ...] | None = None
    # Story 7-0-c24: RecoveryAction envelope — the universal next-step
    # contract carried on every refusal/blocked/terminal response. MVP
    # propagation in this story: INVALID_ACTION_TYPE path (Story 6-19's
    # valid_action_types special-case field is migrated INTO this envelope
    # while being RETAINED for back-compat per the design doc convention).
    # Broader propagation to other ProposeErrorCode branches is named
    # carry-forward C24-FU-1.
    recovery_action: RecoveryAction | None = None


class ProposeActionOut(BaseModel):
    """Result of a propose_action() call. Either ok=True with action_id+tier+status,
    or ok=False with error populated.

    Story 7-0-f30-f31 (F30 HIGH + F31 LOW closures): added
    ``requires_grant`` + ``requires_per_action_confirmation`` boolean signals
    on the SUCCESS path so the agent has in-band recovery hints for the
    Tier-3 SEND grant-mint flow + the per-action confirmation rule. Both
    fields default to ``False`` on the refusal path (no signal needed when
    the action did not enter pending_actions). On the success path they are
    derived from the registry helpers ``requires_grant(action_type)`` +
    ``is_send_family(action_type)`` so adding a new ActionType later
    automatically gets correct signal-field population.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    action_id: int | None = None
    tier: Literal[0, 1, 2, 3] | None = None
    status: Literal["pending", "cooling_off", "pending_grant"] | None = None
    error: ProposeActionError | None = None
    requires_grant: bool = False
    requires_per_action_confirmation: bool = False
    # Story 7-0-c24: RecoveryAction envelope — populated on the success-
    # return path with a mint_grant next-call hint when requires_grant=True.
    # The bare booleans above are RETAINED per back-compat convention; the
    # envelope ships the structured tool_name + args_hint contract that
    # generalizes across all signal-expressivity surfaces. None when
    # requires_grant=False (no next-call signal needed).
    recovery_action: RecoveryAction | None = None


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with `Z` suffix (per AR-PAT-3)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _capture_change_marker(
    db_path: str, email_id: str
) -> tuple[str | None, ProposeActionError | None]:
    """Look up emails.change_marker + deleted_at for a Tier-3 propose.

    Returns (change_marker, None) on success, or (None, ProposeActionError) on
    a refusal condition (EMAIL_NOT_FOUND / EMAIL_DELETED).
    """
    row = await fetchone(db_path, EMAIL_MARKER_AND_DELETED_AT_SELECT, (email_id,))
    if row is None:
        return None, ProposeActionError(
            code="EMAIL_NOT_FOUND",
            message=f"email_id {email_id!r} not found in emails table",
        )
    change_marker, deleted_at = row
    if deleted_at is not None:
        return None, ProposeActionError(
            code="EMAIL_DELETED",
            message=f"email_id {email_id!r} is soft-deleted (deleted_at={deleted_at})",
        )
    # CR-3 (4-2 review): distinct error code for never-synced rows so the
    # caller can disambiguate "row missing entirely" from "row exists but
    # the sync worker hasn't populated change_marker yet". Both are blockers
    # for a Tier-3 propose, but the operator response differs (wait for the
    # next sync iteration vs. investigate why the row is absent).
    if change_marker is None:
        return None, ProposeActionError(
            code="EMAIL_NEVER_SYNCED",
            message=f"email_id {email_id!r} exists but has NULL change_marker — "
                    "sync worker has not yet recorded a changeKey for this row",
        )
    return str(change_marker), None


def _refused(
    code: ProposeErrorCode,
    message: str,
    *,
    action_type: ActionType | None = None,
    tier: Literal[0, 1, 2, 3] | None = None,
    email_id: str | None = None,
) -> ProposeActionOut:
    """Build a refusal ProposeActionOut and emit the structured log line."""
    _logger.warning(
        "propose_action refused",
        extra={
            "event": "action.propose.refused",
            "code": code,
            "action_type": action_type.value if action_type is not None else None,
            "tier_attempted": tier,
            "email_id": email_id,
        },
    )
    return ProposeActionOut(
        ok=False,
        tier=tier,
        error=ProposeActionError(code=code, message=message),
    )


async def propose_action(
    email_id: str | None,
    action_type: ActionType,
    *,
    payload: dict[str, Any] | None = None,
    db_path: str,
) -> ProposeActionOut:
    """Validate + route + insert a new pending_actions row.

    Args:
      email_id: target email graph_id; permitted None ONLY for actions in
        EMAIL_LESS_ACTIONS (MODIFY_INBOX_RULE, MODIFY_OUTLOOK_FILTER,
        TOUCH_DELEGATED_MAILBOX).
      action_type: ActionType enum member (NOT a bare string — the verb shim
        at mailbot_api/verbs/propose_action.py handles string→enum conversion
        for MCP callers).
      payload: free-form JSON-serializable dict for action-specific arguments
        (SEND_REPLY body, MOVE_TO_USER_FOLDER target_folder_id, etc.). A
        `tier` key is refused (FR-5.6).
      db_path: MAILBOT_DB_PATH; required (no default — keeps the function
        pure and test-injectable).

    Returns:
      ProposeActionOut with ok=True + action_id on success, or ok=False +
      error populated on any refusal.
    """
    # 1. Tier-0 refusal (FR-5.6 + epic spec — Tier 0 are verb-level capabilities,
    #    they don't enter pending_actions). tier_for returns plain int; narrow
    #    to the Literal for mypy + Pydantic field-typing.
    tier = cast(Literal[0, 1, 2, 3], tier_for(action_type))
    if tier == 0:
        return _refused(
            "TIER_0_NOT_QUEUEABLE",
            "Tier 0 actions are verb-level capabilities, not user-visible "
            "actions — they do not enter pending_actions",
            action_type=action_type,
            tier=0,
            email_id=email_id,
        )

    # 2. Tier-promotion guard (FR-5.6 verb-boundary defense).
    if payload is not None and "tier" in payload:
        return _refused(
            "TIER_PROMOTION_ATTEMPT",
            "tier is computed by the verb API and cannot be agent-specified",
            action_type=action_type,
            tier=tier,
            email_id=email_id,
        )

    # 3. Email-scope validation.
    if email_id is None and action_type not in EMAIL_LESS_ACTIONS:
        return _refused(
            "INVALID_PAYLOAD",
            f"action_type {action_type.value!r} requires an email_id",
            action_type=action_type,
            tier=tier,
            email_id=None,
        )

    # 4. Capture change_marker for Tier 3 with an email_id; refuse on missing/deleted.
    change_marker: str | None = None
    initial_status: Literal["pending", "cooling_off", "pending_grant"]
    if tier == 3 and email_id is not None:
        change_marker, err = await _capture_change_marker(db_path, email_id)
        if err is not None:
            return _refused(
                err.code, err.message,
                action_type=action_type, tier=tier, email_id=email_id,
            )
        # Route Tier-3: SEND family → cooling_off (Story 4-6 ticks down); else pending.
        initial_status = "cooling_off" if is_send_family(action_type) else "pending"
    elif tier == 3:
        # Email-less Tier 3 — no change_marker to capture (no source email).
        # Still routes SEND_NEW_EMAIL through cooling_off (CR-1 from 4-2 review:
        # compose-from-scratch sends are SEND-family and deserve the 60s window
        # for /cancel). MODIFY_INBOX_RULE / MODIFY_OUTLOOK_FILTER /
        # TOUCH_DELEGATED_MAILBOX skip cooling-off — they're grant-gated.
        initial_status = "cooling_off" if is_send_family(action_type) else "pending"
    elif tier == 2:
        initial_status = "pending_grant"
    else:  # tier == 1
        initial_status = "pending"

    # 5. Serialize payload + insert.
    payload_json = json.dumps(payload or {}, sort_keys=True)
    proposed_at = _utc_now_iso()
    action_id = await execute_insert_returning_id(
        db_path,
        PENDING_ACTION_INSERT,
        (
            email_id,
            action_type.value,
            tier,
            payload_json,
            proposed_at,
            None,  # proposed_by_grant_id — set by Story 4-3's mint_grant flow later
            change_marker,
            initial_status,
        ),
    )

    _logger.info(
        "action proposed",
        extra={
            "event": "action.proposed",
            "action_id": action_id,
            "action_type": action_type.value,
            "tier": tier,
            "status": initial_status,
            "email_id": email_id,
        },
    )
    # Story 7-0-f30-f31 (F30 HIGH + F31 LOW closures): populate the in-band
    # signal fields from the registry helpers so Hermes-side flow recovers
    # without operator intervention. F30: without requires_grant on the
    # success-return, Hermes never knows to call mint_grant after a
    # Tier-3 SEND propose — drainer reverts to pending_grant forever
    # (sixth-pass walk CP-A reproduction). F31: without
    # requires_per_action_confirmation, Hermes treats the user's "send"
    # confirmation as a fresh draft request — duplicate pending_actions
    # rows result. Derivation rules:
    #   - requires_grant: Tier-2 BATCH + Tier-3 (any) need a valid
    #     action_grants row to drain (Story 4-3 + 4-4 contract).
    #   - requires_per_action_confirmation: Tier-3 SEND-family needs the
    #     user to type "send" after the cooling-off window. Tier-2 BATCH
    #     grants cover N actions of the same type without re-confirmation.
    #
    # Story 7-0-c24: ALSO populate the RecoveryAction envelope when a
    # grant is required, so Hermes has the structured next-call contract
    # (tool_name="mint_grant" + args_hint with the exact parameter shape).
    # The bare requires_grant boolean above is retained per back-compat
    # convention. The envelope is None when no grant is required.
    rg = requires_grant(action_type)
    rpac = is_send_family(action_type)
    recovery: RecoveryAction | None = None
    if rg:
        # Build the mint_grant args_hint. email_ids carries the single
        # email_id when present (Tier-3 single-action / Tier-2 single-row
        # propose) OR an empty list for email-less Tier-3 admin actions
        # (MODIFY_INBOX_RULE / MODIFY_OUTLOOK_FILTER /
        # TOUCH_DELEGATED_MAILBOX) — Hermes interpolates per the SKILL.md
        # Recovery Actions section.
        #
        # CR-2 (sonnet-4-6 review 2026-06-13): the hint uses a relative
        # ttl_seconds rather than an absolute expires_at timestamp.
        # Absolute timestamps computed at propose-time go stale if the
        # Hermes-side call to mint_grant is delayed by message latency or
        # follow-up user turns — a past expires_at would mint an
        # already-invalid grant. The relative TTL forces the consumer to
        # re-compute `expires_at = now() + ttl_seconds` at mint-time,
        # eliminating the race. 60s mirrors Story 4-6's cooling-off
        # window for symmetry.
        recovery = RecoveryAction(
            tool_name="mint_grant",
            args_hint={
                "action_type": action_type.value,
                "email_ids": [email_id] if email_id is not None else [],
                "ttl_seconds": 60,
            },
            user_facing_guidance=None,
        )
    return ProposeActionOut(
        ok=True,
        action_id=action_id,
        tier=tier,
        status=initial_status,
        error=None,
        requires_grant=rg,
        requires_per_action_confirmation=rpac,
        recovery_action=recovery,
    )


__all__ = [
    "ProposeActionError",
    "ProposeActionOut",
    "propose_action",
]
