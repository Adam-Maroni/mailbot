"""Integration tests for Story 1-8 worker_health + sync-health alarm.

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - mocked sync_worker.run_once via monkeypatch
  - real notifications.send_urgent writing to a tmp_path MAILBOT_LOGS_PATH
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.notifications import send_urgent
from mailbot_api.sync.sync_worker import SyncResult
from mailbot_api.worker import (
    STALE_THRESHOLD_MINUTES,
    WorkerState,
    _check_alarm,
    _run_sync_iteration,
    minutes_since,
    sync_loop,
    upsert_heartbeat,
)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def test_worker_health_table_exists_after_migration(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    row = await fetchone(
        db_path,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='worker_health'",
        (),
    )
    assert row == ("worker_health",)


async def test_upsert_heartbeat_ok(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    await upsert_heartbeat(db_path, component="sync", outcome="ok")
    row = await fetchone(
        db_path, "SELECT component, last_outcome, last_error FROM worker_health WHERE component='sync'", ()
    )
    assert row == ("sync", "ok", None)


async def test_upsert_heartbeat_failed_records_error(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    await upsert_heartbeat(
        db_path, component="sync", outcome="failed", error="GraphAuthError: invalid_grant"
    )
    row = await fetchone(
        db_path, "SELECT last_outcome, last_error FROM worker_health WHERE component='sync'", ()
    )
    assert row == ("failed", "GraphAuthError: invalid_grant")


async def test_run_sync_iteration_success_writes_ok_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    state = WorkerState(alarm_fired_for_episode=True)  # simulate alarm was firing

    async def fake_run_once(_db_path: str) -> SyncResult:
        return SyncResult(
            messages_seen=0,
            messages_upserted=0,
            messages_soft_deleted=0,
            duration_ms=10,
            new_delta_link="https://graph.microsoft.com/v1.0/delta?$deltatoken=D",
        )

    monkeypatch.setattr("mailbot_api.worker.run_once", fake_run_once)
    result = await _run_sync_iteration(db_path, state)
    assert result is not None
    # Heartbeat written.
    row = await fetchone(
        db_path, "SELECT last_outcome FROM worker_health WHERE component='sync'", ()
    )
    assert row == ("ok",)
    # Alarm flag cleared on success.
    assert state.alarm_fired_for_episode is False


async def test_run_sync_iteration_failure_writes_failed_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    state = WorkerState()

    async def boom(_db_path: str) -> SyncResult:
        raise RuntimeError("oops")

    monkeypatch.setattr("mailbot_api.worker.run_once", boom)
    result = await _run_sync_iteration(db_path, state)
    assert result is None
    row = await fetchone(
        db_path, "SELECT last_outcome, last_error FROM worker_health WHERE component='sync'", ()
    )
    assert row is not None
    assert row[0] == "failed"
    assert "RuntimeError" in (row[1] or "")
    # Failure does NOT clear the alarm-fired flag.
    assert state.alarm_fired_for_episode is False  # was False to begin with


async def test_check_alarm_does_not_fire_when_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    state = WorkerState()

    # Fresh ok heartbeat.
    await upsert_heartbeat(db_path, component="sync", outcome="ok")
    await _check_alarm(db_path, state)
    assert state.alarm_fired_for_episode is False
    # No notification dispatched.
    assert not (tmp_path / "logs" / "notifications_pending.jsonl").exists()


async def test_check_alarm_fires_on_failed_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `failed` outcome (regardless of elapsed minutes) trips the alarm
    immediately — the alarm condition is `last_outcome != ok OR elapsed > 60m`."""
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    state = WorkerState()
    await upsert_heartbeat(db_path, component="sync", outcome="failed", error="boom")
    await _check_alarm(db_path, state)
    assert state.alarm_fired_for_episode is True
    jsonl = (tmp_path / "logs" / "notifications_pending.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) == 1
    record = json.loads(jsonl[0])
    assert "sync stale" in record["message"]
    assert record["kind"] == "urgent"


async def test_alarm_fires_only_once_per_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    state = WorkerState()
    await upsert_heartbeat(db_path, component="sync", outcome="failed", error="boom")
    await _check_alarm(db_path, state)
    await _check_alarm(db_path, state)
    await _check_alarm(db_path, state)
    jsonl = (tmp_path / "logs" / "notifications_pending.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl) == 1  # debounced


async def test_alarm_resets_on_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After alarm fires + sync recovers, a subsequent failure should fire the alarm AGAIN."""
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    state = WorkerState()

    # Episode 1: failure → alarm fires.
    await upsert_heartbeat(db_path, component="sync", outcome="failed", error="boom")
    await _check_alarm(db_path, state)
    assert state.alarm_fired_for_episode is True

    # Recovery via _run_sync_iteration.
    async def good(_db_path: str) -> SyncResult:
        return SyncResult(
            messages_seen=1,
            messages_upserted=1,
            messages_soft_deleted=0,
            duration_ms=5,
            new_delta_link="d",
        )

    monkeypatch.setattr("mailbot_api.worker.run_once", good)
    await _run_sync_iteration(db_path, state)
    assert state.alarm_fired_for_episode is False  # cleared

    # Episode 2: failure again — alarm should fire again.
    await upsert_heartbeat(db_path, component="sync", outcome="failed", error="boom2")
    await _check_alarm(db_path, state)
    assert state.alarm_fired_for_episode is True

    jsonl_lines = (tmp_path / "logs" / "notifications_pending.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 2  # two episodes, two notifications


async def test_check_alarm_silent_when_no_heartbeat_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First 4 minutes of startup: worker_health is empty; alarm must not fire."""
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    state = WorkerState()
    await _check_alarm(db_path, state)
    assert state.alarm_fired_for_episode is False


async def test_send_urgent_writes_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    send_urgent("test message")
    send_urgent("another")
    path = tmp_path / "logs" / "notifications_pending.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["message"] == "test message"
    assert r1["kind"] == "urgent"
    assert r1["ts"].endswith("Z")


async def test_sync_loop_runs_bounded_iterations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_loop with iterations=2 + sleep=no-op runs exactly 2 sync passes."""
    db_path = await _prepare_db(tmp_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))

    calls: list[int] = []

    async def fake_run_once(_db_path: str) -> SyncResult:
        calls.append(len(calls) + 1)
        return SyncResult(
            messages_seen=0,
            messages_upserted=0,
            messages_soft_deleted=0,
            duration_ms=1,
            new_delta_link="d",
        )

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("mailbot_api.worker.run_once", fake_run_once)

    await sync_loop(db_path, interval_seconds=0, sleep=fake_sleep, iterations=2)
    assert calls == [1, 2]


def test_minutes_since_basic() -> None:
    from datetime import datetime, timedelta, timezone

    ten_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elapsed = minutes_since(ten_min_ago)
    assert 9.0 <= elapsed <= 11.0  # 1-minute tolerance


def test_stale_threshold_constant() -> None:
    """Architecture FR-1.5 pins 1 hour (60 min)."""
    assert STALE_THRESHOLD_MINUTES == 60
