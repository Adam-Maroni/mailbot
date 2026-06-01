"""FastAPI app for mailbot-api container.

Story 1-2: ships /health and /v1/health.
Story 1-3: adds FastAPI lifespan handler that applies pending DB migrations on startup.
Story 1-4: env reads go through config.get_secret per Rule F.
Story 1-8: /health + /v1/health enriched with sync_* fields read from worker_health.
Story 2-2: lifespan loads router/policy.yaml and starts watchfiles hot-reloader.

Verb routes, /v1/chat/completions, /v1/embeddings, and MCP server land in later stories.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel

from mailbot_api.config import SecretMissing, get_secret, get_secret_optional
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.logging import configure_logging
from mailbot_api.router.anomaly import AnomalyDetector
from mailbot_api.router.budget import get_guard
from mailbot_api.router.lanes import LaneScheduler
from mailbot_api.router.pause import get_pause_state
from mailbot_api.router.policy import (
    PolicyValidationError,
    load_policy,
    policy_reload_loop,
    set_policy_snapshot,
)
from mailbot_api.router.registry import init_default_adapters
from mailbot_api.worker import (
    STALE_THRESHOLD_MINUTES,
    minutes_since,
    read_sync_health,
)

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan: apply DB migrations + load policy + start watcher.

    Per CR-10 (1-3) and Rule F (1-4):
      - get_secret_optional reads MAILBOT_SKIP_DB; "1" allows test bypass.
      - get_secret reads MAILBOT_DB_PATH; SecretMissing propagates as a
        RuntimeError-equivalent and uvicorn exits cleanly.

    Story 2-2: after DB migrations, load policy.yaml. On
    PolicyValidationError, abort the lifespan with a structured log line
    (we never serve traffic against an unvalidated policy). On success,
    schedule the watchfiles hot-reload loop as a task and tear it down at
    shutdown via stop_event.
    """
    skip_db = get_secret_optional("MAILBOT_SKIP_DB", "0") == "1"
    skip_policy = get_secret_optional("MAILBOT_SKIP_POLICY", "0") == "1"
    # Story 3-3: lifespan tests that bypass DB or run Router code without
    # needing the sensitivity gate set MAILBOT_SKIP_PATTERNS=1 to skip the
    # patterns.yaml load. Production startup never sets this.
    skip_patterns = get_secret_optional("MAILBOT_SKIP_PATTERNS", "0") == "1"

    db_path: str | None = None
    if not skip_db:
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

    # Story 2-2 / review fix HIGH: policy load is decoupled from the DB-skip
    # branch. Tests that bypass DB but exercise Router-side code (Story 2-4+)
    # set MAILBOT_SKIP_DB=1 AND MAILBOT_POLICY_PATH=<test fixture path>;
    # tests that need neither set both MAILBOT_SKIP_DB=1 and
    # MAILBOT_SKIP_POLICY=1 for the prior minimal-static-health behavior.
    policy_watcher_task: asyncio.Task[None] | None = None
    policy_stop_event: asyncio.Event | None = None
    if not skip_policy:
        policy_path = Path(get_secret_optional("MAILBOT_POLICY_PATH", "/app/router/policy.yaml"))
        try:
            initial_policy = load_policy(policy_path)
        except PolicyValidationError as exc:
            logger.error(
                "policy startup failed",
                extra={"event": "policy.startup.failed", "details": exc.details},
            )
            raise RuntimeError(f"policy.yaml failed to load: {exc.details}") from exc
        set_policy_snapshot(initial_policy)
        logger.info(
            "policy loaded",
            extra={"event": "policy.startup.loaded", "version": initial_policy.version},
        )

        # Story 3-3 AC-2: FR-2.5 startup safeguard. Fail-fast if policy.yaml
        # drifted at boot to a non-Qwen model for sensitivity_class. The
        # per-call safeguard in classify_sensitivity handles the hot-reload
        # case.
        from mailbot_api.sensitivity import assert_qwen_only, load_patterns
        from mailbot_api.sensitivity.patterns import set_patterns_snapshot as _set_sensitivity_patterns

        assert_qwen_only(initial_policy)
        logger.info(
            "sensitivity FR-2.5 startup safeguard passed",
            extra={"event": "sensitivity.startup.qwen_only_ok"},
        )

        # Story 3-3 AC-3: load sensitivity_patterns.yaml. Co-located with
        # policy.yaml under MAILBOT_PATTERNS_PATH (defaults to
        # /app/router/sensitivity_patterns.yaml). Bypassed when
        # MAILBOT_SKIP_PATTERNS=1 (Router-unit-test path).
        if not skip_patterns:
            patterns_path = Path(get_secret_optional("MAILBOT_PATTERNS_PATH", "/app/router/sensitivity_patterns.yaml"))
            try:
                sensitivity_patterns = load_patterns(patterns_path)
                _set_sensitivity_patterns(sensitivity_patterns)
                logger.info(
                    "sensitivity patterns loaded",
                    extra={
                        "event": "sensitivity.patterns.startup.loaded",
                        "version": sensitivity_patterns.version,
                        "force_confidential_count": len(sensitivity_patterns.force_confidential),
                        "force_sensitive_count": len(sensitivity_patterns.force_sensitive),
                    },
                )
            except Exception as exc:  # noqa: BLE001 — startup-phase, surface details
                logger.error(
                    "sensitivity patterns startup failed",
                    extra={"event": "sensitivity.patterns.startup.failed", "detail": str(exc)},
                )
                raise RuntimeError(f"sensitivity_patterns.yaml failed to load: {exc}") from exc

        # Story 2-4: register the default adapter set (Ollama; Story 2-6 will
        # add Anthropic). Lifespan order matters — must happen after policy
        # load so a later ask_router call finds both pieces wired.
        init_default_adapters()
        logger.info(
            "adapters registered",
            extra={"event": "adapters.startup.registered"},
        )

        # Story 2-5: lane scheduler lifecycle. Worker-pool body is a stub for
        # this story; Story 2-9 will populate the queue-based dispatch path.
        lane_scheduler = LaneScheduler(pool_size=8)
        await lane_scheduler.start()

        # Story 2-8: initialize the budget guard with rolled-forward spend.
        # `db_path` is non-None on this branch (we just resolved it above).
        anomaly_detector: AnomalyDetector | None = None
        if db_path is not None:
            await get_guard().initialize(db_path)
            logger.info(
                "budget guard initialized",
                extra={
                    "event": "budget.startup.initialized",
                    "today_spend_usd": get_guard().today_spend_usd,
                    "this_month_spend_usd": get_guard().this_month_spend_usd,
                    "degraded": get_guard().is_degraded(),
                },
            )
            # Story 2-9: pause state + anomaly detector.
            await get_pause_state().initialize(db_path)
            anomaly_detector = AnomalyDetector(db_path, interval_seconds=3600.0)
            await anomaly_detector.start()

        policy_stop_event = asyncio.Event()
        policy_watcher_task = asyncio.create_task(policy_reload_loop(policy_path, stop_event=policy_stop_event))

    # Stash db_path + watcher handles on app state so endpoint handlers + the
    # shutdown branch can reach them. `_app is None` arises in unit tests that
    # drive the lifespan directly via `async with lifespan(None)`; the state
    # writes are skipped in that path.
    if _app is not None:
        _app.state.db_path = db_path
        _app.state.policy_stop_event = policy_stop_event
        _app.state.policy_watcher_task = policy_watcher_task
        if not skip_policy:
            _app.state.lane_scheduler = lane_scheduler
    try:
        yield
    finally:
        if policy_stop_event is not None and policy_watcher_task is not None:
            policy_stop_event.set()
            try:
                await asyncio.wait_for(policy_watcher_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
                logger.warning(
                    "policy watcher shutdown timeout",
                    extra={"event": "policy.shutdown.timeout", "exc_type": type(exc).__name__},
                )
                policy_watcher_task.cancel()
        if not skip_policy:
            await lane_scheduler.stop(timeout=30.0)
            if anomaly_detector is not None:
                await anomaly_detector.stop(timeout=5.0)


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
    payload["sync_health_alarm"] = last_outcome != "ok" or elapsed > STALE_THRESHOLD_MINUTES
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


# --- Story 2-10: /v1/chat/completions OpenAI-compatible endpoint ---


class _ChatMessage(BaseModel):
    role: str
    content: str


class _ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[_ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.0


def _check_bearer_auth(authorization: str | None) -> None:
    """Validate the Authorization: Bearer <MAILBOT_ROUTER_KEY> header.

    OpenAI-shape error body on mismatch (so Hermes treats us like a real
    provider for error rendering)."""
    expected = get_secret_optional("MAILBOT_ROUTER_KEY", "")
    if not expected:
        # If MAILBOT_ROUTER_KEY isn't configured, the endpoint refuses all
        # requests — fail-closed is the safer default than allow-all.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "authentication_error",
                    "message": "MAILBOT_ROUTER_KEY not configured",
                }
            },
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "authentication_error",
                    "message": "missing or malformed Authorization header",
                }
            },
        )
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "type": "authentication_error",
                    "message": "invalid bearer token",
                }
            },
        )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: _ChatCompletionsRequest,
    raw_request: Request,
    authorization: str | None = Header(default=None),
    x_mailbot_caller_origin: str | None = Header(default=None),
) -> dict[str, Any]:
    """OpenAI-compatible chat-completions endpoint.

    Translates the OpenAI request shape into ``ask_router(task_type='hermes_aux',
    force_model=<request.model>, content=<rendered messages>, ...)`` and
    translates the result back to OpenAI shape. ``caller_origin`` is sourced
    from the ``X-Mailbot-Caller-Origin`` header (default ``unknown-external``).
    """
    _check_bearer_auth(authorization)

    db_path = _db_path_from_app()
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "type": "service_unavailable",
                    "message": "router not initialized",
                }
            },
        )

    # Render OpenAI messages array into our prompt template's `content` dict.
    # Hermes-aux prompts use a minimal template that accepts the joined
    # message content; the prompt module lives at
    # mailbot_api/prompts/hermes_aux/v1.py.
    joined = "\n".join(f"{m.role}: {m.content}" for m in request.messages)
    content = {"messages": joined}

    # Late import to avoid the lifespan circular-import surface.
    from mailbot_api.router import ask_router as _ask_router

    caller_origin = x_mailbot_caller_origin if x_mailbot_caller_origin else "unknown-external"
    result = await _ask_router(
        "hermes_aux",
        content,
        db_path=db_path,
        force_model=request.model,
        force=False,
        caller_origin=caller_origin,
        caller_verb="hermes_aux",
    )

    if not result.ok or result.output is None:
        detail = "router refused" if result.error is None else result.error.message
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "type": "router_error",
                    "message": detail,
                }
            },
        )

    # Translate the parsed output back to OpenAI shape. The hermes_aux
    # prompt's OUTPUT_SCHEMA is HermesAuxOutput with `text` field.
    output_text = getattr(result.output, "text", "")
    return {
        "id": f"chatcmpl-mailbot-{id(raw_request):x}",
        "object": "chat.completion",
        "created": 0,
        "model": result.model_used,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": output_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.tokens_in,
            "completion_tokens": result.tokens_out,
            "total_tokens": result.tokens_in + result.tokens_out,
            "cached_input_tokens": result.cached_tokens_in,
        },
    }


@app.post("/v1/embeddings")
async def embeddings(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """OpenAI-compatible embeddings endpoint (stub).

    Story 2-10 ships the auth gate + shape; Epic 3 Story 3-4 ships the
    real nomic-embed-text adapter that this endpoint dispatches against.
    Until then the endpoint returns 501.
    """
    _check_bearer_auth(authorization)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": {
                "type": "not_implemented",
                "message": "embeddings adapter ships in Story 3-4",
            }
        },
    )
