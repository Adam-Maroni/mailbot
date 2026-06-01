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
