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

from mailbot_api.config import get_secret_optional
from mailbot_api.router.models import AnthropicAdapter, ModelAdapter, OllamaAdapter

_log = logging.getLogger(__name__)

_ADAPTER_REGISTRY: dict[str, ModelAdapter] = {}


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
    register_adapter(
        "qwen2.5:3b-instruct-q4_K_M",
        OllamaAdapter(
            model_id="qwen2.5:3b-instruct-q4_K_M",
            base_url=ollama_url,
            timeout_seconds=30.0,
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
