"""Story 10.5.5 (AC-2, F-10-3-2) — degraded tool-call path returns a clean typed
refusal instead of a doomed qwen dispatch.

Root cause of the 18/18 failure: while degraded, `dispatch_tool_call` demotes the
model (haiku → qwen) and then dispatches the tool-call to
`OllamaAdapter.call_with_tools`, which unconditionally raises
`tools_unsupported` — an opaque `failed` audit row with 0 tokens. The fix: at
the router gate, after resolving the target model, detect that the target cannot
serve tools and return `ToolCallResult(ok=False, error=RouterError(
code=TOOL_CALLS_UNAVAILABLE_DEGRADED, ...))` BEFORE any `call_with_tools`.

These tests assert:
  1. Route (a) — degraded demotion haiku→qwen returns the typed refusal, and the
     qwen adapter's `call_with_tools` is NEVER invoked (spy).
  2. The refusal carries the stable `TOOL_CALLS_UNAVAILABLE_DEGRADED` code and is
     non-retryable with a recovery-oriented message.
  3. An audit row is written (not a bare provider failure) so the fault is
     reconstructable.
  4. Route (b) — a policy resolving `hermes_aux` directly to qwen (not via
     degraded demotion) also refuses cleanly.
  5. NOT-degraded, tool-capable model → unchanged happy path (no regression).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db import connection, queries
from mailbot_api.db.connection import fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import (
    ChatCompletionFunctionDef,
    ChatCompletionToolDef,
    ErrorCode,
)
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import ToolCallAdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import dispatch_tool_call

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


def _policy_yaml(model: str) -> str:
    return f"""\
version: "test-10-5-5-v1"

tasks:
  hermes_aux:
    model: "{model}"
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


def _setup(tmp_path: Path, policy_model: str = _HAIKU) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_policy_yaml(policy_model), encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


class _SpyToolAdapter:
    """Records whether call_with_tools was invoked. If the router fix is
    correct, this must stay False on the degraded/qwen path."""

    def __init__(self) -> None:
        self.call_with_tools_invoked = False

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        self.call_with_tools_invoked = True
        # Mirror the real OllamaAdapter: qwen can't serve tools.
        from mailbot_api.router.models import AdapterProviderError

        raise AdapterProviderError(model_id=_QWEN, sanitized_message="tools_unsupported")


class _HappyToolAdapter:
    def __init__(self) -> None:
        self.call_with_tools_invoked = False

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        self.call_with_tools_invoked = True
        return ToolCallAdapterResponse(
            text="hi",
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
    return [{"role": "user", "content": "archive that email"}]


async def _set_degraded(db_path: str) -> None:
    await connection.execute_write(
        db_path, queries.DEGRADED_MODE_ENTER, ("2026-07-03T14:41:24Z",)
    )


async def _degraded_refusal_rows(db_path: str) -> int:
    rows = await fetchall(
        db_path,
        "SELECT COUNT(*) FROM router_calls WHERE task_type = ? AND outcome = ?",
        ("chat_completions_tool_call", "failed"),
    )
    return int(rows[0][0]) if rows else 0


async def test_degraded_demotion_to_qwen_refuses_cleanly_no_dispatch(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Route (a): haiku policy + degraded → demote to qwen → typed refusal, and
    the qwen adapter's call_with_tools is NEVER invoked."""
    db_path = _setup(tmp_path, policy_model=_HAIKU)
    qwen_spy = _SpyToolAdapter()
    register_adapter(_HAIKU, _HappyToolAdapter())
    register_adapter(_QWEN, qwen_spy)
    await _set_degraded(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.TOOL_CALLS_UNAVAILABLE_DEGRADED
    assert result.error.retryable is False
    # The doomed dispatch never happened.
    assert qwen_spy.call_with_tools_invoked is False
    # Recovery-oriented message.
    assert "degraded" in result.error.message.lower()
    # model_used reflects the demoted target.
    assert result.model_used == _QWEN


async def test_degraded_refusal_writes_audit_row(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: the refusal is auditable (a failed chat_completions_tool_call row),
    not a silent return."""
    db_path = _setup(tmp_path, policy_model=_HAIKU)
    register_adapter(_HAIKU, _HappyToolAdapter())
    register_adapter(_QWEN, _SpyToolAdapter())
    await _set_degraded(db_path)

    await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )
    assert await _degraded_refusal_rows(db_path) == 1


async def test_policy_resolving_directly_to_qwen_refuses_cleanly(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Route (b): policy hermes_aux resolves directly to qwen (NOT via degraded
    demotion) — a tools request must still refuse cleanly, not dispatch."""
    db_path = _setup(tmp_path, policy_model=_QWEN)
    qwen_spy = _SpyToolAdapter()
    register_adapter(_QWEN, qwen_spy)
    # NOT degraded — the target is qwen purely from policy.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.TOOL_CALLS_UNAVAILABLE_DEGRADED
    assert qwen_spy.call_with_tools_invoked is False


async def test_route_b_refusal_message_does_not_claim_degraded(
    tmp_path: Path, _clean_state: Any
) -> None:
    """W2b (walk 2026-07-11): when the target is qwen WITHOUT degraded mode
    (route b — a user override / policy pick), the refusal message must NOT
    claim 'degraded mode' (the pre-fix bug Adam hit: `use qwen` one-shot with
    degraded OFF surfaced a 'degraded mode' message). It must name the real
    cause (local model can't serve tool-calls)."""
    db_path = _setup(tmp_path, policy_model=_QWEN)
    register_adapter(_QWEN, _SpyToolAdapter())
    # NOT degraded — qwen purely from policy/override.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    msg = result.error.message.lower()
    assert "degraded" not in msg  # the W2b fix — no false degraded claim
    assert "local model" in msg   # names the real cause
    assert _QWEN in result.error.message  # tells the user WHICH model


async def test_route_a_refusal_message_does_claim_degraded(
    tmp_path: Path, _clean_state: Any
) -> None:
    """W2b converse: when degraded mode IS the cause (route a), the message
    SHOULD say so — the cause-branching must not over-correct."""
    db_path = _setup(tmp_path, policy_model=_HAIKU)
    register_adapter(_HAIKU, _HappyToolAdapter())
    register_adapter(_QWEN, _SpyToolAdapter())
    await _set_degraded(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert "degraded" in result.error.message.lower()


async def test_not_degraded_tool_capable_model_happy_path(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Regression: a tool-capable model (haiku) not degraded dispatches normally."""
    db_path = _setup(tmp_path, policy_model=_HAIKU)
    haiku = _HappyToolAdapter()
    register_adapter(_HAIKU, haiku)
    # Not degraded.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert haiku.call_with_tools_invoked is True
