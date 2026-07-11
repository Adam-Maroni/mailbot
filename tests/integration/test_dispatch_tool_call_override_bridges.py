"""Story 9.5.2 Run 3 (Path B, Flavor 1) — dispatch_tool_call override bridges.

Verifies that Hermes-chat-driven MCP invocations of `set_model_oneshot` and
`set_model_persistent` actually engage on the downstream
`/v1/chat/completions` dispatch flowing through `dispatch_tool_call` — the
architectural gap Story 9.5.2 Run 3 discovered.

Path B change (2026-07-03):
  * `dispatch_tool_call` now peeks the one-shot slot (mirrors
    `ask_router` at router.py:218-223) and forces model + emits
    `slash_command:one_shot:adam` when armed.
  * `dispatch_tool_call` now peeks `policy.overrides_applied` for the
    task key `"hermes_aux"` (Flavor 1: chat lane is a valid persistent-
    override target) and forces model + emits
    `slash_command:persistent:adam` when the entry is present.

Verifies BOTH the model was forced AND the audit reason is emitted with the
locked-set vocabulary value.
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


# ---------------------------------------------------------------------------
# Fixtures + harness (mirrors test_dispatch_tool_call_sensitivity_gate_f28.py)
# ---------------------------------------------------------------------------


_POLICY_BASELINE_YAML = f"""\
version: "test-9-5-2-path-b-v1"

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
"""


_POLICY_YAML_WITH_HERMES_AUX_OVERRIDE = _POLICY_BASELINE_YAML


_USER_OVERRIDES_YAML = f"""\
tasks:
  hermes_aux:
    model: "{_OPUS}"
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
    """Adapter that records which model it was invoked as, returns canned success."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.invocations: list[dict[str, Any]] = []

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
        self.invocations.append({"messages": messages, "tools": tools})
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


def _setup_baseline(tmp_path: Path) -> str:
    """Baseline policy — no user overrides."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_BASELINE_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


def _setup_with_hermes_aux_persistent_override(tmp_path: Path) -> str:
    """Policy where `hermes_aux` is overridden to opus in user-overrides.yaml."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML_WITH_HERMES_AUX_OVERRIDE, encoding="utf-8")
    user_overrides = tmp_path / "policy.user-overrides.yaml"
    user_overrides.write_text(_USER_OVERRIDES_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml, overrides_path=user_overrides))
    return db_path


def _tools() -> list[ChatCompletionToolDef]:
    return [
        ChatCompletionToolDef(
            type="function",
            function=ChatCompletionFunctionDef(
                name="noop",
                description="A no-op tool.",
                parameters={"type": "object", "properties": {}},
            ),
        )
    ]


# ---------------------------------------------------------------------------
# AC-1 bridge — one-shot slot peek in dispatch_tool_call
# ---------------------------------------------------------------------------


async def test_dispatch_tool_call_bridges_oneshot_override(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-1 bridge — when the one-shot slot is armed with a model, a
    subsequent Hermes-chat-driven dispatch (through `dispatch_tool_call`)
    force-uses that model AND emits `slash_command:one_shot:adam` audit
    reason. Mirrors `ask_router`'s peek at router.py:218-223.
    """
    db_path = _setup_baseline(tmp_path)
    # Register both adapters so the routing can succeed regardless of which
    # model the bridge selects.
    haiku_adapter = _RecordingAdapter(_HAIKU)
    opus_adapter = _RecordingAdapter(_OPUS)
    register_adapter(_HAIKU, haiku_adapter)
    register_adapter(_OPUS, opus_adapter)

    # Arm the one-shot slot with opus.
    _set_oneshot_override(model=_OPUS, session_id="test-session-9-5-2")

    # Dispatch through dispatch_tool_call as Hermes chat would — the
    # default model (from hermes_aux policy) is haiku, but the one-shot
    # should force opus.
    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,  # the alias-resolved default from policy.hermes_aux
        db_path=db_path,
    )
    assert result.ok is True, f"expected ok; got {result}"

    # Opus adapter got the call — one-shot forced the model.
    assert len(opus_adapter.invocations) == 1, (
        f"expected opus to be dispatched via one-shot bridge; opus.invocations={len(opus_adapter.invocations)}, "
        f"haiku.invocations={len(haiku_adapter.invocations)}"
    )
    assert len(haiku_adapter.invocations) == 0

    # Audit row carries the locked-set vocab reason.
    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _OPUS
    assert rows[0][1] == "slash_command:one_shot:adam"

    # The one-shot slot MUST be consumed after this dispatch. Otherwise
    # every subsequent Hermes-chat completion would re-fire the override,
    # creating a lock-out if the model happened to be tool-incapable.
    from mailbot_api.router.oneshot import _get_active_oneshot_override  # noqa: PLC0415
    assert _get_active_oneshot_override() is None, (
        "one-shot slot must be consumed after dispatch_tool_call dispatch; "
        "otherwise the next Hermes-chat completion would re-force the override"
    )


async def test_dispatch_tool_call_oneshot_slot_consumed_on_adapter_failure(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """Story 9-3 semantic parity — consume is outcome-independent. Even if
    the adapter fails post-consume (e.g., qwen doesn't support tools), the
    slot is spent. This prevents the lock-out pattern where a broken
    override model would infinitely re-force itself on every retry.
    """
    db_path = _setup_baseline(tmp_path)
    # Register a broken adapter for opus (raises to simulate tools_unsupported).
    haiku_adapter = _RecordingAdapter(_HAIKU)

    class _BrokenAdapter:
        async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            raise NotImplementedError

        async def call_with_tools(self, **_kwargs: Any) -> Any:
            raise RuntimeError("tools_unsupported")

    register_adapter(_HAIKU, haiku_adapter)
    register_adapter(_OPUS, _BrokenAdapter())

    _set_oneshot_override(model=_OPUS, session_id="test-session")

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
    )
    # Adapter failed — result.ok is False, but slot was still consumed.
    assert result.ok is False

    from mailbot_api.router.oneshot import _get_active_oneshot_override  # noqa: PLC0415
    assert _get_active_oneshot_override() is None, (
        "one-shot slot must be consumed even on adapter failure — otherwise "
        "a broken override model creates a permanent lock-out"
    )


async def test_dispatch_tool_call_oneshot_bridge_yields_to_explicit_is_force_override(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """When the caller sets `is_force_override=True` (explicit API-side
    override from a non-chat surface), the one-shot slot is NOT consulted
    — matches `ask_router` precedence semantics. Audit reason is
    OVERRIDE_API.
    """
    db_path = _setup_baseline(tmp_path)
    haiku_adapter = _RecordingAdapter(_HAIKU)
    opus_adapter = _RecordingAdapter(_OPUS)
    register_adapter(_HAIKU, haiku_adapter)
    register_adapter(_OPUS, opus_adapter)

    # Arm the one-shot slot with opus — but caller explicit-forces haiku.
    _set_oneshot_override(model=_OPUS, session_id="test-session-9-5-2")

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,
        is_force_override=True,  # explicit — should win over one-shot
        db_path=db_path,
    )
    assert result.ok is True

    # Haiku got the call (explicit force wins).
    assert len(haiku_adapter.invocations) == 1
    assert len(opus_adapter.invocations) == 0

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _HAIKU
    assert rows[0][1] == "override:api:force_model"


# ---------------------------------------------------------------------------
# AC-2 bridge — persistent override peek keyed on "hermes_aux" lane
# ---------------------------------------------------------------------------


async def test_dispatch_tool_call_bridges_persistent_hermes_aux_override(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """AC-2 bridge (Flavor 1) — when `policy.user-overrides.yaml` sets a
    persistent override for the `hermes_aux` task, a subsequent
    Hermes-chat-driven dispatch uses that overridden model AND emits
    `slash_command:persistent:adam` audit reason.

    Flavor-1 semantic: `hermes_aux` is a valid task key for the
    persistent-override use-case, keyed on the LANE (not a per-email task).
    """
    db_path = _setup_with_hermes_aux_persistent_override(tmp_path)
    haiku_adapter = _RecordingAdapter(_HAIKU)
    opus_adapter = _RecordingAdapter(_OPUS)
    register_adapter(_HAIKU, haiku_adapter)
    register_adapter(_OPUS, opus_adapter)

    # Dispatch with model=_HAIKU (Hermes's LLM asked for the alias-resolved
    # default) — the persistent override for hermes_aux should force opus.
    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
    )
    assert result.ok is True

    # Opus got the call — persistent-override bridge forced the model.
    assert len(opus_adapter.invocations) == 1
    assert len(haiku_adapter.invocations) == 0

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _OPUS
    assert rows[0][1] == "slash_command:persistent:adam"


async def test_oneshot_takes_precedence_over_persistent_in_dispatch_tool_call(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """One-shot precedence over persistent — mirrors `ask_router` semantics
    where the one-shot peek fires FIRST at router.py:218-223 (before the
    persistent branch at router.py:287-288).
    """
    db_path = _setup_with_hermes_aux_persistent_override(tmp_path)
    haiku_adapter = _RecordingAdapter(_HAIKU)
    opus_adapter = _RecordingAdapter(_OPUS)
    qwen_adapter = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku_adapter)
    register_adapter(_OPUS, opus_adapter)
    register_adapter(_QWEN, qwen_adapter)

    # Persistent override is opus (hermes_aux entry in user-overrides).
    # One-shot arms qwen. One-shot should win.
    _set_oneshot_override(model=_QWEN, session_id="test-session")

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
    )
    # Story AI-1: qwen is tool-capable now, so the one-shot qwen pick DISPATCHES
    # (the old pre-dispatch refusal is gone). The precedence contract this test
    # guards is proven the same way, just on the success path: the SELECTED and
    # INVOKED model is qwen (the one-shot pick), NOT opus (persistent) or haiku
    # (policy). Whether the resulting tool-call may ACT is a downstream
    # (model-independent) propose_action decision, not this dispatcher's job.
    assert result.ok is True
    assert result.model_used == _QWEN
    # The one-shot pick (qwen) was the ONLY adapter invoked — precedence proven.
    assert len(qwen_adapter.invocations) == 1
    assert len(opus_adapter.invocations) == 0
    assert len(haiku_adapter.invocations) == 0

    # The dispatch is auditable and records the one-shot precedence reason.
    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _QWEN
    assert rows[0][1] == "slash_command:one_shot:adam"


async def test_no_override_no_bridge_engagement(
    tmp_path: Path, _clean_state: Any,
) -> None:
    """Baseline no-op — no one-shot armed, no persistent override, no
    is_force_override. Should route via `policy_default("hermes_aux")` at
    haiku, matching pre-Path-B behavior for regression coverage.
    """
    db_path = _setup_baseline(tmp_path)
    haiku_adapter = _RecordingAdapter(_HAIKU)
    register_adapter(_HAIKU, haiku_adapter)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "test"}],
        tools=_tools(),
        model=_HAIKU,
        db_path=db_path,
    )
    assert result.ok is True
    assert len(haiku_adapter.invocations) == 1

    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == _HAIKU
    assert rows[0][1] == "policy:hermes_aux:default"
