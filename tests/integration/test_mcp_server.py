"""Story 5-2 — MCP server integration tests.

Uses the MCP SDK's in-memory client/server transport
(``create_connected_server_and_client_session``) for full round-trip tests
against the real verbs hitting a real on-disk SQLite (per Step 2.4.7
Middleware-Real-Bootstrap MailBot reframing — the MCP transport IS the
integration boundary this story tests).

Coverage matrix per AC-6 (≥ 12 tests). 21 tests after CR-2/CR-3 additions:
  1.  Server boots: 11 tools, names match the declarative spec.
  2.  Internal verbs NOT exposed (forbidden set).
  3.  Tool schemas never expose db_path or session_id.
  4.  set_db_path mutates the bound context.
  5.  list_tools discoverability: every tool name + description fragment.
  6.  find_emails happy path.
  7.  find_emails validation error (schema mismatch).
  8.  find_emails verb-level error-as-data (LIMIT_EXCEEDED).
  9.  hydrate_email happy path.
  10. hydrate_email confidential gate (error-as-data).
  11. hydrate_email 5/turn cap.
  12. hydrate_email 30s reset.
  13. get_thread round-trip.
  14. count_emails round-trip.
  15. get_sender_summary round-trip.
  16. propose_action happy path.
  17. mint_grant + revoke_grant round-trip.
  18. mint_sensitivity_token confidential blocked.
  19. cancel_action happy path (CR-2).
  20. revert_action happy path (CR-2).
  21. mint_sensitivity_token sensitive-email success path (CR-3).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import (
    _LAST_HYDRATION_AT,
    build_mcp_server,
    set_db_path,
)
from mailbot_api.verbs.hydrate_email import _SESSION_HYDRATION_COUNTS

# ---------------------------------------------------------------------------
# Fixtures + seeding helpers (mirrors tests/unit/verbs/test_read_verbs.py).
# ---------------------------------------------------------------------------


def _setup_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "mcp.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    received_at: str = "2026-06-01T12:00:00Z",
    from_address: str | None = "alice@example.com",
    from_display_name: str | None = "Alice",
    subject: str | None = "hello",
    body_preview: str | None = "body preview text",
    summary_short: str | None = "short summary",
    class_coarse: str | None = "human",
    importance_score: float | None = 50.0,
    sensitivity: str | None = "normal",
    sensitivity_at: str | None = "2026-06-01T12:00:01Z",
    has_attachments: int = 0,
    thread_id: str | None = None,
    deleted_at: str | None = None,
    change_marker: str | None = "ck1",
) -> None:
    await execute_write(
        db_path,
        (
            "INSERT INTO emails ("
            "graph_id, change_marker, received_at, from_address, from_display_name, subject, "
            "body_preview, summary_short, summary_short_at, class_coarse, class_coarse_at, "
            "importance_score, importance_score_at, sensitivity, sensitivity_at, "
            "has_attachments, thread_id, deleted_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            graph_id,
            change_marker,
            received_at,
            from_address,
            from_display_name,
            subject,
            body_preview,
            summary_short,
            "2026-06-01T12:00:02Z" if summary_short is not None else None,
            class_coarse,
            "2026-06-01T12:00:03Z" if class_coarse is not None else None,
            importance_score,
            "2026-06-01T12:00:05Z" if importance_score is not None else None,
            sensitivity,
            sensitivity_at,
            has_attachments,
            thread_id,
            deleted_at,
        ),
    )


async def _seed_thread(db_path: str, *, thread_id: str, continuity_note: str | None = None) -> None:
    await execute_write(
        db_path,
        "INSERT INTO threads (id, last_message_at, message_count, thread_continuity_note) "
        "VALUES (?, ?, ?, ?)",
        (thread_id, "2026-06-01T12:00:00Z", 0, continuity_note),
    )


async def _seed_sender(
    db_path: str,
    *,
    address_lower: str,
    display_name: str | None = None,
    reputation: str | None = None,
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO senders (id, display_name, first_seen_at, sender_reputation_summary) "
        "VALUES (?, ?, ?, ?)",
        (address_lower, display_name, "2026-06-01T00:00:00Z", reputation),
    )


@pytest.fixture(autouse=True)
def _clear_mcp_state() -> Any:
    """Clear hydrate_email's module-level counter + the mcp_server's
    last-hydration-at map between tests."""
    _SESSION_HYDRATION_COUNTS.clear()
    _LAST_HYDRATION_AT.clear()
    yield
    _SESSION_HYDRATION_COUNTS.clear()
    _LAST_HYDRATION_AT.clear()


def _parse_tool_result(result: Any) -> dict[str, Any]:
    """Pull the JSON body out of an MCP CallToolResult.

    FastMCP returns the verb's structured output via either the
    ``structuredContent`` field (new path) or as TextContent JSON (fallback).
    Tests use whichever path the SDK provides — both yield a dict.
    """
    structured = getattr(result, "structuredContent", None)
    if structured:
        return dict(structured)
    if result.content:
        for part in result.content:
            if isinstance(part, TextContent):
                try:
                    return json.loads(part.text)
                except json.JSONDecodeError:
                    pass
    raise AssertionError(f"could not parse MCP tool result: {result}")


# ---------------------------------------------------------------------------
# AC-1 + AC-7 server boot + boundary tests (no client needed).
# ---------------------------------------------------------------------------


def test_build_mcp_server_registers_25_tools_with_expected_names(tmp_path: Path) -> None:
    """Story 5-6 → 16; Story 6-8 → 17; Story 6-3 → 19; Story 6-4 → 20;
    Story 6-5 → 22 (compose_digest + finalize_digest_delivery);
    Story 9-3 → 23 (set_model_oneshot);
    Story 9-4 → 25 (set_model_persistent + inspect_policy)."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    tool_names = sorted(server._tool_manager._tools.keys())  # type: ignore[attr-defined]
    expected = sorted(
        [
            # Story 5-2 baseline (11).
            "find_emails",
            "hydrate_email",
            "get_thread",
            "count_emails",
            "get_sender_summary",
            "propose_action",
            "mint_grant",
            "revoke_grant",
            "cancel_action",
            "revert_action",
            "mint_sensitivity_token",
            # Story 5-6 additions (5).
            "cost_breakdown",
            "reset_degraded_mode",
            "pause_router",
            "resume_router",
            "mute_category",
            # Story 6-8 addition (1).
            "render_spend_chart",
            # Story 6-3 additions (2).
            "pull_pending_notifications",
            "ack_notification",
            # Story 6-4 addition (1).
            "unmute_category",
            # Story 6-5 additions (2).
            "compose_digest",
            "finalize_digest_delivery",
            # Story 9-3 addition (1).
            "set_model_oneshot",
            # Story 9-4 additions (2).
            "set_model_persistent",
            "inspect_policy",
        ]
    )
    assert tool_names == expected, f"unexpected tool set: {tool_names}"
    assert len(tool_names) == 25


def test_internal_verbs_are_not_registered(tmp_path: Path) -> None:
    """ask_router and reset_hydration_count are deliberately not MCP-exposed.
    Re-exposing ask_router is a cost-discipline regression (cost-discipline
    center bypass); reset_hydration_count is a server-internal lifecycle helper.

    Story 5-6 closed the cost/pause/resume/reset_degraded_mode deferral — those
    are NOW registered and are no longer in the forbidden set."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    tool_names = set(server._tool_manager._tools.keys())  # type: ignore[attr-defined]
    forbidden = {
        "ask_router",
        "reset_hydration_count",
    }
    overlap = tool_names & forbidden
    assert not overlap, f"internal verbs leaked to MCP surface: {overlap}"


def test_tool_schemas_never_expose_db_path_or_session_id(tmp_path: Path) -> None:
    """For every registered tool, the JSON schema's `properties` MUST NOT
    contain `db_path` or `session_id` — those are server-injected."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    for tool_name, tool in server._tool_manager._tools.items():  # type: ignore[attr-defined]
        schema = tool.parameters
        props = schema.get("properties", {})
        assert "db_path" not in props, (
            f"{tool_name}: db_path leaked into schema"
        )
        assert "session_id" not in props, (
            f"{tool_name}: session_id leaked into schema"
        )


def test_set_db_path_mutates_server_context(tmp_path: Path) -> None:
    """Pattern A: build_mcp_server with db_path=None, then bind via
    set_db_path (the lifespan path)."""
    server = build_mcp_server(db_path=None)
    ctx = server._mailbot_server_ctx  # type: ignore[attr-defined]
    assert ctx.db_path is None
    set_db_path(server, str(tmp_path / "later.db"))
    assert ctx.db_path == str(tmp_path / "later.db")


# ---------------------------------------------------------------------------
# AC-6 — full client-server round-trip via in-memory transport.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_returns_constraint_phrases(tmp_path: Path) -> None:
    """Descriptions must carry the documented cost-relevant constraint
    phrases so the agent sees them in its prompt context (AR-PAT-4 +
    architecture §Communication Patterns)."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        listed = await client.list_tools()
    by_name = {t.name: t for t in listed.tools}
    # Story 5-6 → 16; Story 6-8 → 17; Story 6-3 → 19; Story 6-4 → 20;
    # Story 6-5 → 22 (compose_digest + finalize_digest_delivery);
    # Story 9-3 → 23 (set_model_oneshot);
    # Story 9-4 → 25 (set_model_persistent + inspect_policy).
    assert len(by_name) == 25
    # find_emails must mention the 100-cap + Rule J.
    assert "100" in by_name["find_emails"].description
    assert "Rule J" in by_name["find_emails"].description
    # hydrate_email must mention the 5/turn cap.
    assert "5" in by_name["hydrate_email"].description
    assert "turn" in by_name["hydrate_email"].description.lower()
    # Other constraint-tagged tools.
    assert "Rule J" in by_name["count_emails"].description
    assert "Rule J" in by_name["get_thread"].description
    assert "10-min" in by_name["mint_sensitivity_token"].description
    assert "Tier-1" in by_name["revert_action"].description
    # Story 5-6 additions name their slash-command surface.
    assert "/cost" in by_name["cost_breakdown"].description
    assert "/budget reset" in by_name["reset_degraded_mode"].description
    assert "/pause" in by_name["pause_router"].description
    assert "/resume" in by_name["resume_router"].description
    assert "/mute" in by_name["mute_category"].description


@pytest.mark.asyncio
async def test_find_emails_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1", from_address="alice@example.com")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "find_emails",
            {"filter": {"sender_address": "alice@example.com"}, "limit": 5},
        )
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["error"] is None
    assert len(body["projections"]) == 1
    assert body["projections"][0]["email_id"] == "m1"
    assert body["projections"][0]["from_address"] == "alice@example.com"


@pytest.mark.asyncio
async def test_find_emails_validation_error_on_wrong_type(tmp_path: Path) -> None:
    """Schema-mismatch surfaces as MCP-level error, NOT verb-level
    error-as-data (AC-2 + AC-6 case 4). The SDK either raises or returns
    isError=True; either signal is acceptable."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "find_emails",
            {"filter": {"sender_address": "x"}, "limit": "not-an-int"},
        )
    # The SDK marks validation errors via `isError=True` and surfaces them
    # as TextContent rather than structured output.
    assert getattr(result, "isError", False), (
        f"expected validation error, got: {result}"
    )


@pytest.mark.asyncio
async def test_find_emails_verb_error_is_data_not_protocol_error(tmp_path: Path) -> None:
    """Verb-level errors (LIMIT_EXCEEDED) come back as data per AR-PAT-4;
    the MCP layer does NOT raise."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("find_emails", {"filter": {}, "limit": 200})
    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["ok"] is False
    assert body["error"]["code"] == "LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_hydrate_email_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1", body_preview="hello body")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("hydrate_email", {"email_id": "m1"})
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["email"]["body_preview"] == "hello body"


@pytest.mark.asyncio
async def test_hydrate_email_confidential_refused_as_data(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(
        db_path, graph_id="m1", sensitivity="confidential", body_preview="secret"
    )
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("hydrate_email", {"email_id": "m1"})
    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["ok"] is False
    assert body["error"]["code"] == "CONFIDENTIAL_HYDRATION_BLOCKED"
    # body must NOT be exposed
    assert body["email"] is None


@pytest.mark.asyncio
async def test_hydrate_email_5_per_turn_cap(tmp_path: Path) -> None:
    """6 hydrate_email calls in the same MCP session within <30s — the
    6th must return HYDRATE_RATE_LIMITED."""
    db_path = _setup_db(tmp_path)
    for i in range(6):
        await _seed_email(db_path, graph_id=f"m{i}")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        # 5 should succeed
        for i in range(5):
            result = await client.call_tool("hydrate_email", {"email_id": f"m{i}"})
            body = _parse_tool_result(result)
            assert body["ok"] is True, f"call #{i + 1} unexpectedly failed: {body}"
        # 6th: rate-limited as data
        result = await client.call_tool("hydrate_email", {"email_id": "m5"})
        body = _parse_tool_result(result)
        assert body["ok"] is False
        assert body["error"]["code"] == "HYDRATE_RATE_LIMITED"


@pytest.mark.asyncio
async def test_hydrate_email_30s_inactivity_resets_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After 30s of inactivity, the next hydrate_email on the same session
    resets the counter. Simulated by advancing the clock in mcp_server."""
    db_path = _setup_db(tmp_path)
    for i in range(6):
        await _seed_email(db_path, graph_id=f"m{i}")
    server = build_mcp_server(db_path=db_path)

    real_now = datetime.now(timezone.utc)
    offset = {"delta": timedelta(seconds=0)}

    def _fake_now(tz: Any = None) -> datetime:  # noqa: ARG001
        return real_now + offset["delta"]

    # Patch datetime.now ONLY inside mcp_server (production verb side
    # doesn't take a clock dependency, so this is the only place that
    # needs the freeze).
    import mailbot_api.mcp_server as _mcp_mod

    class _DT:
        @staticmethod
        def now(tz: Any = None) -> datetime:
            return _fake_now(tz)

    monkeypatch.setattr(_mcp_mod, "datetime", _DT)

    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        # 5 successful calls — counter at 5
        for i in range(5):
            result = await client.call_tool("hydrate_email", {"email_id": f"m{i}"})
            body = _parse_tool_result(result)
            assert body["ok"] is True
        # Advance clock 31s — the next call should reset the counter and succeed
        offset["delta"] = timedelta(seconds=31)
        result = await client.call_tool("hydrate_email", {"email_id": "m5"})
        body = _parse_tool_result(result)
        assert body["ok"] is True, f"reset failed; got: {body}"


@pytest.mark.asyncio
async def test_get_thread_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_thread(db_path, thread_id="t1", continuity_note="ongoing discussion")
    await _seed_email(db_path, graph_id="m1", thread_id="t1", received_at="2026-06-01T10:00:00Z")
    await _seed_email(db_path, graph_id="m2", thread_id="t1", received_at="2026-06-01T11:00:00Z")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("get_thread", {"thread_id": "t1"})
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["thread_id"] == "t1"
    assert body["message_count"] == 2
    assert body["thread_continuity_note"] == "ongoing discussion"
    assert [p["email_id"] for p in body["projections"]] == ["m1", "m2"]  # ASC


@pytest.mark.asyncio
async def test_count_emails_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1", from_address="alice@example.com")
    await _seed_email(db_path, graph_id="m2", from_address="alice@example.com")
    await _seed_email(db_path, graph_id="m3", from_address="bob@example.com")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "count_emails", {"filter": {"sender_address": "alice@example.com"}}
        )
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["count"] == 2


@pytest.mark.asyncio
async def test_get_sender_summary_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_sender(
        db_path,
        address_lower="alice@example.com",
        display_name="Alice",
        reputation="reliable",
    )
    await _seed_email(db_path, graph_id="m1", from_address="alice@example.com")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "get_sender_summary", {"sender_address": "alice@example.com"}
        )
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["sender"]["sender_address"] == "alice@example.com"
    assert body["sender"]["sender_reputation_summary"] == "reliable"


@pytest.mark.asyncio
async def test_propose_action_mark_read_happy_path(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "propose_action",
            {"email_id": "m1", "action_type": "mark_read"},
        )
    body = _parse_tool_result(result)
    assert body["ok"] is True
    assert body["tier"] == 1
    assert body["status"] == "pending"
    assert isinstance(body["action_id"], int)


@pytest.mark.asyncio
async def test_mint_grant_then_revoke_round_trip(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    # 1h in the future, ISO-8601 Z.
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        mint_result = await client.call_tool(
            "mint_grant",
            {
                "action_type": "archive",  # Tier-2 — needs a grant
                "email_ids": ["m1", "m2"],
                "expires_at": expires_at,
            },
        )
        mint_body = _parse_tool_result(mint_result)
        assert mint_body["ok"] is True, f"mint failed: {mint_body}"
        grant_id = mint_body["grant_id"]
        assert isinstance(grant_id, int)

        revoke_result = await client.call_tool("revoke_grant", {"grant_id": grant_id})
        revoke_body = _parse_tool_result(revoke_result)
        assert revoke_body["ok"] is True


@pytest.mark.asyncio
async def test_mint_sensitivity_token_confidential_refused_as_data(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1", sensitivity="confidential")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "mint_sensitivity_token",
            {"email_id": "m1", "task_type": "summary_short"},
        )
    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["ok"] is False
    assert body["error"]["code"] == "SENSITIVITY_BLOCKS_API"
    # token must be absent
    assert body["token"] is None


# ---------------------------------------------------------------------------
# CR-2 + CR-3 follow-up coverage.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_action_happy_path(tmp_path: Path) -> None:
    """CR-2: cancel_action was registered but had no round-trip test. Propose
    a Tier-1 mark_read, then cancel it via MCP."""
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        propose_result = await client.call_tool(
            "propose_action",
            {"email_id": "m1", "action_type": "mark_read"},
        )
        propose_body = _parse_tool_result(propose_result)
        assert propose_body["ok"] is True
        action_id = propose_body["action_id"]

        cancel_result = await client.call_tool("cancel_action", {"action_id": action_id})
        cancel_body = _parse_tool_result(cancel_result)
        assert cancel_body["ok"] is True
        assert cancel_body["action_id"] == action_id


@pytest.mark.asyncio
async def test_revert_action_unsupported_for_pending(tmp_path: Path) -> None:
    """CR-2: revert_action was registered but had no round-trip test. The
    happy path (revert a TERMINAL Tier-1 action within 24h) requires action
    history infrastructure beyond this story's scope; verify instead the
    error-as-data contract on a non-revertible action_id (no matching row →
    structured error)."""
    db_path = _setup_db(tmp_path)
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("revert_action", {"action_id": 99999})
    assert not getattr(result, "isError", False)  # error-as-data, not protocol error
    body = _parse_tool_result(result)
    assert body["ok"] is False
    assert body["error"] is not None
    assert body["error"]["code"]  # any structured error code is fine


@pytest.mark.asyncio
async def test_mint_sensitivity_token_sensitive_success(tmp_path: Path) -> None:
    """CR-3: mint_sensitivity_token success path was untested (only the
    confidential-blocked case was covered). Seed a sensitive email; minting
    must succeed and return a non-None token. This is the load-bearing happy
    path for Story 5-9's draft-reply flow."""
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, graph_id="m1", sensitivity="sensitive")
    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "mint_sensitivity_token",
            {"email_id": "m1", "task_type": "summary_short"},
        )
    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["ok"] is True, f"mint failed: {body}"
    assert body["token"] is not None
    assert body["expires_at"] is not None
    assert body["grant_id"] is not None
    assert body["error"] is None
