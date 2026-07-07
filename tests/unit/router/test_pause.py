"""Tests for mailbot_api/router/pause.py (Story 2-9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.pause import _reset_pause_state_for_test, get_pause_state


@pytest.fixture
def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "pause.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _clean_pause() -> None:
    _reset_pause_state_for_test()
    yield
    _reset_pause_state_for_test()


async def test_initial_state_is_unpaused(_fresh_db: str) -> None:
    state = get_pause_state()
    await state.initialize(_fresh_db)
    assert state.is_paused() is False
    assert state.reason() is None


async def test_pause_then_resume_round_trip(_fresh_db: str) -> None:
    state = get_pause_state()
    await state.initialize(_fresh_db)
    await state.pause(_fresh_db, reason="manual test")
    assert state.is_paused() is True
    assert state.reason() == "manual test"
    await state.resume(_fresh_db)
    assert state.is_paused() is False
    assert state.reason() is None


async def test_pause_persists_across_initialize(_fresh_db: str) -> None:
    """Simulating restart: pause via state A, drop the in-memory flag,
    re-initialize state B — it should pick up the persisted paused=1."""
    state_a = get_pause_state()
    await state_a.initialize(_fresh_db)
    await state_a.pause(_fresh_db, reason="across-restart")

    _reset_pause_state_for_test()
    state_b = get_pause_state()
    await state_b.initialize(_fresh_db)
    assert state_b.is_paused() is True
    assert state_b.reason() == "across-restart"


# ---- Story 10.5.1 (F4, CRITICAL) — cross-process authoritative read ----------


async def test_is_paused_now_sees_bare_db_pause_without_initialize(_fresh_db: str) -> None:
    """THE regression that would have caught F4.

    Simulate the two-process reality: "process A" (the API) writes paused=1 to
    the DB via a first PauseState instance; "process B" (the worker drainer)
    NEVER calls initialize() so its in-memory mirror is still False. The
    authoritative reader `is_paused_now(db_path)` must observe the DB truth
    WITHOUT any initialize() on the checking instance.

    Contrast `test_pause_persists_across_initialize` above, which only covers
    the restart-reseed path (initialize() IS called on the fresh instance) —
    that path passed all along; the cross-process LIVE path is the F4 gap.
    """
    # Process A pauses (writes the DB row).
    state_a = get_pause_state()
    await state_a.initialize(_fresh_db)
    await state_a.pause(_fresh_db, reason="process-a-pause")

    # Process B: fresh instance, NEVER initialized — its stale mirror says False.
    from mailbot_api.router.pause import PauseState

    state_b = PauseState()
    assert state_b.is_paused() is False  # stale in-memory mirror (the F4 bug)
    # Authoritative read hits the DB and sees the truth.
    assert await state_b.is_paused_now(_fresh_db) is True
    assert await state_b.reason_now(_fresh_db) == "process-a-pause"


async def test_is_paused_now_false_when_unpaused(_fresh_db: str) -> None:
    from mailbot_api.router.pause import PauseState

    state = PauseState()
    assert await state.is_paused_now(_fresh_db) is False
    assert await state.reason_now(_fresh_db) is None


async def test_is_paused_now_reflects_live_resume(_fresh_db: str) -> None:
    """After a resume writes the DB row, the authoritative reader flips back to
    False on the very next read — no re-initialize needed."""
    state_a = get_pause_state()
    await state_a.initialize(_fresh_db)
    await state_a.pause(_fresh_db, reason="temp")

    from mailbot_api.router.pause import PauseState

    reader = PauseState()
    assert await reader.is_paused_now(_fresh_db) is True
    await state_a.resume(_fresh_db)
    assert await reader.is_paused_now(_fresh_db) is False
    assert await reader.reason_now(_fresh_db) is None


async def test_is_paused_now_fails_closed_on_read_error() -> None:
    """Fail-closed contract: a DB read failure is treated as PAUSED so a hiccup
    can never silently re-open the write path."""
    from mailbot_api.router.pause import PauseState

    state = PauseState()
    # A nonexistent DB path raises inside fetchone → fail-closed → True.
    assert await state.is_paused_now("/nonexistent/dir/definitely-not-a.db") is True
