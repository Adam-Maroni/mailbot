"""Story 4-8 — Tier-1 24-hour reverter unit tests.

Real SQLite. Tests every refusal branch + the inverse-action map.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.reverter import REVERT_WINDOW, revert_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(db_path: str, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com", "cm-v1", None),
    )


async def _mark_applied_with_history(
    db_path: str, action_id: int, *, terminal_at: str | None = None,
) -> None:
    """Simulate a successful drain: status='applied' + action_history row."""
    if terminal_at is None:
        terminal_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'applied', terminal_at = ? WHERE id = ?",
        (terminal_at, action_id),
    )
    await execute_write(
        db_path,
        "INSERT INTO action_history (action_id, pre_state, applied_at) VALUES (?, ?, ?)",
        (action_id, "{}", terminal_at),
    )


async def test_revert_mark_read_within_24h_succeeds_with_mark_unread_inverse(
    tmp_path: Path,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    assert rev.original_action_id == out.action_id
    assert rev.revert_action_id is not None
    assert rev.revert_action_id != out.action_id

    # New pending_actions row has the inverse action_type.
    with get_connection(db_path) as conn:
        new_row = conn.execute(
            "SELECT action_type, tier, status FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()
        history_revoked = conn.execute(
            "SELECT reverted_at FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert new_row[0] == "mark_unread"
    assert new_row[1] == 1
    assert new_row[2] == "pending"
    assert history_revoked is not None


async def test_revert_mark_unread_inverse_pairs_to_mark_read(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_UNREAD, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    with get_connection(db_path) as conn:
        action_type = conn.execute(
            "SELECT action_type FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()[0]
    assert action_type == "mark_read"


async def test_revert_add_local_category_inverse_pairs_to_remove(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.ADD_LOCAL_CATEGORY, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    with get_connection(db_path) as conn:
        action_type = conn.execute(
            "SELECT action_type FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()[0]
    assert action_type == "remove_local_category"


async def test_revert_tier_2_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    # Manually push to applied for the test.
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error is not None
    assert rev.error.code == "ONLY_TIER_1_REVERTIBLE"


async def test_revert_not_applied_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Don't mark applied — stays 'pending'.
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "NOT_APPLIED"


async def test_revert_beyond_24h_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    old_iso = (
        datetime.now(timezone.utc) - REVERT_WINDOW - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")
    await _mark_applied_with_history(db_path, out.action_id, terminal_at=old_iso)
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "REVERT_WINDOW_EXPIRED"


async def test_revert_already_reverted_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)
    first = await revert_action(out.action_id, db_path=db_path)
    assert first.ok is True
    second = await revert_action(out.action_id, db_path=db_path)
    assert second.ok is False
    assert second.error.code == "ALREADY_REVERTED"


async def test_revert_move_to_triage_folder_refused_with_inverse_unavailable(
    tmp_path: Path,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MOVE_TO_TRIAGE_FOLDER, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "INVERSE_UNAVAILABLE"


async def test_revert_nonexistent_action_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    rev = await revert_action(99999, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "ACTION_NOT_FOUND"
