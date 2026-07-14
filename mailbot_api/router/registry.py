"""ModelAdapter registry per Story 2-4 AC-1.

Process-wide singleton dict mapping model_id → ModelAdapter instance. The
FastAPI lifespan calls ``init_default_adapters()`` after policy load so the
Ollama adapter is registered before any ``ask_router`` call. Story 2-6 will
add Anthropic adapter registration to the same hook.

Test isolation: ``_reset_registry_for_test()`` clears the dict (mirrors the
pattern from Story 2-2's policy snapshot helper).
"""

from __future__ import annotations

import logging
import math

from mailbot_api.config import get_secret_optional
from mailbot_api.router.models import AnthropicAdapter, ModelAdapter, OllamaAdapter

_log = logging.getLogger(__name__)

_ADAPTER_REGISTRY: dict[str, ModelAdapter] = {}


def _parse_keep_alive(raw: str) -> int | str:
    """Parse an OLLAMA_KEEP_ALIVE env value to ollama's keep_alive form.

    Ollama accepts keep_alive as an int in seconds (-1 = never evict, 0 = evict
    immediately) OR a Go-duration string ("30m", "5m"). An integer-like value
    (e.g. "-1", "300") is returned as an int so the never-evict sentinel matches
    ollama's expectation; anything else (a duration string) passes through
    verbatim. Story 10-6-4.

    Robustness (Story 10-6-4 CR F3/F4): a whitespace-only value falls back to
    the never-evict default (-1) rather than forwarding an empty string ollama
    would reject; and an eviction-ENABLING int value (0 = evict immediately, or
    any non-negative int that is not a never-evict sentinel) is honored but
    WARN-logged, because OLLAMA_KEEP_ALIVE=0 silently re-introduces the exact
    cold-cache latency bug this story fixes.
    """
    stripped = raw.strip()
    if not stripped:
        # Whitespace-only (get_secret_optional only falls back on empty "") —
        # treat as unset → never-evict default rather than an invalid "".
        return -1
    try:
        value = int(stripped)
    except ValueError:
        # A Go-duration string ("30m") — pass through verbatim.
        return stripped
    if value == 0:
        _log.warning(
            "OLLAMA_KEEP_ALIVE=0 evicts the model immediately after each call, "
            "re-introducing the cold-cache latency this story fixes; "
            "use -1 (never evict) or a duration like '30m'",
            extra={"event": "adapters.ollama.keep_alive.eviction_enabled"},
        )
    return value


def _parse_ollama_timeout(raw: str, *, default: float = 120.0) -> float:
    """Parse OLLAMA_TIMEOUT_SECONDS to a positive, finite float (Story 10-6-4 CR F2/F3).

    A malformed value (non-numeric, whitespace-only, non-positive, or non-finite
    like NaN/inf) falls back to ``default`` with a WARN log naming the env var,
    rather than crashing adapter registration with an uncaught ValueError or
    forwarding a nonsensical timeout (immediate-timeout / unbounded wait) to
    ``asyncio.wait_for``.
    """
    stripped = raw.strip()
    try:
        value = float(stripped)
    except ValueError:
        _log.warning(
            "OLLAMA_TIMEOUT_SECONDS=%r is not a number; falling back to %.1fs",
            raw,
            default,
            extra={"event": "adapters.ollama.timeout.invalid"},
        )
        return default
    if not math.isfinite(value) or value <= 0.0:
        _log.warning(
            "OLLAMA_TIMEOUT_SECONDS=%r is not a positive finite number; "
            "falling back to %.1fs",
            raw,
            default,
            extra={"event": "adapters.ollama.timeout.invalid"},
        )
        return default
    return value


def register_adapter(model_id: str, adapter: ModelAdapter) -> None:
    """Idempotent register — re-registering the same model_id replaces the adapter."""
    _ADAPTER_REGISTRY[model_id] = adapter


def get_adapter(model_id: str) -> ModelAdapter:
    """Return the registered adapter for ``model_id``; raise KeyError if absent."""
    try:
        return _ADAPTER_REGISTRY[model_id]
    except KeyError as exc:
        raise KeyError(f"no adapter registered for model_id={model_id!r}") from exc


def init_default_adapters() -> None:
    """Register the default set of adapters from env-driven config.

    Story 2-4: registers the Ollama adapter for ``qwen2.5:3b-instruct-q4_K_M``.
    Story 2-6: registers the two Anthropic adapters when ``ANTHROPIC_API_KEY``
    is set. Missing key is non-fatal — Ollama-only environments (dev hosts
    without an Anthropic key) still boot cleanly; haiku/opus dispatch surfaces
    as ``KeyError`` → ``RouterError(code=PROVIDER_ERROR, ...)`` per Story 2-4.
    """
    ollama_url = get_secret_optional("OLLAMA_URL", "http://localhost:11434")
    # Story 10-6-4 (F-10-6-1-W1): keep qwen resident + tolerate the one cold
    # first-call. Both env-configurable, Ollama sites only (the Anthropic
    # timeout stays 60s below — AC-2).
    ollama_keep_alive = _parse_keep_alive(get_secret_optional("OLLAMA_KEEP_ALIVE", "-1"))
    ollama_timeout = _parse_ollama_timeout(
        get_secret_optional("OLLAMA_TIMEOUT_SECONDS", "120.0")
    )
    register_adapter(
        "qwen2.5:3b-instruct-q4_K_M",
        OllamaAdapter(
            model_id="qwen2.5:3b-instruct-q4_K_M",
            base_url=ollama_url,
            timeout_seconds=ollama_timeout,
            keep_alive=ollama_keep_alive,
        ),
    )

    # Story 4-0 Finding 6: nomic-embed-text was missing from the default
    # registration. Story 3-4's dispatch_embedding looks it up by model_id and
    # crashed with KeyError on first real ingest pipeline run.
    # Story 10-6-4: nomic gets keep_alive so `embed()` pins it resident (the
    # ingest pipeline calls embed once per email — residency avoids a per-email
    # cold model-load). NOTE (CR F1): `embed()` uses the dedicated
    # _EMBEDDING_TIMEOUT_SECONDS (15s), NOT this timeout_seconds — the chat
    # budget is passed for constructor uniformity but the embed path does not
    # read it. keep_alive IS honored by embed(); the timeout is not.
    register_adapter(
        "nomic-embed-text",
        OllamaAdapter(
            model_id="nomic-embed-text",
            base_url=ollama_url,
            timeout_seconds=ollama_timeout,
            keep_alive=ollama_keep_alive,
        ),
    )

    anthropic_key = get_secret_optional("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        _log.warning(
            "ANTHROPIC_API_KEY not set — Anthropic adapters not registered; "
            "Router will route haiku/opus dispatches to PROVIDER_ERROR",
            extra={"event": "adapters.anthropic.skipped"},
        )
        return

    for model_id in ("claude-haiku-4-5-20251001", "claude-opus-4-7"):
        register_adapter(
            model_id,
            AnthropicAdapter(
                model_id=model_id,
                api_key=anthropic_key,
                timeout_seconds=60.0,
            ),
        )


def _reset_registry_for_test() -> None:
    """Test-only helper — clear the registry between tests. Do NOT call from production."""
    _ADAPTER_REGISTRY.clear()


# Story 2-4 review fix LOW: `_reset_registry_for_test` is intentionally NOT
# in __all__ — test-only helpers should not show up under `from registry
# import *` or IDE auto-complete for production callers.
__all__ = [
    "get_adapter",
    "init_default_adapters",
    "register_adapter",
]
