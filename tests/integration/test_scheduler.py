"""Integration tests for Story 6-6 `mailbot_api.observability.scheduler.Scheduler`.

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - real `worker_health` upserts via the existing query layer
  - asyncio with very short intervals so the test exercises real timing

Coverage:
  - register + start spins one task per registered component
  - successful iteration writes worker_health outcome="ok"
  - failed iteration writes worker_health outcome="failed" + sanitized error
  - one task failing does NOT crash other tasks (single-task isolation)
  - slow-task threshold emits the documented warning log event
  - managed task heartbeat reflects underlying instance liveness
  - cannot register after start (raises)
  - clean stop() cancels all tasks and stops managed instances
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.scheduler import (
    Scheduler,
)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _read_health(db_path: str, component: str) -> tuple[str, str | None] | None:
    row = await fetchone(
        db_path,
        "SELECT last_outcome, last_error FROM worker_health WHERE component = ?",
        (component,),
    )
    if row is None:
        return None
    return (row[0], row[1])


async def test_scheduler_interval_task_writes_ok_heartbeat(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    call_count = 0

    async def _tick() -> None:
        nonlocal call_count
        call_count += 1

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("test_ok", 0.05, _tick)
    await scheduler.start()
    try:
        await asyncio.sleep(0.15)
    finally:
        await scheduler.stop(timeout=2.0)

    assert call_count >= 2
    health = await _read_health(db_path, "test_ok")
    assert health is not None
    assert health == ("ok", None)


async def test_scheduler_interval_task_failure_writes_failed_heartbeat(
    tmp_path: Path,
) -> None:
    db_path = await _prepare_db(tmp_path)
    call_count = 0

    async def _tick() -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("synthetic test failure")

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("test_fail", 0.05, _tick)
    await scheduler.start()
    try:
        await asyncio.sleep(0.15)
    finally:
        await scheduler.stop(timeout=2.0)

    assert call_count >= 1
    health = await _read_health(db_path, "test_fail")
    assert health is not None
    outcome, error = health
    assert outcome == "failed"
    assert error is not None
    assert "RuntimeError" in error
    assert "synthetic test failure" in error


async def test_scheduler_one_task_failure_does_not_affect_other_tasks(
    tmp_path: Path,
) -> None:
    db_path = await _prepare_db(tmp_path)
    healthy_calls = 0

    async def _healthy() -> None:
        nonlocal healthy_calls
        healthy_calls += 1

    async def _broken() -> None:
        raise ValueError("oops")

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("healthy_task", 0.05, _healthy)
    scheduler.register_interval_task("broken_task", 0.05, _broken)
    await scheduler.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        await scheduler.stop(timeout=2.0)

    assert healthy_calls >= 2

    h = await _read_health(db_path, "healthy_task")
    b = await _read_health(db_path, "broken_task")
    assert h is not None and h[0] == "ok"
    assert b is not None and b[0] == "failed"


async def test_scheduler_cannot_register_after_start(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)

    async def _noop() -> None:
        return

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("first", 1.0, _noop)
    await scheduler.start()
    try:
        with pytest.raises(RuntimeError, match="cannot register tasks after"):
            scheduler.register_interval_task("late", 1.0, _noop)
    finally:
        await scheduler.stop(timeout=2.0)


async def test_scheduler_slow_task_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = await _prepare_db(tmp_path)

    # Lower the slow-task threshold so the test runs in finite time.
    monkeypatch.setattr(
        "mailbot_api.observability.scheduler.SLOW_TASK_THRESHOLD_SECONDS", 0.05,
    )

    async def _slow() -> None:
        await asyncio.sleep(0.1)

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("slow_task", 0.5, _slow)
    with caplog.at_level(logging.WARNING):
        await scheduler.start()
        try:
            # Give it time for one slow iteration to complete.
            await asyncio.sleep(0.2)
        finally:
            await scheduler.stop(timeout=2.0)

    slow_records = [
        r for r in caplog.records
        if getattr(r, "event", None) == "scheduler.slow_task"
    ]
    assert len(slow_records) >= 1
    assert getattr(slow_records[0], "component", None) == "slow_task"


async def test_scheduler_slow_task_logs_warning_even_when_task_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-3 (2026-06-03): a task that hangs for >SLOW_TASK_THRESHOLD seconds
    AND THEN raises must still emit `event="scheduler.slow_task"`. The
    pre-CR-3 implementation only logged the warning on the success path,
    creating a monitoring blind spot for slow-then-failed tasks."""
    db_path = await _prepare_db(tmp_path)

    monkeypatch.setattr(
        "mailbot_api.observability.scheduler.SLOW_TASK_THRESHOLD_SECONDS", 0.05,
    )

    async def _slow_then_fails() -> None:
        await asyncio.sleep(0.1)
        raise RuntimeError("slow and broken")

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("slow_failing_task", 0.5, _slow_then_fails)
    with caplog.at_level(logging.WARNING):
        await scheduler.start()
        try:
            await asyncio.sleep(0.2)
        finally:
            await scheduler.stop(timeout=2.0)

    slow_records = [
        r for r in caplog.records
        if getattr(r, "event", None) == "scheduler.slow_task"
        and getattr(r, "component", None) == "slow_failing_task"
    ]
    assert len(slow_records) >= 1
    # The outcome label on the slow-task warning records the failure too.
    assert getattr(slow_records[0], "outcome", None) == "failed"

    # AND the failure heartbeat still lands.
    health = await _read_health(db_path, "slow_failing_task")
    assert health is not None
    assert health[0] == "failed"


async def test_scheduler_stop_is_idempotent(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)

    async def _noop() -> None:
        return

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("noop", 0.1, _noop)
    await scheduler.start()
    await scheduler.stop(timeout=2.0)
    # Second stop should be a no-op, NOT raise.
    await scheduler.stop(timeout=2.0)


async def test_scheduler_start_is_idempotent(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)

    async def _noop() -> None:
        return

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("noop", 0.1, _noop)
    await scheduler.start()
    # Second start should be a no-op (existing tasks keep running).
    await scheduler.start()
    await scheduler.stop(timeout=2.0)


async def test_scheduler_managed_task_lifecycle(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)

    class _FakeManaged:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False
            self._task: asyncio.Task[None] | None = None

        async def start(self) -> None:
            self.started = True
            self._task = asyncio.create_task(asyncio.sleep(3600))

        async def stop(self, *, timeout: float = 5.0) -> None:
            self.stopped = True
            if self._task is not None:
                self._task.cancel()

    managed = _FakeManaged()
    scheduler = Scheduler(db_path=db_path)
    scheduler.register_managed_task(
        "fake_managed", managed, heartbeat_interval_seconds=0.05,
    )
    await scheduler.start()
    try:
        await asyncio.sleep(0.1)
    finally:
        await scheduler.stop(timeout=2.0)

    assert managed.started
    assert managed.stopped

    health = await _read_health(db_path, "fake_managed")
    assert health is not None
    assert health[0] == "ok"


async def test_scheduler_managed_task_reports_failed_when_inner_task_done(
    tmp_path: Path,
) -> None:
    db_path = await _prepare_db(tmp_path)

    class _DyingManaged:
        def __init__(self) -> None:
            self._task: asyncio.Task[None] | None = None

        async def start(self) -> None:
            async def _short() -> None:
                return

            self._task = asyncio.create_task(_short())
            # Let it finish immediately.
            await asyncio.sleep(0)

        async def stop(self, *, timeout: float = 5.0) -> None:
            return

    managed = _DyingManaged()
    scheduler = Scheduler(db_path=db_path)
    scheduler.register_managed_task(
        "dying", managed, heartbeat_interval_seconds=0.05,
    )
    await scheduler.start()
    try:
        await asyncio.sleep(0.15)
    finally:
        await scheduler.stop(timeout=2.0)

    health = await _read_health(db_path, "dying")
    assert health is not None
    outcome, error = health
    assert outcome == "failed"
    assert error == "managed_task_not_running"


async def test_scheduler_records_one_row_per_component(tmp_path: Path) -> None:
    """worker_health is keyed by component (UPSERT on CONFLICT), so a long-running
    task contributes ONE row regardless of how many iterations it has run."""
    db_path = await _prepare_db(tmp_path)

    async def _tick() -> None:
        return

    scheduler = Scheduler(db_path=db_path)
    scheduler.register_interval_task("upsert_test", 0.02, _tick)
    await scheduler.start()
    try:
        await asyncio.sleep(0.1)
    finally:
        await scheduler.stop(timeout=2.0)

    rows = await fetchall(
        db_path,
        "SELECT component FROM worker_health WHERE component = ?",
        ("upsert_test",),
    )
    assert len(rows) == 1
