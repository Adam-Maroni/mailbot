"""Story 4-6 — 20-send/day cap enforcement in the drainer.

Pre-seeds N consumed send rows + asserts the drainer refuses the next SEND
when the cap is hit. Verifies both successful + failed sends count, and
that midnight UTC rollover resets the counter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.drainer import DAILY_SEND_CAP, run_tick
from mailbot_api.actions.graph_write import FakeGraphWriteAdapter
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    return db_path


async def _seed_email(db_path: str, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com", "cm-v1", None),
    )


async def _seed_consumed_send_row(
    db_path: str, *, graph_id: str, terminal_at_iso: str, status: str = "applied",
) -> None:
    """Insert a SEND_REPLY row pre-marked as terminal with budget_consumed=1."""
    await _seed_email(db_path, graph_id)
    await execute_write(
        db_path,
        "INSERT INTO pending_actions ("
        "  email_id, action_type, tier, payload, proposed_at, status, "
        "  terminal_at, budget_consumed, change_marker_at_propose"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (graph_id, "send_reply", 3, "{}", terminal_at_iso, status,
         terminal_at_iso, 1, "cm-v1"),
    )


async def _propose_and_arm_send(db_path: str, graph_id: str) -> int:
    """Propose a fresh SEND_REPLY, force into 'pending', mint matching grant."""
    await _seed_email(db_path, graph_id)
    out = await propose_action(
        graph_id, ActionType.SEND_REPLY, payload={"body": "Hi"}, db_path=db_path,
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    await mint_grant(
        ActionType.SEND_REPLY, [graph_id],
        datetime.now(timezone.utc) + timedelta(hours=1),
        db_path=db_path,
    )
    return out.action_id


async def test_send_within_cap_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No prior consumption → SEND_REPLY drains normally + budget=1."""
    db_path = _setup(tmp_path, monkeypatch)
    aid = await _propose_and_arm_send(db_path, "e-fresh")
    await run_tick(db_path, FakeGraphWriteAdapter())
    with get_connection(db_path) as conn:
        status, reason, budget = conn.execute(
            "SELECT status, failure_reason, budget_consumed "
            "FROM pending_actions WHERE id = ?", (aid,),
        ).fetchone()
    assert status == "applied"
    assert reason is None
    assert budget == 1


async def test_send_at_cap_refused_with_daily_cap_exceeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20 prior consumed today → 21st SEND_REPLY refused with daily_send_cap_exceeded."""
    db_path = _setup(tmp_path, monkeypatch)
    today_midnight = (
        datetime.now(timezone.utc)
        .replace(hour=12, minute=0, second=0, microsecond=0)
    ).isoformat().replace("+00:00", "Z")
    for i in range(DAILY_SEND_CAP):
        await _seed_consumed_send_row(
            db_path, graph_id=f"e-prev-{i}", terminal_at_iso=today_midnight,
        )
    # Now propose the 21st.
    aid = await _propose_and_arm_send(db_path, "e-21st")
    await run_tick(db_path, FakeGraphWriteAdapter())
    with get_connection(db_path) as conn:
        status, reason, budget = conn.execute(
            "SELECT status, failure_reason, budget_consumed "
            "FROM pending_actions WHERE id = ?", (aid,),
        ).fetchone()
    assert status == "failed"
    assert reason == "daily_send_cap_exceeded"
    assert budget == 1  # AR-D5-2 — failed sends still consume budget


async def test_failed_send_counts_toward_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """19 successful + 1 failed (both budget_consumed=1) = 20 total → 21st refused."""
    db_path = _setup(tmp_path, monkeypatch)
    today_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for i in range(19):
        await _seed_consumed_send_row(
            db_path, graph_id=f"e-ok-{i}", terminal_at_iso=today_iso,
        )
    # 1 failed send (still budget=1 per AR-D5-2).
    await _seed_consumed_send_row(
        db_path, graph_id="e-failed", terminal_at_iso=today_iso, status="failed",
    )
    aid = await _propose_and_arm_send(db_path, "e-21st")
    await run_tick(db_path, FakeGraphWriteAdapter())
    with get_connection(db_path) as conn:
        status, reason = conn.execute(
            "SELECT status, failure_reason FROM pending_actions WHERE id = ?",
            (aid,),
        ).fetchone()
    assert status == "failed"
    assert reason == "daily_send_cap_exceeded"


async def test_yesterday_rows_do_not_count_toward_today_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows with terminal_at = yesterday don't count against today's cap."""
    db_path = _setup(tmp_path, monkeypatch)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0,
    ).isoformat().replace("+00:00", "Z")
    # Seed 25 yesterday-consumed rows.
    for i in range(25):
        await _seed_consumed_send_row(
            db_path, graph_id=f"e-yesterday-{i}", terminal_at_iso=yesterday,
        )
    aid = await _propose_and_arm_send(db_path, "e-today")
    await run_tick(db_path, FakeGraphWriteAdapter())
    with get_connection(db_path) as conn:
        status = conn.execute(
            "SELECT status FROM pending_actions WHERE id = ?", (aid,),
        ).fetchone()[0]
    assert status == "applied"  # yesterday's count doesn't apply
