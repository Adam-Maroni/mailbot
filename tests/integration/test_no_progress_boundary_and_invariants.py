"""Story 10.7.7 (AC-6) — invariant + boundary coverage for the NO_PROGRESS guard.

  * The router NO_PROGRESS terminal renders as a graceful 200 completion at the
    /v1/chat/completions boundary (NOT a 502 Hermes would retry into a loop).
  * The guard is a loop-TERMINATOR, not an auth bypass: a storm returns a
    terminal refusal carrying NO tool_calls (the model cannot ACT), so the
    sensitivity/grant pipeline is never reached or weakened by the guard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mailbot_api.db.connection import execute_write
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.main import _no_progress_completion
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import (
    ChatCompletionFunctionDef,
    ChatCompletionToolDef,
    ErrorCode,
    RouterError,
    ToolCallResult,
)
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import ToolCallAdapterResponse
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import _reset_policy_snapshot_for_test, load_policy, set_policy_snapshot
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.router.router import _REPEAT_INVOCATION_THRESHOLD, dispatch_tool_call

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU = "claude-haiku-4-5-20251001"
_SECRET_GRAPH_ID = "AAMkAGI2-secret-graph-id-do-not-leak"

_POLICY_YAML = f"""\
version: "test-10-7-7-inv-v1"

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


# ---- pure render unit ---------------------------------------------------------


class _FakeRequest:
    """Minimal stand-in for starlette Request — only id() is used by the render."""


def test_no_progress_completion_renders_calm_message() -> None:
    """The pure render maps a NO_PROGRESS ToolCallResult to a 200-shape body."""
    result = ToolCallResult(
        ok=False,
        error=RouterError(
            code=ErrorCode.NO_PROGRESS,
            message="I keep calling `find_emails` with the same input…",
            retryable=False,
            model_attempted=[_QWEN],
        ),
        model_used=_QWEN,
    )
    body = _no_progress_completion(result, _FakeRequest())  # type: ignore[arg-type]
    assert body is not None
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert "find_emails" in body["choices"][0]["message"]["content"]
    # $0 render — no tokens attributed.
    assert body["usage"]["total_tokens"] == 0


def test_no_progress_completion_ignores_other_errors() -> None:
    """A non-NO_PROGRESS failure falls through (returns None → 502 path)."""
    result = ToolCallResult(
        ok=False,
        error=RouterError(code=ErrorCode.PROVIDER_ERROR, message="boom", retryable=True),
    )
    assert _no_progress_completion(result, _FakeRequest()) is None  # type: ignore[arg-type]


def test_no_progress_completion_ignores_success() -> None:
    """An ok result is never rendered as a refusal."""
    result = ToolCallResult(ok=True, tool_calls=None, model_used=_QWEN)
    assert _no_progress_completion(result, _FakeRequest()) is None  # type: ignore[arg-type]


# ---- full-endpoint boundary render (200, not 502) -----------------------------


def _bootstrap_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    db_path = str(tmp_path / "app.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-router-key-xyz")
    from mailbot_api.main import app

    return app, db_path


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


def _storm_messages(n: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": "find my unread emails"}]
    for i in range(n):
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": f"call-{i}",
                "type": "function",
                "function": {"name": "find_emails", "arguments": json.dumps({})},
            }],
        })
        messages.append({"role": "tool", "tool_call_id": f"call-{i}", "content": "{\"ok\": true}"})
    return messages


def test_chat_boundary_renders_storm_as_200_not_502(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _clean_state: Any
) -> None:
    """AC-6: a runaway find_emails storm returns a graceful 200 (calm message),
    NOT a raw 502 Hermes would retry into another loop. A local adapter is
    registered but must NOT be invoked (the guard fires before dispatch)."""

    class _LocalFake:
        def __init__(self) -> None:
            self.invocations = 0

        async def call(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
            raise NotImplementedError

        async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:  # pragma: no cover
            self.invocations += 1
            return ToolCallAdapterResponse(
                text="should not be reached",
                tool_calls=[],
                tokens_in=1,
                tokens_out=1,
                cached_tokens_in=0,
                latency_ms=1,
                finish_reason="stop",
                raw={},
            )

    app, _db_path = _bootstrap_app(tmp_path, monkeypatch)
    fake = _LocalFake()
    with TestClient(app) as client:
        register_adapter(_QWEN, fake)
        resp = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer test-router-key-xyz"},
            json={
                "model": "hermes_aux",  # default → local lane (qwen)
                "stream": False,
                "messages": _storm_messages(_REPEAT_INVOCATION_THRESHOLD),
                "tools": [t.model_dump() for t in _tools()],
            },
        )

    assert resp.status_code == 200, resp.text
    content = resp.json()["choices"][0]["message"]["content"].lower()
    assert "find_emails" in content or "same" in content
    # $0 fail-closed: the adapter was never reached.
    assert fake.invocations == 0


# ---- AC-6(ii)/(iii): guard is a loop-terminator, NOT an auth bypass ----------


async def _seed_sensitive(db_path: str, *, graph_id: str, sensitivity: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id, "2026-06-02T00:00:00Z", "s", "x@y.com", "b",
            sensitivity, "2026-06-02T00:01:00Z", "v1", 0.9, _QWEN,
        ),
    )


def _proposetool() -> list[ChatCompletionToolDef]:
    return [
        ChatCompletionToolDef(
            type="function",
            function=ChatCompletionFunctionDef(
                name="propose_action",
                description="Propose an action on an email.",
                parameters={"type": "object", "properties": {"email_id": {"type": "string"}}},
            ),
        )
    ]


def _sensitive_storm(graph_id: str, n: int) -> list[dict[str, Any]]:
    """A storm of identical propose_action calls all referencing a sensitive
    email_id (in the tool args, which the sensitivity gate resolves)."""
    args = json.dumps({"email_id": graph_id})
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "act on this email"}]
    for i in range(n):
        msgs.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{i}", "type": "function",
                            "function": {"name": "propose_action", "arguments": args}}],
        })
    return msgs


def _load_policy(tmp_path: Path) -> None:
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))


async def test_sensitive_storm_terminates_without_auth_bypass(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-6(ii): a storm of a SENSITIVE-email tool-call still terminates with
    NO_PROGRESS (a terminal refusal carrying NO tool_calls) — the guard cannot
    be used to slip an action past the sensitivity gate, because it returns an
    error result with no action surface at all."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    _load_policy(tmp_path)
    await _seed_sensitive(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="confidential")

    result = await dispatch_tool_call(
        messages=_sensitive_storm(_SECRET_GRAPH_ID, _REPEAT_INVOCATION_THRESHOLD),
        tools=[t.model_dump() for t in _proposetool()],
        model=_QWEN,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NO_PROGRESS
    # No action surface: the terminal carries no tool_calls, so nothing can act.
    assert result.tool_calls is None
    # The secret id never leaks into the terminal message.
    assert _SECRET_GRAPH_ID not in (result.error.message or "")


async def test_non_storm_sensitive_call_still_hits_sensitivity_gate(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-6(ii)/(iii): a NON-storm sensitive-email tool-call (below threshold)
    is NOT swallowed by the guard — it flows through to the sensitivity gate
    unchanged and is refused with a sensitivity code (the guard did not weaken
    or bypass the existing authorization pipeline)."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    _load_policy(tmp_path)
    await _seed_sensitive(db_path, graph_id=_SECRET_GRAPH_ID, sensitivity="confidential")

    result = await dispatch_tool_call(
        messages=_sensitive_storm(_SECRET_GRAPH_ID, 1),  # single call — no storm
        tools=[t.model_dump() for t in _proposetool()],
        model=_HAIKU,  # API-bound so the confidential API-block gate fires
        is_force_override=True,
        db_path=db_path,
        caller_origin="hermes-chat",
        caller_verb="hermes_aux_tools",
        email_id=_SECRET_GRAPH_ID,
    )

    assert result.ok is False
    assert result.error is not None
    # The sensitivity gate — NOT the storm guard — refused this call.
    assert result.error.code is ErrorCode.SENSITIVITY_BLOCKS_API
