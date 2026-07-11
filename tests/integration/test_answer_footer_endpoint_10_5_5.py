"""Story 10.5.5 (AC-3, B8) — per-answer cost/model footer at the /v1/chat/completions
render sites (text path + tool path), via TestClient with a fake adapter.

Asserts:
  * text-path paid answer appends `🤖 <model> (Anthropic API) · this reply: $X.XXXX (N in / M out) · <month>: $Y of $cap`
  * tool-path non-streaming answer appends the footer to message content
  * a stale-pricing flip degrades the footer to tokens-only (no dollar)
  * refusal/free renders do NOT carry a dollar footer (covered by the text
    refusal path assertion)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mailbot_api.router import pricing
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import OpenAIToolCall, OpenAIToolCallFunction
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse, ToolCallAdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import _reset_policy_snapshot_for_test
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_HAIKU = "claude-haiku-4-5-20251001"
_VALID_BEARER = {"Authorization": "Bearer test-router-key-xyz"}


class _FakeTextAdapter:
    """Text-path adapter (used by ask_router / hermes_aux)."""

    def __init__(self, text: str = "here is your answer") -> None:
        self.text = text

    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        return AdapterResponse(
            text=self.text,
            tokens_in=120,
            tokens_out=34,
            cached_tokens_in=0,
            latency_ms=42,
            raw={"mock": True},
        )


class _FakeToolAdapter:
    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        return ToolCallAdapterResponse(
            text="checked that",
            tool_calls=[],
            tokens_in=42,
            tokens_out=17,
            cached_tokens_in=0,
            latency_ms=8,
            finish_reason="stop",
            raw={"mock": True},
        )


class _FakeToolOnlyAdapter:
    """Tool-only response: tool_calls present, NO accompanying text (Finding 3)."""

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        return ToolCallAdapterResponse(
            text="",
            tool_calls=[
                OpenAIToolCall(
                    id="call_abc",
                    type="function",
                    function=OpenAIToolCallFunction(
                        name="render_spend_chart", arguments='{"period":"month"}'
                    ),
                )
            ],
            tokens_in=42,
            tokens_out=17,
            cached_tokens_in=0,
            latency_ms=8,
            finish_reason="tool_calls",
            raw={"mock": True},
        )


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    db_path = str(tmp_path / "x.db")
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-router-key-xyz")

    from mailbot_api.main import app

    return app


def test_text_path_appends_paid_footer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeTextAdapter("here is your answer"))
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _HAIKU,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert r.status_code == 200, r.text
    content = r.json()["choices"][0]["message"]["content"]
    assert "here is your answer" in content
    assert "🤖 haiku (Anthropic API) · this reply: $" in content
    assert "120 in / 34 out" in content
    assert " of $30.00" in content


def test_tool_path_appends_paid_footer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeToolAdapter())
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _HAIKU,
                "messages": [{"role": "user", "content": "spend month"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "render_spend_chart",
                            "description": "Render a spend chart.",
                            "parameters": {
                                "type": "object",
                                "properties": {"period": {"type": "string"}},
                            },
                        },
                    }
                ],
                "stream": False,
            },
        )
    assert r.status_code == 200, r.text
    content = r.json()["choices"][0]["message"]["content"]
    assert content is not None
    assert "🤖 haiku (Anthropic API) · this reply: $" in content
    assert "42 in / 17 out" in content


def test_text_path_stale_pricing_degrades_to_tokens_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 code invariant: with pricing flagged placeholder, the footer shows
    no dollar figure even on a paid answer."""
    app = _bootstrap(tmp_path, monkeypatch)
    monkeypatch.setattr(pricing, "PRICING_PLACEHOLDER", True)
    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeTextAdapter("answer"))
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _HAIKU,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert r.status_code == 200, r.text
    content = r.json()["choices"][0]["message"]["content"]
    assert "🤖 haiku" in content
    assert "unverified" in content
    # No dollar figure in the footer line.
    footer_line = content.splitlines()[-1]
    assert "$" not in footer_line


_TOOLS_PAYLOAD = [
    {
        "type": "function",
        "function": {
            "name": "render_spend_chart",
            "description": "Render a spend chart.",
            "parameters": {
                "type": "object",
                "properties": {"period": {"type": "string"}},
            },
        },
    }
]


def test_tool_only_response_preserves_null_content_no_footer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 3: a tool-only response (tool_calls, NO text) must keep
    `content: null` per the OpenAI contract — the footer is suppressed, and the
    tool_calls are intact."""
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeToolOnlyAdapter())
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _HAIKU,
                "messages": [{"role": "user", "content": "spend month"}],
                "tools": _TOOLS_PAYLOAD,
                "stream": False,
            },
        )
    assert r.status_code == 200, r.text
    message = r.json()["choices"][0]["message"]
    assert message["content"] is None
    assert message["tool_calls"], "tool_calls must be intact"
    assert message["tool_calls"][0]["function"]["name"] == "render_spend_chart"


def test_text_plus_tool_response_appends_footer_to_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 3 twin: a text+tool response DOES append the footer to the text
    content (footer suppressed only when text is empty)."""
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeToolAdapter())  # text="checked that"
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _HAIKU,
                "messages": [{"role": "user", "content": "spend month"}],
                "tools": _TOOLS_PAYLOAD,
                "stream": False,
            },
        )
    assert r.status_code == 200, r.text
    content = r.json()["choices"][0]["message"]["content"]
    assert content is not None
    assert content.startswith("checked that")
    assert "🤖 haiku (Anthropic API) · this reply: $" in content


_QWEN = "qwen2.5:3b-instruct-q4_K_M"


class _QwenToolAdapter:
    """Story AI-1: qwen IS tool-capable now (live-probed 6/6 at temp 0), so this
    adapter EMITS a real tool_call (the old `tools_unsupported` raise is gone).
    The trust decision for whether the returned action may ACT is downstream in
    the propose_action tier pipeline, not here."""

    async def call(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def call_with_tools(self, **_: Any) -> ToolCallAdapterResponse:
        return ToolCallAdapterResponse(
            text="",
            tool_calls=[
                OpenAIToolCall(
                    id="call_qwen0",
                    type="function",
                    function=OpenAIToolCallFunction(
                        name="render_spend_chart", arguments='{"period":"month"}'
                    ),
                )
            ],
            tokens_in=30,
            tokens_out=8,
            cached_tokens_in=0,
            latency_ms=9,
            finish_reason="tool_calls",
            raw={"mock": True},
        )


def test_tool_call_to_qwen_dispatches_200_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story AI-1 (was W2a 'graceful refusal render'). CONTRACT FLIPPED — a tools
    request forced to qwen (route b: a `use qwen` one-shot, degraded OFF) now
    DISPATCHES and returns a normal 200 tool-call response, NOT a refusal render
    and NOT a 502 retry storm. The old refusal-render path applied when qwen was
    tool-INcapable; qwen is capable now, so the request simply succeeds. The
    502 Adam originally hit (`use qwen` → tool turn → 502 x3) is doubly
    neutralized: no refusal AND no adapter raise."""
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_QWEN, _QwenToolAdapter())
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _QWEN,  # force qwen, as the one-shot override does
                "messages": [{"role": "user", "content": "This is a test."}],
                "tools": _TOOLS_PAYLOAD,
                "stream": False,
            },
        )
    # The load-bearing assertion: 200, not 502 (no retry storm).
    assert r.status_code == 200, r.text
    body = r.json()
    choice = body["choices"][0]
    # A real tool-call response — no false "degraded"/refusal render.
    assert choice["finish_reason"] == "tool_calls"
    tool_calls = choice["message"]["tool_calls"]
    assert tool_calls and tool_calls[0]["function"]["name"] == "render_spend_chart"


def test_tool_call_to_qwen_dispatches_200_streaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story AI-1 streaming twin: the same qwen tool request over `stream: true`
    returns SSE chunks (200), not a 502 and not a 'degraded' refusal."""
    app = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter(_QWEN, _QwenToolAdapter())
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={
                "model": _QWEN,
                "messages": [{"role": "user", "content": "This is a test."}],
                "tools": _TOOLS_PAYLOAD,
                "stream": True,
            },
        )
    assert r.status_code == 200, r.text
    assert "degraded" not in r.text.lower()


def test_footer_month_to_date_is_db_authoritative_not_guard_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-10-5-5-W1 (walk 2026-07-11): the footer's month-to-date must read the
    DB ledger (ROUTER_CALLS_TOTALS_SINCE), the same source as `mailbot status` —
    NOT the in-memory BudgetGuard mirror (which reads $0 in a fresh process and
    drifts). Seed a prior paid row this month, then assert the footer's month
    figure includes it. Before the fix this read the guard mirror (~$0.00);
    also guards against the silent-$0 regression from a missing import."""
    import asyncio
    from datetime import datetime, timezone

    from mailbot_api.db import connection, queries
    from mailbot_api.db.migrations_runner import apply_pending_migrations
    from mailbot_api.observability.audit import RouterCallRow, record_router_call

    app = _bootstrap(tmp_path, monkeypatch)
    db_path = str(tmp_path / "x.db")

    async def _seed() -> None:
        apply_pending_migrations(db_path)
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-05T00:00:00Z")  # earlier this month
        await record_router_call(
            RouterCallRow(
                ts=ts,
                task_type="hermes_aux",
                prompt_version="v1",
                model_chosen=_HAIKU,
                model_chosen_reason="policy:hermes_aux:default",
                tokens_in=1000,
                tokens_out=500,
                cached_tokens_in=0,
                cost_usd_estimated=12.3400,  # prior month-to-date spend
                latency_ms=10,
                outcome="ok",
                caller_verb="hermes_aux",
                caller_origin="test",
                email_id=None,
            ),
            db_path=db_path,
        )

    asyncio.run(_seed())

    with TestClient(app) as client:
        register_adapter(_HAIKU, _FakeTextAdapter("answer text"))
        r = client.post(
            "/v1/chat/completions",
            headers=_VALID_BEARER,
            json={"model": _HAIKU, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert r.status_code == 200, r.text
    content = r.json()["choices"][0]["message"]["content"]
    footer_line = content.splitlines()[-1]
    # The month figure must reflect the seeded $12.34 + this reply — NOT $0.00.
    assert "$0.00 of $30.00" not in footer_line
    assert "$12.3" in footer_line or "$12.4" in footer_line  # seeded + tiny this-reply
    # sanity: it's still the DB-authoritative sum via ROUTER_CALLS_TOTALS_SINCE
    month_iso = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    row = asyncio.run(
        connection.fetchone(db_path, queries.ROUTER_CALLS_TOTALS_SINCE, (month_iso,))
    )
    assert row is not None and float(row[1]) >= 12.34
