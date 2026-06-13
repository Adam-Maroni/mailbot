"""Story 7-0-c24 — RecoveryAction envelope MVP coverage tests.

AC §7: 6 integration tests covering the architectural foundation + the 2
MVP propagation surfaces shipped this story.

  1. RecoveryAction Pydantic shape: frozen, default-construction, field types.
  2. INVALID_ACTION_TYPE path: error carries BOTH the legacy valid_action_types
     tuple AND the new recovery_action envelope with tool_name="propose_action"
     + self-contained args_hint (valid_choices) + non-None user_facing_guidance
     pointing at the MCP resource. (Back-compat retention + CR-1 self-contained
     envelope proof.)
  3. GRANT_REQUIRED hint on Tier-2 BATCH propose: ProposeActionOut.recovery_action
     populated with tool_name="mint_grant" + correct args_hint shape including
     relative ttl_seconds (CR-2 race-free contract).
  4. GRANT_REQUIRED hint on Tier-3 SEND propose: same shape, single-element
     email_ids; bare requires_grant boolean ALSO True (back-compat retention).
  5. Counter-test: Tier-1 LOCAL propose returns recovery_action=None
     (no signal needed — auto-approval path).
  6. Email-less Tier-3 admin envelope shape (pre-review FIX-NOW): MODIFY_INBOX_RULE
     etc. emit empty email_ids list (not None) + ttl_seconds.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mailbot_api.actions import RecoveryAction
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.propose_action import propose_action as propose_action_shim


async def _seed_email(db_path: str, *, graph_id: str = "e-1") -> None:
    """Standard email seed — change_marker non-NULL so Tier-3 propose path
    captures it without refusing on EMAIL_NEVER_SYNCED."""
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-13T00:00:00Z", "s", "a@b.c", "cm-v1", None),
    )


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


# ---- Test 1: RecoveryAction Pydantic shape ----------------------------------


def test_recovery_action_shape_frozen_and_defaults() -> None:
    """AC §7 test 1 — RecoveryAction is frozen with all-optional defaults.
    Mutation attempts raise ValidationError; default construction yields
    tool_name=None + args_hint={} + user_facing_guidance=None."""
    # Default construction.
    ra = RecoveryAction()
    assert ra.tool_name is None
    assert ra.args_hint == {}
    assert ra.user_facing_guidance is None

    # Full construction.
    ra2 = RecoveryAction(
        tool_name="mint_grant",
        args_hint={"action_type": "send_reply", "email_ids": ["e-1"]},
        user_facing_guidance="please confirm by typing /confirm",
    )
    assert ra2.tool_name == "mint_grant"
    assert ra2.args_hint["action_type"] == "send_reply"
    assert ra2.user_facing_guidance is not None

    # Frozen: mutation raises ValidationError per Pydantic v2 ConfigDict(frozen=True).
    with pytest.raises(ValidationError):
        ra2.tool_name = "different"  # type: ignore[misc]


# ---- Test 2: INVALID_ACTION_TYPE recovery envelope --------------------------


async def test_invalid_action_type_error_carries_both_legacy_and_envelope(
    tmp_path: Path,
) -> None:
    """AC §7 test 2 — back-compat retention proof. The INVALID_ACTION_TYPE
    refusal arm carries BOTH the Story 6-19 `valid_action_types` field
    (legacy consumers) AND the new `recovery_action` envelope (new
    consumers). Both are populated; neither is None."""
    db_path = _setup(tmp_path)
    out = await propose_action_shim(
        "e-1", "SEND_EMAIL",  # hallucinated synonym; rejected
        db_path=db_path,
    )
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "INVALID_ACTION_TYPE"

    # Back-compat legacy field — Story 6-19 contract.
    assert out.error.valid_action_types is not None
    assert isinstance(out.error.valid_action_types, tuple)
    assert "send_reply" in out.error.valid_action_types

    # New envelope — Story 7-0-c24 contract. CR-1 (sonnet-4-6 review):
    # the envelope is self-contained — args_hint carries the canonical
    # action_type list as `valid_choices` so the consumer never needs to
    # cross-reference the parallel `valid_action_types` field to recover.
    assert out.error.recovery_action is not None
    assert out.error.recovery_action.tool_name == "propose_action"
    assert out.error.recovery_action.args_hint["action_type"] == (
        "<choose one from valid_choices>"
    )
    assert "valid_choices" in out.error.recovery_action.args_hint
    valid_choices = out.error.recovery_action.args_hint["valid_choices"]
    assert isinstance(valid_choices, list)
    assert "send_reply" in valid_choices
    # user_facing_guidance now non-None — names the MCP resource per
    # CR-1 patch (the chat-surface mapping recovery path).
    assert out.error.recovery_action.user_facing_guidance is not None
    assert "mailbot://action-types" in out.error.recovery_action.user_facing_guidance


# ---- Test 3: GRANT_REQUIRED hint on Tier-2 BATCH ----------------------------


async def test_tier_2_batch_propose_carries_mint_grant_recovery(
    tmp_path: Path,
) -> None:
    """AC §7 test 3 — Tier-2 BATCH propose (e.g., ARCHIVE) returns
    ok=True with recovery_action.tool_name='mint_grant' and args_hint
    enumerating the action_type + the email_ids + expires_at hint."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action_shim(
        "e-1", ActionType.ARCHIVE.value, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 2
    assert out.requires_grant is True  # back-compat boolean still populated

    assert out.recovery_action is not None
    assert out.recovery_action.tool_name == "mint_grant"
    hint = out.recovery_action.args_hint
    assert hint["action_type"] == "archive"
    assert hint["email_ids"] == ["e-1"]
    # CR-2 (sonnet-4-6 review): relative TTL not absolute expires_at —
    # consumers re-compute expires_at = now() + ttl_seconds at mint-time
    # to avoid race-on-stale-hint.
    assert hint["ttl_seconds"] == 60
    assert "expires_at" not in hint


# ---- Test 4: GRANT_REQUIRED hint on Tier-3 SEND -----------------------------


async def test_tier_3_send_reply_propose_carries_mint_grant_recovery(
    tmp_path: Path,
) -> None:
    """AC §7 test 4 — Tier-3 SEND-family propose (SEND_REPLY) returns
    recovery_action.tool_name='mint_grant' with single-element email_ids.
    Bare requires_grant boolean is ALSO populated for back-compat
    consumers; both fields point to the same underlying contract."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action_shim(
        "e-1", ActionType.SEND_REPLY.value, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 3
    assert out.status == "cooling_off"
    # Back-compat retention: both bare booleans + envelope populated.
    assert out.requires_grant is True
    assert out.requires_per_action_confirmation is True

    assert out.recovery_action is not None
    assert out.recovery_action.tool_name == "mint_grant"
    hint = out.recovery_action.args_hint
    assert hint["action_type"] == "send_reply"
    assert hint["email_ids"] == ["e-1"]  # single-element per Tier-3 per-action grant


# ---- Test 5: Counter-test — Tier-1 LOCAL has no envelope --------------------


async def test_tier_1_local_propose_has_no_recovery_action(tmp_path: Path) -> None:
    """AC §7 test 5 — Tier-1 LOCAL propose (e.g., MARK_READ) is
    auto-approved; no grant needed, no in-band next-call signal. The
    recovery_action field is None. Counter-test guard against accidental
    population on the Tier-1 path (the registry-driven derivation must
    correctly emit None when requires_grant(action_type) is False)."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action_shim(
        "e-1", ActionType.MARK_READ.value, db_path=db_path,
    )
    assert out.ok is True
    assert out.tier == 1
    assert out.requires_grant is False
    assert out.recovery_action is None


# ---- Test 6: Email-less Tier-3 admin envelope shape (pre-review FIX NOW) ----


async def test_email_less_tier_3_admin_envelope_carries_empty_email_ids(
    tmp_path: Path,
) -> None:
    """Pre-review self-audit FIX NOW (issue 4) — email-less Tier-3 admin
    actions (MODIFY_INBOX_RULE, MODIFY_OUTLOOK_FILTER, TOUCH_DELEGATED_MAILBOX)
    pass email_id=None per Story 4-2 CR-1 EMAIL_LESS_ACTIONS routing. The
    envelope's args_hint.email_ids should be an empty list (NOT None and
    NOT a single-element list with None), so Hermes can unconditionally
    pass it to mint_grant which accepts empty email_ids for admin
    actions per Story 4-3's grant-scope contract."""
    db_path = _setup(tmp_path)
    # No email seed needed — these are email-less.
    out = await propose_action_shim(
        None, ActionType.MODIFY_INBOX_RULE.value, db_path=db_path,
    )
    assert out.ok is True, f"unexpected refusal: {out.error}"
    assert out.tier == 3
    assert out.requires_grant is True

    assert out.recovery_action is not None
    assert out.recovery_action.tool_name == "mint_grant"
    hint = out.recovery_action.args_hint
    assert hint["action_type"] == "modify_inbox_rule"
    # Empty list, not None — Hermes can unconditionally interpolate.
    assert hint["email_ids"] == []
    # CR-2 (sonnet-4-6 review): relative TTL.
    assert hint["ttl_seconds"] == 60
