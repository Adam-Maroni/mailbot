"""Tests for mailbot_api/router/budget.py (Story 2-8)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import (
    DAILY_SOFT_WARN_USD,
    MONTHLY_HARD_CAP_USD,
    PER_CALL_REFUSAL_THRESHOLD_USD,
    BudgetGuard,
    demote_model,
    get_guard,
)


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


def test_demote_model_chain() -> None:
    assert demote_model("claude-opus-4-7") == "claude-haiku-4-5-20251001"
    assert demote_model("claude-haiku-4-5-20251001") == "qwen2.5:3b-instruct-q4_K_M"
    assert demote_model("qwen2.5:3b-instruct-q4_K_M") == "qwen2.5:3b-instruct-q4_K_M"
    assert demote_model("unknown-model") == "unknown-model"


def test_thresholds_match_architecture_constants() -> None:
    """Architecture: Layer 2 = $2/day; Layer 3 = $30/mo; Layer 4 = $0.20/call."""
    assert DAILY_SOFT_WARN_USD == 2.0
    assert MONTHLY_HARD_CAP_USD == 30.0
    assert PER_CALL_REFUSAL_THRESHOLD_USD == 0.20


async def test_budget_guard_initialize_zero_when_no_rows(_fresh_db: str) -> None:
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)
    assert guard.today_spend_usd == 0.0
    assert guard.this_month_spend_usd == 0.0
    assert guard.is_degraded() is False


async def test_budget_guard_add_spend_accumulates(_fresh_db: str) -> None:
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)
    await guard.add_spend(_fresh_db, 0.50)
    await guard.add_spend(_fresh_db, 1.00)
    assert guard.today_spend_usd == 1.50
    assert guard.this_month_spend_usd == 1.50


async def test_layer_2_soft_warn_fires_once(
    _fresh_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Crossing $2/day fires ONE warning; subsequent calls don't refire same day."""
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)

    with caplog.at_level(logging.WARNING, logger="mailbot_api.router.budget"):
        # First crossing.
        await guard.add_spend(_fresh_db, 1.50)
        await guard.add_spend(_fresh_db, 1.00)  # crosses $2
        warn_count_after_cross = sum(
            1
            for r in caplog.records
            if getattr(r, "event", None) == "budget.daily.soft_warn"
        )
        # Another call later same day should NOT re-fire.
        await guard.add_spend(_fresh_db, 0.50)
        warn_count_final = sum(
            1
            for r in caplog.records
            if getattr(r, "event", None) == "budget.daily.soft_warn"
        )

    assert warn_count_after_cross == 1
    assert warn_count_final == 1


async def test_layer_3_enters_degraded_mode_on_monthly_breach(
    _fresh_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)

    with caplog.at_level(logging.ERROR, logger="mailbot_api.router.budget"):
        await guard.add_spend(_fresh_db, 25.0)
        assert guard.is_degraded() is False
        await guard.add_spend(_fresh_db, 6.0)  # crosses $30

    assert guard.is_degraded() is True
    # SQLite singleton row reflects the state.
    row = await fetchone(
        _fresh_db,
        "SELECT active, entered_at FROM degraded_mode_state WHERE id = 1",
        (),
    )
    assert row is not None
    assert row[0] == 1
    assert row[1] is not None  # entered_at populated

    assert any(
        getattr(r, "event", None) == "budget.degraded.entered" for r in caplog.records
    )


async def test_exit_degraded_mode_clears_flag(_fresh_db: str) -> None:
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)
    # Force into degraded mode.
    await guard.add_spend(_fresh_db, 35.0)
    assert guard.is_degraded() is True

    await guard.exit_degraded_mode(_fresh_db, reason="manual_reset")
    assert guard.is_degraded() is False
    row = await fetchone(
        _fresh_db,
        "SELECT active, exited_at FROM degraded_mode_state WHERE id = 1",
        (),
    )
    assert row is not None
    assert row[0] == 0
    assert row[1] is not None  # exited_at populated


async def test_exit_degraded_mode_when_not_active_is_noop(_fresh_db: str) -> None:
    guard = BudgetGuard()
    await guard.initialize(_fresh_db)
    # Not in degraded mode; exit should be safe.
    await guard.exit_degraded_mode(_fresh_db, reason="bogus")
    assert guard.is_degraded() is False


async def test_budget_guard_initialize_rolls_forward_router_calls_spend(
    _fresh_db: str,
) -> None:
    """If router_calls already has rows, BudgetGuard.initialize sums them
    into the in-memory counters via the ROUTER_CALLS_SPEND_SINCE query."""
    from mailbot_api.observability.audit import RouterCallRow, record_router_call

    rows = [
        RouterCallRow(
            task_type="draft_reply",
            prompt_version="v1",
            model_chosen="claude-opus-4-7",
            model_chosen_reason="policy:draft_reply:default",
            cost_usd_estimated=0.50,
            outcome="ok",
        ),
        RouterCallRow(
            task_type="draft_reply",
            prompt_version="v1",
            model_chosen="claude-opus-4-7",
            model_chosen_reason="policy:draft_reply:default",
            cost_usd_estimated=0.25,
            outcome="ok",
        ),
    ]
    for r in rows:
        await record_router_call(r, db_path=_fresh_db)

    guard = BudgetGuard()
    await guard.initialize(_fresh_db)
    # Both rows were within today + this month → both counters reflect them.
    assert guard.today_spend_usd == 0.75
    assert guard.this_month_spend_usd == 0.75


# ---- Story 10.5.1 (AC-2, the CLASS) — cross-process authoritative read -------


async def test_is_degraded_now_sees_bare_db_degraded_without_initialize(
    _fresh_db: str,
) -> None:
    """The BudgetGuard twin of the F4 regression.

    A degraded-mode entry that fired in "process A" (writes the
    degraded_mode_state row) must be observed by "process B"'s
    `is_degraded_now(db_path)` even though B never called initialize() — the
    same per-process in-memory singleton landmine as PauseState. Before the
    fix, `is_degraded()` returned B's stale mirror (False).
    """
    # Process A enters degraded mode (writes the DB row).
    guard_a = BudgetGuard()
    await guard_a.initialize(_fresh_db)
    await guard_a.add_spend(_fresh_db, 35.0)  # crosses $30 → degraded
    assert guard_a.is_degraded() is True

    # Process B: fresh, never initialized → stale mirror says False.
    guard_b = BudgetGuard()
    assert guard_b.is_degraded() is False  # the pre-fix landmine
    assert await guard_b.is_degraded_now(_fresh_db) is True


async def test_is_degraded_now_false_when_not_degraded(_fresh_db: str) -> None:
    guard = BudgetGuard()
    assert await guard.is_degraded_now(_fresh_db) is False


async def test_is_degraded_now_reflects_live_exit(_fresh_db: str) -> None:
    """After a reset writes the DB row, the authoritative reader flips to False
    on the next read — no re-initialize needed."""
    guard_a = BudgetGuard()
    await guard_a.initialize(_fresh_db)
    await guard_a.add_spend(_fresh_db, 35.0)

    reader = BudgetGuard()
    assert await reader.is_degraded_now(_fresh_db) is True
    await guard_a.exit_degraded_mode(_fresh_db, reason="manual_reset")
    assert await reader.is_degraded_now(_fresh_db) is False


async def test_is_degraded_now_fails_closed_on_read_error() -> None:
    """Fail-closed contract: a DB read failure is treated as DEGRADED so a
    hiccup can never silently re-enable full-cost dispatch."""
    guard = BudgetGuard()
    assert await guard.is_degraded_now("/nonexistent/dir/definitely-not-a.db") is True
