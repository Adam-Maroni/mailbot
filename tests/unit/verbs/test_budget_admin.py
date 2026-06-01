"""Unit tests for mailbot_api/verbs/budget_admin.py (Story 2-8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import get_guard
from mailbot_api.verbs.budget_admin import BudgetResetOut, reset_degraded_mode


@pytest.fixture
def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "budget.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _clean_guard() -> None:
    get_guard().reset_for_test()
    yield
    get_guard().reset_for_test()


async def test_reset_when_active_returns_previously_true(_fresh_db: str) -> None:
    guard = get_guard()
    await guard.initialize(_fresh_db)
    await guard.add_spend(_fresh_db, 35.0)
    assert guard.is_degraded() is True

    out = await reset_degraded_mode(db_path=_fresh_db, reason="manual_reset")
    assert isinstance(out, BudgetResetOut)
    assert out.ok is True
    assert out.previously_active is True
    assert "exited" in out.message
    assert guard.is_degraded() is False


async def test_reset_when_inactive_returns_previously_false(_fresh_db: str) -> None:
    guard = get_guard()
    await guard.initialize(_fresh_db)
    out = await reset_degraded_mode(db_path=_fresh_db, reason="bogus")
    assert out.ok is True
    assert out.previously_active is False
    assert "not active" in out.message
