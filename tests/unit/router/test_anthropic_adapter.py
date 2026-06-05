"""Mocked-transport tests for AnthropicAdapter (Story 2-6).

Uses ``httpx.MockTransport`` injected into an ``anthropic.AsyncClient`` so the
adapter exercises the real SDK surface (request serialization, response
parsing) without a live API key.

Tests assert:
  * Every request carries SYSTEM block with cache_control: ephemeral
  * cold-call → cached_tokens_in=0
  * warm-call → cached_tokens_in>0 (from cache_read_input_tokens)
  * timeout → AdapterTimeout
  * other errors → AdapterProviderError with sanitized message
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import anthropic
import httpx
import pytest

from mailbot_api.router.errors import (
    ChatCompletionFunctionDef,
    ChatCompletionToolDef,
)
from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterResponse,
    AdapterTimeout,
    AnthropicAdapter,
)

_BASE_URL = "https://api.anthropic.com"


def _mock_messages_response(
    *,
    text: str = "Hello",
    input_tokens: int = 50,
    output_tokens: int = 5,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> dict[str, Any]:
    return {
        "id": "msg_01abc",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
        },
    }


def _make_adapter(
    handler: httpx.MockTransport,
    *,
    model_id: str = "claude-haiku-4-5-20251001",
    timeout_seconds: float = 60.0,
) -> tuple[AnthropicAdapter, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def _wrapped_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler.handler(request)

    transport = httpx.MockTransport(_wrapped_handler)
    client = anthropic.AsyncClient(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=transport, base_url=_BASE_URL),
    )
    adapter = AnthropicAdapter(
        model_id=model_id, client=client, timeout_seconds=timeout_seconds
    )
    return adapter, captured


async def test_anthropic_adapter_cold_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response())

    adapter, captured = _make_adapter(httpx.MockTransport(_handler))
    result = await adapter.call(system="sys", user="hi", max_tokens_out=10)

    assert isinstance(result, AdapterResponse)
    assert result.text == "Hello"
    assert result.tokens_in == 50
    assert result.tokens_out == 5
    assert result.cached_tokens_in == 0
    assert result.latency_ms >= 0
    # The request carried the cache_control: ephemeral marker.
    body = json.loads(captured[0].content)
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["system"][0]["text"] == "sys"
    assert body["system"][0]["type"] == "text"


async def test_anthropic_adapter_warm_call_records_cached_tokens() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_mock_messages_response(
                input_tokens=5,  # fresh input small because most was cached
                cache_read=120,
                cache_creation=0,
            ),
        )

    adapter, _ = _make_adapter(httpx.MockTransport(_handler))
    result = await adapter.call(system="sys", user="hi", max_tokens_out=10)
    assert result.cached_tokens_in == 120
    assert result.tokens_in == 5


async def test_anthropic_adapter_cache_creation_path() -> None:
    """First call to a fresh cache key records cache_creation_input_tokens."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_mock_messages_response(
                input_tokens=10,
                cache_read=0,
                cache_creation=100,
            ),
        )

    adapter, _ = _make_adapter(httpx.MockTransport(_handler))
    result = await adapter.call(system="sys", user="hi", max_tokens_out=10)
    # creation tokens count as cached for accounting purposes.
    assert result.cached_tokens_in == 100


async def test_anthropic_adapter_cache_control_on_every_request() -> None:
    """Per Rule M: every call tags SYSTEM with cache_control: ephemeral."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response())

    adapter, captured = _make_adapter(httpx.MockTransport(_handler))
    for _ in range(3):
        await adapter.call(system="sys", user="hi", max_tokens_out=10)

    for req in captured:
        body = json.loads(req.content)
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_anthropic_adapter_timeout() -> None:
    async def _slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2.0)
        return httpx.Response(200, json=_mock_messages_response())

    transport = httpx.MockTransport(_slow_handler)
    client = anthropic.AsyncClient(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=transport, base_url=_BASE_URL),
    )
    adapter = AnthropicAdapter(
        model_id="claude-haiku-4-5-20251001", client=client, timeout_seconds=0.05
    )
    with pytest.raises(AdapterTimeout) as ei:
        await adapter.call(system="sys", user="hi", max_tokens_out=10)
    assert ei.value.model_id == "claude-haiku-4-5-20251001"


async def test_anthropic_adapter_wraps_provider_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"type": "error", "error": {"type": "api_error", "message": "upstream blew up"}},
        )

    adapter, _ = _make_adapter(httpx.MockTransport(_handler))
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="sys", user="hi", max_tokens_out=10)
    assert ei.value.model_id == "claude-haiku-4-5-20251001"


async def test_anthropic_adapter_request_targets_correct_model_id() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response())

    adapter, captured = _make_adapter(
        httpx.MockTransport(_handler), model_id="claude-opus-4-7"
    )
    await adapter.call(system="sys", user="hi", max_tokens_out=10)
    body = json.loads(captured[0].content)
    assert body["model"] == "claude-opus-4-7"


# ----------------------------------------------------------------------------
# F19 regression — Anthropic deprecated `temperature` on claude-opus-4-7
# (reasoning model). Adapter must omit the param when model_id is Opus 4.7
# and keep it on other models (Haiku, etc.). See Story 6-12 + models.py:559.
# ----------------------------------------------------------------------------


async def test_anthropic_adapter_call_omits_temperature_on_opus_4_7() -> None:
    """F19: `AnthropicAdapter.call` must NOT send `temperature` when model is Opus 4.7."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response())

    adapter, captured = _make_adapter(
        httpx.MockTransport(_handler), model_id="claude-opus-4-7"
    )
    await adapter.call(system="sys", user="hi", max_tokens_out=10, temperature=0.7)

    body = json.loads(captured[0].content)
    assert body["model"] == "claude-opus-4-7"
    assert (
        "temperature" not in body
    ), f"F19 regression: temperature leaked into Opus 4.7 request body: {body!r}"


async def test_anthropic_adapter_call_keeps_temperature_on_haiku() -> None:
    """F19 counter-test: `temperature` MUST still be sent on non-Opus models."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response())

    adapter, captured = _make_adapter(
        httpx.MockTransport(_handler), model_id="claude-haiku-4-5-20251001"
    )
    await adapter.call(system="sys", user="hi", max_tokens_out=10, temperature=0.7)

    body = json.loads(captured[0].content)
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert (
        body.get("temperature") == 0.7
    ), f"F19 counter-test: temperature dropped on Haiku request body: {body!r}"


def _trivial_tool() -> ChatCompletionToolDef:
    """Minimal OpenAI tool definition for `call_with_tools` regression tests."""
    return ChatCompletionToolDef(
        type="function",
        function=ChatCompletionFunctionDef(
            name="ping",
            description="No-op tool used in F19 regression tests.",
            parameters={"type": "object", "properties": {}},
        ),
    )


def _mock_messages_response_no_tool_use() -> dict[str, Any]:
    """Mock Anthropic response with stop_reason=end_turn (no tool_use blocks)."""
    return {
        "id": "msg_01tool",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": "no tool needed"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 30,
            "output_tokens": 4,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }


async def test_anthropic_adapter_call_with_tools_omits_temperature_on_opus_4_7() -> None:
    """F19: `AnthropicAdapter.call_with_tools` must NOT send `temperature` on Opus 4.7."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response_no_tool_use())

    adapter, captured = _make_adapter(
        httpx.MockTransport(_handler), model_id="claude-opus-4-7"
    )
    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[_trivial_tool()],
        max_tokens_out=10,
        temperature=0.7,
    )

    body = json.loads(captured[0].content)
    assert body["model"] == "claude-opus-4-7"
    assert (
        "temperature" not in body
    ), f"F19 regression: temperature leaked into Opus 4.7 call_with_tools body: {body!r}"


async def test_anthropic_adapter_call_with_tools_keeps_temperature_on_haiku() -> None:
    """F19 counter-test: `temperature` MUST still be sent on non-Opus models for call_with_tools."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mock_messages_response_no_tool_use())

    adapter, captured = _make_adapter(
        httpx.MockTransport(_handler), model_id="claude-haiku-4-5-20251001"
    )
    await adapter.call_with_tools(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[_trivial_tool()],
        max_tokens_out=10,
        temperature=0.7,
    )

    body = json.loads(captured[0].content)
    assert body["model"] == "claude-haiku-4-5-20251001"
    assert (
        body.get("temperature") == 0.7
    ), f"F19 counter-test: temperature dropped on Haiku call_with_tools body: {body!r}"


# ----------------------------------------------------------------------------
# F19 live smoke — guards against Anthropic reintroducing/relocating the param.
# Default-excluded via `-m 'not live'` in pyproject.toml. Opt in: `pytest -m live`.
# Requires ANTHROPIC_API_KEY in env. Costs ~$0.001 per run.
# ----------------------------------------------------------------------------


@pytest.mark.live
async def test_anthropic_adapter_live_opus_4_7_smoke() -> None:
    """Live: minimal Opus 4.7 messages.create() must return 200 with the F19 gate in place."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set — cannot run live Opus smoke test")

    client = anthropic.AsyncClient(api_key=api_key)
    adapter = AnthropicAdapter(
        model_id="claude-opus-4-7", client=client, timeout_seconds=60.0
    )

    result = await adapter.call(
        system="You are a test harness. Reply with the single word OK.",
        user="ping",
        max_tokens_out=16,
        temperature=0.0,
    )

    assert isinstance(result, AdapterResponse)
    assert result.tokens_in > 0
    assert result.tokens_out > 0
    # We don't assert the exact text — Opus is non-deterministic at low max_tokens.
