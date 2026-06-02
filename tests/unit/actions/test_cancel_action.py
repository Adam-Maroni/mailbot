"""Story 4-6 — cancel_action unit tests.

Real on-disk SQLite. Tests the atomic cancel + race-safe interaction with
cooling_off_tick.
"""

from __future__ import annotations

from pathlib import Path

from mailbot_api.actions.cancel import cancel_action
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.verbs.cancel_action import cancel_action as cancel_action_shim


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_send_reply_cooling_off(db_path: str) -> int:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("e-1", "2026-06-02T00:00:00Z", "Subject", "alice@example.com", "cm-v1", None),
    )
    out = await propose_action(
        "e-1", ActionType.SEND_REPLY,
        payload={"body": "Hi"}, db_path=db_path,
    )
    return out.action_id


async def test_cancel_action_in_cooling_off_succeeds(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _seed_send_reply_cooling_off(db_path)
    out = await cancel_action(aid, db_path=db_path)
    assert out.ok is True
    assert out.cancelled is True
    assert out.reason is None
    with get_connection(db_path) as conn:
        status, terminal_at = conn.execute(
            "SELECT status, terminal_at FROM pending_actions WHERE id = ?",
            (aid,),
        ).fetchone()
    assert status == "cancelled"
    assert terminal_at is not None


async def test_cancel_already_promoted_row_is_noop(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _seed_send_reply_cooling_off(db_path)
    # Promote manually — simulate cooling-off ticker already ran.
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
        (aid,),
    )
    out = await cancel_action(aid, db_path=db_path)
    assert out.ok is True
    assert out.cancelled is False
    assert out.reason == "action_not_in_cooling_off"


async def test_cancel_nonexistent_action_is_noop(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    out = await cancel_action(99999, db_path=db_path)
    assert out.ok is True
    assert out.cancelled is False
    assert out.reason == "action_not_in_cooling_off"


async def test_cancel_already_cancelled_is_noop(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _seed_send_reply_cooling_off(db_path)
    first = await cancel_action(aid, db_path=db_path)
    assert first.cancelled is True
    second = await cancel_action(aid, db_path=db_path)
    assert second.cancelled is False
    assert second.reason == "action_not_in_cooling_off"


async def test_cancel_via_verb_shim(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _seed_send_reply_cooling_off(db_path)
    out = await cancel_action_shim(aid, db_path=db_path)
    assert out.ok is True
    assert out.cancelled is True
