"""Story 4-5 — replay_action unit tests.

Real on-disk SQLite. Refusal coverage: not-found, not-failed, window-expired,
grant-invalid for Tier-2/3. Happy path: re-queue + status flip back to pending.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.replay import REPLAY_WINDOW, replay_action
from mailbot_api.actions.types import ActionType
from mailbot_api.actions.user_confirmation import record_grant_confirmation
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


# Story 10.5.2 (F-10-5-8): mint_grant now requires a user-gated confirmation.
# Auto-seed one before each mint so these Story-4-5 replay tests keep their
# original setup intent (gate coverage lives in
# tests/integration/test_mint_requires_user_confirmation.py).
@pytest.fixture(autouse=True)
def _auto_confirm_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    import mailbot_api.actions.authorization as _authz

    _real_mint = _authz.mint_grant

    async def _mint_with_confirmation(action_type, email_ids, expires_at, *, db_path):  # type: ignore[no-untyped-def]
        await record_grant_confirmation(
            db_path, action_type=action_type.value, email_ids=list(email_ids),
        )
        return await _real_mint(action_type, email_ids, expires_at, db_path=db_path)

    monkeypatch.setattr(_authz, "mint_grant", _mint_with_confirmation)
    monkeypatch.setattr("tests.unit.actions.test_replay.mint_grant", _mint_with_confirmation)


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(db_path: str, *, graph_id: str = "e-1") -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com", "cm-v1", None),
    )


async def _mark_failed(
    db_path: str, action_id: int, *, terminal_at: str,
) -> None:
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'failed', failure_reason = 'test', "
        "terminal_at = ? WHERE id = ?",
        (terminal_at, action_id),
    )


async def test_replay_nonexistent_action_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await replay_action(99999, db_path=db_path)
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "ACTION_NOT_FOUND"


async def test_replay_pending_action_refused_with_not_failed(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Don't mark failed — leave in 'pending'.
    res = await replay_action(out.action_id, db_path=db_path)
    assert res.ok is False
    assert res.error.code == "ACTION_NOT_FAILED"


async def test_replay_move_family_target_deleted_refuses_directs_to_revert(
    tmp_path: Path,
) -> None:
    """Story 10.5.4 AC-3 / F-10-6-2: replaying a move-family row whose target
    email is soft-deleted must NOT silently re-queue (the drainer would just
    re-refuse target_deleted). It refuses with the distinct
    REPLAY_MOVE_TARGET_DELETED code directing the operator to `mailbot revert`.
    """
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="mv-1")
    out = await propose_action(
        "mv-1",
        ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-triage"},
        db_path=db_path,
    )
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await _mark_failed(db_path, out.action_id, terminal_at=now_iso)
    # Simulate the move-induced soft-delete (10-1 walk F5): the move out of the
    # synced folder set arrives as an @removed delta.
    await execute_write(
        db_path,
        "UPDATE emails SET deleted_at = ?, removed_reason = 'deleted' WHERE graph_id = ?",
        (now_iso, "mv-1"),
    )

    res = await replay_action(out.action_id, db_path=db_path)

    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "REPLAY_MOVE_TARGET_DELETED"
    assert "revert" in res.error.message.lower()

    # The row must NOT have been re-queued (still 'failed', not flipped to pending).
    with get_connection(db_path) as conn:
        status = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (out.action_id,),
        ).fetchone()[0]
    assert status == "failed"


async def test_replay_within_7_days_tier_1_happy_path(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Mark failed with terminal_at = today.
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await _mark_failed(db_path, out.action_id, terminal_at=now_iso)

    res = await replay_action(out.action_id, db_path=db_path)
    assert res.ok is True
    assert res.action_id == out.action_id
    # Verify status flipped back.
    with get_connection(db_path) as conn:
        status, terminal_at, failure_reason, retry_count = conn.execute(
            "SELECT status, terminal_at, failure_reason, retry_count "
            "FROM pending_actions WHERE id = ?",
            (out.action_id,),
        ).fetchone()
    assert status == "pending"
    assert terminal_at is None
    assert failure_reason is None
    assert retry_count == 0


async def test_replay_outside_7_day_window_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    old_iso = (
        datetime.now(timezone.utc) - REPLAY_WINDOW - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")
    await _mark_failed(db_path, out.action_id, terminal_at=old_iso)

    res = await replay_action(out.action_id, db_path=db_path)
    assert res.ok is False
    assert res.error.code == "REPLAY_WINDOW_EXPIRED"


async def test_replay_tier_3_without_valid_grant_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await _mark_failed(db_path, out.action_id, terminal_at=now_iso)
    # No grant exists → replay refused with GRANT_INVALID.
    res = await replay_action(out.action_id, db_path=db_path)
    assert res.ok is False
    assert res.error.code == "GRANT_INVALID"


async def test_replay_tier_3_with_valid_grant_succeeds(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path)
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await _mark_failed(db_path, out.action_id, terminal_at=now_iso)
    # Mint a fresh grant.
    await mint_grant(
        ActionType.DELETE, ["e-1"],
        datetime.now(timezone.utc) + timedelta(hours=1),
        db_path=db_path,
    )
    res = await replay_action(out.action_id, db_path=db_path)
    assert res.ok is True
