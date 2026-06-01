"""Integration tests for /v1/chat/completions endpoint (Story 2-10).

Uses FastAPI TestClient with monkeypatched env so the lifespan boots cleanly
without a live Anthropic API key. The Hermes-aux dispatch is routed through
a registered fake adapter — no real network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import _reset_policy_snapshot_for_test
from mailbot_api.router.registry import (
    _reset_registry_for_test,
    register_adapter,
)


class _FakeAdapter:
    def __init__(self, text: str = "hello back") -> None:
        self.text = text

    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        return AdapterResponse(
            text=self.text,
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=42,
            raw={"mock": True},
        )


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, _FakeAdapter]:
    db_path = str(tmp_path / "x.db")
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    # Story 3-3: lifespan also loads sensitivity_patterns.yaml.
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )
    monkeypatch.setenv("MAILBOT_ROUTER_KEY", "test-router-key-xyz")

    # Pre-register a fake adapter for the model the endpoint will dispatch to.
    fake = _FakeAdapter("hermes says hi")
    # Will be re-registered post-lifespan-init (init_default_adapters wipes nothing).
    register_adapter("claude-haiku-4-5-20251001", fake)
    register_adapter("claude-opus-4-7", fake)

    from mailbot_api.main import app

    return app, fake


def test_chat_completions_401_without_bearer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter("claude-haiku-4-5-20251001", _FakeAdapter("x"))
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert r.status_code == 401
    body = r.json()
    assert body["detail"]["error"]["type"] == "authentication_error"


def test_chat_completions_401_wrong_bearer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter("claude-haiku-4-5-20251001", _FakeAdapter("x"))
        r = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong-key"},
            json={
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert r.status_code == 401
    body = r.json()
    assert body["detail"]["error"]["type"] == "authentication_error"


def test_chat_completions_happy_path_with_caller_origin_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _ = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        # Re-register inside the lifespan (init_default_adapters preserves
        # our pre-registered adapters since they used different model IDs
        # than the lifespan's automatic registration).
        register_adapter("claude-haiku-4-5-20251001", _FakeAdapter("hermes back"))
        r = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-router-key-xyz",
                "X-Mailbot-Caller-Origin": "hermes-aux-compression",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "user", "content": "compress this please"}],
                "max_tokens": 100,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "hermes back"
    assert "usage" in body
    assert body["usage"]["prompt_tokens"] == 10
    assert body["usage"]["completion_tokens"] == 5


def test_chat_completions_records_caller_origin_in_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller_origin from X-Mailbot-Caller-Origin must land in router_calls."""
    from mailbot_api.db.connection import fetchone

    db_path = str(tmp_path / "x.db")
    app, _ = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        register_adapter("claude-haiku-4-5-20251001", _FakeAdapter("x"))
        client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer test-router-key-xyz",
                "X-Mailbot-Caller-Origin": "hermes-aux-title",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "user", "content": "title this"}],
            },
        )

    row = json.loads(
        json.dumps(
            None
        )
    )  # placeholder — we'll re-query below
    # Re-open DB outside the lifespan to verify the row.
    import asyncio as _aio

    async def _check() -> tuple[Any, ...] | None:
        return await fetchone(
            db_path,
            "SELECT caller_origin, task_type FROM router_calls",
            (),
        )

    row = _aio.run(_check())
    assert row is not None
    assert row[0] == "hermes-aux-title"
    assert row[1] == "hermes_aux"


def test_embeddings_endpoint_501_with_valid_bearer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 3-4 ships the real adapter; for now /v1/embeddings is gated 501."""
    app, _ = _bootstrap(tmp_path, monkeypatch)
    with TestClient(app) as client:
        r = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer test-router-key-xyz"},
            json={"input": "hi"},
        )
    assert r.status_code == 501
