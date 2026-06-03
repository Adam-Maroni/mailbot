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
    removed_reason: str = "deleted",
) -> dict:
    # Story 1-10: production Graph messages carry `changeKey` (not @odata.etag,
    # which doesn't exist on the message resource). Tests emit changeKey by
    # default; specific fallback tests can mutate the dict to remove changeKey
    # and add @odata.etag.
    msg: dict = {
        "id": graph_id,
        "changeKey": change_marker,
        "subject": subject,
        "bodyPreview": body_preview,
        "hasAttachments": has_attachments,
        "receivedDateTime": received_at,
        "conversationId": conversation_id,
        "from": {"emailAddress": {"address": sender_email, "name": sender_name}},
    }
    if removed:
        msg["@removed"] = {"reason": removed_reason}
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

    # Story 1-10 AC-3: removed_reason captured alongside deleted_at.
    row = await fetchone(
        db_path,
        "SELECT deleted_at, removed_reason FROM emails WHERE graph_id = ?",
        ("g-1",),
    )
    assert row is not None
    assert row[0] is not None  # deleted_at set
    assert row[1] == "deleted"  # removed_reason captured from @removed.reason


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


# --- Story 1-10: delta-token invalidation + duplicate-replay tests ---


def _transport_with_status(
    status: int,
    body: dict | None = None,
    token_response: dict | None = None,
) -> tuple[httpx.MockTransport, list[str]]:
    """Build a MockTransport that returns the given (status, body) for every
    Graph data-plane request. Token endpoint still returns 200 OK.

    Used by Story 1-10 tests for the 410 Gone and 404 syncStateNotFound branches.
    """
    token_response = token_response or {
        "access_token": "at-test",
        "refresh_token": "rt-rotated",
        "expires_in": 3600,
    }
    request_log: list[str] = []
    body = body or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        request_log.append(url)
        if "login.microsoftonline.com" in request.url.host:
            return httpx.Response(200, json=token_response)
        if "graph.microsoft.com" in request.url.host:
            return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "unhandled"})

    return httpx.MockTransport(handler), request_log


async def test_handles_410_gone_clears_delta_link_and_notifies_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: HTTP 410 from the delta endpoint clears sync_state.delta_link,
    fires one urgent notification, and returns without raising."""
    import mailbot_api.sync.sync_worker as sync_worker

    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    # Logs land in a tmp dir so the assertion is sandboxed.
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    # Reset the module-level debounce flag (test isolation).
    sync_worker._resync_notification_fired = False

    # Seed sync_state with a stored delta_link, so the worker would otherwise
    # follow it.
    from mailbot_api.db.connection import execute_write
    await execute_write(
        db_path,
        "INSERT INTO sync_state (provider, delta_link, last_sync_at, last_sync_messages_seen) "
        "VALUES (?, ?, ?, ?)",
        ("microsoft_graph", "https://graph.microsoft.com/v1.0/delta?$deltatoken=OLD", "2026-06-01T00:00:00Z", 0),
    )

    transport, _ = _transport_with_status(410, {"code": "syncStateInvalid"})
    result = await run_once(db_path, transport=transport)

    # Worker returned cleanly without raising.
    assert result.new_delta_link is None
    assert result.messages_seen == 0

    # sync_state.delta_link cleared.
    state = await fetchone(
        db_path, "SELECT delta_link FROM sync_state WHERE provider = ?", ("microsoft_graph",)
    )
    assert state is not None
    assert state[0] is None  # NULL — fresh resync on next tick

    # Story 6-3 reframe: notifications now land in `notifications_outbox`
    # (SQLite) instead of the legacy JSONL file. Assert via DB queries.
    from mailbot_api.db.connection import fetchall as _fetchall
    from mailbot_api.db.connection import fetchone as _fetchone
    from mailbot_api.db.queries import (
        NOTIFICATIONS_OUTBOX_COUNT_ALL,
        NOTIFICATIONS_OUTBOX_LIST_ALL,
    )

    count_row = await _fetchone(db_path, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count_row is not None and count_row[0] == 1
    rows = await _fetchall(db_path, NOTIFICATIONS_OUTBOX_LIST_ALL, ())
    assert "delta token reset" in rows[0][3]

    # Second 410 in the same episode does NOT re-notify (debounced).
    transport2, _ = _transport_with_status(410, {"code": "syncStateInvalid"})
    await run_once(db_path, transport=transport2)
    count_row = await _fetchone(db_path, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count_row is not None and count_row[0] == 1  # still just the one


async def test_handles_404_sync_state_not_found_same_recovery_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: HTTP 404 with body code 'syncStateNotFound' triggers the same
    recovery as 410 — clears delta_link, notifies, returns cleanly."""
    import mailbot_api.sync.sync_worker as sync_worker

    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    sync_worker._resync_notification_fired = False

    from mailbot_api.db.connection import execute_write
    await execute_write(
        db_path,
        "INSERT INTO sync_state (provider, delta_link, last_sync_at, last_sync_messages_seen) "
        "VALUES (?, ?, ?, ?)",
        ("microsoft_graph", "https://graph.microsoft.com/v1.0/delta?$deltatoken=OLD", "2026-06-01T00:00:00Z", 0),
    )

    # Case-insensitive match per AC-5: docs don't pin casing. Body uses the
    # real Graph nested OData error envelope shape.
    transport, _ = _transport_with_status(
        404,
        {"error": {"code": "SyncStateNotFound", "message": "Token expired"}},
    )
    result = await run_once(db_path, transport=transport)
    assert result.new_delta_link is None

    state = await fetchone(
        db_path, "SELECT delta_link FROM sync_state WHERE provider = ?", ("microsoft_graph",)
    )
    assert state is not None
    assert state[0] is None

    # Story 6-3: notifications go to notifications_outbox.
    from mailbot_api.db.connection import fetchone as _fetchone
    from mailbot_api.db.queries import NOTIFICATIONS_OUTBOX_COUNT_ALL

    count_row = await _fetchone(db_path, NOTIFICATIONS_OUTBOX_COUNT_ALL, ())
    assert count_row is not None and count_row[0] == 1


async def test_404_without_sync_state_not_found_does_not_clear_delta_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5 negative: a generic 404 (no syncStateNotFound code) is treated as
    a regular failure — delta_link is NOT cleared, no notification fires."""
    import mailbot_api.sync.sync_worker as sync_worker

    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    sync_worker._resync_notification_fired = False

    from mailbot_api.db.connection import execute_write
    await execute_write(
        db_path,
        "INSERT INTO sync_state (provider, delta_link, last_sync_at, last_sync_messages_seen) "
        "VALUES (?, ?, ?, ?)",
        ("microsoft_graph", "https://graph.microsoft.com/v1.0/delta?$deltatoken=KEEP", "2026-06-01T00:00:00Z", 5),
    )

    transport, _ = _transport_with_status(
        404,
        {"error": {"code": "MailboxNotFound", "message": "wrong endpoint"}},
    )
    await run_once(db_path, transport=transport)

    # delta_link preserved.
    state = await fetchone(
        db_path, "SELECT delta_link FROM sync_state WHERE provider = ?", ("microsoft_graph",)
    )
    assert state is not None
    assert state[0] is not None
    assert "KEEP" in state[0]

    # No notification — Story 6-3: outbox stays empty.
    from mailbot_api.db.connection import fetchone as _fetchone_neg
    from mailbot_api.db.queries import NOTIFICATIONS_OUTBOX_COUNT_ALL as _COUNT_NEG

    count_row = await _fetchone_neg(db_path, _COUNT_NEG, ())
    assert count_row is not None and count_row[0] == 0


async def test_resync_notification_clears_after_successful_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 debounce reset: after a successful sync, the next 410 re-notifies."""
    import mailbot_api.sync.sync_worker as sync_worker

    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    sync_worker._resync_notification_fired = False

    # Episode 1: 410 → notification fires.
    transport1, _ = _transport_with_status(410, {"code": "syncStateInvalid"})
    await run_once(db_path, transport=transport1)

    # Successful sync (clean delta page, advances delta_link, clears flag).
    page = {
        "value": [_make_message("g-after-recovery")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=FRESH",
    }
    transport2, _ = _transport([page])
    result = await run_once(db_path, transport=transport2)
    assert result.new_delta_link is not None  # success advances delta_link

    # Episode 2: another 410 → notification fires AGAIN (debounce cleared).
    transport3, _ = _transport_with_status(410, {"code": "syncStateInvalid"})
    await run_once(db_path, transport=transport3)

    # Story 6-3: outbox has 2 rows total — one per episode.
    from mailbot_api.db.connection import fetchone as _fetchone_e2
    from mailbot_api.db.queries import NOTIFICATIONS_OUTBOX_COUNT_ALL as _COUNT_E2

    count_row = await _fetchone_e2(db_path, _COUNT_E2, ())
    assert count_row is not None and count_row[0] == 2


async def test_handles_duplicate_message_in_single_delta_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-6: the same graph_id appearing twice in one delta page with different
    changeKey values produces exactly one row whose change_marker is the
    last-seen value. Replays in a single page are explicitly permitted by the
    Graph delta-query docs."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page = {
        "value": [
            _make_message("dup-1", change_marker="ck-v1", subject="first-seen"),
            _make_message("dup-1", change_marker="ck-v2", subject="last-seen"),
        ],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    transport, _ = _transport([page])
    result = await run_once(db_path, transport=transport)

    # messages_upserted counts writes attempted (per AC-6 logging contract).
    assert result.messages_seen == 2
    assert result.messages_upserted == 2  # AC-6: both writes counted

    # Exactly one row, with the LAST-SEEN change_marker.
    rows = await fetchall(
        db_path,
        "SELECT graph_id, change_marker, subject FROM emails WHERE graph_id = ?",
        ("dup-1",),
    )
    assert len(rows) == 1
    assert rows[0] == ("dup-1", "ck-v2", "last-seen")


async def test_change_key_fallback_to_odata_etag_when_change_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2 defensive path: if a Graph response lacks `changeKey` but carries
    `@odata.etag`, the worker uses the fallback and logs a structured warning.
    Production Graph responses on the message resource should never hit this."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    # Hand-build a message that does NOT have changeKey but does have @odata.etag.
    msg = _make_message("g-fallback")
    del msg["changeKey"]
    msg["@odata.etag"] = "etag-fallback-v1"

    page = {
        "value": [msg],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    transport, _ = _transport([page])
    result = await run_once(db_path, transport=transport)
    assert result.messages_upserted == 1

    row = await fetchone(
        db_path, "SELECT change_marker FROM emails WHERE graph_id = ?", ("g-fallback",)
    )
    assert row is not None
    assert row[0] == "etag-fallback-v1"


async def test_sync_worker_delta_request_carries_prefer_immutable_id_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1: the delta-endpoint GET from sync_worker._fetch_page_with_retry
    carries the same `Prefer: IdType="ImmutableId"` header that graph_client
    applies to /me. Without this header, message IDs rotate on folder move."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "login.microsoftonline.com" in request.url.host:
            return httpx.Response(
                200,
                json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
            )
        if "graph.microsoft.com" in request.url.host:
            captured["Prefer"] = request.headers.get("Prefer", "")
            return httpx.Response(
                200,
                json={
                    "value": [],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
                },
            )
        return httpx.Response(404)

    await run_once(db_path, transport=httpx.MockTransport(handler))
    assert captured["Prefer"] == 'IdType="ImmutableId"'


async def test_removed_reason_changed_vs_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3: `removed_reason` distinguishes 'changed' (recoverable) from
    'deleted' (permanent). Both land as soft-delete with the verbatim reason."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)

    page1 = {
        "value": [_make_message("g-changed"), _make_message("g-deleted")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D1",
    }
    transport1, _ = _transport([page1])
    await run_once(db_path, transport=transport1)

    page2 = {
        "value": [
            _make_message("g-changed", removed=True, removed_reason="changed"),
            _make_message("g-deleted", removed=True, removed_reason="deleted"),
        ],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta?$deltatoken=D2",
    }
    transport2, _ = _transport([page2])
    result = await run_once(db_path, transport=transport2)
    assert result.messages_soft_deleted == 2

    rows = await fetchall(
        db_path,
        "SELECT graph_id, removed_reason FROM emails WHERE graph_id IN (?, ?) ORDER BY graph_id",
        ("g-changed", "g-deleted"),
    )
    assert rows == [("g-changed", "changed"), ("g-deleted", "deleted")]
