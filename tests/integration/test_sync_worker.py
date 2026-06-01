"""Integration tests for sync_worker.run_once per Story 1-7.

Tests run against:
  - real on-disk SQLite (tmp_path) with all migrations applied
  - mocked httpx transport at the network boundary (Graph identity + Graph API)

Tests cover: full delta page → email/sender/thread upsert; idempotent re-run;
@removed soft-delete; multi-page pagination (nextLink); 429 retry with
Retry-After; idempotency on re-processed payload.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.sync.sync_worker import run_once

_BASE_ENV = {
    "OUTLOOK_CLIENT_ID": "test-client",
    "OUTLOOK_CLIENT_SECRET": "test-secret",
    "OUTLOOK_TENANT_ID": "test-tenant",
    "OUTLOOK_REFRESH_TOKEN": "rt-bootstrap",
    "MAILBOT_DB_PATH": "/tmp/mailbot-test.db",
}


def _set_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        if k != "MAILBOT_DB_PATH":
            monkeypatch.setenv(k, v)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


def _make_message(
    graph_id: str,
    *,
    subject: str = "Hello",
    sender_email: str = "alice@example.com",
    sender_name: str = "Alice",
    received_at: str = "2026-06-01T08:00:00Z",
    conversation_id: str = "conv-1",
    body_preview: str = "Hi there",
    has_attachments: bool = False,
    change_marker: str = "etag-v1",
    removed: bool = False,
) -> dict:
    msg: dict = {
        "id": graph_id,
        "@odata.etag": change_marker,
        "subject": subject,
        "bodyPreview": body_preview,
        "hasAttachments": has_attachments,
        "receivedDateTime": received_at,
        "conversationId": conversation_id,
        "from": {"emailAddress": {"address": sender_email, "name": sender_name}},
    }
    if removed:
        msg["@removed"] = {"reason": "deleted"}
    return msg


def _transport(
    pages: list[dict],
    token_response: dict | None = None,
    throttle_first_n: int = 0,
    throttle_retry_after: int = 1,
) -> tuple[httpx.MockTransport, list[str]]:
    """Build a MockTransport returning the supplied pages in order.

    Token endpoint responds with `token_response` (default valid).
    `throttle_first_n` = number of times to return 429 before serving the first page.
    Returns (transport, request_log).
    """
    token_response = token_response or {
        "access_token": "at-test",
        "refresh_token": "rt-rotated",
        "expires_in": 3600,
    }
    request_log: list[str] = []
    page_iter = iter(pages)
    throttle_remaining = {"n": throttle_first_n}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        request_log.append(url)
        if "login.microsoftonline.com" in request.url.host:
            return httpx.Response(200, json=token_response)
        if "graph.microsoft.com" in request.url.host:
            if throttle_remaining["n"] > 0:
                throttle_remaining["n"] -= 1
                return httpx.Response(
                    429, headers={"Retry-After": str(throttle_retry_after)}, json={"error": "throttled"}
                )
            try:
                page = next(page_iter)
            except StopIteration:
                return httpx.Response(404, json={"error": "no_more_pages"})
            return httpx.Response(200, json=page)
        return httpx.Response(404, json={"error": "unhandled"})

    return httpx.MockTransport(handler), request_log


async def test_first_sync_upserts_email_sender_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page = {
        "value": [_make_message("graph-id-1")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?$deltatoken=DELTA_1",
    }
    transport, _log = _transport([page])

    result = await run_once(db_path, transport=transport)
    assert result.messages_seen == 1
    assert result.messages_upserted == 1
    assert result.messages_soft_deleted == 0
    assert result.new_delta_link and "DELTA_1" in result.new_delta_link

    # Verify rows landed.
    emails = await fetchall(db_path, "SELECT graph_id, change_marker, subject, has_attachments FROM emails", ())
    assert emails == [("graph-id-1", "etag-v1", "Hello", 0)]
    senders = await fetchall(db_path, "SELECT id, display_name, domain FROM senders", ())
    assert ("alice@example.com", "Alice", "example.com") in senders
    threads = await fetchall(db_path, "SELECT id, message_count FROM threads", ())
    assert ("conv-1", 1) in threads
    # sync_state delta_link persisted.
    state = await fetchone(
        db_path,
        "SELECT delta_link, last_sync_messages_seen FROM sync_state WHERE provider = ?",
        ("microsoft_graph",),
    )
    assert state is not None
    assert "DELTA_1" in state[0]
    assert state[1] == 1


async def test_idempotent_resync_with_no_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second sync against an empty delta page produces zero upserts."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page1 = {
        "value": [_make_message("graph-id-1")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    page2_empty = {
        "value": [],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D2",
    }

    transport1, _ = _transport([page1])
    await run_once(db_path, transport=transport1)

    email_count_before = await fetchone(db_path, "SELECT COUNT(*) FROM emails", ())
    assert email_count_before == (1,)

    transport2, _ = _transport([page2_empty])
    result = await run_once(db_path, transport=transport2)
    assert result.messages_seen == 0
    assert result.messages_upserted == 0
    assert result.messages_soft_deleted == 0

    email_count_after = await fetchone(db_path, "SELECT COUNT(*) FROM emails", ())
    assert email_count_after == (1,)  # unchanged


async def test_idempotent_on_replayed_payload_same_change_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-processing the SAME delta payload twice: second pass writes zero new
    rows (FR-1.4 idempotency on (graph_id, change_marker))."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page = {
        "value": [_make_message("g-1"), _make_message("g-2", sender_email="bob@example.com")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }

    # First sync.
    transport, _ = _transport([page])
    r1 = await run_once(db_path, transport=transport)
    assert r1.messages_upserted == 2

    # Replay same payload (NOTE: a fresh transport so the page iterator resets).
    transport2, _ = _transport([page])
    r2 = await run_once(db_path, transport=transport2)
    assert r2.messages_seen == 2
    # change_marker hasn't changed → EMAIL_UPSERT's WHERE clause makes the UPDATE a no-op.
    # But the row still passes through ON CONFLICT, which rowcount may report as 1.
    # We accept rowcount-driven counts here; the real invariant is that the COUNT(*)
    # of emails is unchanged.
    count = await fetchone(db_path, "SELECT COUNT(*) FROM emails", ())
    assert count == (2,)


async def test_removed_annotation_soft_deletes_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page1 = {
        "value": [_make_message("g-1")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    page2 = {
        "value": [_make_message("g-1", removed=True)],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D2",
    }

    transport1, _ = _transport([page1])
    await run_once(db_path, transport=transport1)

    transport2, _ = _transport([page2])
    r = await run_once(db_path, transport=transport2)
    assert r.messages_soft_deleted == 1

    row = await fetchone(db_path, "SELECT deleted_at FROM emails WHERE graph_id = ?", ("g-1",))
    assert row is not None
    assert row[0] is not None  # deleted_at set


async def test_multi_page_pagination_via_next_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page1 = {
        "value": [_make_message(f"g-{i}") for i in range(3)],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/delta?$skiptoken=PAGE2",
    }
    page2 = {
        "value": [_make_message(f"g-{i}") for i in range(3, 5)],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D_FINAL",
    }

    transport, _ = _transport([page1, page2])
    result = await run_once(db_path, transport=transport)
    assert result.messages_seen == 5
    assert result.messages_upserted == 5
    assert "D_FINAL" in (result.new_delta_link or "")

    count = await fetchone(db_path, "SELECT COUNT(*) FROM emails", ())
    assert count == (5,)


async def test_429_retry_with_retry_after_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page = {
        "value": [_make_message("g-1")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }

    # First 2 requests return 429 with Retry-After: 0; third succeeds.
    transport, log = _transport([page], throttle_first_n=2, throttle_retry_after=0)
    result = await run_once(db_path, transport=transport)
    assert result.messages_upserted == 1
    # The Graph API was hit at least 3 times (2 throttle + 1 success) plus the
    # token-exchange ping. The exact count depends on whether the worker re-fetches
    # the token; we just assert we got past the throttling.
    graph_hits = [u for u in log if "graph.microsoft.com" in u]
    assert len(graph_hits) >= 3


async def test_delta_link_not_advanced_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the page fetch ultimately fails (e.g., 500 after exhausted retries),
    sync_state.delta_link is NOT advanced."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    # Throttle past max retries → final response is 429.
    transport, _ = _transport([], throttle_first_n=10, throttle_retry_after=0)
    result = await run_once(db_path, transport=transport)
    assert result.new_delta_link is None

    state = await fetchone(db_path, "SELECT delta_link FROM sync_state WHERE provider = ?", ("microsoft_graph",))
    # No row at all OR row exists but delta_link is None — both signal "no advance."
    assert state is None or state[0] is None


async def test_malformed_message_skipped_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page = {
        "value": [
            {"subject": "no id here"},  # missing id
            _make_message("g-ok"),
        ],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    transport, _ = _transport([page])
    result = await run_once(db_path, transport=transport)
    assert result.messages_seen == 2
    assert result.messages_upserted == 1  # only the well-formed one
