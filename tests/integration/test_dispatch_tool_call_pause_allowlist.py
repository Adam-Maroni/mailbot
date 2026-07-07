"""Story 10.5.1 (AC-3, AC-4) — resume-while-paused tool-surface restriction.

F1 + F-10-5-4: the old pause gate 502'd the whole chat-interpretation turn, so
a "resume" typed in Discord could never reach `resume_router` (deadlock) and
`hermes_aux` chat ingress was fully bricked. The fix makes `dispatch_tool_call`
CONDITIONAL while paused: PERMIT the interpretation turn but restrict the
offered `tools` to a control/status allowlist so no write/action tool-call can
be dispatched (F4 containment), while `resume_router` stays reachable.

These tests assert:
  1. While paused, a write/action tool (`propose_action`) is filtered OUT of
     the tools handed to the adapter — the model can't reach it.
  2. While paused, a control tool (`resume_router`) IS still offered.
  3. The paused refusal writes a `pause_gate:refused` audit row (AC-4).
  4. When NOT paused, the full tool surface is offered (no regression).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import (
    ChatCompletionFunctionDef,
    ChatCompletionToolDef,
)
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import ToolCallAdapterResponse
from mailbot_api.router.pause import PauseState, _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import dispatch_tool_call

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"

_POLICY_YAML = f"""\
version: "test-10-5-1-v1"

tasks:
  hermes_aux:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state() -> Any:
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


class _RecordingToolAdapter:
    """Adapter that records the `tools` list it was handed, so the test can
    assert which tools survived the paused-restriction filter."""

    def __init__(self) -> None:
        self.seen_tools: list[Any] | None = None

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
        tool_choice: Any = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        self.seen_tools = list(tools)
        return ToolCallAdapterResponse(
            text="ok",
            tool_calls=[],
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=12,
            finish_reason="stop",
            raw={"mock": True},
        )


def _tool(name: str) -> ChatCompletionToolDef:
    return ChatCompletionToolDef(
        type="function",
        function=ChatCompletionFunctionDef(
            name=name,
            description=f"The {name} verb.",
            parameters={"type": "object", "properties": {}},
        ),
    )


def _messages() -> list[dict[str, Any]]:
    return [{"role": "user", "content": "please resume the router"}]


async def _pause_via_db(db_path: str) -> None:
    """Pause by writing the DB row (simulating the API process), then reset the
    module singleton so the checking path cannot rely on a warm mirror."""
    api_state = PauseState()
    await api_state.initialize(db_path)
    await api_state.pause(db_path, reason="operator-pause")
    _reset_pause_state_for_test()


async def _pause_refusal_rows(db_path: str) -> int:
    rows = await fetchall(
        db_path,
        "SELECT COUNT(*) FROM router_calls WHERE model_chosen_reason = ?",
        ("pause_gate:refused",),
    )
    return int(rows[0][0]) if rows else 0


async def test_paused_filters_out_write_action_tool(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-3 + F4 containment: while paused, `propose_action` is filtered out of
    the tools handed to the adapter, so the model cannot dispatch a write."""
    db_path = _setup(tmp_path)
    adapter = _RecordingToolAdapter()
    register_adapter(_HAIKU, adapter)
    await _pause_via_db(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("resume_router"), _tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux",
    )

    # The interpretation turn was PERMITTED (not a 502) — the whole point of AC-3.
    assert result.ok is True
    # But only the control tool survived; the write tool was filtered out.
    assert adapter.seen_tools is not None
    seen_names = {t.function.name for t in adapter.seen_tools}
    assert seen_names == {"resume_router"}
    assert "propose_action" not in seen_names


async def test_paused_refusal_writes_audit_row(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-4: filtering out a write/action tool while paused leaves an audit row."""
    db_path = _setup(tmp_path)
    adapter = _RecordingToolAdapter()
    register_adapter(_HAIKU, adapter)
    await _pause_via_db(db_path)

    await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("resume_router"), _tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux",
    )
    assert await _pause_refusal_rows(db_path) == 1


async def test_paused_control_only_request_no_audit_row(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A paused request offering ONLY control/status tools is fully permitted
    and does not record a refusal (nothing was filtered out)."""
    db_path = _setup(tmp_path)
    adapter = _RecordingToolAdapter()
    register_adapter(_HAIKU, adapter)
    await _pause_via_db(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("resume_router"), _tool("inspect_policy")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux",
    )
    assert result.ok is True
    assert adapter.seen_tools is not None
    assert {t.function.name for t in adapter.seen_tools} == {
        "resume_router",
        "inspect_policy",
    }
    assert await _pause_refusal_rows(db_path) == 0


async def test_paused_allowlist_matches_hermes_mcp_namespaced_names(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Story 10.5.1 (F-10-5-4 live-walk fix, 2026-07-07) — the allowlist must
    match Hermes's NAMESPACED MCP tool names (`mcp_mailbot_api_resume_router`),
    not just the bare verb. The live Discord walk exposed that the raw-name
    comparison filtered out EVERY tool (allowed_count: 0) in production because
    Hermes prefixes every verb, so the resume control path was unreachable —
    re-opening the F-10-5-4 deadlock from a new angle."""
    db_path = _setup(tmp_path)
    adapter = _RecordingToolAdapter()
    register_adapter(_HAIKU, adapter)
    await _pause_via_db(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        # Exactly the shape Hermes sends: mcp_<server>_<verb>.
        tools=[
            _tool("mcp_mailbot_api_resume_router"),
            _tool("mcp_mailbot_api_inspect_policy"),
            _tool("mcp_mailbot_api_propose_action"),  # write — must still be filtered
        ],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )
    assert result.ok is True
    assert adapter.seen_tools is not None
    seen = {t.function.name for t in adapter.seen_tools}
    # Control + status survive; the namespaced write verb is filtered out.
    assert seen == {"mcp_mailbot_api_resume_router", "mcp_mailbot_api_inspect_policy"}
    assert "mcp_mailbot_api_propose_action" not in seen
    # The filtered write verb left a refusal audit row.
    assert await _pause_refusal_rows(db_path) == 1


async def test_not_paused_offers_full_tool_surface(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Regression: when NOT paused, the full tool surface reaches the adapter
    unchanged (the restriction only applies while paused)."""
    db_path = _setup(tmp_path)
    adapter = _RecordingToolAdapter()
    register_adapter(_HAIKU, adapter)
    # No pause.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("resume_router"), _tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux",
    )
    assert result.ok is True
    assert adapter.seen_tools is not None
    assert {t.function.name for t in adapter.seen_tools} == {
        "resume_router",
        "propose_action",
    }
    assert await _pause_refusal_rows(db_path) == 0
