"""Story 10.5.2 (Epic 10.5 Cluster B) — genuine sensitive-escalation handshake
(F-10-5-7): user-confirmed, session-independent, attaches, does not brick.

Covers the CODE portion of AC-4 (the live end-to-end walk is Task 5,
Adam-hands-on). Proves:
  1. `is_escalation_confirmation` is a deterministic exact-phrase match.
  2. A sensitive refusal records a pending refusal keyed by caller_origin.
  3. `confirm_pending_escalation` turns the pending refusal into a real,
     single-use user_confirmation for the (email_id, task) — WITHOUT any
     session id (the F-10-5-7 divergence is gone by construction).
  4. After confirmation, the mint that previously refused now SUCCEEDS.
  5. No-brick: a stale/absent pending refusal does not poison later turns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.actions.types import ActionType
from mailbot_api.actions.user_confirmation import (
    arm_escalation,
    confirm_pending_escalation,
    confirm_pending_grant,
    consume_escalation_arm,
    consume_grant_confirmation,
    consume_sensitivity_confirmation,
    is_escalation_confirmation,
    is_grant_approval,
    record_pending_grant_approval,
    record_pending_sensitive_refusal,
)
from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.mint_sensitivity_token import mint_sensitivity_token


@pytest.fixture
async def _db_path(tmp_path: Path) -> str:
    _clear_registry_for_tests()
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_sensitive(db_path: str, *, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-02T00:00:00Z", "s", "x@y.com", "b",
            "sensitive", "2026-06-02T00:01:00Z", "v1", 0.9, "qwen2.5:3b-instruct-q4_K_M",
        ),
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("yes, escalate", True),
        ("Yes, Escalate", True),
        ("  yes, escalate.  ", True),
        ("escalate", True),
        ("yes escalate", True),
        ("yes", False),  # bare yes is NOT enough — must be explicit
        ("please escalate this whole thread to my manager", False),  # not exact
        ("no", False),
        ("cancel", False),
    ],
)
def test_is_escalation_confirmation_is_exact(text: str, expected: bool) -> None:
    """Deterministic exact-phrase match — never a fuzzy interpretation."""
    assert is_escalation_confirmation(text) is expected


async def test_pending_refusal_then_confirm_unlocks_mint(_db_path: str) -> None:
    """The full handshake: refusal recorded → user confirms → mint succeeds.
    No session id anywhere — correlation is caller_origin + (email, task)."""
    await _seed_sensitive(_db_path, graph_id="e-sens")

    # Before confirmation, the mint refuses (F-10-5-5 gate).
    pre = await mint_sensitivity_token("e-sens", "draft_reply", db_path=_db_path)
    assert pre.ok is False
    assert pre.error is not None
    assert pre.error.code == "NEEDS_USER_CONFIRMATION"

    # The router recorded a pending sensitive refusal for this caller.
    await record_pending_sensitive_refusal(
        _db_path, caller_origin="discord:home", email_id="e-sens", task_type="draft_reply",
    )

    # The user replies "yes, escalate" → boundary confirms the pending refusal.
    resolved = await confirm_pending_escalation(_db_path, caller_origin="discord:home")
    assert resolved == ("e-sens", "draft_reply")

    # Now the SAME mint succeeds — the confirmation attached by (email, task),
    # independent of any session identity (F-10-5-7 fixed).
    post = await mint_sensitivity_token("e-sens", "draft_reply", db_path=_db_path)
    assert post.ok is True, post.error
    assert post.token is not None


async def test_confirm_is_single_use_and_scoped(_db_path: str) -> None:
    """The confirmation created by the handshake is single-use; a second mint
    refuses, and the pending refusal is cleared after confirming."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    await record_pending_sensitive_refusal(
        _db_path, caller_origin="discord:home", email_id="e-sens", task_type="draft_reply",
    )
    await confirm_pending_escalation(_db_path, caller_origin="discord:home")

    first = await mint_sensitivity_token("e-sens", "draft_reply", db_path=_db_path)
    assert first.ok is True
    second = await mint_sensitivity_token("e-sens", "draft_reply", db_path=_db_path)
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "NEEDS_USER_CONFIRMATION"

    # Pending refusal was cleared — a repeat confirm finds nothing.
    assert await confirm_pending_escalation(_db_path, caller_origin="discord:home") is None


async def test_no_brick_confirm_without_pending_is_noop(_db_path: str) -> None:
    """No-brick: an escalation confirmation with no pending refusal is a
    harmless no-op — it does NOT create a spurious confirmation, and later
    normal turns are unaffected."""
    resolved = await confirm_pending_escalation(_db_path, caller_origin="discord:home")
    assert resolved is None
    # No confirmation was created for anything.
    assert (
        await consume_sensitivity_confirmation(
            _db_path, email_id="e-sens", task_type="draft_reply"
        )
        is False
    )


async def test_confirm_correlates_only_the_matching_caller(_db_path: str) -> None:
    """A pending refusal for caller A is not consumable by caller B."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    await record_pending_sensitive_refusal(
        _db_path, caller_origin="discord:home", email_id="e-sens", task_type="draft_reply",
    )
    # A different caller confirming finds nothing.
    assert await confirm_pending_escalation(_db_path, caller_origin="discord:other") is None
    # The original caller can still confirm.
    assert await confirm_pending_escalation(_db_path, caller_origin="discord:home") == (
        "e-sens",
        "draft_reply",
    )


async def test_escalation_claim_is_atomic_second_confirm_is_none(_db_path: str) -> None:
    """CR-6: the claim atomically deletes-returning, so a second confirm for the
    same caller finds nothing (no double-mint from one 'yes')."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    await record_pending_sensitive_refusal(
        _db_path, caller_origin="discord:home", email_id="e-sens", task_type="draft_reply",
    )
    first = await confirm_pending_escalation(_db_path, caller_origin="discord:home")
    assert first == ("e-sens", "draft_reply")
    second = await confirm_pending_escalation(_db_path, caller_origin="discord:home")
    assert second is None


# --- CR-3 / CR-4: Tier-2 grant-approval handshake ---


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("yes", True),
        ("approve", True),
        ("yes, approve", True),
        ("go ahead", True),
        ("no", False),
        ("yes, escalate", False),  # escalation phrase is NOT a grant approval
        ("archive everything forever", False),
    ],
)
def test_is_grant_approval_is_exact(text: str, expected: bool) -> None:
    assert is_grant_approval(text) is expected


async def test_grant_approval_handshake_unblocks_mint(_db_path: str) -> None:
    """CR-3: without a production path to create a grant confirmation, mint_grant
    is permanently blocked. The boundary records a pending grant approval, the
    user 'yes' confirms it, and the scoped mint then succeeds."""
    # Before approval, the Tier-2 mint refuses (CR-3 would be a permanent block
    # if nothing could ever create the confirmation).
    pre = await mint_grant(ActionType.ARCHIVE, ["e1", "e2"], _future(), db_path=_db_path)
    assert pre.ok is False
    assert pre.error is not None
    assert pre.error.code == "NEEDS_USER_CONFIRMATION"

    # Boundary records what a "yes" would authorize (exact email set).
    await record_pending_grant_approval(
        _db_path, caller_origin="discord:home", action_type="archive", email_ids=["e1", "e2"],
    )
    resolved = await confirm_pending_grant(_db_path, caller_origin="discord:home")
    assert resolved == ("archive", ["e1", "e2"])

    # Now the scoped mint succeeds.
    post = await mint_grant(ActionType.ARCHIVE, ["e1", "e2"], _future(), db_path=_db_path)
    assert post.ok is True, post.error


async def test_grant_confirmation_is_email_scoped(_db_path: str) -> None:
    """CR-4: a confirmation for emails {e1,e2} does NOT authorize a mint for a
    different set {e1,e3} — the blast radius is the user-approved set."""
    await record_pending_grant_approval(
        _db_path, caller_origin="discord:home", action_type="archive", email_ids=["e1", "e2"],
    )
    await confirm_pending_grant(_db_path, caller_origin="discord:home")

    # Different email set → refused.
    wrong = await mint_grant(ActionType.ARCHIVE, ["e1", "e3"], _future(), db_path=_db_path)
    assert wrong.ok is False
    assert wrong.error is not None
    assert wrong.error.code == "NEEDS_USER_CONFIRMATION"


async def test_grant_confirmation_order_independent(_db_path: str) -> None:
    """CR-4: email_ids match is order-independent (canonical sorted JSON)."""
    await record_pending_grant_approval(
        _db_path, caller_origin="discord:home", action_type="archive", email_ids=["e2", "e1"],
    )
    await confirm_pending_grant(_db_path, caller_origin="discord:home")
    # Mint with the reverse order still matches.
    ok = await mint_grant(ActionType.ARCHIVE, ["e1", "e2"], _future(), db_path=_db_path)
    assert ok.ok is True, ok.error


async def test_grant_consume_is_single_use(_db_path: str) -> None:
    """The grant confirmation is single-use — a second mint of the same set refuses."""
    await record_pending_grant_approval(
        _db_path, caller_origin="discord:home", action_type="archive", email_ids=["e1"],
    )
    await confirm_pending_grant(_db_path, caller_origin="discord:home")
    first = await mint_grant(ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path)
    assert first.ok is True
    second = await mint_grant(ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path)
    assert second.ok is False
    assert second.error is not None


async def test_direct_consume_grant_confirmation_signature(_db_path: str) -> None:
    """`consume_grant_confirmation` now requires email_ids (CR-4)."""
    await record_pending_grant_approval(
        _db_path, caller_origin="discord:home", action_type="archive", email_ids=["e1"],
    )
    await confirm_pending_grant(_db_path, caller_origin="discord:home")
    assert (
        await consume_grant_confirmation(_db_path, action_type="archive", email_ids=["e1"])
        is True
    )


# --- F-10-5-2-W1: same-turn ordering fix (escalation ARM) ---


async def test_arm_then_mint_same_turn_succeeds(_db_path: str) -> None:
    """Live-walk regression: in the real Discord flow the user's 'yes, escalate'
    and the agent's mint attempt land in the SAME turn, so no confirmation was
    pre-recorded for the exact (email, task). Arming the escalation lets the
    mint verb consume it and proceed — reproduces the exact ordering the walk
    surfaced (F-10-5-2-W1)."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    # Boundary arms on 'yes, escalate' (no pending confirmation for this scope).
    await arm_escalation(_db_path)
    # Agent's mint attempt in the same turn now succeeds by consuming the arm.
    out = await mint_sensitivity_token("e-sens", "chat_completions_tool_call", db_path=_db_path)
    assert out.ok is True, out.error
    assert out.token is not None


async def test_arm_is_single_use(_db_path: str) -> None:
    """The arm is consumed once — a second mint (no fresh arm) refuses."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    await arm_escalation(_db_path)
    first = await mint_sensitivity_token("e-sens", "chat_completions_tool_call", db_path=_db_path)
    assert first.ok is True
    second = await mint_sensitivity_token("e-sens", "chat_completions_tool_call", db_path=_db_path)
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "NEEDS_USER_CONFIRMATION"


async def test_consume_escalation_arm_without_arm_is_false(_db_path: str) -> None:
    """No arm set → consume returns False (no spurious confirmation)."""
    assert (
        await consume_escalation_arm(_db_path, email_id="e-sens", task_type="draft_reply")
        is False
    )


async def test_mint_without_arm_or_confirmation_still_refuses(_db_path: str) -> None:
    """The arm does NOT weaken the gate: with neither a confirmation nor an arm,
    the mint still refuses (non-agent-assertable invariant preserved)."""
    await _seed_sensitive(_db_path, graph_id="e-sens")
    out = await mint_sensitivity_token("e-sens", "draft_reply", db_path=_db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "NEEDS_USER_CONFIRMATION"
