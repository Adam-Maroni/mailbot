"""Story 10.7.2 — qwen-specific tool-call system-prompt injection at the
`dispatch_tool_call` seam (DEFENSIVE / optional per the 10.7.0 spike §4.4).

The 10.7.0 characterization spike measured that a system prompt adds ZERO on a
good tool description (leaf selection 20/20 either way) and does NOT recover the
flat-26 surface (0/N even with a strong prompt). So this story is explicitly
belt-and-suspenders: a SHORT qwen-only instruction is composed into the
`system_text` handed to `adapter.call_with_tools`, gated on the local
tool-capable model regex (`qwen2.5:*`), so a residual on the real Hermes path
has a cheap lever to lean on — WITHOUT touching the API-bound (`claude-*`) path
and WITHOUT replacing the client-sent system messages.

Contract asserted here (spy the `system` kwarg reaching `call_with_tools`):
  * AC-1: a `qwen2.5:*` tools dispatch → `system` contains the qwen instruction.
  * AC-1: a `claude-*` tools dispatch → `system` does NOT contain the instruction
    (the API-bound path is unchanged).
  * AC-2: client-sent system messages are all preserved alongside the
    instruction (the `"\n\n"` concatenation contract, CR-6 Story 6-9).
  * AC-2: a qwen dispatch with ZERO client system messages still gets a valid
    instruction-only `system`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db import connection, queries
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
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import (
    _QWEN_TOOLCALL_SYSTEM_INSTRUCTION,
    _compose_qwen_toolcall_system_text,
    dispatch_tool_call,
)

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_TOOL_CALL_TASK_TYPE = "chat_completions_tool_call"

_POLICY_YAML = f"""\
version: "test-10-7-2-v1"

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
                description="find/list/show/search unread mail in the inbox.",
                parameters={"type": "object", "properties": {}},
            ),
        )
    ]


async def test_qwen_tool_dispatch_injects_instruction(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1: a `qwen2.5:*` tools dispatch composes the qwen instruction into the
    `system` handed to `call_with_tools`."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(qwen.invocations) == 1
    system = qwen.invocations[0]["kwargs"]["system"]
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION in system


async def test_qwen_instruction_composes_with_client_system_messages(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: the qwen instruction is composed ALONGSIDE all client-sent system
    messages (the `"\\n\\n"` concatenation contract is preserved, not replaced)."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[
            {"role": "system", "content": "SOUL-BLOCK-ALPHA"},
            {"role": "system", "content": "AGENTS-BLOCK-BETA"},
            {"role": "user", "content": "find my unread emails"},
        ],
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    system = qwen.invocations[0]["kwargs"]["system"]
    # All client system blocks survive.
    assert "SOUL-BLOCK-ALPHA" in system
    assert "AGENTS-BLOCK-BETA" in system
    # AND the qwen instruction is present.
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION in system


async def test_qwen_instruction_present_with_zero_client_system_messages(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2: a qwen dispatch with NO client system messages still gets a valid
    instruction-only `system`."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    system = qwen.invocations[0]["kwargs"]["system"]
    assert system.strip() != ""
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION in system


async def test_claude_tool_dispatch_does_not_inject_instruction(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1: an API-bound (`claude-*`) tools dispatch is UNCHANGED — no qwen
    instruction is injected; the client system_text passes through verbatim."""
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    register_adapter(_HAIKU, haiku)

    result = await dispatch_tool_call(
        messages=[
            {"role": "system", "content": "SOUL-BLOCK-ALPHA"},
            {"role": "user", "content": "find my unread emails"},
        ],
        tools=_tools(),
        model=_HAIKU,
        is_force_override=True,  # force the claude model to be the dispatch target
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(haiku.invocations) == 1
    system = haiku.invocations[0]["kwargs"]["system"]
    # The API-bound path must NOT carry the qwen instruction.
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION not in system
    # Client system messages still reach the model unchanged.
    assert system == "SOUL-BLOCK-ALPHA"


async def _set_degraded(db_path: str) -> None:
    await connection.execute_write(
        db_path, queries.DEGRADED_MODE_ENTER, ("2026-07-16T00:00:00Z",)
    )


async def test_budget_degraded_demotion_to_qwen_receives_instruction(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-1 placement rationale (10.7.2 review [Patch]): the injection gates on
    the EFFECTIVE post-degraded-demotion `model`, so a budget-degraded turn that
    started as haiku but demoted to qwen MUST receive the instruction. This is
    the exact scenario the story cites as its reason for gating at the late
    call site; without this test a future reordering of the demotion vs. the
    system-text assembly could silently break it.

    Policy target is haiku; degraded mode active → `dispatch_tool_call` demotes
    to qwen; the qwen adapter (spy) must capture a `system` carrying the
    instruction.
    """
    # The standard policy has hermes_aux=haiku AND chat_completions_tool_call=qwen.
    # Dispatch with model=_HAIKU under degraded mode → demotes to qwen.
    db_path = _setup(tmp_path)

    haiku = _RecordingAdapter(_HAIKU)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_HAIKU, haiku)
    register_adapter(_QWEN, qwen)
    await _set_degraded(db_path)

    result = await dispatch_tool_call(
        messages=[{"role": "user", "content": "find my unread emails"}],
        tools=_tools(),
        model=_HAIKU,  # demoted to qwen by degraded mode
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    # qwen was reached (demoted target); haiku was NOT.
    assert len(qwen.invocations) == 1
    assert len(haiku.invocations) == 0
    assert result.model_used == _QWEN
    system = qwen.invocations[0]["kwargs"]["system"]
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION in system


async def test_whitespace_only_client_system_message_no_leading_junk(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2 edge (10.7.2 review [Patch]): a client system message that is
    all-whitespace must NOT produce a leading blank-line artifact before the
    instruction. The `.strip()` truthiness test treats whitespace-only as empty,
    so the qwen dispatch gets the instruction ALONE (no leading `"\\n\\n"`)."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=[
            {"role": "system", "content": "   \n\t  "},  # all whitespace
            {"role": "user", "content": "find my unread emails"},
        ],
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    system = qwen.invocations[0]["kwargs"]["system"]
    # Instruction present, and NOT preceded by whitespace-block junk.
    assert _QWEN_TOOLCALL_SYSTEM_INSTRUCTION in system
    assert not system.startswith((" ", "\n", "\t"))


# ---- Direct unit tests for the pure helper (10.7.2 review [Patch]) ----
# The 4 seam tests above exercise the helper only through the full
# `dispatch_tool_call` integration path. These pin the regex boundary behavior
# (case-sensitive, colon-required) directly on the pure function.


def test_compose_helper_injects_for_canonical_qwen() -> None:
    out = _compose_qwen_toolcall_system_text(_QWEN, "PERSONA")
    assert out == "PERSONA" + "\n\n" + _QWEN_TOOLCALL_SYSTEM_INSTRUCTION


def test_compose_helper_instruction_only_for_empty_system() -> None:
    assert _compose_qwen_toolcall_system_text(_QWEN, "") == _QWEN_TOOLCALL_SYSTEM_INSTRUCTION


def test_compose_helper_instruction_only_for_whitespace_system() -> None:
    assert (
        _compose_qwen_toolcall_system_text(_QWEN, "  \n ")
        == _QWEN_TOOLCALL_SYSTEM_INSTRUCTION
    )


def test_compose_helper_noop_for_claude() -> None:
    assert _compose_qwen_toolcall_system_text(_HAIKU, "PERSONA") == "PERSONA"


def test_compose_helper_noop_for_empty_model() -> None:
    # Empty model id must NOT match the qwen regex — returns system_text as-is.
    assert _compose_qwen_toolcall_system_text("", "PERSONA") == "PERSONA"


def test_compose_helper_case_sensitive_qwen_gate() -> None:
    # The gate is case-SENSITIVE (`^qwen2\.5:`); a capitalized variant must NOT
    # inject — locks the intended boundary rather than silently widening it.
    assert _compose_qwen_toolcall_system_text("Qwen2.5:3b", "PERSONA") == "PERSONA"


def test_compose_helper_colon_required_qwen_gate() -> None:
    # The gate requires the `:` (family + tag separator); a no-colon `qwen2.5`
    # is not a servable model id and must NOT inject.
    assert _compose_qwen_toolcall_system_text("qwen2.5", "PERSONA") == "PERSONA"
