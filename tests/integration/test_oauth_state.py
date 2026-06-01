"""Integration tests for oauth_state table + token rotation per Story 1-6.

Tests run against:
  - real on-disk SQLite (tmp_path) with the 002_oauth_state migration applied
  - mocked httpx transport (httpx.MockTransport) at the network boundary

NOT mocked: the GraphClient/oauth.py production code path; the db.connection
async wrappers; the migration runner.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.sync.graph_client import GraphAuthError
from mailbot_api.sync.oauth import (
    exchange_and_persist,
    get_access_token,
    load_oauth_state,
    seed_oauth_state_from_env,
)

_BASE_ENV = {
    "OUTLOOK_CLIENT_ID": "test-client",
    "OUTLOOK_CLIENT_SECRET": "test-secret",
    "OUTLOOK_TENANT_ID": "test-tenant",
    "OUTLOOK_REFRESH_TOKEN": "rt-bootstrap",
}


def _set_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)


def _set_creds_public_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Like _set_creds but with OUTLOOK_CLIENT_SECRET unset — simulates the
    public-client (Mobile and desktop apps platform) Entra setup that Story 4-0's
    Phase 3.5 walkthrough exposed."""
    for k, v in _BASE_ENV.items():
        if k == "OUTLOOK_CLIENT_SECRET":
            monkeypatch.delenv(k, raising=False)
            continue
        monkeypatch.setenv(k, v)


def _token_transport(
    rotated_refresh: str = "rt-rotated",
    access_token: str = "at-fresh",
    expires_in: int = 3600,
    status: int = 200,
    error_body: dict | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if status >= 400:
            return httpx.Response(status, json=error_body or {"error": "invalid_grant"})
        return httpx.Response(
            status,
            json={
                "access_token": access_token,
                "refresh_token": rotated_refresh,
                "expires_in": expires_in,
                "token_type": "Bearer",
            },
        )

    return httpx.MockTransport(handler)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def test_oauth_state_table_exists_after_migration(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    row = await fetchone(
        db_path,
        "SELECT name FROM sqlite_master WHERE type='table' AND name='oauth_state'",
        (),
    )
    assert row == ("oauth_state",)


async def test_load_returns_none_when_unseeded(tmp_path: Path) -> None:
    db_path = await _prepare_db(tmp_path)
    state = await load_oauth_state(db_path)
    assert state is None


async def test_seed_inserts_row_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    state = await seed_oauth_state_from_env(db_path)
    assert state.provider == "microsoft_graph"
    assert state.refresh_token == "rt-bootstrap"
    assert state.rotation_count == 0
    assert state.access_token is None  # not exchanged yet
    assert state.access_expires_at is None


async def test_seed_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    first = await seed_oauth_state_from_env(db_path)
    # Change the env value — second call should NOT overwrite.
    monkeypatch.setenv("OUTLOOK_REFRESH_TOKEN", "rt-different")
    second = await seed_oauth_state_from_env(db_path)
    assert first.refresh_token == second.refresh_token == "rt-bootstrap"


async def test_exchange_persists_rotated_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    state = await seed_oauth_state_from_env(db_path)
    transport = _token_transport(rotated_refresh="rt-rotated-1")
    refreshed = await exchange_and_persist(db_path, state=state, transport=transport)
    assert refreshed.refresh_token == "rt-rotated-1"
    assert refreshed.access_token == "at-fresh"
    assert refreshed.access_expires_at is not None
    assert refreshed.last_rotated_at is not None
    assert refreshed.rotation_count == 1


async def test_exchange_when_refresh_unchanged_does_not_bump_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the identity endpoint returns the SAME refresh_token (not rotated),
    `rotation_count` stays put."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    state = await seed_oauth_state_from_env(db_path)
    transport = _token_transport(rotated_refresh="rt-bootstrap")  # same as seed
    refreshed = await exchange_and_persist(db_path, state=state, transport=transport)
    assert refreshed.refresh_token == "rt-bootstrap"
    assert refreshed.rotation_count == 0


async def test_invalid_grant_raises_graph_auth_error_and_does_not_change_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    state = await seed_oauth_state_from_env(db_path)
    transport = _token_transport(status=400, error_body={"error": "invalid_grant"})
    with pytest.raises(GraphAuthError) as excinfo:
        await exchange_and_persist(db_path, state=state, transport=transport)
    assert excinfo.value.code == "invalid_grant"

    # State unchanged in DB.
    persisted = await load_oauth_state(db_path)
    assert persisted is not None
    assert persisted.refresh_token == "rt-bootstrap"
    assert persisted.access_token is None
    assert persisted.rotation_count == 0


async def test_get_access_token_seeds_then_exchanges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First call after deploy: seed + exchange + return access token."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    transport = _token_transport(access_token="at-first-call")
    token = await get_access_token(db_path, transport=transport)
    assert token == "at-first-call"
    state = await load_oauth_state(db_path)
    assert state is not None
    assert state.access_token == "at-first-call"
    assert state.rotation_count == 1  # bootstrap rt → rotated rt


async def test_get_access_token_caches_valid_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second call: reuse the persisted access_token without hitting the network."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "access_token": "at-cached",
                "refresh_token": "rt-rotated",
                "expires_in": 3600,
            },
        )

    transport = httpx.MockTransport(handler)
    t1 = await get_access_token(db_path, transport=transport)
    t2 = await get_access_token(db_path, transport=transport)
    assert t1 == t2 == "at-cached"
    assert call_count == 1  # token exchange only happened once


# --------------------------------------------------------------------------- #
# Public-client (no OUTLOOK_CLIENT_SECRET) path — Story 4-0 Phase 3.5 finding.
# --------------------------------------------------------------------------- #


async def test_public_client_exchange_omits_client_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When OUTLOOK_CLIENT_SECRET is unset, the refresh-token exchange form body
    MUST omit the key. Real Entra returns AADSTS90023 for public clients sending
    a secret, so the production code path must respect the env-var absence."""
    import urllib.parse

    db_path = await _prepare_db(tmp_path)
    _set_creds_public_client(monkeypatch)
    state = await seed_oauth_state_from_env(db_path)

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(urllib.parse.parse_qsl(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "access_token": "at-pub",
                "refresh_token": "rt-pub-rotated",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    await exchange_and_persist(db_path, state=state, transport=transport)

    assert len(captured) == 1
    form = captured[0]
    assert "client_secret" not in form, (
        "Public-client refresh-token exchange must omit client_secret entirely; "
        "Entra returns AADSTS90023 if it's present (even empty-string)."
    )
    assert form["grant_type"] == "refresh_token"
    assert form["client_id"] == "test-client"
    assert form["refresh_token"] == "rt-bootstrap"
