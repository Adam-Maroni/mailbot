"""Story 6-1 — assembler + /admin/status + CLI rendering integration tests.

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - the real assemble_status() function (not mocked)
  - FastAPI TestClient for the /admin/status HTTP endpoint
  - the CLI's _render_status_report helper for warning-verdict logic

Coverage:
  - empty DB: assemble_status returns a well-formed StatusReport
  - sync stale: sync_health_alarm fires
  - pending_actions by tier: pending_count_by_tier matches the seed
  - failed_in_last_24h counts only failed rows within window
  - 7-day cache hit ratio computes correctly
  - last_5_router_errors honors LIMIT 5
  - hermes-aux drift threshold flag fires
  - degraded_mode_state.active=1 surfaces in budget
  - HTTP endpoint requires bearer; returns 401 without; returns 200 with
  - CLI rendering produces warning markers + correct exit verdict
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.status import (
    HERMES_AUX_DRIFT_THRESHOLD_24H,
    StatusReport,
    assemble_status,
)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def test_empty_db_returns_well_formed_report(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    report = await assemble_status(db_path)
    assert isinstance(report, StatusReport)
    assert report.sync.last_heartbeat_at is None
    assert report.sync.sync_health_alarm is False
    assert report.ingest.unprocessed_count == 0
    assert report.ingest.backpressure_active is False
    assert report.actions.pending_count_by_tier == {}
    assert report.actions.awaiting_grant_count == 0
    assert report.actions.failed_in_last_24h == 0
    assert report.budget.today_usd == 0.0
    assert report.budget.month_usd == 0.0
    assert report.budget.degraded_mode_active is False
    assert report.cache.cache_hit_rate_7d == 0.0
    assert report.errors.last_5_router_errors == []
    assert report.hermes_aux.last_24h_count == 0
    assert report.hermes_aux.drift_alarm is False


async def test_sync_stale_triggers_health_alarm(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    # Seed a stale 'ok' heartbeat 90 min ago.
    stale_ts = _iso(datetime.now(timezone.utc) - timedelta(minutes=90))
    await execute_write(
        db_path,
        "INSERT INTO worker_health (component, last_heartbeat_at, last_outcome, last_error) "
        "VALUES (?, ?, 'ok', NULL)",
        ("sync", stale_ts),
    )
    report = await assemble_status(db_path)
    assert report.sync.sync_health_alarm is True
    assert report.sync.minutes_since_last_ok is not None
    assert report.sync.minutes_since_last_ok > 60.0


async def test_pending_actions_by_tier(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    now_iso = _iso(datetime.now(timezone.utc))
    # Seed a mix of pending statuses across tiers.
    rows = [
        (1, "pending", "archive", "{}"),
        (1, "pending", "archive", "{}"),
        (2, "pending_grant", "archive", "{}"),
        (3, "cooling_off", "send_reply", "{}"),
        (1, "applied", "archive", "{}"),  # excluded — terminal
    ]
    for tier, status, action_type, payload in rows:
        await execute_write(
            db_path,
            "INSERT INTO pending_actions "
            "(email_id, action_type, tier, payload, proposed_at, status, retry_count, budget_consumed) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
            (None, action_type, tier, payload, now_iso, status),
        )
    report = await assemble_status(db_path)
    assert report.actions.pending_count_by_tier == {1: 2, 2: 1, 3: 1}
    assert report.actions.awaiting_grant_count == 1


async def test_pending_actions_failed_in_last_24h(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    recent = _iso(datetime.now(timezone.utc) - timedelta(hours=12))
    old = _iso(datetime.now(timezone.utc) - timedelta(hours=48))
    for ts in (recent, recent, old):
        await execute_write(
            db_path,
            "INSERT INTO pending_actions "
            "(email_id, action_type, tier, payload, proposed_at, status, retry_count, budget_consumed, terminal_at) "
            "VALUES (?, 'archive', 1, '{}', ?, 'failed', 0, 0, ?)",
            (None, ts, ts),
        )
    report = await assemble_status(db_path)
    assert report.actions.failed_in_last_24h == 2


async def test_cache_hit_rate_7d(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    now_iso = _iso(datetime.now(timezone.utc))
    rows = [
        (now_iso, "t", "v1", "qwen", "policy", 100, 50, 30, 0.001, 100, "ok", None, "x", None, None, None),
        (now_iso, "t", "v1", "qwen", "policy", 200, 60, 50, 0.002, 120, "ok", None, "x", None, None, None),
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls "
            "(ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
            " tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
            " outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    report = await assemble_status(db_path)
    # cached_in=80; in=300; 80/300 ≈ 0.2667
    assert 0.26 < report.cache.cache_hit_rate_7d < 0.27


async def test_last_5_router_errors_honors_limit(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    base = datetime.now(timezone.utc)
    rows = []
    for i in range(7):
        ts = _iso(base - timedelta(minutes=i))
        rows.append(
            (ts, "t", "v1", "qwen", "policy", 100, 50, 0, 0.001, 100, "failed",
             None, "x", None, None, None),
        )
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls "
            "(ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
            " tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
            " outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    report = await assemble_status(db_path)
    assert len(report.errors.last_5_router_errors) == 5


async def test_hermes_aux_drift_alarm_fires_above_threshold(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    now_iso = _iso(datetime.now(timezone.utc))
    count = HERMES_AUX_DRIFT_THRESHOLD_24H + 5
    rows = [
        (now_iso, "hermes_aux", "v1", "qwen", "policy", 100, 50, 0, 0.001, 100, "ok",
         None, "hermes-aux-compression", None, None, None)
        for _ in range(count)
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO router_calls "
            "(ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
            " tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
            " outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    report = await assemble_status(db_path)
    assert report.hermes_aux.last_24h_count == count
    assert report.hermes_aux.drift_alarm is True


async def test_degraded_mode_active_surfaces_in_budget(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    await execute_write(
        db_path,
        "UPDATE degraded_mode_state SET active = 1, entered_at = ? WHERE id = 1",
        (_iso(datetime.now(timezone.utc)),),
    )
    report = await assemble_status(db_path)
    assert report.budget.degraded_mode_active is True


# --- HTTP endpoint integration tests via FastAPI TestClient ---


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Boot the real FastAPI app with bypass flags so we don't need a live
    Ollama / Anthropic / Policy. The /admin/status endpoint only needs db_path."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    monkeypatch.setenv("MAILBOT_SKIP_POLICY", "1")
    monkeypatch.setenv("MAILBOT_SKIP_PATTERNS", "1")
    monkeypatch.setenv("MAILBOT_SKIP_MCP", "1")
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")

    from mailbot_api.main import app

    with TestClient(app) as client:
        yield client


def test_admin_status_requires_bearer_token(app_client: TestClient) -> None:
    resp = app_client.get("/admin/status")
    assert resp.status_code == 401


def test_admin_status_rejects_wrong_bearer(app_client: TestClient) -> None:
    resp = app_client.get(
        "/admin/status",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_admin_status_returns_report_with_valid_bearer(app_client: TestClient) -> None:
    resp = app_client.get(
        "/admin/status",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # The report should have every expected section.
    assert "container_health" in body
    assert "sync" in body
    assert "ingest" in body
    assert "actions" in body
    assert "budget" in body
    assert "cache" in body
    assert "errors" in body
    assert "hermes_aux" in body
    # mailbot-api always reports ok (we ARE this process)
    assert body["container_health"]["mailbot_api"] == "ok"


# --- CLI rendering verdict tests ---


def test_render_status_report_clean_returns_no_warnings() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "ok", "ollama": "ok"},
        "sync": {
            "last_heartbeat_at": "2026-06-03T15:00:00.000000Z",
            "last_outcome": "ok",
            "minutes_since_last_ok": 2.1,
            "sync_health_alarm": False,
        },
        "ingest": {
            "unprocessed_count": 10,
            "backpressure_active": False,
            "last_heartbeat_at": None,
            "last_outcome": None,
        },
        "actions": {
            "pending_count_by_tier": {1: 3, 2: 0, 3: 0},
            "awaiting_grant_count": 0,
            "failed_in_last_24h": 0,
        },
        "budget": {
            "today_usd": 0.12,
            "month_usd": 4.31,
            "month_cap_usd": 30.0,
            "degraded_mode_active": False,
            "daily_warn_fired_today": False,
        },
        "cache": {"cache_hit_rate_7d": 0.42},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 12, "drift_alarm": False},
    }
    warnings = _render_status_report(report)
    assert warnings == []


def test_render_status_report_warning_for_sync_alarm() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "ok", "ollama": "ok"},
        "sync": {
            "last_heartbeat_at": "2026-06-03T15:00:00.000000Z",
            "last_outcome": "failed",
            "minutes_since_last_ok": None,
            "sync_health_alarm": True,
        },
        "ingest": {"unprocessed_count": 0, "backpressure_active": False, "last_heartbeat_at": None, "last_outcome": None},
        "actions": {"pending_count_by_tier": {}, "awaiting_grant_count": 0, "failed_in_last_24h": 0},
        "budget": {"today_usd": 0.0, "month_usd": 0.0, "month_cap_usd": 30.0, "degraded_mode_active": False, "daily_warn_fired_today": False},
        "cache": {"cache_hit_rate_7d": 0.0},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 0, "drift_alarm": False},
    }
    warnings = _render_status_report(report)
    assert "sync" in warnings


def test_render_status_report_warning_for_degraded_mode() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "ok", "ollama": "ok"},
        "sync": {"last_heartbeat_at": None, "last_outcome": None, "minutes_since_last_ok": None, "sync_health_alarm": False},
        "ingest": {"unprocessed_count": 0, "backpressure_active": False, "last_heartbeat_at": None, "last_outcome": None},
        "actions": {"pending_count_by_tier": {}, "awaiting_grant_count": 0, "failed_in_last_24h": 0},
        "budget": {"today_usd": 1.85, "month_usd": 28.4, "month_cap_usd": 30.0, "degraded_mode_active": True, "daily_warn_fired_today": False},
        "cache": {"cache_hit_rate_7d": 0.0},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 0, "drift_alarm": False},
    }
    warnings = _render_status_report(report)
    assert "budget" in warnings


def test_render_status_report_warning_for_container_not_ok() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "unknown", "ollama": "ok"},
        "sync": {"last_heartbeat_at": None, "last_outcome": None, "minutes_since_last_ok": None, "sync_health_alarm": False},
        "ingest": {"unprocessed_count": 0, "backpressure_active": False, "last_heartbeat_at": None, "last_outcome": None},
        "actions": {"pending_count_by_tier": {}, "awaiting_grant_count": 0, "failed_in_last_24h": 0},
        "budget": {"today_usd": 0.0, "month_usd": 0.0, "month_cap_usd": 30.0, "degraded_mode_active": False, "daily_warn_fired_today": False},
        "cache": {"cache_hit_rate_7d": 0.0},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 0, "drift_alarm": False},
    }
    warnings = _render_status_report(report)
    assert "containers" in warnings
