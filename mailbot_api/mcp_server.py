"""MCP server exposing MailBot verbs as tools — Story 5-2; extended in Story 5-6.

Builds a ``FastMCP`` instance and registers 16 of the project's verbs as MCP
tools.

The 11 baseline tools (Story 5-2): ``find_emails``, ``hydrate_email``,
``get_thread``, ``count_emails``, ``get_sender_summary``, ``propose_action``,
``mint_grant``, ``revoke_grant``, ``cancel_action``, ``revert_action``,
``mint_sensitivity_token``.

The 5 slash-command surface tools added in Story 5-6 (closing Story 5-2's
deferral): ``cost_breakdown`` (slash: /cost), ``reset_degraded_mode``
(/budget reset), ``pause_router`` (/pause), ``resume_router`` (/resume), and
the new ``mute_category`` (/mute). Each maps to a Discord slash command
declared in ``hermes-config/config.yaml#gateway.discord.slash_commands``.

Per AR-D7-1 the server runs as part of the ``uvicorn mailbot_api.main:app``
process on port 8000 under path ``/mcp`` (FastMCP's default ``streamable_http_path``).
Hermes connects from inside the Docker network as the MCP client (Story 5-4).

Server-injected per-call: ``db_path`` (resolved lazily from FastAPI ``app.state``
at call time via the ``_ServerContext`` indirection) and ``session_id`` (for
``hydrate_email`` only — derived from ``id(ctx.session)`` which is stable
across calls on the same MCP transport session).

Per-turn hydration counter reset (AC-4): the wrapper for ``hydrate_email``
auto-resets the per-session counter after ``_HYDRATION_TURN_RESET_SECONDS``
(30s) of inactivity on the same session_id. This implements the per-turn
Rule J discipline without depending on the transport exposing a turn-boundary
event.

Verbs intentionally NOT registered:

- ``ask_router``: Hermes-as-agent's inference path is the OpenAI
  ``/v1/chat/completions`` endpoint (Story 2-10). Re-exposing ``ask_router``
  as a tool would bypass the cost-discipline center.
- ``reset_hydration_count``: server-internal lifecycle helper, called by
  this module's ``_hydrate_email_wrapper``.

Previously-deferred verbs (cost/reset_degraded_mode/pause_router/resume_router)
are now registered as of Story 5-6.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from mailbot_api.verbs import (
    count_emails as _count_emails,
)
from mailbot_api.verbs import (
    find_emails as _find_emails,
)
from mailbot_api.verbs import (
    get_sender_summary as _get_sender_summary,
)
from mailbot_api.verbs import (
    get_thread as _get_thread,
)
from mailbot_api.verbs import (
    hydrate_email as _hydrate_email,
)
from mailbot_api.verbs import (
    reset_hydration_count as _reset_hydration_count,
)
from mailbot_api.verbs.budget_admin import reset_degraded_mode as _reset_degraded_mode
from mailbot_api.verbs.cancel_action import cancel_action as _cancel_action
from mailbot_api.verbs.cost import cost_breakdown as _cost_breakdown
from mailbot_api.verbs.mint_grant import mint_grant as _mint_grant
from mailbot_api.verbs.mint_sensitivity_token import (
    mint_sensitivity_token as _mint_sensitivity_token,
)
from mailbot_api.verbs.mute_category import mute_category as _mute_category
from mailbot_api.verbs.propose_action import propose_action as _propose_action
from mailbot_api.verbs.revert_action import revert_action as _revert_action
from mailbot_api.verbs.revoke_grant import revoke_grant as _revoke_grant
from mailbot_api.verbs.router_control import (
    pause_router as _pause_router,
)
from mailbot_api.verbs.router_control import (
    resume_router as _resume_router,
)
from mailbot_api.verbs.schemas import FindEmailsFilter

_logger = logging.getLogger(__name__)

# AC-4: per-turn reset window. A "turn" in the streamable-HTTP transport is
# defined here as a span of activity on one session_id; 30s of inactivity
# ends the turn and the hydration counter resets on the next call.
_HYDRATION_TURN_RESET_SECONDS = 30

# Module-level state for the per-session "last activity at" timestamps used
# by the per-turn hydration reset. Keyed by the same session_id that
# hydrate_email's underlying counter uses. Process-local + ephemeral by design
# (mirrors the underlying counter in mailbot_api/verbs/hydrate_email.py).
_LAST_HYDRATION_AT: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Server context — lazy db_path resolution (Pattern A from story Dev Notes).
# ---------------------------------------------------------------------------


@dataclass
class _ServerContext:
    """Per-server-instance context shared by every tool wrapper.

    ``db_path`` resolution is a closure over this dataclass so the wrappers
    can read whatever value FastAPI ``app.state.db_path`` resolves to at
    call time — production binds via ``set_db_path`` from the lifespan
    after ``MAILBOT_DB_PATH`` is read; tests bind via ``build_mcp_server(db_path=...)``.
    """

    db_path: str | None = None
    # Future: room for additional shared state (e.g. an app-state weakref).
    extra: dict[str, Any] = field(default_factory=dict)

    def require_db_path(self) -> str:
        if self.db_path is None:
            raise RuntimeError(
                "MCP server has no db_path bound — call set_db_path on the "
                "ServerContext (or pass db_path to build_mcp_server) before "
                "invoking any tool."
            )
        return self.db_path


def _session_id_from_ctx(ctx: Context[Any, Any, Any]) -> str:
    """Derive a stable per-MCP-session identifier from the FastMCP Context.

    ``ctx.session`` is the ``ServerSession`` object that FastMCP's transport
    creates once per MCP client connection. ``id(...)`` on it is stable for
    the lifetime of that session and unique within the process — perfect
    for keying per-session counters (the underlying hydrate_email counter
    is a process-local dict so process-local uniqueness is all we need).
    """
    return f"mcp-{id(ctx.session):x}"


# ---------------------------------------------------------------------------
# Tool wrappers — thin adapters around the verb functions.
# ---------------------------------------------------------------------------


def _build_wrappers(server_ctx: _ServerContext) -> dict[str, Any]:
    """Construct the 16 tool wrappers closed over the given _ServerContext.
    (11 Story-5-2 baseline + 5 Story-5-6 slash-command surface.)

    Returned dict maps verb-name → wrapper coroutine. The wrappers each take
    only agent-supplied kwargs (db_path / session_id never appear in their
    signatures), so FastMCP derives a clean JSON schema with no
    server-internal fields exposed.

    Each wrapper:
      - emits one structured log line per dispatch (AC-8 — sanitized);
      - converts verb-level errors-as-data through unchanged (AR-PAT-4);
      - converts unexpected exceptions to ``mcp.tool.crash`` log + re-raise
        (the SDK turns the re-raise into a protocol-level MCP error).
    """

    def _log_ok(tool: str, sid: str | None, latency_ms: int) -> None:
        _logger.info(
            "mcp tool ok",
            extra={
                "event": "mcp.tool.ok",
                "tool": tool,
                "session_id": sid,
                "latency_ms": latency_ms,
            },
        )

    def _log_error_as_data(tool: str, sid: str | None, error_code: str, latency_ms: int) -> None:
        _logger.info(
            "mcp tool error_as_data",
            extra={
                "event": "mcp.tool.error_as_data",
                "tool": tool,
                "session_id": sid,
                "error_code": error_code,
                "latency_ms": latency_ms,
            },
        )

    def _log_crash(tool: str, sid: str | None, exc: BaseException, latency_ms: int) -> None:
        _logger.error(
            "mcp tool crash",
            extra={
                "event": "mcp.tool.crash",
                "tool": tool,
                "session_id": sid,
                "exc_type": type(exc).__name__,
                "latency_ms": latency_ms,
            },
        )

    def _maybe_error_code(out: Any) -> str | None:
        """Extract a verb-level error code from a <Verb>Out shape, if present."""
        err = getattr(out, "error", None)
        if err is None:
            return None
        return getattr(err, "code", None)

    # ---- read verbs ----

    async def find_emails(
        filter: FindEmailsFilter, ctx: Context[Any, Any, Any], limit: int = 25
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _find_emails(filter, db_path=server_ctx.require_db_path(), limit=limit)
        except Exception as exc:  # noqa: BLE001 — boundary catch per AR-PAT-4
            _log_crash("find_emails", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("find_emails", sid, code, latency_ms)
        else:
            _log_ok("find_emails", sid, latency_ms)
        return out

    async def hydrate_email(email_id: str, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        # AC-4: per-turn timeout reset. If the last hydration on this session
        # was more than _HYDRATION_TURN_RESET_SECONDS ago, treat it as a new
        # turn and reset the counter before the underlying verb checks it.
        now = datetime.now(timezone.utc)
        last_at = _LAST_HYDRATION_AT.get(sid)
        if last_at is not None and (now - last_at).total_seconds() > _HYDRATION_TURN_RESET_SECONDS:
            _reset_hydration_count(sid)
        _LAST_HYDRATION_AT[sid] = now

        t0 = time.perf_counter()
        try:
            out = await _hydrate_email(
                email_id, db_path=server_ctx.require_db_path(), session_id=sid
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("hydrate_email", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("hydrate_email", sid, code, latency_ms)
        else:
            _log_ok("hydrate_email", sid, latency_ms)
        return out

    async def get_thread(thread_id: str, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _get_thread(thread_id, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("get_thread", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("get_thread", sid, code, latency_ms)
        else:
            _log_ok("get_thread", sid, latency_ms)
        return out

    async def count_emails(filter: FindEmailsFilter, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _count_emails(filter, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("count_emails", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("count_emails", sid, code, latency_ms)
        else:
            _log_ok("count_emails", sid, latency_ms)
        return out

    async def get_sender_summary(sender_address: str, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _get_sender_summary(sender_address, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("get_sender_summary", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("get_sender_summary", sid, code, latency_ms)
        else:
            _log_ok("get_sender_summary", sid, latency_ms)
        return out

    # ---- write verbs ----

    async def propose_action(
        email_id: str | None,
        action_type: str,
        ctx: Context[Any, Any, Any],
        payload: dict[str, Any] | None = None,
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _propose_action(
                email_id,
                action_type,
                payload=payload,
                db_path=server_ctx.require_db_path(),
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("propose_action", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("propose_action", sid, code, latency_ms)
        else:
            _log_ok("propose_action", sid, latency_ms)
        return out

    async def mint_grant(
        action_type: str,
        email_ids: list[str],
        expires_at: str,
        ctx: Context[Any, Any, Any],
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _mint_grant(
                action_type, email_ids, expires_at, db_path=server_ctx.require_db_path()
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("mint_grant", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("mint_grant", sid, code, latency_ms)
        else:
            _log_ok("mint_grant", sid, latency_ms)
        return out

    async def revoke_grant(grant_id: int, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _revoke_grant(grant_id, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("revoke_grant", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("revoke_grant", sid, code, latency_ms)
        else:
            _log_ok("revoke_grant", sid, latency_ms)
        return out

    async def cancel_action(action_id: int, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _cancel_action(action_id, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("cancel_action", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("cancel_action", sid, code, latency_ms)
        else:
            _log_ok("cancel_action", sid, latency_ms)
        return out

    async def revert_action(action_id: int, ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _revert_action(action_id, db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("revert_action", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("revert_action", sid, code, latency_ms)
        else:
            _log_ok("revert_action", sid, latency_ms)
        return out

    async def mint_sensitivity_token(
        email_id: str, task_type: str, ctx: Context[Any, Any, Any]
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _mint_sensitivity_token(
                email_id, task_type, db_path=server_ctx.require_db_path()
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("mint_sensitivity_token", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("mint_sensitivity_token", sid, code, latency_ms)
        else:
            _log_ok("mint_sensitivity_token", sid, latency_ms)
        return out

    # ---- Story 5-6: router-control + mute_category ----
    #
    # These five verbs are the slash-command surface for /cost, /pause, /resume,
    # /budget reset, and /mute. The Hermes Discord adapter dispatches each
    # slash command to its corresponding tool here per
    # hermes-config/config.yaml#gateway.discord.slash_commands.

    async def cost_breakdown(
        ctx: Context[Any, Any, Any], period: str = "today"
    ) -> Any:
        # Story 5-6 CR-1 fix: default to "today" so the slash command's
        # `required: false` period option works end-to-end. Without the default,
        # invoking /cost with no period argument would fail at the MCP boundary
        # with a missing-parameter error.
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            # The verb signature is Literal["today", "month"]; runtime validation
            # at the Pydantic-input layer keeps the boundary clean. The verb
            # itself raises ValueError for any other string (CR-2 defensive guard).
            out = await _cost_breakdown(period, db_path=server_ctx.require_db_path())  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            _log_crash("cost_breakdown", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("cost_breakdown", sid, code, latency_ms)
        else:
            _log_ok("cost_breakdown", sid, latency_ms)
        return out

    async def reset_degraded_mode(
        ctx: Context[Any, Any, Any], reason: str = "manual_reset"
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _reset_degraded_mode(
                db_path=server_ctx.require_db_path(), reason=reason
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("reset_degraded_mode", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("reset_degraded_mode", sid, code, latency_ms)
        else:
            _log_ok("reset_degraded_mode", sid, latency_ms)
        return out

    async def pause_router(ctx: Context[Any, Any, Any], reason: str = "unspecified") -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _pause_router(db_path=server_ctx.require_db_path(), reason=reason)
        except Exception as exc:  # noqa: BLE001
            _log_crash("pause_router", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("pause_router", sid, code, latency_ms)
        else:
            _log_ok("pause_router", sid, latency_ms)
        return out

    async def resume_router(ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _resume_router(db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("resume_router", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("resume_router", sid, code, latency_ms)
        else:
            _log_ok("resume_router", sid, latency_ms)
        return out

    async def mute_category(
        category: str,
        ctx: Context[Any, Any, Any],
        muted_until: str | None = None,
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _mute_category(
                category,
                db_path=server_ctx.require_db_path(),
                muted_until=muted_until,
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("mute_category", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("mute_category", sid, code, latency_ms)
        else:
            _log_ok("mute_category", sid, latency_ms)
        return out

    return {
        "find_emails": find_emails,
        "hydrate_email": hydrate_email,
        "get_thread": get_thread,
        "count_emails": count_emails,
        "get_sender_summary": get_sender_summary,
        "propose_action": propose_action,
        "mint_grant": mint_grant,
        "revoke_grant": revoke_grant,
        "cancel_action": cancel_action,
        "revert_action": revert_action,
        "mint_sensitivity_token": mint_sensitivity_token,
        # Story 5-6 — slash-command verbs.
        "cost_breakdown": cost_breakdown,
        "reset_degraded_mode": reset_degraded_mode,
        "pause_router": pause_router,
        "resume_router": resume_router,
        "mute_category": mute_category,
    }


# ---------------------------------------------------------------------------
# Declarative tool specs (AC-1): name → constraint hint clause.
# ---------------------------------------------------------------------------


_TOOL_DESCRIPTIONS: dict[str, str] = {
    "find_emails": (
        "Return up to `limit` email projections matching `filter`. "
        "Capped at 100 results — Rule J projections only; "
        "use hydrate_email for full bodies."
    ),
    "hydrate_email": (
        "Return the full hydration of one email by `email_id`. "
        "Rate-limited to 5 calls per chat turn — Rule J hydration discipline. "
        "Confidential emails are refused."
    ),
    "get_thread": (
        "Return all projections in a thread, ordered ASC by received_at, "
        "plus the cached thread continuity note. Rule J — projections only."
    ),
    "count_emails": (
        "Return the count of emails matching `filter` (cheap signal). "
        "Rule J — projections only; returns count, no rows."
    ),
    "get_sender_summary": (
        "Return per-sender enrichment for a sender_address. "
        "Rule J — cached sender enrichment (reputation + last-seen)."
    ),
    "propose_action": (
        "Propose an action against an email or email-less. "
        "Tier-aware; second auth check on apply."
    ),
    "mint_grant": (
        "Mint a scoped + time-bounded grant for a given action_type + email_ids."
    ),
    "revoke_grant": (
        "Revoke a previously-minted grant by grant_id."
    ),
    "cancel_action": (
        "Atomic cancel of a pending action by action_id."
    ),
    "revert_action": (
        "Revert a Tier-1 action by action_id. 24h window; "
        "MOVE_TO_TRIAGE_FOLDER returns INVERSE_UNAVAILABLE."
    ),
    "mint_sensitivity_token": (
        "Mint a single-use confirmation token for a sensitive email + task_type. "
        "Sensitive emails only; ephemeral 10-min token (AR-D12-1). "
        "Confidential refused unconditionally; normal needs no token."
    ),
    # Story 5-6 — slash-command verbs (registration closes Story 5-2's deferral).
    "cost_breakdown": (
        "Return Router cost breakdown for the period (today | month). "
        "Per-task / per-model / per-caller_origin aggregations + cache hit rate. "
        "Slash-command surface: /cost (Story 5-6)."
    ),
    "reset_degraded_mode": (
        "Flip degraded_mode_state to inactive and clear the in-memory flag. "
        "Slash-command surface: /budget reset (Story 5-6)."
    ),
    "pause_router": (
        "Pause the Router lane scheduler with a reason. "
        "Slash-command surface: /pause (Story 5-6)."
    ),
    "resume_router": (
        "Resume the Router lane scheduler. "
        "Slash-command surface: /resume (Story 5-6)."
    ),
    "mute_category": (
        "Mute a notification category until a timestamp (or indefinitely). "
        "Slash-command surface: /mute (Story 5-6); "
        "Epic 6's dispatcher reads from notification_mutes."
    ),
}


_EXPECTED_TOOL_COUNT = 16


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def build_mcp_server(*, db_path: str | None = None) -> FastMCP:
    """Build and configure a FastMCP server with all 16 MailBot tools registered.
    (11 Story-5-2 baseline read+write verbs + 5 Story-5-6 slash-command surface
    verbs.)

    ``db_path`` may be passed eagerly (production binds it from the FastAPI
    lifespan once ``MAILBOT_DB_PATH`` is resolved) or left None and bound
    later via ``set_db_path(server, db_path)``.

    The returned server has a ``_mailbot_server_ctx`` attribute (the
    ``_ServerContext`` instance) for tests and the lifespan to mutate.
    """
    server = FastMCP(
        name="mailbot-api",
        instructions=(
            "MailBot agent-facing verb surface. Read verbs (find_emails, "
            "hydrate_email, get_thread, count_emails, get_sender_summary) are "
            "projection-first per Rule J. Write verbs (propose_action, "
            "mint_grant, revoke_grant, cancel_action, revert_action, "
            "mint_sensitivity_token) follow the second-auth-check pattern. "
            "Slash-command-surface verbs (cost_breakdown, reset_degraded_mode, "
            "pause_router, resume_router, mute_category) are the verb side of "
            "Discord slash commands; agent invocations are allowed but should "
            "cite the user intent in the reasoning trace. "
            "Always inspect `result.error` after every tool call — verbs return "
            "error-as-data and never raise across the MCP boundary."
        ),
    )

    server_ctx = _ServerContext(db_path=db_path)
    # Stash on the server so set_db_path / tests / the lifespan can reach it
    # without re-introspecting the wrappers.
    server._mailbot_server_ctx = server_ctx  # type: ignore[attr-defined]

    wrappers = _build_wrappers(server_ctx)

    # AC-1 fail-fast: missing entry in _TOOL_DESCRIPTIONS or _build_wrappers
    # surfaces immediately rather than partial-registering. Asserts run BEFORE
    # the loop so divergence raises a clear AssertionError instead of a less
    # informative KeyError mid-loop (CR-8 finding).
    assert len(wrappers) == _EXPECTED_TOOL_COUNT, (
        f"expected {_EXPECTED_TOOL_COUNT} MCP tools, got {len(wrappers)}"
    )
    assert set(wrappers) == set(_TOOL_DESCRIPTIONS), (
        "wrapper set ≠ description set — fix the declarative list."
    )

    for tool_name, wrapper in wrappers.items():
        description = _TOOL_DESCRIPTIONS[tool_name]
        server.add_tool(wrapper, name=tool_name, description=description)

    return server


def set_db_path(server: FastMCP, db_path: str) -> None:
    """Bind a db_path onto an existing FastMCP server's _ServerContext.

    Used by the FastAPI lifespan in main.py: build the server at module
    import time (when MAILBOT_DB_PATH may not yet be set), then bind the
    resolved path inside the lifespan before yielding.
    """
    ctx: _ServerContext = server._mailbot_server_ctx  # type: ignore[attr-defined]
    ctx.db_path = db_path


def _reset_mcp_session_state_for_test() -> None:
    """Test-only: clear the per-session last-hydration-at map. Mirrors the
    Story 5-1 reset_hydration_count helper for the verb-side counter."""
    _LAST_HYDRATION_AT.clear()


__all__ = [
    "build_mcp_server",
    "set_db_path",
]
# Note: _reset_mcp_session_state_for_test is intentionally NOT in __all__
# (underscore-prefixed test helper; tests import it by explicit name).
