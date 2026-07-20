"""Story 10.7.7 (AC-2/AC-3, F-10-7-6-R2) — repeat-invocation / turn-termination
guard: a same-verb-same-args storm short-circuits at $0 (no adapter, no paid
escalation) instead of looping.

The 10.7.6 clause-3 walk fixed SELECTION (qwen reaches find_emails) but the turn
ran away — ~60 identical `find_emails({})` calls in 26 min, no reply, then
Hermes escalated the whole turn to the PAID lane (haiku) → 502. Nothing on the
mailbot side detected the storm and gave the model a terminal signal. This guard
does, at the dispatch_tool_call seam, BEFORE any adapter call.

Contract asserted here:
  * ≥ N identical (tool, normalized-args) calls in the transcript → the router
    returns NO_PROGRESS terminal, invokes NO adapter (→ $0), records an audit
    row with cost 0.0.
  * On a LOCAL model the guard-fire still touches no paid adapter (AC-3).
  * A transcript of DISTINCT calls (different args) does NOT trip the guard.
  * A single legitimate repeat (below threshold) passes through and dispatches.

Per the Middleware-Real-Bootstrap reframing: real on-disk SQLite, real router
state, a recording adapter registered at the adapter seam (NOT the dispatcher
mocked).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import (
    _REPEAT_INVOCATION_THRESHOLD,
    _max_repeated_tool_invocation,
    dispatch_tool_call,
)

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_TOOL_CALL_TASK_TYPE = "chat_completions_tool_call"

_POLICY_YAML = f"""\
version: "test-10-7-7-v1"

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
    for reset in (
        _reset_registry_for_test,
        _reset_policy_snapshot_for_test,
        _reset_rate_limiter_for_test,
        _reset_semaphore_registry_for_test,
        _reset_guard_for_test,
        _reset_loop_detector_for_test,
        _reset_pause_state_for_test,
        _reset_oneshot_override_for_test,
    ):
        reset()
    yield
    for reset in (
        _reset_policy_snapshot_for_test,
        _reset_registry_for_test,
        _reset_rate_limiter_for_test,
        _reset_semaphore_registry_for_test,
        _reset_guard_for_test,
        _reset_loop_detector_for_test,
        _reset_pause_state_for_test,
        _reset_oneshot_override_for_test,
    ):
        reset()


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


def _assistant_find_emails_call(call_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """One assistant message carrying a find_emails tool_call (OpenAI wire shape:
    arguments is a JSON string)."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "find_emails", "arguments": json.dumps(args)},
            }
        ],
    }


def _storm_transcript(n: int, args: dict[str, Any]) -> list[dict[str, Any]]:
    """A transcript with `n` identical find_emails invocations interleaved with
    tool results — the exact shape Hermes replays after `n` no-op loops."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "find my unread emails"}]
    for i in range(n):
        messages.append(_assistant_find_emails_call(f"call-{i}", args))
        messages.append({"role": "tool", "tool_call_id": f"call-{i}", "content": "{\"ok\": true, \"projections\": []}"})
    return messages


# ---- pure-helper unit coverage ------------------------------------------------


def test_threshold_is_pinned_to_4() -> None:
    """AC-2 drift-pin: the threshold is a literal contract value, not a magic
    number tests silently track. Changing it must break a test on purpose
    (mirrors test_budget.py's `== 0.20` discipline)."""
    assert _REPEAT_INVOCATION_THRESHOLD == 4


def test_max_repeated_counts_trailing_run() -> None:
    """`_max_repeated_tool_invocation` returns the trailing consecutive run of
    the model's latest identical (name, normalized-args) choice."""
    msgs = _storm_transcript(5, {})
    name, count, args = _max_repeated_tool_invocation(msgs)
    assert name == "find_emails"
    assert count == 5
    # The repeated normalized args are surfaced for the guard-fire diagnostic log.
    assert args == "{}"


def test_max_repeated_treats_key_order_as_equivalent() -> None:
    """Arg key-order / whitespace does not defeat the storm detector."""
    msgs = [
        {"role": "assistant", "tool_calls": [
            {"id": "a", "type": "function",
             "function": {"name": "find_emails", "arguments": '{"a":1,"b":2}'}}]},
        {"role": "assistant", "tool_calls": [
            {"id": "b", "type": "function",
             "function": {"name": "find_emails", "arguments": '{"b":2, "a":1}'}}]},
    ]
    _name, count, _args = _max_repeated_tool_invocation(msgs)
    assert count == 2


def test_max_repeated_distinct_args_do_not_accumulate() -> None:
    """Distinct args each count once — a diverse search is not a storm."""
    msgs = [
        _assistant_find_emails_call("a", {"sender_domain": "example.com"}),
        _assistant_find_emails_call("b", {"sender_domain": "other.com"}),
        _assistant_find_emails_call("c", {"query": "invoice"}),
    ]
    _name, count, _args = _max_repeated_tool_invocation(msgs)
    assert count == 1


def test_max_repeated_run_resets_on_intervening_distinct_call() -> None:
    """CR-2026-07-20: a distinct call BREAKS the trailing run — the count is
    only the unbroken tail. Prior identical calls before a distinct one do NOT
    accumulate (this is what prevents a false NO_PROGRESS across a legitimate
    second successful turn)."""
    # 3 identical, then a distinct call, then 2 identical → trailing run = 2.
    msgs = [
        _assistant_find_emails_call("a", {}),
        _assistant_find_emails_call("b", {}),
        _assistant_find_emails_call("c", {}),
        _assistant_find_emails_call("d", {"query": "distinct"}),
        _assistant_find_emails_call("e", {}),
        _assistant_find_emails_call("f", {}),
    ]
    _name, count, _args = _max_repeated_tool_invocation(msgs)
    assert count == 2


def test_max_repeated_lifetime_repeats_across_turns_do_not_trip() -> None:
    """AC-2 "must NOT break a legitimate second user turn": the SAME call
    repeated across 4 turns each SEPARATED by a distinct call counts as a
    trailing run of 1 — well below threshold — so no false storm."""
    msgs: list[dict[str, Any]] = []
    for i in range(4):
        msgs.append(_assistant_find_emails_call(f"same-{i}", {}))
        msgs.append(_assistant_find_emails_call(f"other-{i}", {"query": f"q{i}"}))
    # transcript ends on a DISTINCT call → trailing run of that distinct call = 1.
    _name, count, _args = _max_repeated_tool_invocation(msgs)
    assert count == 1


# ---- guard behavior at the dispatch seam --------------------------------------


async def test_storm_short_circuits_at_zero_cost_local(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-2 + AC-3: a same-args storm on the LOCAL model returns NO_PROGRESS,
    invokes NO adapter (→ $0), and records a zero-cost audit row — never
    escalating to the paid lane."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    haiku = _RecordingAdapter(_HAIKU)
    register_adapter(_QWEN, qwen)
    register_adapter(_HAIKU, haiku)

    result = await dispatch_tool_call(
        messages=_storm_transcript(_REPEAT_INVOCATION_THRESHOLD, {}),
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NO_PROGRESS
    # $0 fail-closed: NO adapter (local OR paid) was invoked.
    assert qwen.invocations == []
    assert haiku.invocations == []
    assert result.cost_usd == 0.0

    rows = await fetchall(
        db_path,
        "SELECT outcome, cost_usd_estimated FROM router_calls WHERE task_type = ?",
        (_TOOL_CALL_TASK_TYPE,),
    )
    assert len(rows) == 1
    assert rows[0][0] == "failed"
    assert rows[0][1] == 0.0


async def test_below_threshold_repeat_dispatches_normally(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A legitimate repeat BELOW threshold is not a storm — it dispatches to the
    adapter as usual (the guard must not break normal repeat calls)."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    result = await dispatch_tool_call(
        messages=_storm_transcript(_REPEAT_INVOCATION_THRESHOLD - 1, {}),
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(qwen.invocations) == 1


async def test_distinct_calls_never_trip_guard(
    tmp_path: Path, _clean_state: Any
) -> None:
    """A transcript of DISTINCT find_emails calls (different args) — well past
    the threshold in count — is NOT a storm and dispatches normally."""
    db_path = _setup(tmp_path)
    qwen = _RecordingAdapter(_QWEN)
    register_adapter(_QWEN, qwen)

    messages: list[dict[str, Any]] = [{"role": "user", "content": "search around"}]
    for i in range(_REPEAT_INVOCATION_THRESHOLD + 3):
        messages.append(_assistant_find_emails_call(f"c{i}", {"query": f"term-{i}"}))
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "{\"ok\": true}"})

    result = await dispatch_tool_call(
        messages=messages,
        tools=_tools(),
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is True
    assert len(qwen.invocations) == 1


async def test_storm_short_circuits_on_paid_model_too(
    tmp_path: Path, _clean_state: Any
) -> None:
    """The guard is model-agnostic: an is_force_override storm on a PAID model
    also fails closed (a runaway is a runaway). No adapter is invoked, so even
    the paid turn spends $0."""
    db_path = _setup(tmp_path)
    haiku = _RecordingAdapter(_HAIKU)
    register_adapter(_HAIKU, haiku)

    result = await dispatch_tool_call(
        messages=_storm_transcript(_REPEAT_INVOCATION_THRESHOLD + 10, {}),
        tools=_tools(),
        model=_HAIKU,
        is_force_override=True,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NO_PROGRESS
    assert haiku.invocations == []
