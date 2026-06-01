"""Integration tests for mailbot-api /health and /v1/health endpoints.

Story 1-2 ships the minimal /health + /v1/health pair.
Story 1-8 enriches the response shape with sync_* fields when a DB is configured.

ASGITransport does NOT trigger lifespan events. For the static-mode (no DB)
tests below, the worker_health table doesn't need to exist; the endpoint code
falls through to `{"ok": True}` because `app.state.db_path` is None.

pytest-asyncio runs in auto mode.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from mailbot_api.main import app


async def test_health_returns_ok_in_static_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reset app.state.db_path that earlier tests may have set.
    if hasattr(app.state, "db_path"):
        delattr(app.state, "db_path")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_v1_health_returns_ok_in_static_mode() -> None:
    if hasattr(app.state, "db_path"):
        delattr(app.state, "db_path")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_health_endpoints_have_same_shape_in_static_mode() -> None:
    if hasattr(app.state, "db_path"):
        delattr(app.state, "db_path")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/health")
        r2 = await client.get("/v1/health")
    assert r1.json() == r2.json()
