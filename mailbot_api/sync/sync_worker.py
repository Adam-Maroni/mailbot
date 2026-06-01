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

from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.queries import (
    EMAIL_SOFT_DELETE,
    EMAIL_UPSERT,
    SENDER_UPSERT,
    SYNC_STATE_SELECT,
    SYNC_STATE_UPSERT,
    THREAD_UPSERT,
)
from mailbot_api.sync.oauth import get_access_token

logger = logging.getLogger(__name__)

_PROVIDER = "microsoft_graph"
_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_DEFAULT_DELTA_URL = f"{_GRAPH_BASE_URL}/me/mailFolders/inbox/messages/delta"

# Retry policy for 429 / 5xx during sync (per AR-D5-1 retry chain, adapted to inbound).
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1, 4, 16)


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


async def _upsert_message(db_path: str, message: dict[str, Any]) -> bool:
    """Upsert one email + its sender/thread. Returns True if a write occurred.

    Soft-delete branch: if the message is annotated `@removed`, we UPDATE the
    `emails.deleted_at` (no sender/thread upsert — the row may not exist yet on
    first sync, in which case the UPDATE is a no-op and that's fine).
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
        rowcount = await execute_write(db_path, EMAIL_SOFT_DELETE, (_utc_iso8601(), graph_id))
        if rowcount:
            logger.info(
                "sync soft-deleted email",
                extra={"event": "sync.email.soft_deleted", "graph_id": graph_id},
            )
        return bool(rowcount)

    change_marker = message.get("@odata.etag") or message.get("changeKey")
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
    headers = {"Authorization": f"Bearer {token}"}
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


async def run_once(
    db_path: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> SyncResult:
    """Run one delta-sync iteration. Returns a SyncResult.

    The transport param is for tests (httpx.MockTransport); production callers
    leave it None.
    """
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

            body = response.json()
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
