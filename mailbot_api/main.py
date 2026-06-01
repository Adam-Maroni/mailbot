"""FastAPI app for mailbot-api container.

Story 1-2: ships /health and /v1/health.
Story 1-3: adds FastAPI lifespan handler that applies pending DB migrations on startup.
Story 1-4: env reads go through config.get_secret per Rule F.
Story 1-8: /health + /v1/health enriched with sync_* fields read from worker_health.

Verb routes, /v1/chat/completions, /v1/embeddings, and MCP server land in later stories.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from mailbot_api.config import SecretMissing, get_secret, get_secret_optional
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.logging import configure_logging
from mailbot_api.worker import (
    STALE_THRESHOLD_MINUTES,
    minutes_since,
    read_sync_health,
)

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan: apply DB migrations on startup.

    Per CR-10 (1-3) and Rule F (1-4):
      - get_secret_optional reads MAILBOT_SKIP_DB; "1" allows test bypass.
      - get_secret reads MAILBOT_DB_PATH; SecretMissing propagates as a
        RuntimeError-equivalent and uvicorn exits cleanly.
    """
    skip = get_secret_optional("MAILBOT_SKIP_DB", "0") == "1"
    if skip:
        yield
        return

    try:
        db_path = get_secret("MAILBOT_DB_PATH")
    except SecretMissing as exc:
        raise RuntimeError(
            f"{exc.name} is unset. Set it to the SQLite file path or set "
            f"MAILBOT_SKIP_DB=1 for static health-only test runs."
        ) from exc

    applied = apply_pending_migrations(db_path)
    if applied:
        logger.info(
            "db migrations applied",
            extra={"event": "db.migrations.startup_applied", "count": len(applied), "files": applied},
        )

    # Stash db_path on app state so endpoint handlers can read it without
    # re-doing the env+SecretMissing dance on every request.
    _app.state.db_path = db_path
    yield


app = FastAPI(
    title="mailbot-api",
    description="MailBot internal API: Router, verbs, MCP server, sync worker",
    version="0.1.0",
    lifespan=lifespan,
)


async def _build_health_payload(db_path: str | None) -> dict[str, Any]:
    """Compose the enriched /health response. db_path=None → static healthy
    response (Story 1-2 shape) for test-mode runs without a DB."""
    payload: dict[str, Any] = {"ok": True}
    if db_path is None:
        return payload

    last_heartbeat_at, last_outcome, _last_error = await read_sync_health(db_path)
    payload["sync_last_heartbeat_at"] = last_heartbeat_at
    payload["sync_last_outcome"] = last_outcome

    if last_heartbeat_at is None or last_outcome is None:
        payload["sync_minutes_since_last_ok"] = None
        payload["sync_health_alarm"] = False
        return payload

    elapsed = minutes_since(last_heartbeat_at)
    payload["sync_minutes_since_last_ok"] = elapsed if last_outcome == "ok" else None
    payload["sync_health_alarm"] = (
        last_outcome != "ok" or elapsed > STALE_THRESHOLD_MINUTES
    )
    return payload


def _db_path_from_app() -> str | None:
    """Return app.state.db_path if set; otherwise None (test-mode startup)."""
    return getattr(app.state, "db_path", None)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness + sync-health snapshot. HTTP status always 200; clients inspect
    the body's `sync_health_alarm` boolean."""
    return await _build_health_payload(_db_path_from_app())


@app.get("/v1/health")
async def health_v1() -> dict[str, Any]:
    """Versioned health endpoint — same shape as /health."""
    return await _build_health_payload(_db_path_from_app())
