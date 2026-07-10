"""Story 10.5.2 (Epic 10.5 Cluster B) — mints are NOT agent-assertable.

F-10-5-5 (self-mint sensitivity token, no confirmation) + F-10-5-8 (Tier-2
grant minted with no user "yes") are fixed by requiring a genuine user-gated
confirmation record — created only at the chat boundary, never by a verb — and
consumed single-use at mint time.

These tests prove:
  1. mint_sensitivity_token REFUSES (NEEDS_USER_CONFIRMATION) with no record.
  2. mint_sensitivity_token SUCCEEDS once a confirmation record exists.
  3. the confirmation is single-use — a second mint refuses.
  4. mint_grant REFUSES (NEEDS_USER_CONFIRMATION) with no record.
  5. mint_grant SUCCEEDS once a grant confirmation exists.
  6. an expired confirmation does NOT satisfy the gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.actions.types import ActionType
from mailbot_api.actions.user_confirmation import (
    record_grant_confirmation,
    record_sensitivity_confirmation,
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


async def _seed_sensitive_email(db_path: str, *, graph_id: str = "e1") -> None:
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


# --- sensitivity token ---


async def test_sensitivity_mint_refuses_without_user_confirmation(_db_path: str) -> None:
    """F-10-5-5: no user confirmation → mint refuses NEEDS_USER_CONFIRMATION."""
    await _seed_sensitive_email(_db_path)
    result = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NEEDS_USER_CONFIRMATION"
    assert result.token is None


async def test_sensitivity_mint_succeeds_with_user_confirmation(_db_path: str) -> None:
    """A genuine confirmation record (only the boundary creates it) unlocks the mint."""
    await _seed_sensitive_email(_db_path)
    await record_sensitivity_confirmation(_db_path, email_id="e1", task_type="draft_reply")
    result = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert result.ok is True, result.error
    assert result.token is not None


async def test_sensitivity_confirmation_is_single_use(_db_path: str) -> None:
    """The confirmation is consumed once — a second mint refuses."""
    await _seed_sensitive_email(_db_path)
    await record_sensitivity_confirmation(_db_path, email_id="e1", task_type="draft_reply")
    first = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert first.ok is True
    second = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "NEEDS_USER_CONFIRMATION"


async def test_sensitivity_confirmation_scope_is_exact(_db_path: str) -> None:
    """A confirmation for a DIFFERENT task does NOT unlock this mint."""
    await _seed_sensitive_email(_db_path)
    await record_sensitivity_confirmation(_db_path, email_id="e1", task_type="summary_short")
    result = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NEEDS_USER_CONFIRMATION"


async def test_expired_confirmation_does_not_satisfy_gate(_db_path: str) -> None:
    """A confirmation older than the TTL is not valid."""
    await _seed_sensitive_email(_db_path)
    # Insert a stale confirmation directly (created_at 20 min ago > 10-min TTL).
    stale = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat().replace(
        "+00:00", "Z"
    )
    await execute_write(
        _db_path,
        "INSERT INTO user_confirmations "
        "(scope, email_id, task_type, action_type, email_ids, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("sensitivity_token", "e1", "draft_reply", None, None, stale),
    )
    result = await mint_sensitivity_token("e1", "draft_reply", db_path=_db_path)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NEEDS_USER_CONFIRMATION"


# --- grant ---


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def test_grant_mint_refuses_without_user_confirmation(_db_path: str) -> None:
    """F-10-5-8: no user confirmation → Tier-2 grant refuses."""
    result = await mint_grant(
        ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NEEDS_USER_CONFIRMATION"


async def test_grant_mint_succeeds_with_user_confirmation(_db_path: str) -> None:
    """A grant confirmation (only the boundary creates it) unlocks mint_grant."""
    await record_grant_confirmation(_db_path, action_type="archive", email_ids=["e1"])
    result = await mint_grant(
        ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path,
    )
    assert result.ok is True, result.error
    assert result.grant_id is not None


async def test_grant_confirmation_is_single_use(_db_path: str) -> None:
    """The grant confirmation is consumed once — a second mint refuses."""
    await record_grant_confirmation(_db_path, action_type="archive", email_ids=["e1"])
    first = await mint_grant(ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path)
    assert first.ok is True
    second = await mint_grant(ActionType.ARCHIVE, ["e1"], _future(), db_path=_db_path)
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "NEEDS_USER_CONFIRMATION"
