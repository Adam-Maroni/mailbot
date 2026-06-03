"""Story 6-2 — pause/resume HTTP endpoints + logs CLI filter logic.

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - FastAPI TestClient for /admin/pause + /admin/resume + /admin/status
  - the CLI's `_filter_log_line` / `_parse_logs_filters` / `_build_logs_argv`
    pure helpers (no live docker required — actual `docker compose logs`
    invocation is a Phase 3.5 manual-verification surface).

Coverage:
  - POST /admin/pause requires bearer; rejects wrong bearer; succeeds with valid bearer
  - POST /admin/resume requires bearer; rejects wrong bearer; succeeds with valid bearer
  - pause → resume round-trip: previously_paused flag flips correctly
  - pause is idempotent (re-pause updates reason; previously_paused stays True)
  - resume of an unpaused router is a no-op (previously_paused=False)
  - GET /admin/status surfaces paused=True + reason + paused_at after pause
  - CLI _render_status_report marks ROUTER as warning when paused
  - _filter_log_line: empty filters pass all; matching event passes; non-matching event drops;
    non-JSON passes; missing field on JSON drops; multi-value OR within field works;
    multi-field AND across fields works
  - _parse_logs_filters: malformed `--filter foo` raises ValueError; valid `--filter event=x` parses
  - _build_logs_argv: shape WITHOUT follow and WITH follow
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailbot_api.db.migrations_runner import apply_pending_migrations


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Boot the real FastAPI app with bypass flags. Per-test fresh DB."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    monkeypatch.setenv("MAILBOT_SKIP_POLICY", "1")
    monkeypatch.setenv("MAILBOT_SKIP_PATTERNS", "1")
    monkeypatch.setenv("MAILBOT_SKIP_MCP", "1")
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")

    # Story 2-9 module-level singleton: reset between tests so the in-memory
    # `paused` flag doesn't leak from one test's pause into the next.
    from mailbot_api.router.pause import _reset_pause_state_for_test

    _reset_pause_state_for_test()

    from mailbot_api.main import app

    with TestClient(app) as client:
        yield client


# --- /admin/pause endpoint -----------------------------------------------


def test_admin_pause_requires_bearer(app_client: TestClient) -> None:
    resp = app_client.post("/admin/pause", json={"reason": "test"})
    assert resp.status_code == 401


def test_admin_pause_rejects_wrong_bearer(app_client: TestClient) -> None:
    resp = app_client.post(
        "/admin/pause",
        json={"reason": "test"},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_admin_pause_succeeds_with_valid_bearer(app_client: TestClient) -> None:
    resp = app_client.post(
        "/admin/pause",
        json={"reason": "scheduled maintenance"},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["previously_paused"] is False
    assert body["reason"] == "scheduled maintenance"
    assert "router paused" in body["message"]
    assert "scheduled maintenance" in body["message"]


def test_admin_pause_idempotent_updates_reason(app_client: TestClient) -> None:
    """Re-pausing an already-paused router updates the reason but reports
    previously_paused=True in the response (so the operator sees it was
    already in pause state)."""
    app_client.post(
        "/admin/pause",
        json={"reason": "first reason"},
        headers={"Authorization": "Bearer test-key"},
    )
    resp = app_client.post(
        "/admin/pause",
        json={"reason": "second reason"},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["previously_paused"] is True
    assert body["reason"] == "second reason"
    assert "already paused" in body["message"]
    assert "second reason" in body["message"]


# --- /admin/resume endpoint ----------------------------------------------


def test_admin_resume_requires_bearer(app_client: TestClient) -> None:
    resp = app_client.post("/admin/resume")
    assert resp.status_code == 401


def test_admin_resume_rejects_wrong_bearer(app_client: TestClient) -> None:
    resp = app_client.post(
        "/admin/resume",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_admin_resume_round_trip_after_pause(app_client: TestClient) -> None:
    """pause → resume round-trip flips previously_paused correctly."""
    pause_resp = app_client.post(
        "/admin/pause",
        json={"reason": "for-resume-test"},
        headers={"Authorization": "Bearer test-key"},
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["previously_paused"] is False

    resume_resp = app_client.post(
        "/admin/resume",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resume_resp.status_code == 200
    body = resume_resp.json()
    assert body["ok"] is True
    assert body["previously_paused"] is True
    assert "resumed" in body["message"]


def test_admin_resume_idempotent_on_unpaused_router(app_client: TestClient) -> None:
    resp = app_client.post(
        "/admin/resume",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["previously_paused"] is False
    assert "was not paused" in body["message"]


# --- /admin/status reflects paused state ---------------------------------


def test_admin_status_reflects_paused_state(app_client: TestClient) -> None:
    """After pause, /admin/status reports `router.paused=True` with reason
    + paused_at."""
    app_client.post(
        "/admin/pause",
        json={"reason": "status board test"},
        headers={"Authorization": "Bearer test-key"},
    )
    resp = app_client.get(
        "/admin/status",
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "router" in body
    router = body["router"]
    assert router["paused"] is True
    assert router["reason"] == "status board test"
    assert router["paused_at"] is not None
    # paused_at should be UTC ISO-8601 with Z suffix.
    assert router["paused_at"].endswith("Z")


# --- CLI rendering — ROUTER warning marker -------------------------------


def test_render_status_report_marks_router_as_warning_when_paused() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "ok", "ollama": "ok"},
        "sync": {"last_heartbeat_at": None, "last_outcome": None, "minutes_since_last_ok": None, "sync_health_alarm": False},
        "ingest": {"unprocessed_count": 0, "backpressure_active": False, "last_heartbeat_at": None, "last_outcome": None},
        "actions": {"pending_count_by_tier": {}, "awaiting_grant_count": 0, "failed_in_last_24h": 0},
        "budget": {"today_usd": 0.0, "month_usd": 0.0, "month_cap_usd": 30.0, "degraded_mode_active": False, "daily_warn_fired_today": False},
        "cache": {"cache_hit_rate_7d": 0.0},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 0, "drift_alarm": False},
        "router": {"paused": True, "reason": "test pause", "paused_at": "2026-06-03T12:00:00.000000Z"},
    }
    warnings = _render_status_report(report)
    assert "router" in warnings


def test_render_status_report_router_clean_when_not_paused() -> None:
    from scripts.mailbot import _render_status_report

    report = {
        "container_health": {"mailbot_api": "ok", "mailbot_hermes": "ok", "ollama": "ok"},
        "sync": {"last_heartbeat_at": None, "last_outcome": None, "minutes_since_last_ok": None, "sync_health_alarm": False},
        "ingest": {"unprocessed_count": 0, "backpressure_active": False, "last_heartbeat_at": None, "last_outcome": None},
        "actions": {"pending_count_by_tier": {}, "awaiting_grant_count": 0, "failed_in_last_24h": 0},
        "budget": {"today_usd": 0.0, "month_usd": 0.0, "month_cap_usd": 30.0, "degraded_mode_active": False, "daily_warn_fired_today": False},
        "cache": {"cache_hit_rate_7d": 0.0},
        "errors": {"last_5_router_errors": []},
        "hermes_aux": {"last_24h_count": 0, "drift_alarm": False},
        "router": {"paused": False, "reason": None, "paused_at": None},
    }
    warnings = _render_status_report(report)
    assert "router" not in warnings


# --- _filter_log_line / _parse_logs_filters / _build_logs_argv -----------


def test_filter_empty_passes_all() -> None:
    from scripts.mailbot import _filter_log_line

    assert _filter_log_line('{"event": "anything"}', {}) == '{"event": "anything"}'
    assert _filter_log_line("not json at all", {}) == "not json at all"


def test_filter_non_json_always_passes() -> None:
    from scripts.mailbot import _filter_log_line

    assert (
        _filter_log_line("docker compose startup line", {"event": ["sync.failed"]})
        == "docker compose startup line"
    )


def test_filter_matching_event_passes() -> None:
    from scripts.mailbot import _filter_log_line

    line = '{"event": "sync.failed", "ts": "2026-06-03T12:00:00Z"}'
    assert _filter_log_line(line, {"event": ["sync.failed"]}) == line


def test_filter_non_matching_event_drops() -> None:
    from scripts.mailbot import _filter_log_line

    line = '{"event": "sync.completed"}'
    assert _filter_log_line(line, {"event": ["sync.failed"]}) is None


def test_filter_missing_field_on_json_line_drops() -> None:
    from scripts.mailbot import _filter_log_line

    line = '{"ts": "now"}'
    assert _filter_log_line(line, {"event": ["sync.failed"]}) is None


def test_filter_multi_value_or_within_field() -> None:
    from scripts.mailbot import _filter_log_line

    line_a = '{"event": "sync.failed"}'
    line_b = '{"event": "sync.throttled"}'
    line_c = '{"event": "sync.completed"}'
    filters = {"event": ["sync.failed", "sync.throttled"]}
    assert _filter_log_line(line_a, filters) == line_a
    assert _filter_log_line(line_b, filters) == line_b
    assert _filter_log_line(line_c, filters) is None


def test_filter_multi_field_and_across_fields() -> None:
    from scripts.mailbot import _filter_log_line

    matches_both = '{"event": "sync.failed", "level": "error"}'
    matches_one = '{"event": "sync.failed", "level": "warning"}'
    matches_other = '{"event": "sync.completed", "level": "error"}'
    filters = {"event": ["sync.failed"], "level": ["error"]}
    assert _filter_log_line(matches_both, filters) == matches_both
    assert _filter_log_line(matches_one, filters) is None
    assert _filter_log_line(matches_other, filters) is None


def test_parse_filters_malformed_raises() -> None:
    from scripts.mailbot import _parse_logs_filters

    with pytest.raises(ValueError, match="malformed --filter"):
        _parse_logs_filters(["no-equals-sign"])

    with pytest.raises(ValueError, match="malformed --filter"):
        _parse_logs_filters(["=missing-field"])

    with pytest.raises(ValueError, match="malformed --filter"):
        _parse_logs_filters(["field="])


def test_parse_filters_valid_input() -> None:
    from scripts.mailbot import _parse_logs_filters

    parsed = _parse_logs_filters(
        ["event=sync.failed", "event=sync.throttled", "level=error"]
    )
    assert parsed == {
        "event": ["sync.failed", "sync.throttled"],
        "level": ["error"],
    }


def test_build_logs_argv_without_follow() -> None:
    from scripts.mailbot import _build_logs_argv

    argv = _build_logs_argv(tail=100, follow=False)
    assert argv == [
        "docker", "compose", "logs",
        "--tail", "100",
        "mailbot-api", "mailbot-hermes", "ollama",
    ]


def test_build_logs_argv_with_follow() -> None:
    from scripts.mailbot import _build_logs_argv

    argv = _build_logs_argv(tail=200, follow=True)
    assert argv == [
        "docker", "compose", "logs", "-f",
        "--tail", "200",
        "mailbot-api", "mailbot-hermes", "ollama",
    ]


# --- CR-7 (Story 6-2 review 2026-06-03): CLI smoke tests ----------------


def _make_fake_httpx_client(app_client: TestClient) -> type:
    """Build a fake `httpx.Client` factory that proxies POST to TestClient.

    Used by the CLI smoke tests to route `_cmd_pause` / `_cmd_resume`'s
    httpx.Client calls into the FastAPI TestClient surface without opening
    a real network socket."""

    class _FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> object:
            # url shape: http://<host>/admin/pause — strip scheme+host to
            # get the path TestClient expects.
            path = url.split("://", 1)[-1]
            path = "/" + path.split("/", 1)[-1] if "/" in path else "/"
            headers = kwargs.get("headers") or {}
            assert isinstance(headers, dict)
            body = kwargs.get("json")
            if body is not None:
                assert isinstance(body, dict)
                return app_client.post(path, headers=headers, json=body)
            return app_client.post(path, headers=headers)

    return _FakeClient


def test_cmd_pause_success_prints_message(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: `_cmd_pause` routed through TestClient — assert exit code
    0 + "router paused" message on stdout."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")
    import httpx

    monkeypatch.setattr(httpx, "Client", _make_fake_httpx_client(app_client))

    from scripts.mailbot import _cmd_pause

    exit_code = _cmd_pause(reason="cli-smoke-test", base_url="http://localhost:8000")
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "router paused" in captured.out
    assert "cli-smoke-test" in captured.out


def test_cmd_resume_success_prints_message(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: pause via TestClient, then `_cmd_resume` routed through
    TestClient — assert exit code 0 + "router resumed" on stdout."""
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-key")

    app_client.post(
        "/admin/pause",
        json={"reason": "for-cli-resume-test"},
        headers={"Authorization": "Bearer test-key"},
    )

    import httpx

    monkeypatch.setattr(httpx, "Client", _make_fake_httpx_client(app_client))

    from scripts.mailbot import _cmd_resume

    exit_code = _cmd_resume(base_url="http://localhost:8000")
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "router resumed" in captured.out


def test_cmd_pause_missing_router_key_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No MAILBOT_ROUTER_KEY → exit 2 + FATAL on stderr."""
    monkeypatch.delenv("MAILBOT_ROUTER_KEY", raising=False)
    from scripts.mailbot import _cmd_pause

    exit_code = _cmd_pause(reason="test", base_url="http://localhost:8000")
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "MAILBOT_ROUTER_KEY required" in captured.err
