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
import json
import time
from typing import Any, Literal, Protocol

import anthropic
import ollama
from pydantic import BaseModel, ConfigDict

from mailbot_api.router.errors import (
    ChatCompletionToolChoice,
    ChatCompletionToolChoiceObject,
    ChatCompletionToolDef,
    OpenAIToolCall,
    OpenAIToolCallFunction,
    sanitize_error,
)


class AdapterResponse(BaseModel):
    """Normalized shape returned by every adapter's ``call`` method."""

    model_config = ConfigDict(extra="forbid")

    text: str
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    latency_ms: int
    raw: dict[str, Any]


class ToolCallAdapterResponse(BaseModel):
    """Story 6-9 (F11 closure) — adapter response for tool-bearing calls.

    Parallels `AdapterResponse` but carries:
      * `text` — optional accompanying assistant text (Anthropic CAN return
        both text + tool_use blocks in one response). Empty string when only
        tool_use blocks are present.
      * `tool_calls` — list of OpenAI-shape tool_calls translated from
        Anthropic's tool_use content blocks. Empty list when the model
        chose to produce text only.
      * `finish_reason` — `"tool_calls"` when any tool_use block present;
        `"length"` when truncated by max_tokens; `"stop"` otherwise.

    Adapters that don't support tool-calling raise `AdapterProviderError`
    with `sanitized_message="tools_unsupported"` rather than returning an
    empty-tool_calls response — silent drop would mask the gap.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    tool_calls: list[OpenAIToolCall]
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    latency_ms: int
    finish_reason: Literal["stop", "tool_calls", "length"]
    raw: dict[str, Any]


class EmbeddingResponse(BaseModel):
    """Normalized shape returned by ``OllamaAdapter.embed`` (Story 3-4).

    Parallels ``AdapterResponse`` but tailored to embeddings:
      * ``vector`` is the raw float list returned by the embedding API.
      * ``dim`` is the embedding dimensionality; ``len(vector) == dim`` is
        invariant-checked at the adapter boundary.
      * No ``text`` / ``tokens_out`` — embedding output is a vector, not a string.
      * No ``cached_tokens_in`` — Ollama's embedding API does not return cache stats.
    """

    model_config = ConfigDict(extra="forbid")

    vector: list[float]
    dim: int
    tokens_in: int
    latency_ms: int
    raw: dict[str, Any]


# Story 3-4: embeddings are faster than chat completions; the spec mandates
# a separate, shorter timeout so a slow embedding call doesn't borrow the
# chat-side 30s budget. Only used by ``OllamaAdapter.embed``.
_EMBEDDING_TIMEOUT_SECONDS: float = 15.0


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

    Story 6-9 (F11 closure): ``call_with_tools`` is the tool-calling sibling.
    Adapters that don't support tool-calling MUST raise
    ``AdapterProviderError(sanitized_message="tools_unsupported")`` rather
    than silently dropping tools — silent drop is how F11 originally hid.
    """

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse: ...

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse: ...


# ---------------------------------------------------------------------------
# Story 6-9 (F11 closure) — OpenAI ↔ Anthropic translation helpers.
#
# Pure functions, no I/O. Tested via unit tests that pass canned shapes
# through the helpers and assert the translated output.
# ---------------------------------------------------------------------------


def _translate_tools_openai_to_anthropic(
    tools: list[ChatCompletionToolDef],
) -> list[dict[str, Any]]:
    """OpenAI `tools=[{"type":"function","function":{...}}]` →
    Anthropic `tools=[{"name","description","input_schema"}]`."""
    return [
        {
            "name": t.function.name,
            "description": t.function.description,
            "input_schema": t.function.parameters or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


_OMIT_TOOL_CHOICE = object()
"""Sentinel returned by `_translate_tool_choice_openai_to_anthropic` to signal
that the caller should OMIT the tool_choice field from the Anthropic request
entirely (vs. passing an explicit `{"type":"auto"}` value). CR-8 (Story 6-9
review): tool_choice is part of Anthropic's cached prefix per Rule M; sending
an explicit value when the caller passed None subtly varies the cache key.
Omitting matches Anthropic's documented default."""


def _translate_tool_choice_openai_to_anthropic(
    tool_choice: ChatCompletionToolChoice | None,
) -> dict[str, Any] | None | object:
    """OpenAI tool_choice → Anthropic tool_choice.

    Return values:
      * dict — explicit Anthropic tool_choice to send
      * None — `"none"` semantics; caller omits both tools and tool_choice
      * `_OMIT_TOOL_CHOICE` — caller omits tool_choice but keeps tools
        (CR-8: caller passed None → Anthropic's documented default is auto;
        omitting matches that default without varying the cached prefix)
    """
    if tool_choice is None:
        return _OMIT_TOOL_CHOICE
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "required":
        return {"type": "any"}
    if tool_choice == "none":
        return None
    if isinstance(tool_choice, ChatCompletionToolChoiceObject):
        return {"type": "tool", "name": tool_choice.function.name}
    # Defensive — Pydantic should have caught any other shape at parse time.
    raise ValueError(f"unrecognized tool_choice: {tool_choice!r}")


def _translate_messages_openai_to_anthropic(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """OpenAI messages history → Anthropic messages.

    Handles three message shapes:
      * `{"role": "user", "content": "..."}` → pass-through
      * `{"role": "assistant", "content": "...", "tool_calls": [...]}`
        → `{"role": "assistant", "content": [<text block?>, <tool_use blocks>]}`
      * `{"role": "tool", "tool_call_id": "...", "content": "..."}`
        → `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}`

    Per §3.4 of 6-9-design-decision.md, tool-result messages travel as
    `user`-role content blocks on the Anthropic side. Adjacent assistant +
    tool messages preserve their relative order.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tool_use_id = msg.get("tool_call_id", "")
            content = msg.get("content", "")
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content,
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            text = msg.get("content")
            if isinstance(text, str) and text:
                blocks.append({"type": "text", "text": text})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    parsed_args = json.loads(fn.get("arguments", "{}"))
                except (TypeError, json.JSONDecodeError):
                    parsed_args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": parsed_args,
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            continue
        # Plain user / assistant text — pass-through.
        out.append(
            {"role": role or "user", "content": msg.get("content", "")}
        )
    return out


def _translate_response_anthropic_to_openai_tool_calls(
    content_blocks: list[dict[str, Any]],
) -> tuple[str, list[OpenAIToolCall]]:
    """Anthropic response content → (joined_text, openai_tool_calls).

    Walks the Anthropic content blocks once, separating `text` blocks
    (joined into one string) from `tool_use` blocks (translated to
    OpenAI's `tool_calls` shape with JSON-stringified arguments).
    """
    text_parts: list[str] = []
    tool_calls: list[OpenAIToolCall] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "tool_use":
            arg_input = block.get("input") or {}
            try:
                args_json = json.dumps(arg_input, separators=(",", ":"))
            except (TypeError, ValueError):
                args_json = "{}"
            tool_calls.append(
                OpenAIToolCall(
                    id=str(block.get("id", "")),
                    type="function",
                    function=OpenAIToolCallFunction(
                        name=str(block.get("name", "")),
                        arguments=args_json,
                    ),
                )
            )
    return "".join(text_parts), tool_calls


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

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        """Story 6-9 (F11 closure) — Ollama tool-call surface.

        Qwen 2.5 doesn't expose OpenAI-shape tool-calling at the inference
        surface we use. Raises a structured error rather than silently
        dropping tools — silent drop is how F11 hid for an entire epic.
        """
        raise AdapterProviderError(
            model_id=self.model_id,
            sanitized_message="tools_unsupported",
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        """Generate an embedding for ``text`` via Ollama's embeddings API (Story 3-4).

        Used by ``mailbot_api/ingest/embedding.py`` (the sole writer of the
        ``emails.embedding`` BLOB column). Uses a separate, shorter timeout
        (``_EMBEDDING_TIMEOUT_SECONDS = 15.0``) than the chat path because
        embeddings are typically much faster than chat completions.

        Defensive contract: ``len(vector) == dim`` is asserted at the adapter
        boundary — a misbehaving Ollama can't corrupt downstream consumers
        with mismatched shapes.
        """
        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.embeddings(model=self.model_id, prompt=text),
                timeout=_EMBEDDING_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise AdapterTimeout(
                model_id=self.model_id,
                timeout_seconds=_EMBEDDING_TIMEOUT_SECONDS,
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

        # Ollama's embeddings response carries the vector under the
        # ``embedding`` key. Convert to plain list of floats for the
        # ``EmbeddingResponse`` wire shape.
        vector_raw = raw_dict.get("embedding") or []
        if not isinstance(vector_raw, list):
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=(
                    f"ollama embeddings response 'embedding' field is not a list; "
                    f"got {type(vector_raw).__name__}"
                ),
            )
        try:
            vector = [float(v) for v in vector_raw]
        except (TypeError, ValueError) as exc:
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message=sanitize_error(exc),
            ) from exc

        dim = len(vector)
        if dim == 0:
            raise AdapterProviderError(
                model_id=self.model_id,
                sanitized_message="ollama embeddings response returned an empty vector",
            )

        # Ollama doesn't return token counts on the embed path; surface 0
        # (callers don't gate on this).
        tokens_in = int(raw_dict.get("prompt_eval_count") or 0)

        return EmbeddingResponse(
            vector=vector,
            dim=dim,
            tokens_in=tokens_in,
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

    async def call_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ChatCompletionToolDef],
        tool_choice: ChatCompletionToolChoice | None = None,
        max_tokens_out: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallAdapterResponse:
        """Story 6-9 (F11 closure) — Anthropic tool-call surface.

        Translates the OpenAI-shape `messages` + `tools` into Anthropic's
        Messages API shape, dispatches with Rule M ephemeral cache on the
        system block, and translates the response content blocks back to
        OpenAI's `tool_calls` shape via the module-level translation
        helpers.

        When `tool_choice="none"`, the tools list is omitted entirely —
        Anthropic has no "force no tools" knob, and the contract matches
        OpenAI's behavior of disabling tool use for that call.
        """
        from anthropic.types import TextBlockParam

        anthropic_messages = _translate_messages_openai_to_anthropic(messages)
        anthropic_tool_choice = _translate_tool_choice_openai_to_anthropic(tool_choice)

        # F14 (Story 6-9 CP-2 walk attempt #4, 2026-06-04): Anthropic rejects
        # `cache_control: ephemeral` on empty text blocks with
        # `"system.0: cache_control cannot be set for empty text blocks"`.
        # When the caller passes no system message (or only whitespace), skip
        # the system block entirely rather than emit an empty cached block.
        system_blocks: list[TextBlockParam] = []
        if system and system.strip():
            system_blocks.append(
                TextBlockParam(
                    type="text",
                    text=system,
                    cache_control={"type": "ephemeral"},
                )
            )

        # Build the request kwargs. tools is omitted entirely when
        # tool_choice == "none" — see docstring + design doc §3.2.
        # F14: system field omitted entirely when no non-empty system text.
        request_kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": max_tokens_out,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_blocks:
            request_kwargs["system"] = system_blocks
        if tool_choice != "none":
            request_kwargs["tools"] = _translate_tools_openai_to_anthropic(tools)
            # CR-8 (Story 6-9 review): include tool_choice only when the
            # caller asked for one. Passing an explicit `{"type":"auto"}`
            # when the caller defaulted to None subtly varies Rule M's
            # cached prefix; omitting hits Anthropic's documented default.
            if (
                anthropic_tool_choice is not None
                and anthropic_tool_choice is not _OMIT_TOOL_CHOICE
            ):
                request_kwargs["tool_choice"] = anthropic_tool_choice

        start_ns = time.monotonic_ns()
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(**request_kwargs),
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

        content_blocks = raw_dict.get("content") or []
        text, tool_calls = _translate_response_anthropic_to_openai_tool_calls(
            content_blocks if isinstance(content_blocks, list) else []
        )

        usage = raw_dict.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)

        # Map Anthropic's stop_reason to OpenAI's finish_reason.
        # Anthropic uses: end_turn, max_tokens, stop_sequence, tool_use.
        # Per §3.3 of design doc: any tool_use block present ⇒ "tool_calls".
        stop_reason = raw_dict.get("stop_reason") or ""
        finish_reason: Literal["stop", "tool_calls", "length"]
        if tool_calls:
            finish_reason = "tool_calls"
        elif stop_reason == "max_tokens":
            finish_reason = "length"
        else:
            finish_reason = "stop"

        return ToolCallAdapterResponse(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens_in=cache_read + cache_creation,
            latency_ms=int(latency_ms),
            finish_reason=finish_reason,
            raw=raw_dict,
        )


__all__ = [
    "AdapterError",
    "AdapterProviderError",
    "AdapterResponse",
    "AdapterTimeout",
    "AnthropicAdapter",
    "EmbeddingResponse",
    "ModelAdapter",
    "OllamaAdapter",
    "ToolCallAdapterResponse",
]
