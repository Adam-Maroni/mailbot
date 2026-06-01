"""Tests for mailbot_api/verbs/router_control.py (Story 2-9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.pause import _reset_pause_state_for_test, get_pause_state
from mailbot_api.verbs.router_control import (
    PauseOut,
    ResumeOut,
    pause_router,
    resume_router,
)


@pytest.fixture
def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "ctrl.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _clean_pause() -> None:
    _reset_pause_state_for_test()
    yield
    _reset_pause_state_for_test()


async def test_pause_router_returns_pause_out(_fresh_db: str) -> None:
    await get_pause_state().initialize(_fresh_db)
    out = await pause_router(db_path=_fresh_db, reason="runaway agent")
    assert isinstance(out, PauseOut)
    assert out.ok is True
    assert out.previously_paused is False
    assert out.reason == "runaway agent"
    assert get_pause_state().is_paused() is True


async def test_resume_router_returns_resume_out(_fresh_db: str) -> None:
    await get_pause_state().initialize(_fresh_db)
    await pause_router(db_path=_fresh_db, reason="x")
    out = await resume_router(db_path=_fresh_db)
    assert isinstance(out, ResumeOut)
    assert out.ok is True
    assert out.previously_paused is True
    assert get_pause_state().is_paused() is False


async def test_resume_when_not_paused(_fresh_db: str) -> None:
    await get_pause_state().initialize(_fresh_db)
    out = await resume_router(db_path=_fresh_db)
    assert out.previously_paused is False
    assert "not paused" in out.message
