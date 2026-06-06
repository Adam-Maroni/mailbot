"""MCP server exposing MailBot verbs as tools — Story 5-2; extended in Story 5-6 + 6-8.

Builds a ``FastMCP`` instance and registers 22 of the project's verbs as MCP
tools.

The 11 baseline tools (Story 5-2): ``find_emails``, ``hydrate_email``,
``get_thread``, ``count_emails``, ``get_sender_summary``, ``propose_action``,
``mint_grant``, ``revoke_grant``, ``cancel_action``, ``revert_action``,
``mint_sensitivity_token``.

The 5 slash-command surface tools added in Story 5-6 (closing Story 5-2's
deferral): ``cost_breakdown`` (slash: /cost), ``reset_degraded_mode``
(/budget reset), ``pause_router`` (/pause), ``resume_router`` (/resume), and
``mute_category`` (/mute).

The 1 analytics tool added in Story 6-8 (AR-ANALYTICS-1): ``render_spend_chart``
(slash: /spend) — returns a matplotlib-rendered PNG of cost-per-task over
today/week/month.

The 2 notification-dispatcher tools added in Story 6-3:
``pull_pending_notifications`` (Hermes atomically claims up to N urgent
rows from notifications_outbox) + ``ack_notification`` (Hermes finalizes
each row with ok/failed). This is the schema-reality replacement for the
epic spec's invented Hermes inbound-HTTP delivery.

Each slash-command surface tool is intended to surface as a Discord slash
command — the dispatch contract is **a follow-up Hermes-skill bundle under
hermes-config/skills/mailbot/** per Story 6-0's RECONCILIATION-NOTES §6 item 1
(Story 5-6's config-YAML registry was based on an invented Hermes schema and
was retired by Story 6-0).

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

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.resources import TextResource
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyUrl

from mailbot_api.actions.types import (
    ACTION_PROPERTIES,
    EMAIL_LESS_ACTIONS,
    ActionType,
    is_send_family,
)
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
from mailbot_api.verbs.ack_notification import ack_notification as _ack_notification
from mailbot_api.verbs.analytics import render_spend_chart as _render_spend_chart
from mailbot_api.verbs.budget_admin import reset_degraded_mode as _reset_degraded_mode
from mailbot_api.verbs.cancel_action import cancel_action as _cancel_action
from mailbot_api.verbs.compose_digest import compose_digest as _compose_digest
from mailbot_api.verbs.cost import cost_breakdown as _cost_breakdown
from mailbot_api.verbs.finalize_digest_delivery import (
    finalize_digest_delivery as _finalize_digest_delivery,
)
from mailbot_api.verbs.mint_grant import mint_grant as _mint_grant
from mailbot_api.verbs.mint_sensitivity_token import (
    mint_sensitivity_token as _mint_sensitivity_token,
)
from mailbot_api.verbs.mute_category import mute_category as _mute_category
from mailbot_api.verbs.propose_action import propose_action as _propose_action
from mailbot_api.verbs.pull_pending_notifications import (
    pull_pending_notifications as _pull_pending_notifications,
)
from mailbot_api.verbs.revert_action import revert_action as _revert_action
from mailbot_api.verbs.revoke_grant import revoke_grant as _revoke_grant
from mailbot_api.verbs.router_control import (
    pause_router as _pause_router,
)
from mailbot_api.verbs.router_control import (
    resume_router as _resume_router,
)
from mailbot_api.verbs.schemas import FindEmailsFilter
from mailbot_api.verbs.unmute_category import unmute_category as _unmute_category

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
    """Construct the 22 tool wrappers closed over the given _ServerContext.
    (11 Story-5-2 baseline + 5 Story-5-6 slash-command surface + 1 Story-6-8
    analytics + 2 Story-6-3 notification dispatcher pull/ack +
    1 Story-6-4 unmute_category + 2 Story-6-5 digest compose/finalize.)

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
    # slash command to its corresponding tool via the (forthcoming) Hermes
    # skill bundle at hermes-config/skills/mailbot/ — see Story 6-0
    # RECONCILIATION-NOTES §6 item 1 for the carry-forward.

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

    # ---- Story 6-5: daily digest composer + delivery finalizer ----

    async def compose_digest(ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _compose_digest(db_path=server_ctx.require_db_path())
        except Exception as exc:  # noqa: BLE001
            _log_crash("compose_digest", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("compose_digest", sid, code, latency_ms)
        else:
            _log_ok("compose_digest", sid, latency_ms)
        return out

    async def finalize_digest_delivery(ctx: Context[Any, Any, Any]) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _finalize_digest_delivery(
                db_path=server_ctx.require_db_path()
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash(
                "finalize_digest_delivery", sid, exc,
                int((time.perf_counter() - t0) * 1000),
            )
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("finalize_digest_delivery", sid, code, latency_ms)
        else:
            _log_ok("finalize_digest_delivery", sid, latency_ms)
        return out

    # ---- Story 6-4: /unmute companion to Story 5-6's /mute ----

    async def unmute_category(
        category: str, ctx: Context[Any, Any, Any]
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _unmute_category(
                category, db_path=server_ctx.require_db_path()
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash("unmute_category", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("unmute_category", sid, code, latency_ms)
        else:
            _log_ok("unmute_category", sid, latency_ms)
        return out

    # ---- Story 6-3: notification dispatcher pull/ack surface ----

    async def pull_pending_notifications(
        ctx: Context[Any, Any, Any], limit: int = 10
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _pull_pending_notifications(
                limit, db_path=server_ctx.require_db_path()
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash(
                "pull_pending_notifications", sid, exc,
                int((time.perf_counter() - t0) * 1000),
            )
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("pull_pending_notifications", sid, code, latency_ms)
        else:
            _log_ok("pull_pending_notifications", sid, latency_ms)
        return out

    async def ack_notification(
        notification_id: int,
        delivery_status: str,
        ctx: Context[Any, Any, Any],
        error: str | None = None,
    ) -> Any:
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _ack_notification(
                notification_id,
                delivery_status,  # type: ignore[arg-type]
                error,
                db_path=server_ctx.require_db_path(),
            )
        except Exception as exc:  # noqa: BLE001
            _log_crash(
                "ack_notification", sid, exc,
                int((time.perf_counter() - t0) * 1000),
            )
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("ack_notification", sid, code, latency_ms)
        else:
            _log_ok("ack_notification", sid, latency_ms)
        return out

    # ---- Story 6-8: render_spend_chart (analytics surface, /spend) ----

    async def render_spend_chart(
        ctx: Context[Any, Any, Any], period: str = "month"
    ) -> Any:
        # Story 6-8 mirrors Story 5-6 CR-1 fix: default to "month" so the
        # Discord slash command's `required: false` period option works
        # end-to-end. The verb itself raises ValueError on any other string
        # via _period_window_start.
        #
        # F15 closure (Story 6-9 CP-2 walk attempt #4, 2026-06-04): the MCP
        # wrapper returns a tuple `(Image, metadata_dict)` so FastMCP emits
        # TWO content blocks per call — an `ImageContent` carrying the PNG
        # (which Hermes's `_cache_mcp_image_block` auto-caches and surfaces
        # as a native Discord attachment via the MEDIA tag pipeline) AND a
        # `TextContent` carrying the human/agent-readable metadata
        # (total_usd, task_count, top_task, etc.) so the assistant can
        # compose the documented "$X.XX spent {period}. Top task: ..."
        # summary line without a sibling MCP call.
        #
        # Non-MCP callers of `_render_spend_chart` (direct verb invocation,
        # CP-2 supplementary evidence path, tests) continue to receive the
        # `RenderSpendChartOut` Pydantic shape unchanged.
        sid = _session_id_from_ctx(ctx)
        t0 = time.perf_counter()
        try:
            out = await _render_spend_chart(period, db_path=server_ctx.require_db_path())  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            _log_crash("render_spend_chart", sid, exc, int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        code = _maybe_error_code(out)
        if code:
            _log_error_as_data("render_spend_chart", sid, code, latency_ms)
            # Error-as-data path: no PNG to wrap; return the structured
            # error shape so the agent sees the failure reason.
            return out
        _log_ok("render_spend_chart", sid, latency_ms)

        # F15: split the PNG bytes out into an MCP Image content block.
        # FastMCP's `_convert_to_content` flattens tuples into multiple
        # content blocks (Image → ImageContent, dict → TextContent).
        from mcp.server.fastmcp.utilities.types import Image as _MCPImage  # noqa: PLC0415

        metadata = {
            "mime_type": out.mime_type,
            "period": out.period,
            "total_usd": out.total_usd,
            "task_count": out.task_count,
            "top_task": out.top_task,
            "top_task_usd": out.top_task_usd,
        }
        return (
            _MCPImage(data=out.image_bytes, format="png"),
            metadata,
        )

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
        # Story 6-8 — analytics surface (/spend slash command).
        "render_spend_chart": render_spend_chart,
        # Story 6-3 — notification dispatcher pull/ack (Hermes-pulled urgent
        # delivery via MCP, replaces the invented inbound-HTTP epic spec).
        "pull_pending_notifications": pull_pending_notifications,
        "ack_notification": ack_notification,
        # Story 6-4 — /unmute companion to Story 5-6's /mute.
        "unmute_category": unmute_category,
        # Story 6-5 — daily digest assembly + delivery sweep.
        "compose_digest": compose_digest,
        "finalize_digest_delivery": finalize_digest_delivery,
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
        "SHARP EDGE: silences ALL tiers including urgent. Avoid indefinite "
        "mutes on ops categories (health, sync, router_anomaly). "
        "Slash-command surface: /mute (Story 5-6); "
        "Epic 6's dispatcher reads from notification_mutes."
    ),
    "render_spend_chart": (
        "Render a per-task cost chart for the period (today | week | month). "
        "Returns a 1200×800 PNG (image/png) ready to attach to a Discord message. "
        "Slash-command surface: /spend (Story 6-8); "
        "AR-ANALYTICS-1 + AR-ANALYTICS-2 — matplotlib Agg backend, bytes-only return."
    ),
    "pull_pending_notifications": (
        "Pull up to `limit` (≤ 25) urgent-tier notifications from "
        "notifications_outbox. Atomically claims each (delivery_status: "
        "pending → delivering). Hermes posts each to Discord then calls "
        "ack_notification. FIFO ordering by enqueued_at. Story 6-3."
    ),
    "ack_notification": (
        "Finalize a pulled notification by id with delivery_status='ok' "
        "(success → terminal ok) or 'failed' (retry under 5-attempt cap, "
        "else terminal failed_max_retries). Story 6-3."
    ),
    "unmute_category": (
        "Clear a notification mute by category. Companion to "
        "/mute (Story 5-6); idempotent — returns was_muted=False if "
        "the category had no mute. Slash-command surface: /unmute. Story 6-4."
    ),
    "compose_digest": (
        "Assemble the 08:00 daily digest payload: unread emails bucketed by "
        "importance, pending Tier-2 batches, queued tier='important' "
        "notifications, weekly artifacts. Cached projections only (Rule J + "
        "Rule A); no LLM call. Hermes's cron job invokes for the intro+post. "
        "Story 6-5."
    ),
    "finalize_digest_delivery": (
        "Mark every queued tier='important' notification as delivered via "
        "digest (delivery_status='ok_via_digest'). Called by Hermes after "
        "posting the digest. Idempotent. Story 6-5."
    ),
}


_EXPECTED_TOOL_COUNT = 22


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Story 6-19 (F29 closure) — `mailbot://action-types` MCP resource.
#
# Discoverability surface for the canonical 23 ActionType enum + per-action
# tier/sensitivity/send-family/email-less metadata. Hermes-side `list_resources`
# probes (which Hermes already does on session bootstrap) return this resource
# so an agent that hallucinated an action_type can recover via `read_resource`.
# Paired with the verb-shim error-time recovery hint (Story 6-19 AC-1) +
# SKILL.md constraint (Story 6-19 AC-3).
# ---------------------------------------------------------------------------

# Hand-curated anti-anchor list of synonyms Hermes's Haiku-4.5 has been
# observed to hallucinate or that the model's parameter-generation prior
# tends to pull toward. Listing them inline with the canonical enum creates
# a "things-that-look-right-but-aren't" signal at the same prompt-context
# location as the canonical list — same anti-anchoring discipline as
# Story 6-18 (qwen v1→v2 prompt). Additive; not load-bearing for correctness.
#
# CR-1 (2026-06-06, sonnet-4-6 review): tuple defense-in-depth — `Final`
# annotates name-binding only; using `tuple[str, ...]` instead of
# `list[str]` prevents any code that imports this constant from
# `.append('hacked')`-ing the underlying object and contaminating the
# resource body for all subsequent server builds. JSON serialization
# converts the tuple to a JSON array naturally.
_ACTION_TYPE_SYNONYMS_REJECTED: Final[tuple[str, ...]] = (
    "send_email", "sendReply", "send", "SEND_EMAIL", "reply",
    "send-reply", "delete_email", "trash", "remove",
)


def _build_action_types_resource_body() -> str:
    """Serialize the canonical ActionType enumeration as JSON for the
    `mailbot://action-types` MCP resource.

    Shape:
      - `action_types`: list of 23 dicts (sorted by `value`), each carrying
        `value` (snake_case), `tier`, `requires_sensitivity_token`,
        `is_send_family`, `is_email_less`.
      - `synonyms_rejected`: anti-anchor list of common hallucinations.
      - `constraint`: human-readable constraint string for prompt-context use.

    Built once at server-construction time. Deterministic across runs.
    """
    entries: list[dict[str, Any]] = []
    # Sorted by `.value` for determinism. Iterating ActionType yields enum
    # members; we sort the materialized list.
    for at in sorted(ActionType, key=lambda a: a.value):
        props = ACTION_PROPERTIES[at]
        entries.append(
            {
                "value": at.value,
                "tier": props.tier,
                "requires_sensitivity_token": props.requires_sensitivity_token,
                "is_send_family": is_send_family(at),
                "is_email_less": at in EMAIL_LESS_ACTIONS,
            }
        )
    body = {
        "action_types": entries,
        "synonyms_rejected": list(_ACTION_TYPE_SYNONYMS_REJECTED),
        "constraint": (
            "Pass the canonical snake_case `value` field as `action_type` "
            "(e.g., \"send_reply\"). Synonyms / variants / UPPER_SNAKE names "
            "are rejected with INVALID_ACTION_TYPE."
        ),
    }
    return json.dumps(body, separators=(",", ":"))


# CR-4 (2026-06-06, sonnet-4-6 review): cache the resource body at module
# level. The body is pure + deterministic; rebuilding it on every
# `build_mcp_server()` call (production once, tests many times) is wasted
# work. Pattern mirrors the existing `_TOOL_DESCRIPTIONS` module-level dict.
_ACTION_TYPES_RESOURCE_BODY: Final[str] = _build_action_types_resource_body()


def build_mcp_server(*, db_path: str | None = None) -> FastMCP:
    """Build and configure a FastMCP server with all 22 MailBot tools registered.
    (11 Story-5-2 baseline read+write verbs + 5 Story-5-6 slash-command surface
    verbs.)

    ``db_path`` may be passed eagerly (production binds it from the FastAPI
    lifespan once ``MAILBOT_DB_PATH`` is resolved) or left None and bound
    later via ``set_db_path(server, db_path)``.

    The returned server has a ``_mailbot_server_ctx`` attribute (the
    ``_ServerContext`` instance) for tests and the lifespan to mutate.
    """
    # Story 6-6.6 F6 closure: `streamable_http_path="/"` defeats the inner-
    # mount double-prefix bug. FastMCP's default registers an INNER Starlette
    # `Route("/mcp", endpoint=streamable_http_app)` inside its returned app.
    # `mailbot_api/main.py` then mounts that whole app via
    # `Mount("/mcp", app=streamable_http_app)`. Effective full path becomes
    # `/mcp/mcp`. POST /mcp from Hermes → Mount strips prefix → empty path →
    # 307 to `/mcp/` (Starlette redirect_slashes default) → still no match →
    # 404. By setting the inner path to `/`, the Mount prefix-strip lands on
    # `/` which matches the inner route directly, and the effective path is
    # back to `/mcp` as documented in `hermes-config/config.yaml`. One kwarg;
    # no Mount edit; no Hermes-side change.
    # F7 closure (2026-06-03): FastMCP 1.27.2 enables DNS-rebinding protection
    # by default, validating the Host header against `allowed_hosts`. Hermes
    # reaches us as `mailbot-api:8000` (Docker service hostname on the internal
    # `mailbot-net` network); pytest's TestClient sends `testserver`; local dev
    # via `localhost:8000` / `127.0.0.1:8000` (Story 6-1's curl checks +
    # operator debugging). Without these in the allow-list, every live request
    # returns HTTP 421 "Invalid Host header" and Hermes gives up after 3
    # retries with `421 Misdirected Request`. DNS-rebinding is a browser-side
    # attack vector; this server is reached only via the Docker-internal MCP
    # transport (never a browser), so the protection is belt-and-suspenders.
    # We keep it enabled with an explicit allow-list rather than disabling
    # entirely — preserves the FastMCP default-safe posture.
    server = FastMCP(
        name="mailbot-api",
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "mailbot-api:8000",
                "localhost:8000",
                "127.0.0.1:8000",
                "testserver",
            ],
        ),
        instructions=(
            "MailBot agent-facing verb surface. Read verbs (find_emails, "
            "hydrate_email, get_thread, count_emails, get_sender_summary) are "
            "projection-first per Rule J. Write verbs (propose_action, "
            "mint_grant, revoke_grant, cancel_action, revert_action, "
            "mint_sensitivity_token) follow the second-auth-check pattern. "
            "Slash-command-surface verbs (cost_breakdown, reset_degraded_mode, "
            "pause_router, resume_router, mute_category, render_spend_chart) "
            "are the verb side of Discord slash commands; agent invocations "
            "are allowed but should cite the user intent in the reasoning "
            "trace. "
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

    # Story 6-19 (F29 closure) — register the canonical ActionType
    # enumeration as an MCP resource so Hermes-side `list_resources` probes
    # surface the recovery path when the agent has hallucinated an
    # action_type value (e.g., `SEND_EMAIL` instead of `send_reply`).
    server.add_resource(
        TextResource(
            uri=AnyUrl("mailbot://action-types"),
            name="action-types",
            description=(
                "Canonical mailbot ActionType enumeration with tier + "
                "sensitivity-token requirement per action. Pass the `value` "
                "field as `propose_action(action_type=...)`."
            ),
            mime_type="application/json",
            text=_ACTION_TYPES_RESOURCE_BODY,
        )
    )

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
