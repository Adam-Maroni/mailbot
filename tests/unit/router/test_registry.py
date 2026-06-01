"""Unit tests for mailbot_api/router/registry.py (Story 2-4 AC-1)."""

from __future__ import annotations

import pytest

from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.registry import (
    _reset_registry_for_test,
    get_adapter,
    register_adapter,
)


class _StubAdapter:
    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        return AdapterResponse(
            text="stub",
            tokens_in=0,
            tokens_out=0,
            cached_tokens_in=0,
            latency_ms=0,
            raw={},
        )


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    yield
    _reset_registry_for_test()


def test_register_then_get_returns_same_instance() -> None:
    stub = _StubAdapter()
    register_adapter("model-x", stub)
    assert get_adapter("model-x") is stub


def test_register_is_idempotent_replace() -> None:
    a = _StubAdapter()
    b = _StubAdapter()
    register_adapter("model-x", a)
    register_adapter("model-x", b)
    assert get_adapter("model-x") is b


def test_get_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="no adapter registered"):
        get_adapter("not-registered")


# --------------------------------------------------------------------------- #
# Story 4-0 Finding 6: init_default_adapters must register nomic-embed-text
# (Story 3-4 dispatch_embedding does a registry lookup on it).
# --------------------------------------------------------------------------- #


def test_init_default_adapters_registers_nomic_embed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without nomic-embed-text in the registry, every ingest pipeline run
    crashes at the embedding step with KeyError. Lock the registration in."""
    from mailbot_api.router.registry import init_default_adapters

    # Ensure no Anthropic registrations interfere with the test.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")

    init_default_adapters()

    # Must not raise — the Ollama-backed nomic adapter is registered alongside Qwen.
    adapter = get_adapter("nomic-embed-text")
    assert adapter is not None
    # Also confirm Qwen still registered (didn't accidentally break it).
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M") is not None
