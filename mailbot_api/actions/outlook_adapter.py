"""OutlookGraphWriteAdapter — Story 4-5.

Implements GraphWriteAdapter Protocol (from Story 4-4) against the real
Microsoft Graph endpoints. Per-action-type dispatch table maps every
Tier-1/2/3 ActionType to its Graph endpoint. Wrapped in the AR-D5-1 error-
classified retry chain (429/503/timeout → exponential 1s/4s/16s × 3; 4xx
non-429 → immediate; 5xx non-503 → 1 retry).

Local-only actions (ADD_LOCAL_CATEGORY, REMOVE_LOCAL_CATEGORY per FR-5.1)
return ok=True without hitting Graph.

Rule B: this is one of TWO files that may touch graph.microsoft.com (the
other being mailbot_api/sync/graph_client.py). Selective-import boundary
enforced by scripts/check_boundaries.py — the allowlist for the read-side
GET /me /messages etc. is extended here for the write-side endpoints.

References:
  - AR-D5-1 retry chain
  - AR-D5-2 budget consumed on failure (drainer enforces; this adapter just
    reports the outcome)
  - FR-5.1 local-only category actions
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import httpx

from mailbot_api.actions.graph_write import GraphApplyResult, GraphReadResult
from mailbot_api.actions.types import ActionType

if TYPE_CHECKING:
    from mailbot_api.actions.drainer import PendingActionRow

_logger = logging.getLogger(__name__)

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_WRITE_TIMEOUT_SECONDS = 30.0
_BACKOFF_SCHEDULE = (1, 4, 16)
_MAX_RETRIES = 3


@dataclass(frozen=True)
class _Dispatch:
    """Per-action-type Graph dispatch instruction."""

    method: str  # "GET" / "POST" / "PATCH" / "DELETE"
    path_template: str  # uses {id} substitution; "" for local-only actions
    build_body_fn: Callable[["PendingActionRow"], dict[str, Any] | None]
    local_only: bool = False


def _body_mark_read(row: "PendingActionRow") -> dict[str, Any]:
    return {"isRead": True}


def _body_mark_unread(row: "PendingActionRow") -> dict[str, Any]:
    return {"isRead": False}


def _body_move(row: "PendingActionRow") -> dict[str, Any]:
    # Destination folder id MUST be in payload for explicit moves.
    # For ARCHIVE / MARK_JUNK / MOVE_TO_INBOX, the destination resolves to
    # well-known well-known-folder names: "archive", "junkemail", "inbox".
    destination = row.payload.get("destination_folder_id")
    if destination is None:
        destination = _DEFAULT_FOLDERS.get(row.action_type, "inbox")
    return {"destinationId": destination}


def _body_send_reply(row: "PendingActionRow") -> dict[str, Any]:
    # Graph reply expects: {"comment": "...", "message": {...}}
    # Story 4-5 ships the simplest shape — body as `comment`.
    return {"comment": row.payload.get("body", "")}


def _body_send_new_email(row: "PendingActionRow") -> dict[str, Any]:
    # Graph /sendMail expects {"message": {"subject", "body", "toRecipients", ...}}
    to_recipients = [
        {"emailAddress": {"address": addr}} for addr in row.payload.get("to", [])
    ]
    return {
        "message": {
            "subject": row.payload.get("subject", ""),
            "body": {
                "contentType": "Text",
                "content": row.payload.get("body", ""),
            },
            "toRecipients": to_recipients,
        },
        "saveToSentItems": True,
    }


def _body_send_forward(row: "PendingActionRow") -> dict[str, Any]:
    to_recipients = [
        {"emailAddress": {"address": addr}} for addr in row.payload.get("to", [])
    ]
    return {
        "comment": row.payload.get("body", ""),
        "toRecipients": to_recipients,
    }


def _body_modify_rule(row: "PendingActionRow") -> dict[str, Any]:
    # Pass-through the full payload as the rule body. Spec doesn't pin shape;
    # operator supplies a Graph-shaped messageRule resource via payload["rule"].
    rule_body = row.payload.get("rule", {})
    return rule_body if isinstance(rule_body, dict) else {}


def _body_passthrough(row: "PendingActionRow") -> dict[str, Any]:
    return row.payload


def _body_none(row: "PendingActionRow") -> None:
    return None


# Graph well-known-folder names for the move-without-explicit-destination case.
# Note: the strings "archive" and "inbox" collide with ActionType.ARCHIVE.value
# and ActionType.MOVE_TO_INBOX's family — but here they're Microsoft Graph
# well-known-folder identifiers, NOT action-type literals. The boundary check
# allowlists this file for that reason (see scripts/check_boundaries.py).
_DEFAULT_FOLDERS = {
    ActionType.ARCHIVE: "archive",
    ActionType.MARK_JUNK: "junkemail",
    ActionType.MOVE_TO_INBOX: "inbox",
}

_DISPATCH_TABLE: dict[ActionType, _Dispatch] = {
    ActionType.MARK_READ: _Dispatch("PATCH", "/me/messages/{id}", _body_mark_read),
    ActionType.MARK_UNREAD: _Dispatch("PATCH", "/me/messages/{id}", _body_mark_unread),
    ActionType.ADD_LOCAL_CATEGORY: _Dispatch("", "", _body_none, local_only=True),
    ActionType.REMOVE_LOCAL_CATEGORY: _Dispatch("", "", _body_none, local_only=True),
    ActionType.MOVE_TO_TRIAGE_FOLDER: _Dispatch("POST", "/me/messages/{id}/move", _body_move),
    ActionType.ARCHIVE: _Dispatch("POST", "/me/messages/{id}/move", _body_move),
    ActionType.MARK_JUNK: _Dispatch("POST", "/me/messages/{id}/move", _body_move),
    ActionType.MOVE_TO_USER_FOLDER: _Dispatch("POST", "/me/messages/{id}/move", _body_move),
    ActionType.UNSUBSCRIBE: _Dispatch(
        "POST", "", _body_passthrough,
    ),  # path comes from payload["unsubscribe_url"]
    ActionType.MOVE_TO_INBOX: _Dispatch("POST", "/me/messages/{id}/move", _body_move),
    ActionType.DELETE: _Dispatch("DELETE", "/me/messages/{id}", _body_none),
    ActionType.SEND_REPLY: _Dispatch("POST", "/me/messages/{id}/reply", _body_send_reply),
    ActionType.SEND_NEW_EMAIL: _Dispatch("POST", "/me/sendMail", _body_send_new_email),
    ActionType.SEND_FORWARD: _Dispatch("POST", "/me/messages/{id}/forward", _body_send_forward),
    # REPLY_TO_INACTIVE_THREAD uses the SEND_REPLY endpoint; thread-age precondition
    # check is deferred to a future story (Story 1-7 doesn't ship last_received_at).
    ActionType.REPLY_TO_INACTIVE_THREAD: _Dispatch(
        "POST", "/me/messages/{id}/reply", _body_send_reply,
    ),
    ActionType.MODIFY_INBOX_RULE: _Dispatch(
        "POST", "/me/mailFolders/inbox/messageRules", _body_modify_rule,
    ),
    ActionType.MODIFY_OUTLOOK_FILTER: _Dispatch(
        "POST", "/me/mailFolders/inbox/messageRules", _body_modify_rule,
    ),
    ActionType.TOUCH_DELEGATED_MAILBOX: _Dispatch(
        "POST", "/users/{upn}/messages", _body_passthrough,
    ),
}


class OutlookGraphWriteAdapter:
    """Real Graph implementation of GraphWriteAdapter (Story 4-5).

    Construct with an access-token provider (the GraphClient handles refresh).
    Tests inject `transport=httpx.MockTransport(...)` to stub responses.
    """

    def __init__(
        self,
        *,
        access_token_provider: Callable[[], str],
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        timeout_seconds: float = _WRITE_TIMEOUT_SECONDS,
    ) -> None:
        self._token_provider = access_token_provider
        # httpx.MockTransport is duck-compatible with both sync + async. We
        # accept BaseTransport at construction and cast at use time.
        self._transport = transport
        self._timeout = httpx.Timeout(timeout_seconds)

    def _build_client(self) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport,  # type: ignore[arg-type]
                timeout=self._timeout,
            )
        return httpx.AsyncClient(timeout=self._timeout)

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult:
        dispatch = _DISPATCH_TABLE.get(row.action_type)
        if dispatch is None:
            return GraphApplyResult(
                ok=False,
                error=f"no_dispatch_for_{row.action_type.value}",
                retry_count=0,
            )

        # Local-only actions (FR-5.1 LOCAL_CATEGORY family) return immediately
        # without a Graph call.
        if dispatch.local_only:
            return GraphApplyResult(ok=True, error=None, retry_count=0)

        # Build URL.
        if row.action_type == ActionType.UNSUBSCRIBE:
            url = row.payload.get("unsubscribe_url", "")
            if not url:
                return GraphApplyResult(
                    ok=False, error="unsubscribe_url_missing", retry_count=0,
                )
        elif "{id}" in dispatch.path_template:
            if row.email_id is None:
                return GraphApplyResult(
                    ok=False,
                    error=f"missing_email_id_for_{row.action_type.value}",
                    retry_count=0,
                )
            url = _GRAPH_BASE_URL + dispatch.path_template.replace("{id}", row.email_id)
        elif "{upn}" in dispatch.path_template:
            upn = row.payload.get("upn", "")
            if not upn:
                return GraphApplyResult(
                    ok=False, error="upn_missing_for_delegated", retry_count=0,
                )
            url = _GRAPH_BASE_URL + dispatch.path_template.replace("{upn}", upn)
        else:
            url = _GRAPH_BASE_URL + dispatch.path_template

        body = dispatch.build_body_fn(row)

        return await self._dispatch_with_retry(dispatch.method, url, body)

    async def read_move_pre_state(self, email_id: str) -> GraphReadResult:
        """Story 10-2: read the message's current parentFolderId — the
        pre-state a move-family revert needs. Same token seam and AR-D5-1
        retry semantics as dispatch; read-only (GET, $select-narrowed).

        The 10-1 walk proved this is the ONLY viable capture point: the local
        emails table has no folder column, and the read must happen before the
        move dispatch mutates parentFolderId.
        """
        url = (
            _GRAPH_BASE_URL
            + "/me/messages/"
            + email_id
            + "?$select=parentFolderId"
        )
        result, response = await self._request_with_retry("GET", url, None)
        if not result.ok or response is None:
            return GraphReadResult(ok=False, error=result.error or "unknown")
        try:
            parent_folder_id = response.json().get("parentFolderId")
        except ValueError:
            return GraphReadResult(ok=False, error="pre_state_body_not_json")
        if not parent_folder_id:
            return GraphReadResult(ok=False, error="parent_folder_id_absent")
        return GraphReadResult(ok=True, source_folder_id=str(parent_folder_id))

    async def _dispatch_with_retry(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
    ) -> GraphApplyResult:
        """AR-D5-1 retry chain. Returns the final GraphApplyResult after at
        most _MAX_RETRIES attempts."""
        result, _response = await self._request_with_retry(method, url, body)
        return result

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
    ) -> tuple[GraphApplyResult, httpx.Response | None]:
        """AR-D5-1 retry chain, returning the successful response alongside
        the result so read paths (Story 10-2 pre-state) can parse the body.
        The response is non-None only when result.ok is True."""
        last_error = "unknown"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                token = self._token_provider()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                async with self._build_client() as client:
                    response = await client.request(method, url, headers=headers, json=body)
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)])
                    continue
                return (GraphApplyResult(ok=False, error="timeout", retry_count=attempt), None)
            except httpx.TransportError as exc:
                last_error = f"transport:{type(exc).__name__}"
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)])
                    continue
                return (GraphApplyResult(ok=False, error=last_error, retry_count=attempt), None)

            status = response.status_code
            if 200 <= status < 300:
                return (GraphApplyResult(ok=True, error=None, retry_count=attempt), response)

            # Per AR-D5-1: 429/503 → exponential backoff up to 3 retries.
            if status in (429, 503):
                if attempt < _MAX_RETRIES:
                    # Respect Retry-After if present; else use backoff schedule.
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            wait = _BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)]
                    else:
                        wait = _BACKOFF_SCHEDULE[min(attempt, len(_BACKOFF_SCHEDULE) - 1)]
                    await asyncio.sleep(wait)
                    continue
                return (
                    GraphApplyResult(
                        ok=False, error=f"provider_{status}_retry_exhausted", retry_count=attempt,
                    ),
                    None,
                )

            # 5xx non-503 → 1 retry then fail (per AR-D5-1).
            if 500 <= status < 600:
                if attempt < 1:
                    await asyncio.sleep(_BACKOFF_SCHEDULE[0])
                    continue
                return (
                    GraphApplyResult(
                        ok=False, error=f"provider_5xx_{status}", retry_count=attempt,
                    ),
                    None,
                )

            # 4xx non-429 → immediate fail.
            if 400 <= status < 500:
                return (
                    GraphApplyResult(
                        ok=False, error=f"provider_4xx_{status}", retry_count=attempt,
                    ),
                    None,
                )

            # Unknown — defensive.
            return (
                GraphApplyResult(
                    ok=False, error=f"unexpected_status_{status}", retry_count=attempt,
                ),
                None,
            )

        return (GraphApplyResult(ok=False, error=last_error, retry_count=_MAX_RETRIES), None)


__all__ = ["OutlookGraphWriteAdapter"]
