"""ActionType enum + tier_for() + cross-cutting properties registry.

This module is the single source of truth for the 23 action types and their
cross-cutting properties (tier, reversibility window, change-marker requirement,
send-budget membership, sensitivity-token requirement).

Story 4-1 establishes the type-foundation for Epic 4:
  - Stories 4-2..4-8 import ActionType and look up properties via tier_for(),
    is_send_family(), requires_grant(), ACTION_PROPERTIES.
  - String-literal action types outside this module (and outside tests/) are
    banned by scripts/check_boundaries.py — agents cannot promote tiers via
    bare strings like propose_action(email_id, "delete", payload).

References:
  - FR-5.1 — Tier 1 silent + auto-revertible (24h)
  - FR-5.2 — Tier 2 batched approval (grant-gated)
  - FR-5.4 — Hard 20-send/day cap (budget_against="daily_send_cap_20")
  - FR-5.6 — Agent cannot promote tier (enforced at verb boundary by Story 4-2
            AND at lint time by Story 4-1's boundary check)
  - AR-D4-1..2 — ETag strict (Tier-3) / lenient 3-rule (Tier-1/2)
  - AR-D5-1..4 — Tier-banded notification strategy (silent/digest/urgent)
  - AR-D6-1..4 — Reversibility window (24h Tier-1 via Story 4-8)
  - AR-D12-1..2 — Sensitivity-token registry contract (consumed by Story 4-7)
  - AR-SCHEMA-3..5 — pending_actions / action_grants / action_history schemas
                     (consumed by Story 4-2)
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Final, Literal, Mapping

from pydantic import BaseModel, ConfigDict


class ActionType(str, Enum):
    """The 23 canonical action types, grouped by tier.

    Subclassing `str` gives JSON-friendly serialization: `ActionType.DELETE`
    JSON-encodes as `"delete"`. The `.value` of each member is the snake_case
    string that appears in SQL, JSON payloads, and Graph API endpoint mappings.
    """

    # Tier 0 — verb-level capabilities (never queued in pending_actions per
    # Story 4-2 AC). Listed here so the contract is complete; downstream
    # callers should never propose_action() one of these.
    READ_SQL = "read_sql"
    ASK_ROUTER = "ask_router"
    GENERATE_DRAFT = "generate_draft"
    SEND_CHAT_NOTIFICATION = "send_chat_notification"
    WRITE_DERIVED_FIELD = "write_derived_field"

    # Tier 1 — silent log + auto-revertible within 24h (FR-5.1; AR-D5-4; AR-D6-3)
    MARK_READ = "mark_read"
    MARK_UNREAD = "mark_unread"
    ADD_LOCAL_CATEGORY = "add_local_category"
    REMOVE_LOCAL_CATEGORY = "remove_local_category"
    MOVE_TO_TRIAGE_FOLDER = "move_to_triage_folder"

    # Tier 2 — batched approval, grant-gated (FR-5.2; AR-D4-2 lenient policy)
    ARCHIVE = "archive"
    MARK_JUNK = "mark_junk"
    MOVE_TO_USER_FOLDER = "move_to_user_folder"
    UNSUBSCRIBE = "unsubscribe"
    MOVE_TO_INBOX = "move_to_inbox"

    # Tier 3 — explicit approval + ETag-strict + (SEND-family) sensitivity-token
    # handshake + hard 20-send/day cap (FR-5.3/5.4; AR-D4-1; AR-D12-1)
    DELETE = "delete"
    SEND_REPLY = "send_reply"
    SEND_NEW_EMAIL = "send_new_email"
    SEND_FORWARD = "send_forward"
    REPLY_TO_INACTIVE_THREAD = "reply_to_inactive_thread"
    MODIFY_INBOX_RULE = "modify_inbox_rule"
    MODIFY_OUTLOOK_FILTER = "modify_outlook_filter"
    TOUCH_DELEGATED_MAILBOX = "touch_delegated_mailbox"


class ActionProperties(BaseModel):
    """Frozen per-action metadata consumed by every Epic-4 verb + the drainer.

    Fields:
      - tier: 0..3 per the 4-tier authorization model
      - reversibility_window_hours: 24 for Tier 1 (FR-5.1 + AR-D6-3), None otherwise
      - change_marker_required: True for Tier 3 only (AR-D4-1 strict ETag)
      - budget_against: "daily_send_cap_20" for the 4 SEND-family actions
                        (FR-5.4 hard cap), None otherwise
      - requires_sensitivity_token: True for the 4 SEND-family actions
                                    (outbound content from a sensitive email
                                    needs the Story 4-7 handshake); False
                                    otherwise.

    DELETE-rationale (CR-2 resolution): DELETE is Tier-3 with
    change_marker_required=True but requires_sensitivity_token=False because
    AR-D12-1 scopes the sensitivity-handshake registry to Router LLM calls
    (mint_sensitivity_token → consume → record_router_call.sensitivity_grant_id),
    NOT to action verbs. A sensitive-email DELETE is still protected by three
    independent layers: (a) Tier-3 grant required via mint_grant + is_grant_valid
    at drain time (Story 4-3/4-4); (b) strict ETag match (AR-D4-1) refuses on
    state drift; (c) 60s cooling-off + /cancel for SEND family doesn't apply
    here, but the Tier-3 grant itself requires the operator to invoke
    mint_grant first — there's no auto-promotion path. The handshake is about
    content leaving the mailbox to a sensitive recipient/topic via an LLM
    call, not about destructive action authorization. If Adam later decides
    sensitive-email destructive actions ALSO need the handshake, this field
    flips to True here — verbs/mint_grant.py would refuse without a token —
    no downstream code changes elsewhere.
    """

    model_config = ConfigDict(frozen=True)

    tier: Literal[0, 1, 2, 3]
    reversibility_window_hours: int | None
    change_marker_required: bool
    budget_against: Literal["daily_send_cap_20"] | None
    requires_sensitivity_token: bool


# Build the property table once, then wrap in MappingProxyType for read-only
# module-singleton semantics (Posture Audit §5.7).
_PROPS: dict[ActionType, ActionProperties] = {
    # Tier 0 — verb-level capabilities
    ActionType.READ_SQL: ActionProperties(
        tier=0,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.ASK_ROUTER: ActionProperties(
        tier=0,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.GENERATE_DRAFT: ActionProperties(
        tier=0,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.SEND_CHAT_NOTIFICATION: ActionProperties(
        tier=0,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.WRITE_DERIVED_FIELD: ActionProperties(
        tier=0,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    # Tier 1 — silent + auto-revertible within 24h
    ActionType.MARK_READ: ActionProperties(
        tier=1,
        reversibility_window_hours=24,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MARK_UNREAD: ActionProperties(
        tier=1,
        reversibility_window_hours=24,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.ADD_LOCAL_CATEGORY: ActionProperties(
        tier=1,
        reversibility_window_hours=24,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.REMOVE_LOCAL_CATEGORY: ActionProperties(
        tier=1,
        reversibility_window_hours=24,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MOVE_TO_TRIAGE_FOLDER: ActionProperties(
        tier=1,
        reversibility_window_hours=24,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    # Tier 2 — grant-gated batches
    ActionType.ARCHIVE: ActionProperties(
        tier=2,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MARK_JUNK: ActionProperties(
        tier=2,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MOVE_TO_USER_FOLDER: ActionProperties(
        tier=2,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.UNSUBSCRIBE: ActionProperties(
        tier=2,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MOVE_TO_INBOX: ActionProperties(
        tier=2,
        reversibility_window_hours=None,
        change_marker_required=False,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    # Tier 3 — explicit approval + ETag-strict + (SEND) sensitivity-token + 20/day cap
    ActionType.DELETE: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.SEND_REPLY: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against="daily_send_cap_20",
        requires_sensitivity_token=True,
    ),
    ActionType.SEND_NEW_EMAIL: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against="daily_send_cap_20",
        requires_sensitivity_token=True,
    ),
    ActionType.SEND_FORWARD: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against="daily_send_cap_20",
        requires_sensitivity_token=True,
    ),
    ActionType.REPLY_TO_INACTIVE_THREAD: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against="daily_send_cap_20",
        requires_sensitivity_token=True,
    ),
    ActionType.MODIFY_INBOX_RULE: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.MODIFY_OUTLOOK_FILTER: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
    ActionType.TOUCH_DELEGATED_MAILBOX: ActionProperties(
        tier=3,
        reversibility_window_hours=None,
        change_marker_required=True,
        budget_against=None,
        requires_sensitivity_token=False,
    ),
}

ACTION_PROPERTIES: Final[Mapping[ActionType, ActionProperties]] = MappingProxyType(_PROPS)

# Defense-in-depth: drop the module-level `_PROPS` name so the underlying dict
# can no longer be reached via `mailbot_api.actions.types._PROPS` and mutated
# behind ACTION_PROPERTIES' back. (MappingProxyType holds its own internal
# reference, so dropping the name does NOT GC the dict.) Code-review CR-3.
del _PROPS


def tier_for(action_type: ActionType) -> int:
    """Return the tier (0..3) for an ActionType.

    Used by every Epic-4 story to gate per-tier behavior. Wrapping the dict
    lookup in a function keeps call sites self-documenting and lets a future
    typed wrapper carry mypy hints more naturally.
    """
    return ACTION_PROPERTIES[action_type].tier


def is_send_family(action_type: ActionType) -> bool:
    """True iff the action belongs to the SEND family (consumes daily send budget).

    The 4 SEND-family actions (SEND_REPLY, SEND_NEW_EMAIL, SEND_FORWARD,
    REPLY_TO_INACTIVE_THREAD) all carry budget_against="daily_send_cap_20".
    Used by Story 4-6's hard 20-send/day cap query + Story 4-2's cooling-off
    routing.
    """
    return ACTION_PROPERTIES[action_type].budget_against == "daily_send_cap_20"


def requires_grant(action_type: ActionType) -> bool:
    """True iff the action requires a valid action_grants row to drain (Tier-2 + Tier-3).

    Tier 0 verbs never enter pending_actions (refused at verb boundary by
    Story 4-2). Tier 1 is auto-approvable per FR-5.1 (revertible via Story 4-8).
    Tier 2 + Tier 3 both need a grant; the drainer (Story 4-4) consults
    is_grant_valid() for them.
    """
    return tier_for(action_type) >= 2


# Story 4-2 AC-8/AC-10: actions that are NOT email-scoped — they operate on
# the mailbox configuration itself (rules, filters, delegated mailbox), not
# on a specific message. `propose_action` permits `email_id=None` ONLY for
# these. Adding a new email-less action requires updating this set + the
# tests/unit/actions/test_types.py::test_email_less_actions_membership_exact
# invariant.
EMAIL_LESS_ACTIONS: Final[frozenset[ActionType]] = frozenset(
    {
        ActionType.MODIFY_INBOX_RULE,
        ActionType.MODIFY_OUTLOOK_FILTER,
        ActionType.TOUCH_DELEGATED_MAILBOX,
        # CR-1 (4-2 review): SEND_NEW_EMAIL is compose-from-scratch — the agent
        # drafts a fresh outbound message with no source email, so there's no
        # email_id to attach. SEND_REPLY / SEND_FORWARD / REPLY_TO_INACTIVE_THREAD
        # all reference an existing inbox row and stay email-scoped.
        ActionType.SEND_NEW_EMAIL,
    }
)


__all__ = [
    "ACTION_PROPERTIES",
    "ActionProperties",
    "ActionType",
    "EMAIL_LESS_ACTIONS",
    "is_send_family",
    "requires_grant",
    "tier_for",
]
