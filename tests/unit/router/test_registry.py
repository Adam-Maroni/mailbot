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


# --------------------------------------------------------------------------- #
# Story 10-6-4 — env-driven keep_alive (AC-1) + Ollama timeout (AC-2).
#
# F-10-6-1-W1: qwen must stay resident (keep_alive) and tolerate the one cold
# first-call (longer timeout). Both are read at registration; the Anthropic
# timeout must stay 60s (AC-2 explicitly forbids touching it).
# --------------------------------------------------------------------------- #


def test_ollama_adapters_default_keep_alive_never_evict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (no OLLAMA_KEEP_ALIVE) ⇒ both Ollama adapters pin resident (-1)."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")

    init_default_adapters()

    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").keep_alive == -1
    assert get_adapter("nomic-embed-text").keep_alive == -1


def test_ollama_keep_alive_env_minus_one_string_parses_to_int(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OLLAMA_KEEP_ALIVE='-1' ⇒ int -1 (the ollama never-evict form), not '-1'."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "-1")

    init_default_adapters()
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").keep_alive == -1
    assert isinstance(get_adapter("qwen2.5:3b-instruct-q4_K_M").keep_alive, int)


def test_ollama_keep_alive_env_duration_string_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A duration string (e.g. '30m') passes through verbatim to the adapter."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "30m")

    init_default_adapters()
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").keep_alive == "30m"


def test_ollama_timeout_default_120s(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default (no OLLAMA_TIMEOUT_SECONDS) ⇒ 120s on both Ollama adapters —
    tolerance for the one cold first-call ingest (~19s) after a restart."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")

    init_default_adapters()
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").timeout_seconds == 120.0
    assert get_adapter("nomic-embed-text").timeout_seconds == 120.0


def test_ollama_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """OLLAMA_TIMEOUT_SECONDS overrides the default on both Ollama adapters."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45")

    init_default_adapters()
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").timeout_seconds == 45.0


def test_anthropic_timeout_unchanged_at_60s(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: the Ollama timeout knob must NOT bleed into the Anthropic adapters —
    they stay at 60s regardless of OLLAMA_TIMEOUT_SECONDS."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45")

    init_default_adapters()
    assert get_adapter("claude-haiku-4-5-20251001").timeout_seconds == 60.0
    assert get_adapter("claude-opus-4-7").timeout_seconds == 60.0


# --------------------------------------------------------------------------- #
# Story 10-6-4 CR (F2/F3/F4) — robust env parsing helpers.
# --------------------------------------------------------------------------- #


def test_parse_keep_alive_int_and_duration() -> None:
    from mailbot_api.router.registry import _parse_keep_alive

    assert _parse_keep_alive("-1") == -1
    assert isinstance(_parse_keep_alive("-1"), int)
    assert _parse_keep_alive("300") == 300
    assert _parse_keep_alive("30m") == "30m"


def test_parse_keep_alive_whitespace_falls_back_to_never_evict() -> None:
    """CR F3: a whitespace-only value must NOT forward an empty string to
    ollama — fall back to the never-evict default (-1)."""
    from mailbot_api.router.registry import _parse_keep_alive

    assert _parse_keep_alive("   ") == -1
    assert _parse_keep_alive("") == -1


def test_parse_keep_alive_zero_warns_but_honored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CR F4: keep_alive=0 (evict immediately) re-introduces the bug this story
    fixes — it is honored (a legitimate ollama value) but WARN-logged."""
    import logging

    from mailbot_api.router.registry import _parse_keep_alive

    with caplog.at_level(logging.WARNING):
        assert _parse_keep_alive("0") == 0
    assert any("evicts the model immediately" in r.message for r in caplog.records)


def test_parse_ollama_timeout_valid() -> None:
    from mailbot_api.router.registry import _parse_ollama_timeout

    assert _parse_ollama_timeout("45") == 45.0
    assert _parse_ollama_timeout("120.0") == 120.0


@pytest.mark.parametrize("bad", ["abc", "   ", "", "-5", "0", "NaN", "inf", "-inf"])
def test_parse_ollama_timeout_invalid_falls_back(
    bad: str, caplog: pytest.LogCaptureFixture
) -> None:
    """CR F2/F3: a malformed / non-positive / non-finite timeout must fall back
    to the default with a WARN log — NOT crash boot or forward a nonsensical
    timeout (immediate-timeout / unbounded / NaN wait) to asyncio.wait_for."""
    import logging

    from mailbot_api.router.registry import _parse_ollama_timeout

    with caplog.at_level(logging.WARNING):
        result = _parse_ollama_timeout(bad, default=120.0)
    assert result == 120.0
    assert any("OLLAMA_TIMEOUT_SECONDS" in r.message for r in caplog.records)


def test_malformed_timeout_env_does_not_crash_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR F2: a malformed OLLAMA_TIMEOUT_SECONDS env must not crash
    init_default_adapters() — the Ollama adapters register with the default."""
    from mailbot_api.router.registry import init_default_adapters

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "not-a-number")

    init_default_adapters()  # must not raise
    assert get_adapter("qwen2.5:3b-instruct-q4_K_M").timeout_seconds == 120.0
