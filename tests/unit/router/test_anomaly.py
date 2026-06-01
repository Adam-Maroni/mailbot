"""Tests for mailbot_api/router/anomaly.py (Story 2-9)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.router.anomaly import (
    _online_update,
    run_anomaly_check,
)


@pytest.fixture
async def _fresh_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "anomaly.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_router_call(db_path: str, *, caller_origin: str, ts: str) -> None:
    """Insert a router_calls row at a specific ts (overriding the default factory)."""
    row = RouterCallRow(
        ts=ts,
        task_type="coarse_class",
        prompt_version="v1",
        model_chosen="qwen2.5:3b-instruct-q4_K_M",
        model_chosen_reason="policy",
        outcome="ok",
        caller_origin=caller_origin,
    )
    await record_router_call(row, db_path=db_path)


async def test_anomaly_check_no_rows_returns_empty(_fresh_db: str) -> None:
    db_path = _fresh_db
    assert await run_anomaly_check(db_path) == []


async def test_anomaly_check_warmup_period_no_alert(_fresh_db: str) -> None:
    """Below warmup samples (<24), no anomaly fires even if the count spikes."""
    db_path = _fresh_db
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for _ in range(50):
        await _seed_router_call(db_path, caller_origin="verb-ask-router", ts=ts)

    anomalies = await run_anomaly_check(db_path, now=now)
    # First call seeds the baseline at sample_count=1. No alert.
    assert anomalies == []


async def test_anomaly_check_warmed_baseline_detects_spike(_fresh_db: str) -> None:
    """After 24 hours of baseline observations, a 10x spike trips the alert."""
    db_path = _fresh_db
    now = datetime.now(timezone.utc)
    hour_of_day = now.hour

    # Pre-seed the baseline with 24 samples at mean=5, stddev=1.
    await execute_write(
        db_path,
        "INSERT INTO call_volume_baseline ("
        "caller_origin, hour_of_day, mean_volume, stddev_volume, sample_count, last_updated"
        ") VALUES (?, ?, ?, ?, ?, ?)",
        ("verb-ask-router", hour_of_day, 5.0, 1.0, 24, "2026-06-01T00:00:00Z"),
    )

    # Now seed a spike of 50 calls in the last hour.
    ts = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for _ in range(50):
        await _seed_router_call(db_path, caller_origin="verb-ask-router", ts=ts)

    anomalies = await run_anomaly_check(db_path, now=now)
    # 50 > 5 + 3*1 = 8 → triggers.
    assert "verb-ask-router" in anomalies


def test_online_update_first_sample() -> None:
    mean, stddev, n = _online_update(old_mean=0.0, old_stddev=0.0, old_n=0, new_value=10.0)
    assert mean == 10.0
    assert stddev == 0.0
    assert n == 1


def test_online_update_second_sample() -> None:
    mean, stddev, n = _online_update(old_mean=10.0, old_stddev=0.0, old_n=1, new_value=20.0)
    assert mean == 15.0
    assert n == 2
    # stddev = sqrt of variance of [10, 20] (sample variance = 50, sample stddev ≈ 7.07)
    assert stddev > 5.0
    assert stddev < 10.0
