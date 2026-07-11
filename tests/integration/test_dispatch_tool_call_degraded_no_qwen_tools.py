"""Story AI-1 — qwen IS tool-capable at the router gate (new contract).

HISTORY: this file was written for Story 10.5.5 (F-10-3-2) under the OLD
contract, when Qwen genuinely failed 18/18 tool-call attempts and the router's
capability gate refused a qwen tool-call with `TOOL_CALLS_UNAVAILABLE_DEGRADED`
BEFORE any `call_with_tools`. The AI-1 live probe (2026-07-11) proved
`OllamaAdapter.call_with_tools` works (6/6 exact at temp 0), and Adam decided
the "safety-net / blast-radius" design (Option 1): the local model is the
zero-cost floor and SHOULD keep acting under budget pressure, gated by the
action's REVERSIBILITY (the propose_action → drain tier pipeline), NOT by mode
and NOT by this router-side capability gate.

So the contract FLIPPED. Under the new design:
  * Route (a) — degraded demotion haiku→qwen: the tool-call PROCEEDS to the
    adapter (call_with_tools IS invoked). Whether the resulting tool-call may
    ACT on the mailbox is enforced downstream and model-independently by the
    propose_action tier/grant/confirmation pipeline (Tier-1 reversible proceed;
    Tier-2/3 irreversible still need grant + sensitivity handshake at drain).
  * Route (b) — policy/override resolving hermes_aux directly to qwen: also
    PROCEEDS.
  * The capability gate now ONLY refuses a genuinely tool-INCAPABLE local model
    (e.g. the `nomic-embed-text` embedding model) — that path is preserved as
    defense-in-depth.
  * A non-degraded tool-capable model (haiku) is unchanged (no regression).

These tests assert the NEW contract. The old "qwen refuses cleanly / adapter
never invoked" assertions are intentionally inverted — see the git history and
`AI-1-local-tool-caller-verify-or-restore.md` for the decision record.
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
    OpenAIToolCall,
    OpenAIToolCallFunction,
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
# An embedding model — genuinely NOT tool-capable; the capability gate must
# still refuse it (defense-in-depth). Used to prove the gate didn't become a
# match-everything no-op after opening it for qwen.
_EMBED = "nomic-embed-text"


def _policy_yaml(model: str) -> str:
    return f"""\
version: "test-ai-1-v1"

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


class _ToolCallingAdapter:
    """Records that call_with_tools was invoked and returns a real tool_call.

    Under the AI-1 contract a qwen tool-call is PERMITTED at the router gate,
    so this adapter (registered for qwen) must actually be reached — the router
    should call it and return its tool_calls to the caller. The action-trust
    decision happens LATER, when the caller drains the returned tool_call
    through propose_action (model-independent tier pipeline) — not here.
    """

    def __init__(self, tool_name: str = "mark_read") -> None:
        self.call_with_tools_invoked = False
        self._tool_name = tool_name

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        self.call_with_tools_invoked = True
        return ToolCallAdapterResponse(
            text="",
            tool_calls=[
                OpenAIToolCall(
                    id="call_0",
                    type="function",
                    function=OpenAIToolCallFunction(
                        name=self._tool_name,
                        arguments='{"email_id":"AAMkAD00"}',
                    ),
                )
            ],
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=12,
            finish_reason="tool_calls",
            raw={"mock": True},
        )


class _IncapableToolAdapter:
    """Records whether call_with_tools was invoked. For a genuinely
    tool-INCAPABLE model the router must refuse BEFORE reaching this, so this
    must stay False on the embedding-model path."""

    def __init__(self) -> None:
        self.call_with_tools_invoked = False

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        self.call_with_tools_invoked = True
        from mailbot_api.router.models import AdapterProviderError

        raise AdapterProviderError(model_id=_EMBED, sanitized_message="tools_unsupported")


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
    return [{"role": "user", "content": "mark that email read"}]


async def _set_degraded(db_path: str) -> None:
    await connection.execute_write(
        db_path, queries.DEGRADED_MODE_ENTER, ("2026-07-03T14:41:24Z",)
    )


async def _failed_tool_call_rows(db_path: str) -> int:
    rows = await fetchall(
        db_path,
        "SELECT COUNT(*) FROM router_calls WHERE task_type = ? AND outcome = ?",
        ("chat_completions_tool_call", "failed"),
    )
    return int(rows[0][0]) if rows else 0


async def test_degraded_demotion_to_qwen_now_dispatches(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Route (a), NEW contract (AI-1): haiku policy + degraded → demote to qwen
    → the tool-call PROCEEDS (qwen adapter IS invoked) and its tool_calls are
    returned. The trust gate for whether the returned action may ACT is the
    downstream propose_action tier pipeline, NOT this router gate."""
    db_path = _setup(tmp_path, policy_model=_HAIKU)
    qwen = _ToolCallingAdapter(tool_name="mark_read")
    register_adapter(_HAIKU, _HappyToolAdapter())
    register_adapter(_QWEN, qwen)
    await _set_degraded(db_path)

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_HAIKU,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    # The qwen adapter WAS reached — the doomed-refusal contract is gone.
    assert qwen.call_with_tools_invoked is True
    # The tool_call the local model emitted is surfaced back to the caller.
    assert result.tool_calls is not None
    assert result.tool_calls[0].function.name == "mark_read"
    # model_used reflects the demoted (local) target.
    assert result.model_used == _QWEN


async def test_policy_resolving_directly_to_qwen_now_dispatches(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Route (b), NEW contract (AI-1): policy hermes_aux resolves directly to
    qwen (a `use qwen` one-shot / persistent pick) — the tool-call PROCEEDS.
    Refusing an intentional local pick was the F-10-3-2 annoyance; it's gone."""
    db_path = _setup(tmp_path, policy_model=_QWEN)
    qwen = _ToolCallingAdapter(tool_name="mark_read")
    register_adapter(_QWEN, qwen)
    # NOT degraded — the target is qwen purely from policy.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert qwen.call_with_tools_invoked is True
    assert result.tool_calls is not None
    assert result.model_used == _QWEN


async def test_incapable_local_model_still_refuses_cleanly(
    tmp_path: Path, _clean_state: Any
) -> None:
    """The capability gate is NOT a match-everything no-op after AI-1: a
    genuinely tool-INCAPABLE local model (embedding model) reaching a tools
    request still refuses cleanly with the stable typed error, BEFORE any
    call_with_tools. This preserves the defense-in-depth the gate was built
    for while opening it for the tool-capable qwen family."""
    db_path = _setup(tmp_path, policy_model=_EMBED)
    embed = _IncapableToolAdapter()
    register_adapter(_EMBED, embed)
    # NOT degraded — embed purely from policy.

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_EMBED,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.TOOL_CALLS_UNAVAILABLE_DEGRADED
    assert result.error.retryable is False
    # The doomed dispatch never happened.
    assert embed.call_with_tools_invoked is False
    # An audit row was written (auditable refusal, not a silent return).
    assert await _failed_tool_call_rows(db_path) == 1


async def test_incapable_local_model_refusal_names_real_cause(
    tmp_path: Path, _clean_state: Any
) -> None:
    """W2b (preserved): when the target is a tool-incapable local model WITHOUT
    degraded mode, the refusal message must NOT falsely claim 'degraded mode';
    it must name the real cause (local model can't serve tool-calls) and say
    which model."""
    db_path = _setup(tmp_path, policy_model=_EMBED)
    register_adapter(_EMBED, _IncapableToolAdapter())

    result = await dispatch_tool_call(
        messages=_messages(),
        tools=[_tool("propose_action")],
        model=_EMBED,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    msg = result.error.message.lower()
    assert "degraded" not in msg
    assert "local model" in msg
    assert _EMBED in result.error.message


async def test_not_degraded_tool_capable_model_happy_path(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Regression: a tool-capable API model (haiku) not degraded dispatches
    normally (unchanged by AI-1)."""
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
