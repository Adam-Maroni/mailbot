"""OAuth refresh-token rotation + persistence per architecture §AR-D9-1/2.

`oauth_state` is the runtime source of truth for the Microsoft Graph refresh
token. `.env` (OUTLOOK_REFRESH_TOKEN) is the **bootstrap seed only** — used on
first run when the table row doesn't exist. After that, rotation events update
the row in place, and `.env` is never re-read for the refresh token.

Why this lives in `sync/` (not `db/queries.py`): the queries.py file is the SQL
boundary; this module composes those queries into the oauth-rotation policy.
For Story 1-6 we accept the simpler pattern of using `db.fetchone` / `db.execute_write`
directly from here; the broader Rule C move (consolidating ALL SQL literals into
queries.py) is a future epic-2 follow-up.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from mailbot_api.config import get_secret
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    OAUTH_STATE_INSERT_SEED,
    OAUTH_STATE_SELECT,
    OAUTH_STATE_UPDATE_AFTER_EXCHANGE,
)
from mailbot_api.sync.graph_client import (
    _DEFAULT_SCOPE,
    _REFRESH_LEEWAY_SECONDS,
    _TOKEN_URL_TEMPLATE,
    GraphAuthError,
)

logger = logging.getLogger(__name__)

_PROVIDER = "microsoft_graph"


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OAuthState:
    """In-memory mirror of an `oauth_state` row."""

    provider: str
    refresh_token: str
    access_token: str | None
    access_expires_at: str | None
    last_rotated_at: str | None
    rotation_count: int

    def access_token_is_valid(self) -> bool:
        """Return True if access_token is present AND not within the refresh leeway."""
        if not self.access_token or not self.access_expires_at:
            return False
        try:
            expiry = datetime.strptime(self.access_expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return False
        # Refresh proactively when we're within _REFRESH_LEEWAY_SECONDS of expiry.
        return expiry.timestamp() >= time.time() + _REFRESH_LEEWAY_SECONDS


async def load_oauth_state(db_path: str) -> OAuthState | None:
    """Return the OAuthState row for microsoft_graph, or None if not yet seeded."""
    row = await fetchone(db_path, OAUTH_STATE_SELECT, (_PROVIDER,))
    if row is None:
        return None
    return OAuthState(
        provider=row[0],
        refresh_token=row[1],
        access_token=row[2],
        access_expires_at=row[3],
        last_rotated_at=row[4],
        rotation_count=row[5],
    )


async def seed_oauth_state_from_env(db_path: str) -> OAuthState:
    """First-run path: read OUTLOOK_REFRESH_TOKEN from env and insert the row.

    Idempotent: if the row already exists, this is a no-op that returns the
    existing state.
    """
    existing = await load_oauth_state(db_path)
    if existing is not None:
        return existing

    refresh_token = get_secret("OUTLOOK_REFRESH_TOKEN")
    await execute_write(db_path, OAUTH_STATE_INSERT_SEED, (_PROVIDER, refresh_token))
    logger.info(
        "oauth_state seeded from env",
        extra={"event": "oauth.state.seeded", "provider": _PROVIDER},
    )
    state = await load_oauth_state(db_path)
    if state is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError("oauth_state insert succeeded but load returned None")
    return state


async def exchange_and_persist(
    db_path: str,
    *,
    state: OAuthState,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 30.0,
) -> OAuthState:
    """Exchange the stored refresh token + persist rotated values to oauth_state.

    Returns the updated OAuthState (in-memory dataclass — re-read from DB after
    the write to ensure parity). Raises GraphAuthError on `invalid_grant` or any
    other non-2xx response.

    `transport` is for test injection (httpx.MockTransport); production callers
    leave it None.
    """
    client_id = get_secret("OUTLOOK_CLIENT_ID")
    client_secret = get_secret("OUTLOOK_CLIENT_SECRET")
    tenant_id = get_secret("OUTLOOK_TENANT_ID")

    token_url = _TOKEN_URL_TEMPLATE.format(tenant=tenant_id)
    form = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": state.refresh_token,
        "scope": _DEFAULT_SCOPE,
    }

    def _build_http() -> httpx.Client:
        if transport is not None:
            return httpx.Client(transport=transport, timeout=httpx.Timeout(timeout_seconds))
        return httpx.Client(timeout=httpx.Timeout(timeout_seconds))

    with _build_http() as http:
        try:
            response = http.post(token_url, data=form)
        except httpx.RequestError as exc:
            logger.error(
                "oauth refresh transport error",
                extra={
                    "event": "oauth.refresh.failed",
                    "error_kind": "transport",
                    "error_type": type(exc).__name__,
                },
            )
            raise GraphAuthError("transport_error", type(exc).__name__) from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        error_code = (
            payload.get("error", "unknown_error") if isinstance(payload, dict) else "unknown_error"
        )
        logger.error(
            "oauth refresh failed",
            extra={
                "event": "oauth.refresh.failed",
                "status_code": response.status_code,
                "error_code": error_code,
                "rotation_count": state.rotation_count,
            },
        )
        raise GraphAuthError(
            str(error_code),
            f"Graph identity endpoint returned status={response.status_code}",
        )

    body = response.json()
    access_token = body.get("access_token")
    expires_in = body.get("expires_in", 3600)
    rotated_refresh = body.get("refresh_token") or state.refresh_token

    if not access_token:
        logger.error(
            "oauth refresh missing access_token",
            extra={"event": "oauth.refresh.failed", "error_kind": "missing_access_token"},
        )
        raise GraphAuthError("missing_access_token", "Token endpoint returned no access_token")

    expiry_iso = datetime.fromtimestamp(time.time() + int(expires_in), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    now_iso = _utc_iso8601()

    new_rotation_count = state.rotation_count + (1 if rotated_refresh != state.refresh_token else 0)

    await execute_write(
        db_path,
        OAUTH_STATE_UPDATE_AFTER_EXCHANGE,
        (
            rotated_refresh,
            access_token,
            expiry_iso,
            now_iso,
            new_rotation_count,
            _PROVIDER,
        ),
    )
    logger.info(
        "oauth token rotated + persisted",
        extra={
            "event": "oauth.token.rotated",
            "persistence": "oauth_state",
            "rotation_count": new_rotation_count,
            "expires_in_s": expires_in,
        },
    )

    refreshed = await load_oauth_state(db_path)
    if refreshed is None:  # pragma: no cover — UPDATE just succeeded
        raise RuntimeError("oauth_state UPDATE succeeded but load returned None")
    return refreshed


async def get_access_token(
    db_path: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """High-level helper used by the sync worker (story 1-7).

    On first call after a fresh deploy: reads `OUTLOOK_REFRESH_TOKEN` from env,
    inserts the bootstrap row, then exchanges + persists.

    On subsequent calls: reads `oauth_state`, returns cached access_token if
    still valid, otherwise exchanges + persists.
    """
    state = await load_oauth_state(db_path)
    if state is None:
        state = await seed_oauth_state_from_env(db_path)

    if state.access_token_is_valid() and state.access_token is not None:
        return state.access_token

    state = await exchange_and_persist(db_path, state=state, transport=transport)
    assert state.access_token is not None  # exchange_and_persist always writes this  # noqa: S101
    return state.access_token


def _safe_json(response: httpx.Response) -> Any:
    """Parse JSON or return {} — tolerant of malformed identity-endpoint responses."""
    try:
        return response.json()
    except ValueError:
        return {}
