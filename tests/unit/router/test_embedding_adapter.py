"""Story 3-4 AC-1: OllamaAdapter.embed unit tests.

Uses a monkeypatched ollama.AsyncClient embeddings method — no real Ollama needed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mailbot_api.router.models import (
    AdapterProviderError,
    AdapterTimeout,
    EmbeddingResponse,
    OllamaAdapter,
)


class _FakeOllamaClient:
    def __init__(self, response: dict[str, Any] | BaseException | None = None) -> None:
        self._response = response
        self.call_log: list[dict[str, Any]] = []

    async def embeddings(
        self, *, model: str, prompt: str, keep_alive: int | str | None = None
    ) -> dict[str, Any]:
        self.call_log.append(
            {"model": model, "prompt": prompt, "keep_alive": keep_alive}
        )
        if isinstance(self._response, BaseException):
            raise self._response
        if self._response is None:
            raise RuntimeError("FakeOllamaClient has no scripted response")
        return self._response


async def test_embed_happy_path_returns_embedding_response() -> None:
    """AC-1 happy path: embed() returns EmbeddingResponse with vector + dim."""
    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _FakeOllamaClient(
        {"embedding": [0.1, 0.2, 0.3, 0.4], "prompt_eval_count": 7}
    )

    result = await adapter.embed("hello world")

    assert isinstance(result, EmbeddingResponse)
    assert result.vector == [0.1, 0.2, 0.3, 0.4]
    assert result.dim == 4
    assert result.tokens_in == 7
    assert result.latency_ms >= 0
    assert result.raw["embedding"] == [0.1, 0.2, 0.3, 0.4]


async def test_embed_passes_keep_alive_to_embeddings_call() -> None:
    """Story 10-6-4 (CR F1): embed() must forward the instance keep_alive to the
    Ollama embeddings call — otherwise the nomic keep_alive wired at registration
    is dead config. The ingest pipeline calls embed once per email, so pinning
    nomic resident (keep_alive=-1) avoids a per-email cold model-load."""
    fake = _FakeOllamaClient({"embedding": [0.1, 0.2], "prompt_eval_count": 3})
    adapter = OllamaAdapter(
        model_id="nomic-embed-text", base_url="http://x:1", keep_alive=-1
    )
    adapter._client = fake

    await adapter.embed("hello")
    assert fake.call_log[-1]["keep_alive"] == -1

    # An explicit duration string forwards verbatim too.
    fake2 = _FakeOllamaClient({"embedding": [0.3], "prompt_eval_count": 1})
    adapter2 = OllamaAdapter(
        model_id="nomic-embed-text", base_url="http://x:1", keep_alive="30m"
    )
    adapter2._client = fake2
    await adapter2.embed("hi")
    assert fake2.call_log[-1]["keep_alive"] == "30m"


async def test_embed_timeout_raises_adapter_timeout(monkeypatch) -> None:
    """AC-1: a timeout on the embeddings call raises AdapterTimeout with the
    Story 3-4 embedding-specific timeout (15s)."""
    # Patch the embedding-specific timeout to a tiny value for the test.
    monkeypatch.setattr(
        "mailbot_api.router.models._EMBEDDING_TIMEOUT_SECONDS", 0.05
    )

    class _SlowClient:
        async def embeddings(
            self, *, model: str, prompt: str, keep_alive: int | str | None = None
        ) -> dict[str, Any]:
            await asyncio.sleep(60)
            return {}

    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _SlowClient()

    with pytest.raises(AdapterTimeout) as exc_info:
        await adapter.embed("hello")
    assert exc_info.value.model_id == "nomic-embed-text"
    assert exc_info.value.timeout_seconds == 0.05


async def test_embed_provider_error_raises_adapter_provider_error() -> None:
    """AC-1: arbitrary upstream exceptions translate to AdapterProviderError."""
    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _FakeOllamaClient(RuntimeError("ollama exploded"))

    with pytest.raises(AdapterProviderError) as exc_info:
        await adapter.embed("hello")
    assert exc_info.value.model_id == "nomic-embed-text"
    # The sanitized message preserves the type name for debuggability.
    assert "RuntimeError" in exc_info.value.sanitized_message
    assert "ollama exploded" in exc_info.value.sanitized_message


async def test_embed_rejects_non_list_embedding_field() -> None:
    """AC-1 defensive: ollama returning non-list 'embedding' field is rejected."""
    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _FakeOllamaClient({"embedding": "not a list", "prompt_eval_count": 0})

    with pytest.raises(AdapterProviderError) as exc_info:
        await adapter.embed("hello")
    assert "not a list" in exc_info.value.sanitized_message


async def test_embed_rejects_empty_embedding() -> None:
    """AC-1 defensive: ollama returning an empty vector is rejected."""
    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _FakeOllamaClient({"embedding": [], "prompt_eval_count": 0})

    with pytest.raises(AdapterProviderError) as exc_info:
        await adapter.embed("hello")
    assert "empty vector" in exc_info.value.sanitized_message


async def test_embed_rejects_non_numeric_values() -> None:
    """AC-1 defensive: ollama returning a list with non-numeric entries is rejected."""
    adapter = OllamaAdapter(model_id="nomic-embed-text", base_url="http://x:1")
    adapter._client = _FakeOllamaClient(
        {"embedding": [0.1, "garbage", 0.3], "prompt_eval_count": 0}
    )

    with pytest.raises(AdapterProviderError):
        await adapter.embed("hello")
