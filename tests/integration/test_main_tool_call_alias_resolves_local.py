"""Story AI-1 Phase 2 (10-6-1, AC-5) — the main.py alias-resolution site.

When Hermes calls /v1/chat/completions with `model="hermes_aux"` (the default
alias — it doesn't force a model), `_chat_completions_tools_dispatch` must
resolve that alias to the `chat_completions_tool_call` policy default (local
qwen), NOT `hermes_aux.model` (haiku).

BEFORE this change the alias resolved to `hermes_aux.model` = haiku, so every
default chat tool-call landed on the paid lane — the layer-3 reachability gap.
This test pins the resolution site itself (complementary to
test_dispatch_tool_call_default_routes_to_local.py which pins the dispatcher).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.main import (
    _chat_completions_tools_dispatch,
    _ChatCompletionsRequest,
    _ChatMessage,
)
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

_HAIKU = "claude-haiku-4-5-20251001"
_OPUS = "claude-opus-4-7"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"

_POLICY_YAML = f"""\
version: "test-ai-1-phase-2-main-v1"

tasks:
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
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()


class _RecordingAdapter:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.invocations = 0

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **kwargs: Any) -> ToolCallAdapterResponse:
        self.invocations += 1
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


def _request(model: str) -> _ChatCompletionsRequest:
    return _ChatCompletionsRequest(
        model=model,
        messages=[_ChatMessage(role="user", content="find my unread emails")],
        tools=[
            ChatCompletionToolDef(
                type="function",
                function=ChatCompletionFunctionDef(
                    name="find_emails",
                    description="Read-only search.",
                    parameters={"type": "object", "properties": {}},
                ),
            )
        ],
    )


async def test_hermes_aux_alias_resolves_to_local_default(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: request.model=="hermes_aux" (default, no force) resolves to the
    chat_completions_tool_call default (qwen) — the local lane is REACHED,
    haiku is NOT invoked, and the audit row records the policy-default reason
    keyed on chat_completions_tool_call."""
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku)
    register_adapter(_QWEN, qwen)

    result = await _chat_completions_tools_dispatch(
        request=_request("hermes_aux"),
        caller_origin="hermes-chat",
        db_path=db_path,
    )

    assert result.ok is True, f"expected ok; got {result}"
    assert qwen.invocations == 1
    assert haiku.invocations == 0
    assert result.model_used == _QWEN

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        ("chat_completions_tool_call",),
    )
    assert len(rows) == 1
    assert rows[0][0] == _QWEN
    assert rows[0][1] == "policy:chat_completions_tool_call:default"


async def test_oneshot_override_wins_through_main_alias_path(
    tmp_path: Path, _clean_state: Any
) -> None:
    """CR (Acceptance Auditor coverage gap, 10-6-1): drive the FULL alias path —
    request.model=="hermes_aux" (resolves to the local default) WITH a one-shot
    override armed — through `_chat_completions_tools_dispatch` and prove the
    one-shot wins over the local default end-to-end (not just at the dispatcher
    unit level). Precedence: override beats the new local default."""
    db_path = _setup(tmp_path)
    opus = _RecordingAdapter(_OPUS)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_OPUS, opus)
    register_adapter(_QWEN, qwen)

    _set_oneshot_override(model=_OPUS, session_id="test-session")

    result = await _chat_completions_tools_dispatch(
        request=_request("hermes_aux"),  # alias → local default, but one-shot armed
        caller_origin="hermes-chat",
        db_path=db_path,
    )

    assert result.ok is True
    assert opus.invocations == 1
    assert qwen.invocations == 0
    assert result.model_used == _OPUS

    rows = await fetchall(
        db_path,
        "SELECT model_chosen_reason FROM router_calls WHERE task_type = ?",
        ("chat_completions_tool_call",),
    )
    assert rows[0][0] == "slash_command:one_shot:adam"


async def test_explicit_model_request_still_forces_that_model(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Regression: an explicit request.model (not the hermes_aux alias) is still
    treated as an explicit force — unchanged by the alias-resolution change."""
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku)
    register_adapter(_QWEN, qwen)

    result = await _chat_completions_tools_dispatch(
        request=_request(_HAIKU),  # caller explicitly asked for haiku
        caller_origin="hermes-chat",
        db_path=db_path,
    )

    assert result.ok is True
    assert haiku.invocations == 1
    assert qwen.invocations == 0

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        ("chat_completions_tool_call",),
    )
    assert rows[0][1] == "override:api:force_model"
