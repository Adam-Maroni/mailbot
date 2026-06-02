"""Story 5-6 AC-9 — MCP-round-trip tests for the 5 newly-registered tools
(cost_breakdown / reset_degraded_mode / pause_router / resume_router /
mute_category).

Pattern mirrors tests/integration/test_mcp_server.py — in-memory client/server
transport, real on-disk SQLite, real verb dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test


def _setup_db(tmp_path: Path) -> str:
    db = tmp_path / "x.db"
    apply_pending_migrations(str(db))
    return str(db)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Story 5-2 test-isolation pattern — clear in-memory singletons between
    tests so pause/budget state doesn't leak across cases."""
    _reset_pause_state_for_test()
    _reset_guard_for_test()
    yield
    _reset_pause_state_for_test()
    _reset_guard_for_test()


def test_mcp_server_registers_16_tools(tmp_path: Path) -> None:
    """AC-9: the server boots with exactly 16 tools."""
    server = build_mcp_server(db_path=_setup_db(tmp_path))
    tool_names = sorted(server._tool_manager._tools.keys())  # type: ignore[attr-defined]
    assert len(tool_names) == 16


def test_mcp_server_lists_5_new_tools(tmp_path: Path) -> None:
    """AC-9: each of the 5 new tools appears with a non-empty description."""
    server = build_mcp_server(db_path=_setup_db(tmp_path))
    tools = server._tool_manager._tools  # type: ignore[attr-defined]
    for name in ("cost_breakdown", "reset_degraded_mode", "pause_router", "resume_router", "mute_category"):
        assert name in tools
        assert tools[name].description, f"{name} has empty description"


@pytest.mark.asyncio
async def test_mcp_server_mute_category_round_trip(tmp_path: Path) -> None:
    """AC-9: client.call('mute_category', ...) writes a notification_mutes row."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "mute_category",
            {"category": "newsletters", "muted_until": "2026-06-09T00:00:00Z"},
        )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["category"] == "newsletters"
    assert payload["previously_muted"] is False


@pytest.mark.asyncio
async def test_mcp_server_pause_resume_round_trip(tmp_path: Path) -> None:
    """AC-9: client.call('pause_router', ...) then client.call('resume_router')
    flip pause state cleanly."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        pause_result = await client.call_tool(
            "pause_router", {"reason": "rate-limit experiment"}
        )
        resume_result = await client.call_tool("resume_router", {})
    pause_payload = json.loads(pause_result.content[0].text)
    resume_payload = json.loads(resume_result.content[0].text)
    assert pause_payload["ok"] is True
    assert pause_payload["previously_paused"] is False
    assert resume_payload["ok"] is True
    assert resume_payload["previously_paused"] is True


@pytest.mark.asyncio
async def test_mcp_server_cost_breakdown_round_trip(tmp_path: Path) -> None:
    """AC-9: client.call('cost_breakdown', period='today') returns the
    expected aggregation shape (empty totals against a fresh DB)."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("cost_breakdown", {"period": "today"})
    payload = json.loads(result.content[0].text)
    assert payload["period"] == "today"
    assert payload["call_count"] == 0
    assert payload["total_usd"] == 0.0


@pytest.mark.asyncio
async def test_mcp_server_cost_breakdown_defaults_to_today_when_period_omitted(
    tmp_path: Path,
) -> None:
    """Story 5-6 CR-1 + CR-7: `/cost` invoked without a period MUST default
    to 'today' (the YAML's `required: false` contract). Missing default at
    the MCP wrapper would surface a missing-parameter error here."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        # Empty args dict — no period supplied.
        result = await client.call_tool("cost_breakdown", {})
    payload = json.loads(result.content[0].text)
    assert payload["period"] == "today", (
        "default period must be 'today' when caller omits the field"
    )


@pytest.mark.asyncio
async def test_mcp_server_reset_degraded_mode_round_trip(tmp_path: Path) -> None:
    """AC-9: client.call('reset_degraded_mode', ...) responds ok=True.

    Against a fresh DB the guard starts NOT degraded; the verb still returns
    ok=True with previously_active=False. This exercises the MCP round-trip
    + the verb's no-op-when-clean branch."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "reset_degraded_mode", {"reason": "test_exit"}
        )
    payload = json.loads(result.content[0].text)
    assert payload["ok"] is True
    assert payload["previously_active"] is False
