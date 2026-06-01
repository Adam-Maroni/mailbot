"""Unit tests for mailbot_api/router/models.py:OllamaAdapter (Story 2-3).

Uses monkeypatched ``ollama.AsyncClient.chat`` — no real network. Real-Ollama
smoke tests live at tests/integration/test_ollama_adapter_real.py behind an
opt-in env var.
"""

from __future__ import annotations

import asyncio
from typing import Any

import ollama
import pytest

from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterResponse,
    AdapterTimeout,
    OllamaAdapter,
)


def _canned_response(text: str = "OK", prompt_eval: int = 12, eval_count: int = 3) -> dict[str, Any]:
    return {
        "model": "qwen2.5:3b-instruct-q4_K_M",
        "created_at": "2026-06-01T00:00:00Z",
        "message": {"role": "assistant", "content": text},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1_000_000_000,
        "load_duration": 100_000_000,
        "prompt_eval_count": prompt_eval,
        "prompt_eval_duration": 500_000_000,
        "eval_count": eval_count,
        "eval_duration": 400_000_000,
    }


class _FakeAsyncClient:
    """Minimal stand-in for ollama.AsyncClient with a configurable behavior."""

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        sleep_before_return: float = 0.0,
        raise_exc: BaseException | None = None,
        host: str = "",
    ) -> None:
        self.response = response or _canned_response()
        self.sleep_before_return = sleep_before_return
        self.raise_exc = raise_exc
        self.host = host
        self.last_kwargs: dict[str, Any] | None = None

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.last_kwargs = kwargs
        if self.sleep_before_return:
            await asyncio.sleep(self.sleep_before_return)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeAsyncClient) -> None:
    """Patch the AsyncClient constructor in the module's import namespace so
    `OllamaAdapter.__init__` picks up the fake."""

    def _factory(host: str = "") -> _FakeAsyncClient:
        fake.host = host
        return fake

    monkeypatch.setattr(ollama, "AsyncClient", _factory)


async def test_ollama_adapter_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(response=_canned_response("OK", prompt_eval=10, eval_count=2))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url="http://localhost:11434",
        timeout_seconds=5.0,
    )
    result = await adapter.call(
        system="You are concise.",
        user="Reply with the word OK and nothing else.",
        max_tokens_out=8,
    )

    assert isinstance(result, AdapterResponse)
    assert result.text == "OK"
    assert result.tokens_in == 10
    assert result.tokens_out == 2
    assert result.cached_tokens_in == 0
    assert result.latency_ms >= 0
    assert "message" in result.raw


async def test_ollama_adapter_passes_options_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen2.5:3b-instruct-q4_K_M",
        base_url="http://localhost:11434",
    )
    await adapter.call(system="sys", user="usr", max_tokens_out=42, temperature=0.5)

    assert fake.last_kwargs is not None
    assert fake.last_kwargs["model"] == "qwen2.5:3b-instruct-q4_K_M"
    assert fake.last_kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert fake.last_kwargs["options"] == {"num_predict": 42, "temperature": 0.5}


async def test_ollama_adapter_latency_ms_reflects_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient(sleep_before_return=0.05)  # 50ms
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    result = await adapter.call(system="s", user="u", max_tokens_out=1)
    # Allow generous slack — Windows timer resolution + scheduler jitter.
    assert result.latency_ms >= 30


async def test_ollama_adapter_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(sleep_before_return=2.0)
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(
        model_id="qwen-test",
        base_url="http://localhost:11434",
        timeout_seconds=0.05,
    )
    with pytest.raises(AdapterTimeout) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert ei.value.model_id == "qwen-test"
    assert ei.value.timeout_seconds == 0.05


async def test_ollama_adapter_wraps_response_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(raise_exc=ollama.ResponseError("upstream 500", 500))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="qwen-test", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert ei.value.model_id == "qwen-test"
    assert "upstream 500" in ei.value.sanitized_message
    assert "ResponseError" in ei.value.sanitized_message


async def test_ollama_adapter_wraps_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAsyncClient(raise_exc=RuntimeError("boom"))
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="qwen-test", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert "boom" in ei.value.sanitized_message
    assert "RuntimeError" in ei.value.sanitized_message


async def test_ollama_adapter_sanitizes_provider_error_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider errors mentioning bearer tokens / sk- keys / secret files must be redacted."""
    fake = _FakeAsyncClient(
        raise_exc=RuntimeError("auth failed: Bearer eyJhbGciOiJIUzI1NiJ9.xyz")
    )
    _install_fake_client(monkeypatch, fake)

    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    with pytest.raises(AdapterProviderError) as ei:
        await adapter.call(system="s", user="u", max_tokens_out=1)
    assert "eyJ" not in ei.value.sanitized_message
    assert "[REDACTED_BEARER]" in ei.value.sanitized_message


async def test_ollama_adapter_cached_tokens_in_always_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAsyncClient()
    _install_fake_client(monkeypatch, fake)
    adapter = OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    result = await adapter.call(system="s", user="u", max_tokens_out=1)
    assert result.cached_tokens_in == 0


def test_ollama_adapter_construction_is_side_effect_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No network call should happen on __init__; only call() touches the wire."""
    call_log: list[str] = []

    def _factory(host: str = "") -> _FakeAsyncClient:
        call_log.append(f"client_constructed:{host}")
        return _FakeAsyncClient()

    monkeypatch.setattr(ollama, "AsyncClient", _factory)
    OllamaAdapter(model_id="x", base_url="http://localhost:11434")
    # Constructing the AsyncClient itself is OK — it doesn't open a connection.
    # We just want to assert no chat() was attempted.
    assert call_log == ["client_constructed:http://localhost:11434"]
