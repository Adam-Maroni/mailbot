"""Story 10.5.3 AC-1 (F-10-5-11) — the Opus draft pipeline must be reachable
from the chat path.

The flagship draft orchestrator (``handle_draft_reply``) shipped in Story 5-9
with L2-green tests but ZERO chat call sites — it was never registered as a
chat-reachable tool, so ``draft_reply`` produced zero ``router_calls`` chat
rows ever (F-10-5-11).

These tests prove the fix at code-L3 WITHOUT the false integration boundary
that hid the gap:

  * The tool is registered on the real MCP surface (``build_mcp_server``) and
    discoverable by name — this is the actual chat call site (Hermes discovers
    verbs via MCP and offers them as OpenAI tools).
  * Invoking it drives ``handle_draft_reply`` for real against a real DB, with
    a fake/local adapter registered so ``ask_router`` executes for real and
    writes a genuine ``router_calls`` row for ``draft_reply`` — NOT a
    monkeypatched ``ask_router`` (that would reproduce the L2-green illusion
    this story exists to kill; see Step 2.4.7 Router-real reframing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from mailbot_api.db.connection import execute_write, fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import (
    _reset_registry_for_test,
    register_adapter,
)

# ---------------------------------------------------------------------------
# Fake Opus adapter — returns valid draft_reply JSON so ask_router's schema
# validation passes and a real router_calls row is written.
# ---------------------------------------------------------------------------


class _FakeOpusAdapter:
    """Minimal ModelAdapter that returns a canned draft_reply JSON payload.

    ask_router runs for real against this adapter — lane/rate/budget/audit all
    execute — so a genuine router_calls row lands for task_type='draft_reply'.
    """

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> Any:
        from mailbot_api.router.models import AdapterResponse

        payload = json.dumps(
            {
                "draft_body": "Confirmed — Tuesday at 2pm works.",
                "suggested_subject": "Re: Meeting tomorrow",
                "tone_signals_used": ["concise"],
                "defender_warnings": [],
            }
        )
        return AdapterResponse(
            text=payload,
            tokens_in=120,
            tokens_out=40,
            cached_tokens_in=0,
            latency_ms=5,
            raw={},
        )


@pytest.fixture(autouse=True)
def _reset_router_state() -> Any:
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_loop_detector_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_loop_detector_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_pause_state_for_test()


def _setup_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "draft_chat.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(db_path: str, graph_id: str, sensitivity: str = "normal") -> None:
    await execute_write(
        db_path,
        (
            "INSERT INTO emails (graph_id, received_at, from_address, subject, "
            "body_preview, sensitivity, sensitivity_at, change_marker) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            graph_id,
            "2026-07-10T11:00:00Z",
            "alice@example.com",
            "Meeting tomorrow",
            "Can you make it at 2pm?",
            sensitivity,
            "2026-07-10T11:00:00Z" if sensitivity else None,
            f"cm-{graph_id}",
        ),
    )


def _install_policy_snapshot() -> None:
    """Load the real repo policy.yaml so draft_reply resolves to its Opus model."""
    policy = load_policy(Path("router/policy.yaml"))
    set_policy_snapshot(policy)


def _parse_tool_result(result: Any) -> dict[str, Any]:
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
# AC-1: draft_reply is a registered, discoverable chat tool.
# ---------------------------------------------------------------------------


def test_draft_reply_tool_is_registered(tmp_path: Path) -> None:
    """The MCP surface MUST expose a `draft_reply` tool. Before Story 10.5.3
    this was absent — the flagship capability had no chat call site
    (F-10-5-11)."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    tool_names = set(server._tool_manager._tools.keys())  # type: ignore[attr-defined]
    assert "draft_reply" in tool_names, (
        "draft_reply not registered as an MCP tool — the Opus draft pipeline "
        "remains unreachable from chat (F-10-5-11)"
    )


@pytest.mark.asyncio
async def test_draft_reply_via_chat_tool_writes_real_router_call(tmp_path: Path) -> None:
    """Invoking the `draft_reply` tool through the real MCP surface drives
    handle_draft_reply for real, and a genuine router_calls row for
    task_type='draft_reply' lands (with a non-qwen Opus model) — proving the
    chat call site is live, not an L2-green illusion.

    ask_router runs for real against a registered fake Opus adapter. NO
    monkeypatch of ask_router.
    """
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, "g-draft", sensitivity="normal")
    _install_policy_snapshot()
    # draft_reply resolves to claude-opus-4-7 per router/policy.yaml.
    register_adapter("claude-opus-4-7", _FakeOpusAdapter("claude-opus-4-7"))

    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "draft_reply",
            {
                "target_email_id": "g-draft",
                "user_message": "reply and confirm 2pm",
                # empty string → caller asserts pre-fetched tone signals, so the
                # orchestrator skips tone_style_mirror; keeps this test focused
                # on the draft_reply router row.
                "tone_signals_blob": "",
            },
        )

    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["state"] == "draft_presented", f"unexpected outcome: {body}"
    assert body["draft_body"]

    rows = await fetchall(
        db_path,
        "SELECT task_type, model_chosen FROM router_calls WHERE task_type = 'draft_reply'",
    )
    assert rows, "no router_calls row written for draft_reply — chat path is dead"
    assert rows[0][0] == "draft_reply"
    # Non-qwen: the flagship draft is Opus-bound, not the free local model.
    assert "qwen" not in (rows[0][1] or "").lower()


@pytest.mark.asyncio
async def test_draft_reply_confidential_refused_through_wrapper_no_router_call(
    tmp_path: Path,
) -> None:
    """CR-10-5-3 (reviewer): the sensitivity gate is preserved AT THE NEW CHAT
    CALL SITE, not just in the pre-existing orchestrator tests. A confidential
    email routed through the `draft_reply` MCP tool returns confidential_refused
    and writes ZERO router_calls rows — the privacy invariant holds on the newly
    exposed surface."""
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, "g-conf", sensitivity="confidential")
    _install_policy_snapshot()
    register_adapter("claude-opus-4-7", _FakeOpusAdapter("claude-opus-4-7"))

    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool(
            "draft_reply",
            {"target_email_id": "g-conf", "user_message": "reply to that"},
        )

    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["state"] == "confidential_refused", f"unexpected outcome: {body}"
    assert body["draft_body"] is None
    assert body["defender_message"]

    # Privacy invariant: NO router_calls row of any kind — the confidential
    # body never reached the API through the new tool.
    rows = await fetchall(db_path, "SELECT COUNT(*) FROM router_calls")
    assert rows[0][0] == 0, "confidential email produced a router_calls row via draft_reply"


@pytest.mark.asyncio
async def test_draft_reply_sensitive_without_token_needs_confirmation(
    tmp_path: Path,
) -> None:
    """CR-10-5-3 (reviewer): a sensitive email with no confirmation_token routed
    through the `draft_reply` MCP tool returns needs_sensitivity_token and writes
    no draft — the token contract is enforced at the new chat call site."""
    db_path = _setup_db(tmp_path)
    await _seed_email(db_path, "g-sens", sensitivity="sensitive")
    _install_policy_snapshot()
    register_adapter("claude-opus-4-7", _FakeOpusAdapter("claude-opus-4-7"))

    server = build_mcp_server(db_path=db_path)
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        # confirmation_token omitted entirely (None default) — exercises the
        # real default path, not the "" sentinel used for tone-skip.
        result = await client.call_tool(
            "draft_reply",
            {"target_email_id": "g-sens", "user_message": "reply to that"},
        )

    assert not getattr(result, "isError", False)
    body = _parse_tool_result(result)
    assert body["state"] == "needs_sensitivity_token", f"unexpected outcome: {body}"
    assert body["draft_body"] is None
