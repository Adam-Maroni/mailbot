"""Story 11.5.4 (GitHub #4) — per-call cost refusal must emit a structured log.

The per-call refusal guard was the ONE budget guard that refused SILENTLY: it
built a `PER_CALL_THRESHOLD_EXCEEDED` RouterResult/ToolCallResult and returned
with no `_logger` call, so an on-call operator had nothing to grep when it fired
on real traffic. These tests pin the `budget.per_call.refused` structured line
at BOTH refusal sites (ask_router L1029, dispatch_tool_call L2720), matching the
existing `budget.*` JsonFormatter convention.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router, dispatch_tool_call
from mailbot_api.router.budget import (
    PER_CALL_REFUSAL_THRESHOLD_USD,
    _reset_guard_for_test,
)
from mailbot_api.router.errors import ChatCompletionToolDef, ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_LOGGER_NAME = "mailbot_api.router.router"
_REFUSAL_EVENT = "budget.per_call.refused"
_OPUS = "claude-opus-4-7"


class _FakeAdapter:
    def __init__(self, responses: list[AdapterResponse] | None = None) -> None:
        self.responses = responses or []

    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        if not self.responses:
            raise RuntimeError("FakeAdapter ran out of scripted responses")
        return self.responses.pop(0)


def _adapter_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=42,
        raw={"mock": True},
    )


def _content() -> dict[str, Any]:
    return {"subject": "hi", "sender": "a@b.co", "body_preview": "x"}


def _task_entry(model: str, max_tokens_out: int) -> dict[str, Any]:
    return {
        "model": model,
        "prompt_version": "v1",
        "escalate": False,
        "max_tokens_out": max_tokens_out,
        "lane": "batch",
        "sensitivity": "any",
        "response_cache_ttl_seconds": 0,
    }


def _write_policy(tmp_path: Path, *, model: str, max_tokens_out: int) -> str:
    db_path = str(tmp_path / "pcr.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    # dispatch_tool_call uses `hermes_aux` as its policy lane proxy, so define it
    # too (alongside coarse_class used by the ask_router tests).
    policy_yaml.write_text(
        yaml.safe_dump(
            {
                "version": "pcr-v1",
                "tasks": {
                    "coarse_class": _task_entry(model, max_tokens_out),
                    "hermes_aux": _task_entry(model, max_tokens_out),
                },
            }
        ),
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


@pytest.fixture
def _clean() -> Any:
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _refusal_records(caplog: pytest.LogCaptureFixture) -> list[Any]:
    return [
        r for r in caplog.records if getattr(r, "event", None) == _REFUSAL_EVENT
    ]


async def test_ask_router_per_call_refusal_emits_log(
    tmp_path: Path, _clean: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-1/AC-3: ask_router's per-call cost refusal emits budget.per_call.refused
    with model + estimated_cost_usd + threshold_usd fields."""
    db_path = _write_policy(tmp_path, model=_OPUS, max_tokens_out=100_000)
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = await ask_router("coarse_class", _content(), db_path=db_path)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PER_CALL_THRESHOLD_EXCEEDED

    recs = _refusal_records(caplog)
    assert len(recs) == 1, "expected exactly one budget.per_call.refused line"
    rec = recs[0]
    assert rec.levelno == logging.WARNING
    assert getattr(rec, "model", None) == _OPUS
    assert getattr(rec, "estimated_cost_usd", None) is not None
    assert getattr(rec, "estimated_cost_usd") > PER_CALL_REFUSAL_THRESHOLD_USD
    assert getattr(rec, "threshold_usd", None) == pytest.approx(
        PER_CALL_REFUSAL_THRESHOLD_USD
    )


async def test_ask_router_per_call_refusal_forced_does_not_log(
    tmp_path: Path, _clean: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-6: force=True bypasses the gate → no refusal, so NO refusal-log fires."""
    db_path = _write_policy(tmp_path, model=_OPUS, max_tokens_out=100_000)
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = await ask_router(
            "coarse_class", _content(), db_path=db_path, force=True
        )

    assert result.ok is True
    assert _refusal_records(caplog) == []


async def test_dispatch_tool_call_per_call_refusal_emits_log(
    tmp_path: Path, _clean: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-2/AC-3: dispatch_tool_call's per-call cost refusal emits the same
    budget.per_call.refused line. An oversized tool description trips the gate
    (mirrors test_chat_completions_per_call_threshold_blocks_oversized_tools)."""
    # dispatch_tool_call still calls snapshot_for_dispatch() → a policy snapshot
    # must be loaded even though the tool-call path picks its model from the
    # `model=` arg (policy-not-loaded refuses with PROVIDER_ERROR before the gate).
    db_path = _write_policy(tmp_path, model=_OPUS, max_tokens_out=1024)
    register_adapter(_OPUS, _FakeAdapter([_adapter_response()]))

    oversized = "x" * 10_000_000  # 10MB description → estimated cost > $0.20
    tools = [
        ChatCompletionToolDef.model_validate(
            {
                "type": "function",
                "function": {
                    "name": "huge_tool",
                    "description": oversized,
                    "parameters": {"type": "object"},
                },
            }
        )
    ]

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = await dispatch_tool_call(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            model=_OPUS,
            db_path=db_path,
        )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PER_CALL_THRESHOLD_EXCEEDED

    recs = _refusal_records(caplog)
    assert len(recs) == 1, "expected exactly one budget.per_call.refused line"
    assert getattr(recs[0], "model", None) == _OPUS
    assert getattr(recs[0], "threshold_usd", None) == pytest.approx(
        PER_CALL_REFUSAL_THRESHOLD_USD
    )
