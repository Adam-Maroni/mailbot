"""Story 4-6 — cooling_off_tick unit tests.

Real on-disk SQLite. Tests the promote-after-window + 0-second short-circuit
+ race-safe atomic UPDATE behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.cooling_off import cooling_off_tick
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


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


async def _send_reply_cooling_off(db_path: str) -> int:
    await _seed_email(db_path)
    out = await propose_action(
        "e-1", ActionType.SEND_REPLY,
        payload={"body": "Hi", "to": ["x@y.com"]}, db_path=db_path,
    )
    assert out.status == "cooling_off"
    return out.action_id


def _status_of(db_path: str, action_id: int) -> str:
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (action_id,),
        ).fetchone()[0]


async def test_cooling_off_tick_with_past_proposed_at_promotes(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _send_reply_cooling_off(db_path)
    # Backdate proposed_at to 70 seconds ago — past the 60s default window.
    past_iso = (
        datetime.now(timezone.utc) - timedelta(seconds=70)
    ).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "UPDATE pending_actions SET proposed_at = ? WHERE id = ?",
        (past_iso, aid),
    )

    promoted = await cooling_off_tick(db_path)
    assert promoted == 1
    assert _status_of(db_path, aid) == "pending"


async def test_cooling_off_tick_within_window_does_not_promote(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aid = await _send_reply_cooling_off(db_path)
    # proposed_at is now() — well within the 60s window.
    promoted = await cooling_off_tick(db_path)
    assert promoted == 0
    assert _status_of(db_path, aid) == "cooling_off"


async def test_cooling_off_zero_seconds_promotes_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path)
    aid = await _send_reply_cooling_off(db_path)
    monkeypatch.setenv("MAILBOT_COOLING_OFF_SECONDS", "0")
    promoted = await cooling_off_tick(db_path)
    assert promoted == 1
    assert _status_of(db_path, aid) == "pending"


async def test_cooling_off_invalid_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path)
    aid = await _send_reply_cooling_off(db_path)
    monkeypatch.setenv("MAILBOT_COOLING_OFF_SECONDS", "not-a-number")
    promoted = await cooling_off_tick(db_path)
    # Default 60s; proposed_at is now → no promotion.
    assert promoted == 0
    assert _status_of(db_path, aid) == "cooling_off"


async def test_cooling_off_tick_promotes_multiple_rows(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    aids = []
    past_iso = (
        datetime.now(timezone.utc) - timedelta(seconds=120)
    ).isoformat().replace("+00:00", "Z")
    for i in range(3):
        await _seed_email(db_path, graph_id=f"e-{i}")
        out = await propose_action(
            f"e-{i}", ActionType.SEND_REPLY,
            payload={"body": "Hi"}, db_path=db_path,
        )
        await execute_write(
            db_path,
            "UPDATE pending_actions SET proposed_at = ? WHERE id = ?",
            (past_iso, out.action_id),
        )
        aids.append(out.action_id)

    promoted = await cooling_off_tick(db_path)
    assert promoted == 3
    for aid in aids:
        assert _status_of(db_path, aid) == "pending"
