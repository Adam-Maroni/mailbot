"""Delta sync worker per architecture §"Outlook Sync" + FR-1.x.

`run_once(db_path)` performs one sync iteration:
  1. Read `sync_state.delta_link` for `microsoft_graph`.
  2. Acquire a Graph access token via `mailbot_api.sync.oauth.get_access_token`.
  3. GET /me/mailFolders/inbox/messages/delta (or follow stored delta_link).
  4. Iterate pages via `@odata.nextLink` until reaching `@odata.deltaLink`.
  5. For each message: upsert senders/threads/emails; mark soft-deleted on `@removed`.
  6. On 429: respect `Retry-After`, log, retry. Bounded retries.
  7. On full-batch success: write new delta_link + last_sync_at + messages_seen
     to sync_state.

Hard invariants:
  - Idempotent on `(graph_id, change_marker)` — re-running with no inbox changes
    produces zero writes (FR-1.4, AC-5).
  - delta_link advances ONLY after the full batch completes.
  - `has_attachments` is the only attachment metadata captured (FR-1.7).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from mailbot_api import notifications
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_SOFT_DELETE,
    EMAIL_UPSERT,
    SENDER_UPSERT,
    SYNC_STATE_SELECT,
    SYNC_STATE_UPSERT,
    SYNC_STATE_UPSERT_NULL_LINK,
    THREAD_UPSERT,
)
from mailbot_api.sync.graph_client import PREFER_IMMUTABLE_ID
from mailbot_api.sync.oauth import get_access_token

logger = logging.getLogger(__name__)

_PROVIDER = "microsoft_graph"
_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_DEFAULT_DELTA_URL = f"{_GRAPH_BASE_URL}/me/mailFolders/inbox/messages/delta"

# Retry policy for 429 / 5xx during sync (per AR-D5-1 retry chain, adapted to inbound).
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1, 4, 16)

# Module-level debounce flag for the "delta token reset" urgent notification
# (AC-4/5). Set when _handle_delta_token_invalidation fires; cleared when the
# next sync completes successfully (i.e., a fresh delta page is received with
# at least a deltaLink or nextLink). One notification per reset episode.
#
# Ownership note: TWO functions touch this flag via `global` declarations.
# `_handle_delta_token_invalidation` SETS it (after firing the notification);
# `run_once` CLEARS it (only after a clean delta-page success at the end of
# the cron iteration). The two `global` declarations are NOT redundant — both
# are required by Python scope rules for writes to a module-level name. The
# split intent: setting lives with the action that decides to notify; clearing
# lives with the success path that authoritatively knows the reset episode
# has ended. Future refactor target: wrap the flag in a small `_SyncState`
# dataclass if the two-process model later adds a second writer.
_resync_notification_fired = False


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_json(response: httpx.Response) -> Any:
    """Parse JSON or return {} — tolerant of malformed Graph responses.

    Used by the 404+syncStateNotFound branch to inspect the error body without
    risking an exception that would mask the underlying HTTP signal.
    """
    try:
        return response.json()
    except ValueError:
        return {}


@dataclass
class SyncResult:
    """Return shape from `run_once` — used by `worker.py`'s scheduler + tests."""

    messages_seen: int
    messages_upserted: int
    messages_soft_deleted: int
    duration_ms: int
    new_delta_link: str | None


async def _load_sync_state_delta_link(db_path: str) -> str | None:
    """Return the stored delta_link for the microsoft_graph provider (or None)."""
    row = await fetchone(db_path, SYNC_STATE_SELECT, (_PROVIDER,))
    if row is None:
        return None
    value = row[1]  # delta_link column
    if value is None:
        return None
    return str(value)


async def _persist_sync_state(
    db_path: str, delta_link: str, messages_seen: int
) -> None:
    await execute_write(
        db_path,
        SYNC_STATE_UPSERT,
        (_PROVIDER, delta_link, _utc_iso8601(), messages_seen),
    )


def _extract_sender(message: dict[str, Any]) -> tuple[str, str, str]:
    """Return (sender_id, display_name, domain) — sender_id is lowercased email."""
    sender_block = message.get("from") or message.get("sender") or {}
    email_block = sender_block.get("emailAddress", {}) if isinstance(sender_block, dict) else {}
    address = (email_block.get("address") or "").lower()
    display = email_block.get("name") or ""
    domain = address.partition("@")[2] if "@" in address else ""
    return address, display, domain


def _is_removed(message: dict[str, Any]) -> bool:
    """Graph marks deletes via `@removed` annotation on the message envelope."""
    return "@removed" in message


def _extract_removed_reason(message: dict[str, Any]) -> str | None:
    """Return Graph's @removed.reason ('changed' | 'deleted') or None if absent.

    Story 1-10 AC-3: distinguishes recoverable removals ('changed' — item moved
    out of synced folder set) from permanent ones ('deleted'). Tolerant of
    schema drift: if `@removed` is present but `reason` is missing or malformed,
    returns None — the column accepts NULL and Epic 4's reverter treats NULL
    as "unknown → confirm via Graph before restoring."
    """
    removed = message.get("@removed")
    if not isinstance(removed, dict):
        return None
    reason = removed.get("reason")
    return str(reason) if reason else None


def _extract_change_marker(message: dict[str, Any]) -> str | None:
    """Return Graph's `changeKey` for the message, with @odata.etag fallback.

    Story 1-10 AC-2: production Graph responses for the message resource ALWAYS
    carry `changeKey` (`@odata.etag` does not exist on that resource per the
    Graph API docs). The fallback to `@odata.etag` is purely defensive — if it
    ever fires, that's a schema drift worth logging.
    """
    change_key = message.get("changeKey")
    if change_key is not None:
        return str(change_key)
    fallback = message.get("@odata.etag")
    if fallback is not None:
        logger.warning(
            "sync change_marker fallback to @odata.etag",
            extra={
                "event": "sync.change_key_fallback",
                "graph_id": message.get("id"),
            },
        )
        return str(fallback)
    return None


async def _upsert_message(db_path: str, message: dict[str, Any]) -> bool:
    """Upsert one email + its sender/thread. Returns True if a write occurred.

    Soft-delete branch: if the message is annotated `@removed`, we UPDATE the
    `emails.deleted_at` + `emails.removed_reason` (no sender/thread upsert —
    the row may not exist yet on first sync, in which case the UPDATE is a
    no-op and that's fine).
    """
    graph_id = message.get("id")
    if not graph_id:
        # Malformed payload — skip and log; do NOT raise (FR-1.4 tolerance).
        logger.error(
            "sync skipped message with no id",
            extra={"event": "sync.message.malformed", "reason": "missing_id"},
        )
        return False

    if _is_removed(message):
        removed_reason = _extract_removed_reason(message)
        rowcount = await execute_write(
            db_path,
            EMAIL_SOFT_DELETE,
            (_utc_iso8601(), removed_reason, graph_id),
        )
        if rowcount:
            logger.info(
                "sync soft-deleted email",
                extra={
                    "event": "sync.email.soft_deleted",
                    "graph_id": graph_id,
                    "removed_reason": removed_reason,
                },
            )
        return bool(rowcount)

    change_marker = _extract_change_marker(message)
    sender_id, sender_display, sender_domain = _extract_sender(message)
    thread_id = message.get("conversationId")
    received_at = message.get("receivedDateTime") or _utc_iso8601()
    subject = message.get("subject", "")
    body_preview = message.get("bodyPreview", "")
    has_attachments = 1 if message.get("hasAttachments") else 0
    from_address = sender_id or None
    from_display_name = sender_display or None

    # Upsert sender first (FK target for emails).
    if sender_id:
        await execute_write(
            db_path,
            SENDER_UPSERT,
            (sender_id, sender_display or None, sender_domain or None, _utc_iso8601()),
        )

    # Upsert thread.
    if thread_id:
        await execute_write(
            db_path,
            THREAD_UPSERT,
            (thread_id, subject if subject else None, received_at),
        )

    rowcount = await execute_write(
        db_path,
        EMAIL_UPSERT,
        (
            graph_id,
            change_marker,
            thread_id,
            from_address,
            received_at,
            from_address,
            from_display_name,
            subject,
            body_preview,
            has_attachments,
        ),
    )
    return bool(rowcount)


def _build_http(
    transport: httpx.BaseTransport | None, timeout: float = 60.0
) -> httpx.AsyncClient:
    if transport is not None:
        # httpx.MockTransport is a BaseTransport that satisfies both sync + async
        # client transport requirements; mypy doesn't model this. Cast for mypy.
        async_transport: httpx.AsyncBaseTransport = transport  # type: ignore[assignment]
        return httpx.AsyncClient(transport=async_transport, timeout=httpx.Timeout(timeout))
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout))


async def _fetch_page_with_retry(
    http: httpx.AsyncClient, url: str, token: str
) -> httpx.Response:
    """GET one delta page, retrying on 429 / 5xx per the retry chain."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": PREFER_IMMUTABLE_ID,
    }
    last_response: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES + 1):
        response = await http.get(url, headers=headers)
        last_response = response
        if response.status_code < 400:
            return response
        if response.status_code == 429 or response.status_code in (502, 503, 504):
            retry_after_header = response.headers.get("Retry-After", "")
            try:
                wait_s = int(retry_after_header)
            except ValueError:
                wait_s = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
            logger.info(
                "sync throttled",
                extra={
                    "event": "sync.throttled",
                    "wait_seconds": wait_s,
                    "attempt": attempt + 1,
                    "status_code": response.status_code,
                },
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(wait_s)
                continue
        # Non-retryable error or retries exhausted.
        break
    assert last_response is not None  # noqa: S101 — loop always assigns
    return last_response


def _is_sync_state_not_found(body: Any) -> bool:
    """Return True if the response body's `code` field contains 'syncStateNotFound'.

    Story 1-10 AC-5: case-insensitive substring match — the Graph docs don't pin
    the exact casing. Real Graph error responses nest the code under
    `body["error"]["code"]` (the documented OData error envelope); some test
    fixtures and earlier docs use a flat `body["code"]` shape. We check the
    nested path first, fall back to the flat path. Tolerant of malformed
    bodies (non-dict, missing `code`).
    """
    if not isinstance(body, dict):
        return False
    error_block = body.get("error")
    code: Any = None
    if isinstance(error_block, dict):
        code = error_block.get("code")
    if not isinstance(code, str):
        code = body.get("code")
    if not isinstance(code, str):
        return False
    return "syncstatenotfound" in code.lower()


async def _handle_delta_token_invalidation(db_path: str, reason: str) -> None:
    """Clear sync_state.delta_link and fire a debounced urgent notification.

    Story 1-10 AC-4/5: shared recovery path for HTTP 410 Gone and HTTP 404 with
    `syncStateNotFound`. The two surfaces are distinct in Microsoft's docs but
    the recovery is identical — restart delta from scratch. Centralizing here
    keeps observability separable (different `reason` strings in the log line)
    while keeping the action one-place-to-change-if-Microsoft-adds-a-third.

    Notification debounce: the module-level `_resync_notification_fired` flag
    prevents notification spam when delta endpoint 410s persistently. Cleared
    on the next successful delta page (see run_once after final_delta_link
    assignment).
    """
    global _resync_notification_fired
    logger.warning(
        "sync delta token invalidated",
        extra={"event": "sync.delta_token_invalidated", "reason": reason},
    )
    await execute_write(
        db_path,
        SYNC_STATE_UPSERT_NULL_LINK,
        (_PROVIDER, _utc_iso8601()),
    )
    if not _resync_notification_fired:
        notifications.send_urgent("delta token reset — full resync in progress")
        _resync_notification_fired = True


async def run_once(
    db_path: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> SyncResult:
    """Run one delta-sync iteration. Returns a SyncResult.

    The transport param is for tests (httpx.MockTransport); production callers
    leave it None.
    """
    global _resync_notification_fired
    start = time.monotonic()

    stored_delta = await _load_sync_state_delta_link(db_path)
    token = await get_access_token(db_path, transport=transport)

    url: str | None = stored_delta or _DEFAULT_DELTA_URL
    messages_seen = 0
    messages_upserted = 0
    messages_soft_deleted = 0
    final_delta_link: str | None = None

    async with _build_http(transport) as http:
        while url is not None:
            response = await _fetch_page_with_retry(http, url, token)
            if response.status_code >= 400:
                # Story 1-10 AC-4/5: detect delta-token invalidation BEFORE the
                # generic failure return. Both 410 (token expired/cache evicted)
                # and 404+syncStateNotFound (token refers to deleted state)
                # share the same recovery path: clear delta_link, notify once,
                # return cleanly so the next worker tick performs a fresh delta.
                if response.status_code == 410:
                    await _handle_delta_token_invalidation(db_path, reason="410_gone")
                    duration_ms = int((time.monotonic() - start) * 1000)
                    return SyncResult(
                        messages_seen=messages_seen,
                        messages_upserted=messages_upserted,
                        messages_soft_deleted=messages_soft_deleted,
                        duration_ms=duration_ms,
                        new_delta_link=None,
                    )
                if response.status_code == 404:
                    body = _safe_json(response)
                    if _is_sync_state_not_found(body):
                        await _handle_delta_token_invalidation(
                            db_path, reason="syncStateNotFound"
                        )
                        duration_ms = int((time.monotonic() - start) * 1000)
                        return SyncResult(
                            messages_seen=messages_seen,
                            messages_upserted=messages_upserted,
                            messages_soft_deleted=messages_soft_deleted,
                            duration_ms=duration_ms,
                            new_delta_link=None,
                        )
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "sync page fetch failed",
                    extra={
                        "event": "sync.page.failed",
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                )
                # Bail out WITHOUT advancing delta_link — next sync will retry.
                return SyncResult(
                    messages_seen=messages_seen,
                    messages_upserted=messages_upserted,
                    messages_soft_deleted=messages_soft_deleted,
                    duration_ms=duration_ms,
                    new_delta_link=None,
                )

            body = _safe_json(response)
            if not isinstance(body, dict):
                # Non-JSON or non-object body on a 2xx response — gateway-injected
                # HTML page or similar. Treat as malformed; do not advance delta_link.
                logger.error(
                    "sync malformed delta page body",
                    extra={
                        "event": "sync.page.malformed",
                        "reason": "non_dict_body",
                    },
                )
                url = None
                break
            messages = body.get("value", []) or []
            for message in messages:
                messages_seen += 1
                if _is_removed(message):
                    if await _upsert_message(db_path, message):
                        messages_soft_deleted += 1
                else:
                    if await _upsert_message(db_path, message):
                        messages_upserted += 1
                # Progress log every 500 messages.
                if messages_seen % 500 == 0:
                    logger.info(
                        "sync progress",
                        extra={
                            "event": "sync.progress",
                            "messages_seen": messages_seen,
                            "messages_upserted": messages_upserted,
                        },
                    )

            next_link = body.get("@odata.nextLink")
            delta_link = body.get("@odata.deltaLink")
            if delta_link:
                final_delta_link = delta_link
                url = None  # final page reached
            elif next_link:
                url = next_link
            else:
                # Neither nextLink nor deltaLink — malformed page. Stop without advance.
                logger.error(
                    "sync malformed delta page",
                    extra={"event": "sync.page.malformed"},
                )
                url = None

    # Persist new delta_link ONLY after full batch completes.
    if final_delta_link is not None:
        await _persist_sync_state(db_path, final_delta_link, messages_seen)
        # Story 1-10: clear the resync-notification debounce flag on a clean
        # sync — the next 410/syncStateNotFound episode is allowed to notify
        # again. This is the only place the flag resets to False.
        _resync_notification_fired = False

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "sync completed",
        extra={
            "event": "sync.completed",
            "messages_seen": messages_seen,
            "messages_upserted": messages_upserted,
            "messages_soft_deleted": messages_soft_deleted,
            "duration_ms": duration_ms,
        },
    )

    return SyncResult(
        messages_seen=messages_seen,
        messages_upserted=messages_upserted,
        messages_soft_deleted=messages_soft_deleted,
        duration_ms=duration_ms,
        new_delta_link=final_delta_link,
    )
