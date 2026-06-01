"""Model adapters per Story 2-3 (Ollama) and Story 2-6 (Anthropic, TBD).

Architecture Rule I + F.1: the ONLY file in the project allowed to import
``ollama`` or ``anthropic``. Enforced by ``scripts/check_boundaries.py``.

Public API:
  * ``AdapterResponse`` — normalized Pydantic shape returned by every adapter
  * ``ModelAdapter`` — Protocol that ``OllamaAdapter`` + ``AnthropicAdapter`` satisfy
  * ``AdapterError`` / ``AdapterTimeout`` / ``AdapterProviderError`` — exception hierarchy
  * ``OllamaAdapter`` — concrete adapter for local Ollama serving

Story 2-3 ships only the Ollama leg + the shared shapes. Story 2-4 will dispatch
through these adapters via the ``ModelAdapter`` Protocol. Story 2-6 will add
the Anthropic concrete class.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol

import anthropic
import ollama
from pydantic import BaseModel, ConfigDict

from mailbot_api.router.errors import sanitize_error


class AdapterResponse(BaseModel):
    """Normalized shape returned by every adapter's ``call`` method."""

    model_config = ConfigDict(extra="forbid")

    text: str
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    latency_ms: int
    raw: dict[str, Any]


class AdapterError(Exception):
    """Base class for all adapter-side failures."""


class AdapterTimeout(AdapterError):
    """Raised when the adapter's hard timeout fires (FR-3.4)."""

    def __init__(self, model_id: str, timeout_seconds: float) -> None:
        super().__init__(f"adapter timeout: model_id={model_id} timeout_seconds={timeout_seconds}")
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds


class AdapterProviderError(AdapterError):
    """Raised when any non-timeout exception occurs inside the adapter.

    Any provider-side failure (HTTP error, JSON parse, model-not-found, etc.)
    converges here. ``sanitized_message`` is the already-redacted string ready
    for Router-level error reporting; the raw exception never crosses this boundary.
    """

    def __init__(self, model_id: str, sanitized_message: str) -> None:
        super().__init__(f"adapter provider error: model_id={model_id} message={sanitized_message}")
        self.model_id = model_id
        self.sanitized_message = sanitized_message


class ModelAdapter(Protocol):
    """Structural interface every adapter implements.

    Story 2-4's ``ask_router`` dispatches against this protocol — no runtime
    inheritance required, so Pydantic-bearing adapter classes don't need to
    fight a metaclass with an ABC.
    """

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse: ...


class OllamaAdapter:
    """Concrete adapter for local Ollama serving (Qwen 2.5 3B Q4_K_M).

    Construction is side-effect-free (no network); the first network call
    happens on ``call(...)``. The ``ollama.AsyncClient`` is constructed
    eagerly in ``__init__`` because it carries no network state until the
    first request — making it eager simplifies testability (one place to
    monkeypatch).
    """

    def __init__(
        self,
        model_id: str,
        base_url: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._client = ollama.AsyncClient(host=base_url)

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        options = {"num_predict": max_tokens_out, "temperature": temperature}

        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.chat(
                    model=self.model_id,
                    messages=messages,
                    options=options,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary: convert everything
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        # ollama's response is a ChatResponse model; convert to a plain dict
        # so AdapterResponse.raw doesn't pin the public shape to an external
        # Pydantic class that may change between SDK releases.
        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        message = raw_dict.get("message") or {}
        text = message.get("content", "") if isinstance(message, dict) else ""

        tokens_in = int(raw_dict.get("prompt_eval_count") or 0)
        tokens_out = int(raw_dict.get("eval_count") or 0)

        return AdapterResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=0,
            latency_ms=int(latency_ms),
            raw=raw_dict,
        )


class AnthropicAdapter:
    """Adapter for Claude Haiku 4.5 + Opus 4.7 with Rule M ephemeral cache.

    Per FR-3.6 and architecture Rule M: every call tags the SYSTEM block with
    ``cache_control={"type": "ephemeral"}`` so Anthropic's 5-minute prompt cache
    is a primary cost lever from day one. Cache hits surface in the response's
    ``usage.cache_read_input_tokens`` field and propagate to
    ``AdapterResponse.cached_tokens_in`` for accurate cost accounting.

    The adapter is intentionally constructor-injectable for tests — pass a
    pre-configured ``anthropic.AsyncClient`` with an ``httpx.MockTransport``
    to exercise cold/warm cache scenarios without a live API.
    """

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
        client: anthropic.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        if client is not None:
            self._client = client
        else:
            # Lazy + permits a test environment without a live API key.
            self._client = anthropic.AsyncClient(api_key=api_key or "test-placeholder-key")

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        from anthropic.types import MessageParam, TextBlockParam

        start_ns = time.monotonic_ns()
        # Rule M: SYSTEM block carries cache_control: ephemeral on every call.
        system_blocks: list[TextBlockParam] = [
            TextBlockParam(
                type="text",
                text=system,
                cache_control={"type": "ephemeral"},
            )
        ]
        messages: list[MessageParam] = [
            MessageParam(role="user", content=user),
        ]

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self.model_id,
                    max_tokens=max_tokens_out,
                    temperature=temperature,
                    system=system_blocks,
                    messages=messages,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=self.timeout_seconds,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — adapter boundary
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        latency_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        raw_dict: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )

        # Extract assistant text from content blocks.
        content_blocks = raw_dict.get("content") or []
        text_parts = [
            cb.get("text", "")
            for cb in content_blocks
            if isinstance(cb, dict) and cb.get("type") == "text"
        ]
        text = "".join(text_parts)

        usage = raw_dict.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)

        return AdapterResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cache_read + cache_creation,
            latency_ms=int(latency_ms),
            raw=raw_dict,
        )


__all__ = [
    "AdapterError",
    "AdapterProviderError",
    "AdapterResponse",
    "AdapterTimeout",
    "AnthropicAdapter",
    "ModelAdapter",
    "OllamaAdapter",
]
