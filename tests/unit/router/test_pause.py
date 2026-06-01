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
