"""Story 4-1 — ActionType + ActionProperties + tier_for/is_send_family/requires_grant invariants.

These tests are the canary for every later Epic-4 story. If the contract here
drifts, every downstream verb / drainer / reverter will read wrong metadata.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from mailbot_api.actions import (
    ACTION_PROPERTIES,
    EMAIL_LESS_ACTIONS,
    ActionProperties,
    ActionType,
    is_send_family,
    requires_grant,
    tier_for,
)

# --- Tier expectations as data, not derived (so a typo in the enum is caught
# by a failing test rather than by a same-typo expectation).

EXPECTED_TIER_0 = {
    ActionType.READ_SQL,
    ActionType.ASK_ROUTER,
    ActionType.GENERATE_DRAFT,
    ActionType.SEND_CHAT_NOTIFICATION,
    ActionType.WRITE_DERIVED_FIELD,
}
EXPECTED_TIER_1 = {
    ActionType.MARK_READ,
    ActionType.MARK_UNREAD,
    ActionType.ADD_LOCAL_CATEGORY,
    ActionType.REMOVE_LOCAL_CATEGORY,
    ActionType.MOVE_TO_TRIAGE_FOLDER,
}
EXPECTED_TIER_2 = {
    ActionType.ARCHIVE,
    ActionType.MARK_JUNK,
    ActionType.MOVE_TO_USER_FOLDER,
    ActionType.UNSUBSCRIBE,
    ActionType.MOVE_TO_INBOX,
}
EXPECTED_TIER_3 = {
    ActionType.DELETE,
    ActionType.SEND_REPLY,
    ActionType.SEND_NEW_EMAIL,
    ActionType.SEND_FORWARD,
    ActionType.REPLY_TO_INACTIVE_THREAD,
    ActionType.MODIFY_INBOX_RULE,
    ActionType.MODIFY_OUTLOOK_FILTER,
    ActionType.TOUCH_DELEGATED_MAILBOX,
}
EXPECTED_SEND_FAMILY = {
    ActionType.SEND_REPLY,
    ActionType.SEND_NEW_EMAIL,
    ActionType.SEND_FORWARD,
    ActionType.REPLY_TO_INACTIVE_THREAD,
}


def test_total_action_count_is_23() -> None:
    """AC-6 §1 — explicit 23 members so a new addition forces an update here."""
    assert len(ActionType) == 23


def test_tier_0_membership_exact() -> None:
    """AC-6 §2."""
    actual = {at for at in ActionType if tier_for(at) == 0}
    assert actual == EXPECTED_TIER_0


def test_tier_1_membership_exact() -> None:
    """AC-6 §3."""
    actual = {at for at in ActionType if tier_for(at) == 1}
    assert actual == EXPECTED_TIER_1


def test_tier_2_membership_exact() -> None:
    """AC-6 §4."""
    actual = {at for at in ActionType if tier_for(at) == 2}
    assert actual == EXPECTED_TIER_2


def test_tier_3_membership_exact() -> None:
    """AC-6 §5."""
    actual = {at for at in ActionType if tier_for(at) == 3}
    assert actual == EXPECTED_TIER_3


def test_reversibility_window_24h_for_tier_1_only() -> None:
    """AC-6 §6 — every Tier-1 action has 24h window; every other tier is None."""
    for at in ActionType:
        props = ACTION_PROPERTIES[at]
        if props.tier == 1:
            assert props.reversibility_window_hours == 24, f"{at} should be 24h"
        else:
            assert props.reversibility_window_hours is None, f"{at} should be None"


def test_change_marker_required_only_for_tier_3() -> None:
    """AC-6 §7 — AR-D4-1 strict-ETag rule is Tier-3-only."""
    for at in ActionType:
        props = ACTION_PROPERTIES[at]
        if props.tier == 3:
            assert props.change_marker_required is True, f"{at} should require change_marker"
        else:
            assert props.change_marker_required is False, f"{at} should NOT require change_marker"


def test_send_family_budget_invariant() -> None:
    """AC-6 §8 — FR-5.4 hard cap targets exactly the 4 SEND-family actions."""
    actual = {at for at in ActionType if is_send_family(at)}
    assert actual == EXPECTED_SEND_FAMILY
    # And budget_against carries the literal string for cap-query joins.
    for at in EXPECTED_SEND_FAMILY:
        assert ACTION_PROPERTIES[at].budget_against == "daily_send_cap_20"
    for at in set(ActionType) - EXPECTED_SEND_FAMILY:
        assert ACTION_PROPERTIES[at].budget_against is None


def test_sensitivity_token_invariant() -> None:
    """AC-6 §9 — the SEND-family actions AND DELETE require the Story 4-7 handshake.

    The 4 SEND-family actions need the handshake because outbound content
    from a sensitive email goes through Anthropic. DELETE was added per
    Adam's Epic 4 retro decision (2026-06-02, Story 4-1 CR-2) — destruction
    of a sensitive email is irreversible and deserves the same confirmation
    gate as sending its contents. Belt-and-suspenders.
    """
    actual = {at for at in ActionType if ACTION_PROPERTIES[at].requires_sensitivity_token}
    expected = EXPECTED_SEND_FAMILY | {ActionType.DELETE}
    assert actual == expected


def test_registry_completeness() -> None:
    """AC-6 §10 — every enum member has an entry; no extras."""
    assert set(ACTION_PROPERTIES.keys()) == set(ActionType)


def test_action_properties_registry_is_frozen_mapping() -> None:
    """AC-6 §11 — MappingProxyType wraps the dict so accidental writes raise."""
    with pytest.raises(TypeError):
        ACTION_PROPERTIES[ActionType.MARK_READ] = ActionProperties(  # type: ignore[index]
            tier=2,
            reversibility_window_hours=None,
            change_marker_required=False,
            budget_against=None,
            requires_sensitivity_token=False,
        )


def test_action_properties_model_is_pydantic_frozen() -> None:
    """AC-6 §12 — `model_config = ConfigDict(frozen=True)` blocks field mutation."""
    props = ACTION_PROPERTIES[ActionType.DELETE]
    with pytest.raises(ValidationError):
        props.tier = 1  # type: ignore[misc]


def test_json_serialization_produces_string_value() -> None:
    """AC-6 §13 — `str, Enum` mixin → JSON-encodes as the .value string.

    Important for SQL serialization (CHECK constraints on pending_actions
    consume the string) and JSON payloads.
    """
    assert json.dumps(ActionType.DELETE) == '"delete"'
    assert json.dumps(ActionType.SEND_REPLY) == '"send_reply"'
    assert json.dumps(ActionType.MARK_READ) == '"mark_read"'


def test_json_deserialization_round_trip() -> None:
    """CR-5: round-trip the value through JSON and reconstruct the enum.

    `json.loads(json.dumps(...))` returns a plain `str`, not an `ActionType` —
    this is standard json-module behavior. Callers must reconstruct via
    `ActionType(value)` at deserialization boundaries. The test pins both
    halves of the contract.
    """
    raw = json.loads(json.dumps(ActionType.DELETE))
    assert raw == "delete"
    assert type(raw) is str  # NOT ActionType — json doesn't preserve subclass
    reconstructed = ActionType(raw)
    assert reconstructed is ActionType.DELETE
    assert reconstructed == "delete"  # str-Enum semantics: equality both directions


def test_action_type_can_be_constructed_from_string_value() -> None:
    """CR-5: every ActionType can be reconstructed from its .value string.

    Stories 4-2..4-8 will read action_type strings from SQL rows (CHECK-
    constrained TEXT) and from JSON payloads — `ActionType("delete")` is the
    canonical reconstruction. An invalid string raises ValueError.
    """
    for at in ActionType:
        assert ActionType(at.value) is at
    with pytest.raises(ValueError, match="not a valid"):
        ActionType("not_a_real_action_type")


def test_tier_for_returns_expected_well_known_values() -> None:
    """AC-3 — invariants the spec named explicitly."""
    assert tier_for(ActionType.READ_SQL) == 0
    assert tier_for(ActionType.MARK_READ) == 1
    assert tier_for(ActionType.ARCHIVE) == 2
    assert tier_for(ActionType.DELETE) == 3
    assert tier_for(ActionType.SEND_REPLY) == 3


def test_requires_grant_is_true_only_for_tier_2_and_tier_3() -> None:
    """AC-4 — Tier 0/1 are not grant-gated; Tier 2/3 are."""
    for at in ActionType:
        expected = tier_for(at) >= 2
        assert requires_grant(at) is expected, f"{at}: requires_grant mismatch"


def test_action_type_value_is_snake_case_string() -> None:
    """Quick safety: every enum value is a non-empty snake_case string."""
    for at in ActionType:
        assert isinstance(at.value, str)
        assert at.value
        assert at.value == at.value.lower()
        assert " " not in at.value
        assert "-" not in at.value


def test_email_less_actions_membership_exact() -> None:
    """Story 4-2 AC-10 — EMAIL_LESS_ACTIONS membership.

    Includes:
      - 3 mailbox-configuration actions (MODIFY_INBOX_RULE, MODIFY_OUTLOOK_FILTER,
        TOUCH_DELEGATED_MAILBOX) — don't operate on a specific email.
      - SEND_NEW_EMAIL — compose-from-scratch outbound mail; no source email.
        (CR-1 from Story 4-2 review.)

    SEND_REPLY / SEND_FORWARD / REPLY_TO_INACTIVE_THREAD stay email-scoped —
    they all reference an existing inbox row.

    Adding a new email-less action requires updating both this test and the
    frozenset definition in types.py — deliberate friction.
    """
    assert EMAIL_LESS_ACTIONS == frozenset(
        {
            ActionType.MODIFY_INBOX_RULE,
            ActionType.MODIFY_OUTLOOK_FILTER,
            ActionType.TOUCH_DELEGATED_MAILBOX,
            ActionType.SEND_NEW_EMAIL,
        }
    )


def test_send_new_email_in_email_less_but_other_sends_not() -> None:
    """CR-1: SEND_NEW_EMAIL is the only SEND-family action that is email-less.

    Pin the asymmetry so a future drift doesn't accidentally include or
    exclude SEND_NEW_EMAIL from EMAIL_LESS_ACTIONS.
    """
    assert ActionType.SEND_NEW_EMAIL in EMAIL_LESS_ACTIONS
    assert ActionType.SEND_REPLY not in EMAIL_LESS_ACTIONS
    assert ActionType.SEND_FORWARD not in EMAIL_LESS_ACTIONS
    assert ActionType.REPLY_TO_INACTIVE_THREAD not in EMAIL_LESS_ACTIONS


def test_move_family_membership_exact_and_matches_dispatch_table() -> None:
    """Story 10-2 — MOVE_FAMILY membership.

    The move-family is defined as "every action that dispatches via
    POST /me/messages/{id}/move" (Epic 10 / Story 10.2 AC interpretation pin).
    Cross-check the frozenset against the adapter's dispatch table so the two
    can never drift apart: adding a new move-dispatching action requires
    updating MOVE_FAMILY (and this test) — deliberate friction, mirroring
    EMAIL_LESS_ACTIONS.
    """
    from mailbot_api.actions.outlook_adapter import _DISPATCH_TABLE
    from mailbot_api.actions.types import MOVE_FAMILY, is_move_family

    assert MOVE_FAMILY == frozenset(
        {
            ActionType.MOVE_TO_TRIAGE_FOLDER,
            ActionType.ARCHIVE,
            ActionType.MARK_JUNK,
            ActionType.MOVE_TO_USER_FOLDER,
            ActionType.MOVE_TO_INBOX,
        }
    )
    move_endpoint_types = {
        at
        for at, dispatch in _DISPATCH_TABLE.items()
        if dispatch.path_template == "/me/messages/{id}/move"
    }
    assert MOVE_FAMILY == move_endpoint_types
    for at in ActionType:
        assert is_move_family(at) == (at in MOVE_FAMILY)


def test_boundary_check_action_value_set_matches_enum_tier_1_to_3() -> None:
    """AC-5 / AC-7 — keep `scripts/check_boundaries.py`'s hardcoded action-value
    set in sync with the Tier 1-3 subset of ActionType. Drift here = the rule
    misses new actions OR fires on non-actions.

    Tier 0 is intentionally excluded from the boundary set because Tier-0
    values (`ask_router`, `read_sql`, etc.) collide with Python symbol names
    and Tier-0 verbs never enter pending_actions anyway.
    """
    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_boundaries.py"
    spec = importlib.util.spec_from_file_location("_cb_for_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # CR-4: explicit attribute checks turn a rename / syntax error / typo
    # into a clear failure message rather than a cryptic AttributeError.
    assert hasattr(module, "_ACTION_TYPE_VALUES"), (
        "check_boundaries.py no longer exports _ACTION_TYPE_VALUES — "
        "the Story 4-1 boundary-rule sync check is broken. Rename the "
        "attribute back OR update this test to match."
    )
    assert hasattr(module, "_ACTION_TYPE_STRING_LITERAL_ALLOW"), (
        "check_boundaries.py no longer exports _ACTION_TYPE_STRING_LITERAL_ALLOW — "
        "the Story 4-1 boundary-rule allowlist is missing. Restore it OR "
        "update this test to match."
    )

    script_values = set(module._ACTION_TYPE_VALUES)
    enum_tier_1_to_3 = {at.value for at in ActionType if tier_for(at) >= 1}
    assert script_values == enum_tier_1_to_3, (
        f"check_boundaries.py _ACTION_TYPE_VALUES drift: "
        f"in-script-only={script_values - enum_tier_1_to_3}, "
        f"in-enum-only={enum_tier_1_to_3 - script_values}"
    )

    # Same for the allowlist. Story 4-5 added outlook_adapter.py for Graph
    # well-known-folder name collisions ("archive", "inbox").
    assert module._ACTION_TYPE_STRING_LITERAL_ALLOW == frozenset(
        {
            "mailbot_api/actions/types.py",
            "mailbot_api/actions/outlook_adapter.py",
        }
    )
