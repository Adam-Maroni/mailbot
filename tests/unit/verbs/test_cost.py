"""Tests for mailbot_api/verbs/cost.py (Story 2-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.router.budget import _reset_guard_for_test, get_guard
from mailbot_api.verbs.cost import CostBreakdownOut, cost_breakdown


@pytest.fixture
async def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "cost.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _clean_guard() -> None:
    _reset_guard_for_test()
    yield
    _reset_guard_for_test()


async def _seed(
    db_path: str,
    *,
    task_type: str,
    model: str,
    caller_origin: str,
    cost: float,
    tokens_in: int = 100,
    cached_tokens_in: int = 0,
) -> None:
    row = RouterCallRow(
        task_type=task_type,
        prompt_version="v1",
        model_chosen=model,
        model_chosen_reason="policy",
        cost_usd_estimated=cost,
        tokens_in=tokens_in,
        cached_tokens_in=cached_tokens_in,
        outcome="ok",
        caller_origin=caller_origin,
    )
    await record_router_call(row, db_path=db_path)


async def test_cost_breakdown_empty_returns_zeros(_fresh_db: str) -> None:
    out = await cost_breakdown("today", db_path=_fresh_db)
    assert isinstance(out, CostBreakdownOut)
    assert out.period == "today"
    assert out.total_usd == 0.0
    assert out.cap_usd is None  # today has no cap
    assert out.call_count == 0
    assert out.per_task == {}
    assert out.per_model == {}
    assert out.per_caller_origin == {}
    assert out.cache_hit_rate == 0.0
    assert out.degraded_mode_active is False


async def test_cost_breakdown_month_has_cap_usd(_fresh_db: str) -> None:
    out = await cost_breakdown("month", db_path=_fresh_db)
    assert out.cap_usd == 30.0


async def test_cost_breakdown_aggregates_correctly(_fresh_db: str) -> None:
    await _seed(
        _fresh_db,
        task_type="coarse_class",
        model="qwen2.5:3b-instruct-q4_K_M",
        caller_origin="verb-ask-router",
        cost=0.001,
        tokens_in=100,
        cached_tokens_in=0,
    )
    await _seed(
        _fresh_db,
        task_type="draft_reply",
        model="claude-opus-4-7",
        caller_origin="verb-ask-router",
        cost=0.50,
        tokens_in=200,
        cached_tokens_in=100,
    )
    await _seed(
        _fresh_db,
        task_type="hermes_aux",
        model="claude-haiku-4-5-20251001",
        caller_origin="hermes-aux-compression",
        cost=0.05,
        tokens_in=300,
        cached_tokens_in=250,
    )

    out = await cost_breakdown("today", db_path=_fresh_db)
    assert out.call_count == 3
    assert out.total_usd == pytest.approx(0.001 + 0.50 + 0.05)
    assert out.per_task == {
        "coarse_class": pytest.approx(0.001),
        "draft_reply": pytest.approx(0.50),
        "hermes_aux": pytest.approx(0.05),
    }
    assert out.per_model["claude-opus-4-7"] == pytest.approx(0.50)
    assert out.per_caller_origin["hermes-aux-compression"] == pytest.approx(0.05)
    # cache hit rate: (0 + 100 + 250) / (100 + 200 + 300) = 350/600
    assert out.cache_hit_rate == pytest.approx(350 / 600)


async def test_cost_breakdown_reflects_degraded_mode(_fresh_db: str) -> None:
    guard = get_guard()
    await guard.initialize(_fresh_db)
    await guard.add_spend(_fresh_db, 35.0)
    out = await cost_breakdown("today", db_path=_fresh_db)
    assert out.degraded_mode_active is True
