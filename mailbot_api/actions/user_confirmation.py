"""User-confirmation primitive — Story 10.5.2 (Epic 10.5 Cluster B).

The API-layer approval record that makes token/grant minting a genuinely
user-gated event, fixing:
  - F-10-5-5 (agent self-mints a sensitivity token with no user confirmation),
  - F-10-5-8 (agent mints a Tier-2 grant + queues writes with no user "yes").

The load-bearing invariant: a confirmation row is created ONLY on a genuine
USER-ROLE confirmation phrase detected at the /v1/chat/completions boundary
(`record_user_confirmation` is called there, never from an MCP verb). The mint
verbs call `consume_user_confirmation` which single-use-consumes a matching
un-expired row. An agent that only issues verb calls cannot manufacture the
row — it does not control the user-role message stream — so it cannot
self-authorize.

TTL: a short window (default 10 minutes, matching the sensitivity-token TTL)
so a stale "yes" cannot be replayed much later. Enforced in code at consume
time, not in SQL, so the window is testable + adjustable without a migration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from mailbot_api.db.connection import (
    execute_write,
    execute_write_returning,
    fetchone,
)
from mailbot_api.db.queries import (
    ESCALATION_ARMED_CLAIM,
    ESCALATION_ARMED_UPSERT,
    PENDING_GRANT_APPROVAL_CLAIM,
    PENDING_GRANT_APPROVAL_UPSERT,
    PENDING_SENSITIVE_REFUSAL_CLAIM,
    PENDING_SENSITIVE_REFUSAL_UPSERT,
    USER_CONFIRMATION_CONSUME,
    USER_CONFIRMATION_FIND_GRANT,
    USER_CONFIRMATION_FIND_SENSITIVITY,
    USER_CONFIRMATION_INSERT,
)

_logger = logging.getLogger(__name__)

CONFIRMATION_TTL = timedelta(minutes=10)

ConfirmationScope = Literal["sensitivity_token", "grant"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    # Stored via _iso(): "...Z" suffix. Normalize back to aware UTC.
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def record_sensitivity_confirmation(
    db_path: str, *, email_id: str, task_type: str,
) -> None:
    """Record a user-gated confirmation for a sensitivity escalation.

    MUST be called ONLY from the chat boundary on a genuine user-role
    confirmation phrase. Never call this from an MCP verb.
    """
    await execute_write(
        db_path,
        USER_CONFIRMATION_INSERT,
        ("sensitivity_token", email_id, task_type, None, None, _iso(_utc_now())),
    )
    _logger.info(
        "user confirmation recorded",
        extra={
            "event": "user_confirmation.recorded",
            "scope": "sensitivity_token",
            "email_id": email_id,
            "task_type": task_type,
        },
    )


def _canonical_email_ids(email_ids: list[str]) -> str:
    """Canonical JSON for email_ids so record + consume match byte-for-byte
    regardless of input order (CR-4 email-scoped grant confirmation)."""
    return json.dumps(sorted(email_ids))


async def record_grant_confirmation(
    db_path: str, *, action_type: str, email_ids: list[str],
) -> None:
    """Record a user-gated confirmation for a Tier-2 grant, scoped to the EXACT
    email set the user approved (CR-4).

    MUST be called ONLY from the chat boundary on a genuine user-role
    confirmation phrase. Never call this from an MCP verb.
    """
    await execute_write(
        db_path,
        USER_CONFIRMATION_INSERT,
        ("grant", None, None, action_type, _canonical_email_ids(email_ids), _iso(_utc_now())),
    )
    _logger.info(
        "user confirmation recorded",
        extra={
            "event": "user_confirmation.recorded",
            "scope": "grant",
            "action_type": action_type,
            "email_count": len(email_ids),
        },
    )


async def _consume(db_path: str, find_query: str, params: tuple[str, ...]) -> bool:
    """Shared single-use consume: find newest un-consumed un-expired row for
    the scope, then atomically mark it consumed. Returns True iff a valid
    confirmation was consumed."""
    row = await fetchone(db_path, find_query, params)
    if row is None:
        return False
    conf_id, created_at = row
    # TTL enforcement in code (not SQL).
    if _parse_iso(created_at) + CONFIRMATION_TTL <= _utc_now():
        return False
    # Atomic single-use consume: rowcount=1 means we won the race.
    consumed = await execute_write_returning(
        db_path,
        USER_CONFIRMATION_CONSUME + " RETURNING id",
        (_iso(_utc_now()), conf_id),
    )
    return consumed is not None


async def consume_sensitivity_confirmation(
    db_path: str, *, email_id: str, task_type: str,
) -> bool:
    """Single-use-consume a user confirmation for (email_id, task_type).

    Called by `mint_sensitivity_token`. Returns True iff a genuine, un-expired,
    un-consumed user confirmation exists for this exact scope.
    """
    return await _consume(
        db_path, USER_CONFIRMATION_FIND_SENSITIVITY, (email_id, task_type)
    )


async def consume_grant_confirmation(
    db_path: str, *, action_type: str, email_ids: list[str],
) -> bool:
    """Single-use-consume a user confirmation for a Tier-2 grant scoped to the
    EXACT (action_type, email_ids) the user approved (CR-4).

    Called by `mint_grant`. Returns True iff a genuine, un-expired, un-consumed
    user confirmation exists for this exact action_type + email set.
    """
    return await _consume(
        db_path,
        USER_CONFIRMATION_FIND_GRANT,
        (action_type, _canonical_email_ids(email_ids)),
    )


# ---------------------------------------------------------------------------
# Boundary correlation for the sensitive-escalation handshake (F-10-5-7)
# ---------------------------------------------------------------------------
#
# A bare "yes, escalate" reply carries no email id. We correlate it back to the
# caller's most-recent SENSITIVE refusal via the pending_sensitive_refusal
# table (keyed by caller_origin, NOT a session id — that divergence WAS the
# F-10-5-7 bug). The chat boundary records a pending refusal whenever it renders
# a sensitive refusal, and on a user confirmation phrase it looks the pending
# entry up, records a real user_confirmation for that (email_id, task), and
# clears the pending entry.

# Explicit, deterministic confirmation phrases (retro §8.7: control verbs use a
# recognized-phrase layer, NOT free-form LLM interpretation). Matched
# case-insensitively against the trimmed user-role message.
_ESCALATE_PHRASES = frozenset({"yes, escalate", "yes escalate", "escalate"})
# Grant-approval phrases (CR-3): a user "yes" to a Tier-2 approval solicitation.
_GRANT_APPROVAL_PHRASES = frozenset(
    {"yes", "yes, approve", "yes approve", "approve", "approved", "confirm", "go ahead"}
)


def _normalize_phrase(text: str) -> str:
    return text.strip().strip(".!?\"' ").lower()


def is_escalation_confirmation(text: str) -> bool:
    """True iff the user-role text is an explicit escalation confirmation.

    Deterministic exact-phrase match (after lowercasing + stripping surrounding
    whitespace/punctuation) — never a fuzzy LLM interpretation, so it cannot be
    tricked into a false positive by conversational text (F-10-5-10 class).
    """
    return _normalize_phrase(text) in _ESCALATE_PHRASES


def is_grant_approval(text: str) -> bool:
    """True iff the user-role text is an explicit Tier-2 grant approval.

    Deterministic exact-phrase match — same anti-false-narration rationale as
    `is_escalation_confirmation`.
    """
    return _normalize_phrase(text) in _GRANT_APPROVAL_PHRASES


async def record_pending_sensitive_refusal(
    db_path: str, *, caller_origin: str, email_id: str, task_type: str,
) -> None:
    """Remember the caller's most-recent sensitive refusal so a later bare
    'yes, escalate' can be correlated. Called at the chat boundary when a
    sensitive refusal is rendered. Most-recent-wins by design (the user is
    responding to what they just saw); CR-5 double-refusal overwrite is
    intentional last-refusal semantics."""
    await execute_write(
        db_path,
        PENDING_SENSITIVE_REFUSAL_UPSERT,
        (caller_origin, email_id, task_type, _iso(_utc_now())),
    )


async def confirm_pending_escalation(
    db_path: str, *, caller_origin: str,
) -> tuple[str, str] | None:
    """On a user escalation confirmation, ATOMICALLY claim (delete-returning)
    the caller's pending sensitive refusal, record a real single-use
    user_confirmation for its (email_id, task_type), and return it.

    CR-6: the claim is a single DELETE ... RETURNING so two concurrent
    "yes, escalate" turns for the same caller cannot both proceed — only one
    deletes the row and gets it back; the other gets None.

    Returns None if there is no (un-expired) pending refusal for this caller.
    """
    claimed = await execute_write_returning(
        db_path, PENDING_SENSITIVE_REFUSAL_CLAIM, (caller_origin,)
    )
    if claimed is None:
        return None
    email_id, task_type, created_at = claimed
    # Reuse the confirmation TTL — a stale pending refusal cannot be escalated
    # (the row is already deleted by the atomic claim; just refuse).
    if _parse_iso(created_at) + CONFIRMATION_TTL <= _utc_now():
        return None
    await record_sensitivity_confirmation(db_path, email_id=email_id, task_type=task_type)
    _logger.info(
        "user escalation confirmed",
        extra={
            "event": "user_confirmation.escalation_confirmed",
            "caller_origin": caller_origin,
            "email_id": email_id,
            "task_type": task_type,
        },
    )
    return (email_id, task_type)


# ---------------------------------------------------------------------------
# Escalation ARM — ordering-independent fix (live-walk finding F-10-5-2-W1)
# ---------------------------------------------------------------------------
#
# In the real Discord flow the persona self-refuses and asks for confirmation,
# so the pending_sensitive_refusal row is written LATER in the same turn (when
# the agent's mint attempt hits the gate) than the boundary's confirm-check runs.
# `confirm_pending_escalation` (which reads the pending row up front) therefore
# never fires. The arm decouples "user said yes" from "a refusal exists now":
# the boundary ARMS the caller on "yes, escalate", and the router's NEXT
# sensitivity refusal CONSUMES the arm — auto-recording a real confirmation for
# that exact (email, task) so the very dispatch that would have been refused
# proceeds. Works regardless of which side of the refusal the "yes" lands on.


async def arm_escalation(db_path: str) -> None:
    """Record that the user said "yes, escalate" — a durable singleton intent
    that `mint_sensitivity_token` consumes for its concrete (email, task).
    Called at the chat boundary on the genuine user-role phrase ONLY (the agent
    verb surface cannot arm — non-agent-assertable invariant preserved)."""
    await execute_write(db_path, ESCALATION_ARMED_UPSERT, (_iso(_utc_now()),))
    _logger.info("escalation armed", extra={"event": "user_confirmation.escalation_armed"})


async def consume_escalation_arm(
    db_path: str, *, email_id: str, task_type: str,
) -> bool:
    """If an escalation is armed, ATOMICALLY consume it (delete-returning) and
    authorize exactly THIS mint. Returns True iff an arm was consumed. Called
    from `mint_sensitivity_token` when no pre-recorded confirmation exists.

    Note: the arm directly authorizes the one mint — it deliberately does NOT
    persist a reusable `user_confirmations` row (that would let a second mint
    succeed off one 'yes'). The atomic delete-returning is the single-use gate.

    Ordering-independent complement to `confirm_pending_escalation`: this fires
    when the user's "yes" arrived in the SAME turn as the agent's mint attempt
    (the real Discord flow the live walk surfaced)."""
    claimed = await execute_write_returning(db_path, ESCALATION_ARMED_CLAIM, ())
    if claimed is None:
        return False
    (armed_at,) = claimed
    if _parse_iso(armed_at) + CONFIRMATION_TTL <= _utc_now():
        return False
    _logger.info(
        "escalation arm consumed — mint authorized",
        extra={
            "event": "user_confirmation.escalation_arm_consumed",
            "email_id": email_id,
            "task_type": task_type,
        },
    )
    return True


# ---------------------------------------------------------------------------
# Boundary correlation for the Tier-2 grant-approval handshake (CR-3/CR-4)
# ---------------------------------------------------------------------------


async def record_pending_grant_approval(
    db_path: str, *, caller_origin: str, action_type: str, email_ids: list[str],
) -> None:
    """Remember what a caller's Tier-2 approval would authorize — the EXACT
    (action_type, email_ids) — so a later 'yes' records a scoped grant
    confirmation. Called at the chat boundary when a Tier-2 action is queued
    pending_grant. Without this, record_grant_confirmation has no production
    caller and every Tier-2 grant is permanently blocked (CR-3); carrying the
    exact email_ids keeps the blast radius user-approved, not agent-chosen
    (CR-4)."""
    await execute_write(
        db_path,
        PENDING_GRANT_APPROVAL_UPSERT,
        (caller_origin, action_type, _canonical_email_ids(email_ids), _iso(_utc_now())),
    )


async def confirm_pending_grant(
    db_path: str, *, caller_origin: str,
) -> tuple[str, list[str]] | None:
    """On a user grant approval, ATOMICALLY claim the caller's pending grant
    approval, record a scoped single-use grant confirmation for its
    (action_type, exact email_ids), and return them. Returns None if no
    (un-expired) pending approval exists for this caller."""
    claimed = await execute_write_returning(
        db_path, PENDING_GRANT_APPROVAL_CLAIM, (caller_origin,)
    )
    if claimed is None:
        return None
    action_type, email_ids_json, created_at = claimed
    if _parse_iso(created_at) + CONFIRMATION_TTL <= _utc_now():
        return None
    email_ids: list[str] = json.loads(email_ids_json)
    await record_grant_confirmation(db_path, action_type=action_type, email_ids=email_ids)
    _logger.info(
        "user grant approved",
        extra={
            "event": "user_confirmation.grant_approved",
            "caller_origin": caller_origin,
            "action_type": action_type,
            "email_count": len(email_ids),
        },
    )
    return (action_type, email_ids)


__all__ = [
    "CONFIRMATION_TTL",
    "ConfirmationScope",
    "arm_escalation",
    "confirm_pending_escalation",
    "confirm_pending_grant",
    "consume_escalation_arm",
    "consume_grant_confirmation",
    "consume_sensitivity_confirmation",
    "is_escalation_confirmation",
    "is_grant_approval",
    "record_grant_confirmation",
    "record_pending_grant_approval",
    "record_pending_sensitive_refusal",
    "record_sensitivity_confirmation",
]
