"""FastAPI app for mailbot-api container.

Story 1-2: ships /health and /v1/health.
Story 1-3: adds FastAPI lifespan handler that applies pending DB migrations on startup.
Story 1-4: env reads go through config.get_secret per Rule F.
Story 1-8: /health + /v1/health enriched with sync_* fields read from worker_health.
Story 2-2: lifespan loads router/policy.yaml and starts watchfiles hot-reloader.
Story 2-10: /v1/chat/completions and /v1/embeddings OpenAI-shape endpoints.
Story 5-2: MCP server mounted at /mcp via FastMCP streamable-HTTP transport.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mailbot_api.config import SecretMissing, get_secret, get_secret_optional
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server
from mailbot_api.observability.logging import configure_logging
from mailbot_api.router.anomaly import AnomalyDetector
from mailbot_api.router.budget import get_guard
from mailbot_api.router.errors import (
    ChatCompletionToolChoice,
    ChatCompletionToolDef,
)
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
    # Story 5-2: MAILBOT_SKIP_MCP=1 bypasses the MCP session-manager
    # lifecycle (useful for tests that boot the FastAPI app without exercising
    # the MCP transport — mirrors the SKIP_DB/SKIP_POLICY/SKIP_PATTERNS pattern).
    skip_mcp = get_secret_optional("MAILBOT_SKIP_MCP", "0") == "1"

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
        # Story 9-1: companion user-overrides file. Bind-mounted RW; absent
        # by default; created on first /model persistent (Story 9-4). The
        # default path is the sibling of policy_path so deployments that
        # override MAILBOT_POLICY_PATH for tests get the override too.
        overrides_path = Path(
            get_secret_optional(
                "MAILBOT_POLICY_OVERRIDES_PATH",
                str(policy_path.parent / "policy.user-overrides.yaml"),
            )
        )
        try:
            initial_policy = load_policy(policy_path, overrides_path=overrides_path)
        except PolicyValidationError as exc:
            logger.error(
                "policy startup failed",
                extra={"event": "policy.startup.failed", "details": exc.details},
            )
            raise RuntimeError(f"policy.yaml failed to load: {exc.details}") from exc
        set_policy_snapshot(initial_policy)
        logger.info(
            "policy loaded",
            extra={
                "event": "policy.startup.loaded",
                "version": initial_policy.version,
                "policy_path": str(policy_path),
                "overrides_path": str(overrides_path),
                "overrides_present": overrides_path.exists(),
            },
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
        # Story 9-1: pass overrides_path so awatch covers BOTH files when the
        # override file exists at startup. If the override file is ABSENT
        # at startup, policy_reload_loop filters it out of the awatch set
        # (watchfiles raises FileNotFoundError on non-existent paths — see
        # `docs/policy-overrides.md` "Hot-reload contract limitation"). Story
        # 9-4 owns the first-create flow and the restart-requirement surfacing.
        policy_watcher_task = asyncio.create_task(
            policy_reload_loop(
                policy_path,
                overrides_path=overrides_path,
                stop_event=policy_stop_event,
            )
        )

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

    # Story 5-2: build a fresh FastMCP server + mount its streamable-HTTP
    # ASGI app on every lifespan entry. Per-lifespan instantiation is
    # required because FastMCP's StreamableHTTPSessionManager binds to the
    # event loop at construction; reusing a single module-level instance
    # across multiple TestClient lifespans (each running on a fresh loop)
    # breaks subsequent runs. The route is appended to the FastAPI router
    # before yield and popped after — single-app, multi-lifespan safe.
    mcp_mount = None
    async with AsyncExitStack() as stack:
        if not skip_mcp and _app is not None and db_path is not None:
            from starlette.routing import Mount

            mcp_server = build_mcp_server(db_path=db_path)
            # `streamable_http_app()` lazily constructs the session manager,
            # so call it FIRST — then `.session_manager` is safe to access.
            streamable_app = mcp_server.streamable_http_app()
            await stack.enter_async_context(mcp_server.session_manager.run())
            mcp_mount = Mount("/mcp", app=streamable_app)
            _app.router.routes.append(mcp_mount)
            _app.state.mcp_server = mcp_server
            # Story 5-6 follow-up (Phase 3.5 finding): pull the count from the
            # canonical source rather than hardcoding. Story 5-6 bumped 11->16
            # but missed this observability line.
            from mailbot_api.mcp_server import _EXPECTED_TOOL_COUNT
            # Story 6-6.6 CR MED-2: distinguish the FastAPI Mount path
            # ("/mcp") from the externally-visible URL path Hermes POSTs to
            # ("/mcp/"). After F6 closure the trailing slash is load-bearing
            # — surface both so operators reading startup logs can verify the
            # routing shape without inspecting hermes-config/config.yaml.
            logger.info(
                "mcp server live",
                extra={
                    "event": "mcp.startup.live",
                    "tools": _EXPECTED_TOOL_COUNT,
                    "mount_path": "/mcp",
                    "hermes_url_path": "/mcp/",
                },
            )
        elif _app is not None and not skip_mcp:
            # CR-6: surface misconfiguration. skip_mcp=False but db_path=None
            # would silently skip the mount (e.g., MAILBOT_SKIP_DB=1 without
            # MAILBOT_SKIP_MCP=1). Log a warning so the gap is operationally
            # visible.
            logger.warning(
                "mcp server skipped — db_path unavailable",
                extra={
                    "event": "mcp.startup.skipped",
                    "reason": "db_path_unavailable",
                    "skip_mcp": skip_mcp,
                },
            )
        try:
            yield
        finally:
            # Pop the per-lifespan mount so the next lifespan can re-mount
            # cleanly (without two routes resolving the same path).
            if mcp_mount is not None and _app is not None:
                try:
                    _app.router.routes.remove(mcp_mount)
                except ValueError:
                    pass
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
# Story 5-2: the /mcp Starlette mount is appended dynamically inside
# `lifespan()` per-startup so the FastMCP session manager binds to the
# active event loop (see lifespan body for the Mount append + cleanup).


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
# Story 6-9 (F11 closure 2026-06-04): extended with OpenAI tools=[...] +
# tool_choice support. When request.tools is present, the endpoint dispatches
# via the dispatch_tool_call sibling rather than ask_router — see
# _bmad-output/implementation-artifacts/6-9-design-decision.md.


class _ChatMessageToolCallFunction(BaseModel):
    """Story 6-9: function sub-object on an assistant tool_call echoed
    back in subsequent-turn requests."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: str  # JSON-stringified per OpenAI wire shape


class _ChatMessageToolCall(BaseModel):
    """Story 6-9: one tool_call element on an assistant message."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["function"]
    function: _ChatMessageToolCallFunction


class _ChatMessage(BaseModel):
    """OpenAI-shape message. Story 6-9 extends with tool-calling fields:
      * `tool_calls` — present on assistant messages echoing tool_use
      * `tool_call_id` — present on tool-role messages
    `content` is optional on assistant messages that carry only tool_calls.

    `extra="ignore"` (vs. the envelope's `extra="forbid"`): real OpenAI
    clients echo back assistant messages with non-standard fields
    (`refusal`, `audio`, deprecated `function_call`, streaming-specific
    fields). A multi-turn round-trip with these fields shouldn't 422 at
    our boundary — we just ignore the unknown fields.
    """

    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[_ChatMessageToolCall] | None = None
    tool_call_id: str | None = None


class _ChatCompletionsRequest(BaseModel):
    """OpenAI-compatible chat-completions request.

    Story 6-9 (F11 closure): extended with `tools` + `tool_choice`.

    Story 6-9 F12 closure (2026-06-04, discovered during CP-2 walk attempt
    #4): switched from `extra="forbid"` to `extra="ignore"`. Hermes sends
    `stream: True` + `stream_options: {"include_usage": True}` on every
    OpenAI-compatible request — both are legitimate OpenAI wire fields, not
    field-name typos. The original design rationale ("forbid catches typos
    that hid F11 for an entire epic") was wrong: OpenAI's wire shape has
    dozens of legitimate fields (`stream`, `stream_options`, `response_format`,
    `seed`, `top_p`, `frequency_penalty`, `presence_penalty`, `logit_bias`,
    `logprobs`, `n`, `stop`, `user`, etc.). Rejecting them breaks real
    clients. Regression coverage for field-name correctness lives in the
    integration tests instead.
    """

    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[_ChatMessage]
    max_tokens: int = 1024
    temperature: float = 0.0
    tools: list[ChatCompletionToolDef] | None = None
    tool_choice: ChatCompletionToolChoice | None = None
    # F13 (Story 6-9 CP-2 walk attempt #4, 2026-06-04): Hermes sends
    # `stream: True` on every OpenAI request. The tools-path branch
    # honors this by returning SSE-framed chunks; the text-only path
    # continues to ignore (no use case has driven streaming for aux tasks).
    stream: bool = False
    stream_options: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_tool_choice_requires_tools(self) -> _ChatCompletionsRequest:
        """Story 6-9 CR-5: reject `tool_choice` set when `tools` is absent.

        OpenAI's spec leaves this undefined; we 422 at the boundary so the
        caller's intent is never silently dropped. The two failure modes
        we reject:
          * `tool_choice="required"` with no tools — meaningless (nothing to require)
          * `tool_choice={"type": "function", ...}` with no tools — references
            a tool that's not in the request
        `tool_choice="auto"` or `"none"` with no tools is harmless and accepted.
        """
        if self.tool_choice is None:
            return self
        # tool_choice provided — verify tools is non-empty
        if not self.tools:
            # Allow only "auto"/"none" semantic choices with no tools list
            if self.tool_choice in ("auto", "none"):
                return self
            raise ValueError(
                "tool_choice requires tools=[...] to be present and non-empty"
            )
        return self


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


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: _ChatCompletionsRequest,
    raw_request: Request,
    authorization: str | None = Header(default=None),
    x_mailbot_caller_origin: str | None = Header(default=None),
) -> dict[str, Any] | StreamingResponse:
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

    caller_origin = x_mailbot_caller_origin if x_mailbot_caller_origin else "unknown-external"

    # Story 6-9 (F11 closure): branch on tools presence. When the caller
    # supplies `tools=[...]`, dispatch via the dispatch_tool_call sibling
    # rather than ask_router. The two paths share sensitivity-gate, pause,
    # budget-guard primitives but have different output shapes (tool_calls
    # vs. validated text), different failure chains (no schema-retry on
    # tool calls), and different audit columns.
    #
    # CR-1 (Story 6-9 review 2026-06-04): branch only on non-empty tools.
    # An explicitly empty `tools=[]` falls through to the text-only path —
    # Anthropic's Messages API rejects empty tools lists with a 400, so
    # we'd surface a confusing 502 to Hermes otherwise. Treating empty list
    # as "no tools intent" matches OpenAI's behavior.
    if request.tools:
        result = await _chat_completions_tools_dispatch(
            request=request,
            caller_origin=caller_origin,
            db_path=db_path,
        )
        _raise_router_error_if_failed(result)

        # F13 (Story 6-9 CP-2 walk attempt #4): branch on `stream` field.
        # Hermes's main-inference path sends `stream=True` by default; an
        # OpenAI SDK client in streaming mode iterates over SSE chunks and
        # gets zero items if we return application/json — interpreted as
        # "empty response" → retry → failure.
        if request.stream:
            include_usage = bool(
                request.stream_options
                and request.stream_options.get("include_usage")
            )
            return StreamingResponse(
                _tool_call_completion_sse_chunks(
                    result=result,
                    raw_request=raw_request,
                    include_usage=include_usage,
                ),
                media_type="text/event-stream",
            )
        return _build_tool_call_completion_response(
            result=result,
            raw_request=raw_request,
        )

    # ---- Story 2-10 original text-only path ----
    # Render OpenAI messages array into our prompt template's `content` dict.
    # Hermes-aux prompts use a minimal template that accepts the joined
    # message content; the prompt module lives at
    # mailbot_api/prompts/hermes_aux/v1.py.
    joined = "\n".join(f"{m.role}: {m.content or ''}" for m in request.messages)
    content = {"messages": joined}

    # Late import to avoid the lifespan circular-import surface.
    from mailbot_api.router import ask_router as _ask_router

    # F8 closure (Story 6-6.8, 2026-06-03): if the client sends the task-type
    # name as the model id (Hermes's documented contract — `hermes-config/
    # config.yaml`'s `model.default: "hermes_aux"` means "use the Router's
    # hermes_aux policy entry to pick the actual backend model at dispatch
    # time"), don't force-override; let ask_router resolve from policy. Any
    # other client-requested model name (e.g. "claude-opus-4-7" from a
    # power-user override) still flows through as a real `force_model` and
    # triggers the existing degraded-mode + sensitivity gates correctly.
    # The bug fixed here: previously `force_model=request.model` passed the
    # alias string `"hermes_aux"` straight to `get_adapter()`, which raised
    # `KeyError("no adapter registered for model_id='hermes_aux'")`. The
    # error surfaced as HTTP 502 to Hermes after 3 retries on every call.
    force_model = request.model if request.model != "hermes_aux" else None

    result = await _ask_router(
        "hermes_aux",
        content,
        db_path=db_path,
        force_model=force_model,
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


async def _chat_completions_tools_dispatch(
    *,
    request: _ChatCompletionsRequest,
    caller_origin: str,
    db_path: str,
) -> Any:  # ToolCallResult
    """Shared dispatch helper for the tool-calling branch of /v1/chat/completions.

    Returns the raw `ToolCallResult` so the caller can shape it as either
    a non-streaming JSON response OR a streaming SSE response (F13).
    """
    from mailbot_api.router import dispatch_tool_call as _dispatch_tool_call  # noqa: PLC0415
    from mailbot_api.router.policy import snapshot_for_dispatch as _snap  # noqa: PLC0415

    # Resolve "hermes_aux" alias to its policy-default model. CR-2/CR-4
    # (Story 6-9 review 2026-06-04): track whether the caller explicitly
    # forced a model so dispatch_tool_call can attribute the audit row's
    # `model_chosen_reason` correctly and gate the degraded-mode opus
    # block on user-force only.
    if request.model == "hermes_aux":
        try:
            policy_snapshot = _snap()
            entry = policy_snapshot.tasks.get("hermes_aux")
            resolved_model = entry.model if entry is not None else "claude-haiku-4-5-20251001"
        except RuntimeError:
            resolved_model = "claude-haiku-4-5-20251001"
        is_force_override = False
    else:
        resolved_model = request.model
        is_force_override = True

    # Convert pydantic _ChatMessage list back to plain dicts for translation
    # downstream (the translator works with plain dicts so it's not pinned
    # to our specific Pydantic shape).
    plain_messages: list[dict[str, Any]] = []
    for m in request.messages:
        msg: dict[str, Any] = {"role": m.role}
        if m.content is not None:
            msg["content"] = m.content
        if m.tool_calls is not None:
            msg["tool_calls"] = [tc.model_dump() for tc in m.tool_calls]
        if m.tool_call_id is not None:
            msg["tool_call_id"] = m.tool_call_id
        plain_messages.append(msg)

    return await _dispatch_tool_call(
        messages=plain_messages,
        tools=request.tools or [],
        tool_choice=request.tool_choice,
        model=resolved_model,
        is_force_override=is_force_override,
        max_tokens_out=request.max_tokens,
        temperature=request.temperature,
        db_path=db_path,
        caller_origin=caller_origin,
        caller_verb="hermes_aux_tools",
    )


def _raise_router_error_if_failed(result: Any) -> None:
    """Helper: raise HTTPException(502) for a failed ToolCallResult."""
    if not result.ok:
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


def _build_tool_call_completion_response(
    *,
    result: Any,
    raw_request: Request,
) -> dict[str, Any]:
    """Shape a successful ToolCallResult into an OpenAI chat.completion dict
    (non-streaming response). Per OpenAI's spec, `content` is null (not
    empty string) when the assistant produced only tool_calls."""
    message_payload: dict[str, Any] = {"role": "assistant"}
    if result.text:
        message_payload["content"] = result.text
    else:
        message_payload["content"] = None
    if result.tool_calls:
        message_payload["tool_calls"] = [tc.model_dump() for tc in result.tool_calls]

    return {
        "id": f"chatcmpl-mailbot-{id(raw_request):x}",
        "object": "chat.completion",
        "created": 0,
        "model": result.model_used,
        "choices": [
            {
                "index": 0,
                "message": message_payload,
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.tokens_in,
            "completion_tokens": result.tokens_out,
            "total_tokens": result.tokens_in + result.tokens_out,
            "cached_input_tokens": result.cached_tokens_in,
        },
    }


def _tool_call_completion_sse_chunks(
    *,
    result: Any,
    raw_request: Request,
    include_usage: bool,
) -> Iterator[str]:
    """F13 (Story 6-9 CP-2 walk attempt #4, 2026-06-04) — emit OpenAI-shape
    SSE chunks for a streaming tool-call response.

    MVP: yields the COMPLETE response as a single delta chunk (carrying both
    optional text content AND all tool_calls at once) followed by a final
    chunk with `finish_reason` and the `[DONE]` sentinel. This is not "true"
    streaming — the underlying dispatch is non-streaming — but it satisfies
    OpenAI client SDKs in streaming mode (e.g., Hermes's main inference path
    which uses `stream=True` by default).

    Per OpenAI's wire shape, each chunk is `data: <json>\\n\\n` and the
    terminator is `data: [DONE]\\n\\n`.
    """
    chunk_id = f"chatcmpl-mailbot-{id(raw_request):x}"
    base = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": 0,
        "model": result.model_used,
    }

    # Chunk 1: role-only delta (OpenAI clients expect this to fire `role` first)
    yield "data: " + json.dumps({
        **base,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        ],
    }) + "\n\n"

    # Chunk 2: content + tool_calls delta (combined since MVP emits at once).
    # Per OpenAI streaming spec, tool_calls in deltas carry an `index` field
    # so the client can accumulate them across chunks. Since we emit each
    # tool_call complete in one chunk, the index is simply the position.
    delta: dict[str, Any] = {}
    if result.text:
        delta["content"] = result.text
    if result.tool_calls:
        delta["tool_calls"] = [
            {
                "index": i,
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for i, tc in enumerate(result.tool_calls)
        ]
    if delta:
        yield "data: " + json.dumps({
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": None,
                }
            ],
        }) + "\n\n"

    # Chunk 3: terminator with finish_reason.
    final_chunk: dict[str, Any] = {
        **base,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": result.finish_reason,
            }
        ],
    }
    if include_usage:
        # OpenAI streaming with `stream_options: {"include_usage": True}`
        # adds a `usage` field on the FINAL chunk before [DONE].
        final_chunk["usage"] = {
            "prompt_tokens": result.tokens_in,
            "completion_tokens": result.tokens_out,
            "total_tokens": result.tokens_in + result.tokens_out,
            "cached_input_tokens": result.cached_tokens_in,
        }
    yield "data: " + json.dumps(final_chunk) + "\n\n"

    # SSE terminator per OpenAI wire shape.
    yield "data: [DONE]\n\n"


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


# --- Story 6-2: POST /admin/pause + POST /admin/resume — operator kill switch ---


class _PauseRequest(BaseModel):
    """Body shape for POST /admin/pause.

    CR-1 (Story 6-2 review 2026-06-03): `reason` rejects empty strings via
    `min_length=1`. Operators who omit a reason get the default; operators
    who send `{"reason": ""}` get a 422 (more useful than persisting blank).
    """

    reason: str = Field(default="manual cli pause", min_length=1)


@app.post("/admin/pause")
async def admin_pause(
    request: _PauseRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Bearer-authed kill switch — pauses the Router via Story 2-9's
    `PauseState`.

    CR-2 (Story 6-2 review 2026-06-03): re-issuing while already paused
    UPDATES the persisted `reason` AND refreshes `paused_at` to the new
    invocation timestamp (per `PAUSE_STATE_PAUSE` query, which always sets
    `paused_at = ?` unconditionally). The status board shows the most-recent
    pause invocation, NOT the first. Operators get `previously_paused=True`
    in the response so they can see this was a re-pause.

    Story 6-2 calls this from `mailbot pause [reason]` CLI; Story 5-6's
    `/pause` MCP slash command also reaches the same underlying state
    (via verbs/router_control.py).
    """
    _check_bearer_auth(authorization)
    db_path = _db_path_from_app()
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "type": "service_unavailable",
                    "message": "pause requires db_path",
                }
            },
        )
    state = get_pause_state()
    previously_paused = state.is_paused()
    await state.pause(db_path, reason=request.reason)
    message = (
        f"router paused — reason: {request.reason}"
        if not previously_paused
        else f"router was already paused — reason updated to: {request.reason}"
    )
    return {
        "ok": True,
        "previously_paused": previously_paused,
        "reason": request.reason,
        "message": message,
    }


@app.post("/admin/resume")
async def admin_resume(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Bearer-authed inverse of /admin/pause. Idempotent: resuming an
    already-running Router is a no-op (responses still include the
    `previously_paused` flag so the operator sees whether it was a no-op)."""
    _check_bearer_auth(authorization)
    db_path = _db_path_from_app()
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "type": "service_unavailable",
                    "message": "resume requires db_path",
                }
            },
        )
    state = get_pause_state()
    previously_paused = state.is_paused()
    await state.resume(db_path)
    message = (
        "router resumed" if previously_paused else "router was not paused"
    )
    return {
        "ok": True,
        "previously_paused": previously_paused,
        "message": message,
    }


# --- Story 6-1: GET /admin/status — operator status board ---


@app.get("/admin/status")
async def admin_status(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Bearer-authed status board read by `mailbot status` CLI.

    Returns a JSON-serialized `StatusReport` (see
    `mailbot_api/observability/status.py`). All section reads run in
    parallel; total wall-clock budget < 1s on 100k router_calls rows.
    """
    _check_bearer_auth(authorization)
    db_path = _db_path_from_app()
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "type": "service_unavailable",
                    "message": "status assembler requires db_path",
                }
            },
        )
    # Late import — observability/status.py imports from worker.py, which
    # imports from main-time-loaded modules. Late-import side-steps the
    # circular surface.
    from mailbot_api.observability.status import assemble_status

    report = await assemble_status(db_path)
    return report.model_dump()
