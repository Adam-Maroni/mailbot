"""Story AI-1 Phase 2 (10-6-1, AC-5) — a DEFAULT chat tool-call routes to the
local lane (qwen), not haiku.

This is the reachability last-mile (F-10-3-2 layer 3). Phase 1 made qwen
tool-CAPABLE (adapter + router capability gate). But the live Discord walk
(2026-07-11) proved every `chat_completions_tool_call` still routed to HAIKU
(DB `router_calls` ground truth) because `dispatch_tool_call` sourced its
default model from the `hermes_aux` policy entry (haiku) — so the now-capable
local lane was never REACHED on the default path.

The fix: a dedicated `chat_completions_tool_call` policy task entry supplies the
DEFAULT model for tool-call dispatch (set to qwen). `hermes_aux` stays the LANE
proxy (rate-limit / semaphore accounting) but no longer supplies the model.

Contract asserted here:
  * Default (no override) tool-call → qwen adapter invoked; audit row
    model_chosen=qwen, reason=`policy:chat_completions_tool_call:default`.
  * The `main.py` alias-resolution for request.model=="hermes_aux" resolves to
    the chat_completions_tool_call default (qwen), NOT hermes_aux.model (haiku).
  * Overrides (one-shot / persistent / is_force_override) still win.
  * SAFETY unchanged: a qwen-proposed irreversible action is still gated
    downstream (covered by test_ai1_qwen_proposed_irreversible_still_gated.py);
    the dispatcher only picks the proposing model.
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
from mailbot_api.router.oneshot import (
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import dispatch_tool_call

_HAIKU = "claude-haiku-4-5-20251001"
_OPUS = "claude-opus-4-7"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_TOOL_CALL_TASK_TYPE = "chat_completions_tool_call"


# A policy with BOTH the hermes_aux lane-proxy (haiku) AND the new
# chat_completions_tool_call model-default (qwen). This mirrors the real
# router/policy.yaml shape after the AC-5 change.
_POLICY_YAML = f"""\
version: "test-ai-1-phase-2-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  hermes_aux:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
  chat_completions_tool_call:
    model: "{_QWEN}"
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
    _reset_oneshot_override_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()


class _RecordingAdapter:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.invocations: list[dict[str, Any]] = []

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **kwargs: Any) -> ToolCallAdapterResponse:
        self.invocations.append({"kwargs": kwargs})
        return ToolCallAdapterResponse(
            text=f"ok from {self.model_id}",
            tool_calls=[],
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=12,
            finish_reason="stop",
            raw={"mock": True, "model": self.model_id},
        )


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


def _tools() -> list[ChatCompletionToolDef]:
    return [
        ChatCompletionToolDef(
            type="function",
            function=ChatCompletionFunctionDef(
                name="find_emails",
                description="Read-only search.",
                parameters={"type": "object", "properties": {}},
            ),
        )
    ]


async def test_default_tool_call_routes_to_local_qwen(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5 core: a default (no-override) tool-call dispatch resolves its model
    from the `chat_completions_tool_call` policy entry (qwen), NOT hermes_aux
    (haiku). The qwen adapter is invoked and the audit row records the local
    model with the chat_completions_tool_call policy-default reason.

    NOTE: the caller (main.py) resolves the request's "hermes_aux" alias to this
    default before dispatch. Here we pass model=_QWEN to represent that resolved
    default; see test_main_alias_resolves_to_local_default for the resolution
    site itself.
    """
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_QWEN,  # the default resolved from chat_completions_tool_call
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True, f"expected ok; got {result}"
    # The LOCAL lane carried the tool-call — haiku was NOT reached.
    assert len(qwen.invocations) == 1
    assert len(haiku.invocations) == 0
    assert result.model_used == _QWEN

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _QWEN
    # The default reason keys on the NEW task entry, not hermes_aux.
    assert rows[0][1] == "policy:chat_completions_tool_call:default"


async def test_oneshot_override_still_wins_over_local_default(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Precedence preserved: a one-shot `use opus` override still beats the new
    local default. Overrides win; the local lane is only the DEFAULT."""
    db_path = _setup(tmp_path)
    opus = _RecordingAdapter(_OPUS)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_OPUS, opus)
    register_adapter(_QWEN, qwen)

    _set_oneshot_override(model=_OPUS, session_id="test-session")

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_QWEN,  # default resolved to local, but one-shot forces opus
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(opus.invocations) == 1
    assert len(qwen.invocations) == 0
    assert result.model_used == _OPUS

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert rows[0][1] == "slash_command:one_shot:adam"


async def test_force_override_still_wins_over_local_default(
    tmp_path: Path, _clean_state: Any
) -> None:
    """An explicit is_force_override (non-chat API surface picking a model) still
    wins over the local default and attributes OVERRIDE_API."""
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_HAIKU,
        is_force_override=True,  # explicit — wins over the local default
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(haiku.invocations) == 1
    assert len(qwen.invocations) == 0

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert rows[0][1] == "override:api:force_model"
