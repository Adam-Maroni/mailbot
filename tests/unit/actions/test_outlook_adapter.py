"""Story 4-5 — OutlookGraphWriteAdapter unit tests.

Uses httpx.MockTransport to stub Graph responses without real network. The
retry chain is exercised by routing responses based on a per-test request
counter inside the transport.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from mailbot_api.actions.drainer import PendingActionRow
from mailbot_api.actions.outlook_adapter import OutlookGraphWriteAdapter
from mailbot_api.actions.types import ActionType, tier_for


def _row(
    *,
    action_type: ActionType,
    email_id: str | None = "e-1",
    payload: dict[str, Any] | None = None,
) -> PendingActionRow:
    # The PendingActionRow tier field is Literal[1, 2, 3]; tier_for returns
    # 0..3, and Tier-0 never reaches the drainer per Story 4-2 — clamp to 1
    # for the rare Tier-0 enum that might appear in a test fixture.
    raw_tier = tier_for(action_type)
    tier = max(1, raw_tier)
    return PendingActionRow(
        id=1,
        email_id=email_id,
        action_type=action_type,
        tier=tier,  # type: ignore[arg-type]
        payload=payload or {},
        proposed_at="2026-06-02T00:00:00Z",
        proposed_by_grant_id=None,
        change_marker_at_propose=None,
        status="draining",
        retry_count=0,
        failure_reason=None,
        terminal_at=None,
        budget_consumed=0,
    )


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def _ok_handler(status: int = 200, body: bytes = b'{}'):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)
    return handler


def _fake_token() -> str:
    return "fake-access-token"


# ---- happy-path dispatches ---------------------------------------------------


async def test_mark_read_issues_patch_with_isread_true() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(200, json={})

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is True
    assert captured["method"] == "PATCH"
    assert "graph.microsoft.com" in captured["url"]
    assert "/me/messages/e-1" in captured["url"]
    assert b'"isRead":true' in captured["body"]


async def test_archive_issues_post_move_with_destination_id() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(200, json={})

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.ARCHIVE))
    assert out.ok is True
    assert "/me/messages/e-1/move" in captured["url"]
    assert b'"destinationId":"archive"' in captured["body"]


async def test_delete_issues_delete() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        return httpx.Response(204)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.DELETE))
    assert out.ok is True
    assert captured["method"] == "DELETE"
    assert "/me/messages/e-1" in captured["url"]


async def test_send_reply_issues_post_with_comment() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(202)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(
        _row(action_type=ActionType.SEND_REPLY, payload={"body": "Thanks!"}),
    )
    assert out.ok is True
    assert "/me/messages/e-1/reply" in captured["url"]
    assert b'Thanks!' in captured["body"]


async def test_send_new_email_issues_post_sendmail_no_id_in_path() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(202)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(
        _row(
            action_type=ActionType.SEND_NEW_EMAIL,
            email_id=None,  # email-less per Story 4-2 CR-1
            payload={
                "to": ["new@example.com"],
                "subject": "Hi",
                "body": "First contact.",
            },
        ),
    )
    assert out.ok is True
    assert captured["url"].endswith("/sendMail")
    assert b'"saveToSentItems":true' in captured["body"]


# ---- local-only family --------------------------------------------------------


async def test_add_local_category_no_graph_call_returns_ok() -> None:
    request_count = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(500)  # would fail if called

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(
        _row(action_type=ActionType.ADD_LOCAL_CATEGORY, payload={"category": "VIP"}),
    )
    assert out.ok is True
    assert out.retry_count == 0
    assert request_count == 0  # no Graph call issued


# ---- retry chain --------------------------------------------------------------


async def test_429_with_retry_after_retries_then_succeeds() -> None:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0.001"})
        return httpx.Response(200, json={})

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is True
    assert counter["n"] == 3


async def test_4xx_non_429_immediate_fail_no_retry() -> None:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(403)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_403"
    assert out.retry_count == 0
    assert counter["n"] == 1  # no retry


async def test_5xx_non_503_retries_once_then_fails() -> None:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(500)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )

    # Speed up the test by monkeypatching asyncio.sleep to no-op.
    orig_sleep = asyncio.sleep

    async def _fast_sleep(_t: float) -> None:
        return None

    asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]

    assert out.ok is False
    assert out.error == "provider_5xx_500"
    assert out.retry_count == 1
    assert counter["n"] == 2  # initial + 1 retry


async def test_503_retries_three_times_then_fails() -> None:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(503)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )

    orig_sleep = asyncio.sleep

    async def _fast_sleep(_t: float) -> None:
        return None

    asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]

    assert out.ok is False
    assert out.error == "provider_503_retry_exhausted"
    assert out.retry_count == 3
    assert counter["n"] == 4  # initial + 3 retries


# ---- 401 auth-refresh retry (Story 10.6.0) -----------------------------------


async def test_401_refresh_hook_retries_once_then_succeeds() -> None:
    """AC-1: a 401 invokes the async refresh hook and retries the SAME dispatch
    once; a 401-then-200 sequence yields ok=True. AC-3-shape: the refresh hook
    freshens the token the sync provider returns, so the retry carries it."""
    counter = {"n": 0}
    tokens_seen: list[str] = []
    refresh_calls = {"n": 0}
    # Mutable token cell the sync provider reads — the refresh hook mutates it.
    cell = {"value": "stale-token"}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        tokens_seen.append(req.headers.get("Authorization", ""))
        if counter["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={})

    async def on_auth_failure() -> None:
        refresh_calls["n"] += 1
        cell["value"] = "fresh-token"

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: cell["value"],
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is True
    assert refresh_calls["n"] == 1  # refreshed exactly once
    assert counter["n"] == 2  # initial 401 + 1 retry
    # AC-3 shape: first attempt carried the stale token, retry carried the fresh one.
    assert tokens_seen[0] == "Bearer stale-token"
    assert tokens_seen[1] == "Bearer fresh-token"


async def test_401_then_401_with_hook_is_bounded_and_fails_terminal() -> None:
    """AC-2: a 401-then-401 (refresh did not help) exits terminal with the
    existing provider_4xx_401 error — the auth-refresh retry fires at most once,
    no infinite loop."""
    counter = {"n": 0}
    refresh_calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(401)

    async def on_auth_failure() -> None:
        refresh_calls["n"] += 1

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_401"
    assert refresh_calls["n"] == 1  # refreshed exactly once, then gave up
    assert counter["n"] == 2  # initial 401 + 1 auth-refresh retry, no more


async def test_401_without_hook_immediate_fail_unchanged() -> None:
    """AC-2: when no refresh hook is supplied, a 401 is an immediate terminal
    fail — today's behavior preserved."""
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(401)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_401"
    assert out.retry_count == 0
    assert counter["n"] == 1  # no retry


async def test_403_with_hook_does_not_refresh_or_retry() -> None:
    """AC-4: a non-401 4xx (403) is an immediate terminal fail even when a
    refresh hook is supplied — the hook is NOT awaited."""
    counter = {"n": 0}
    refresh_calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(403)

    async def on_auth_failure() -> None:
        refresh_calls["n"] += 1

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_403"
    assert out.retry_count == 0
    assert refresh_calls["n"] == 0  # non-401 4xx never triggers refresh
    assert counter["n"] == 1


async def test_401_refresh_then_429_preserves_full_ar_d5_1_backoffs() -> None:
    """CR finding: the 401 auth-refresh retry must NOT consume an AR-D5-1
    backoff slot. A 401 followed by 429s still gets the full _MAX_RETRIES (3)
    backoff retries before exhausting — i.e. 1 (initial 401) + 1 (refresh retry,
    429) + 3 (429 backoffs) = 5 requests, ending in provider_429_retry_exhausted
    with retry_count == _MAX_RETRIES (the 401 refresh did not eat a slot)."""
    counter = {"n": 0}
    refresh_calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return httpx.Response(401)
        return httpx.Response(429, headers={"Retry-After": "0.001"})

    async def on_auth_failure() -> None:
        refresh_calls["n"] += 1

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )

    orig_sleep = asyncio.sleep

    async def _fast_sleep(_t: float) -> None:
        return None

    asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]

    assert out.ok is False
    assert out.error == "provider_429_retry_exhausted"
    assert refresh_calls["n"] == 1  # 401 refreshed once
    # 1 (401) + 1 (refresh retry → 429) + 3 (429 backoffs) = 5 requests.
    assert counter["n"] == 5
    assert out.retry_count == 3  # full _MAX_RETRIES backoffs, 401 didn't consume one


async def test_401_refresh_hook_raises_fails_closed_not_propagated() -> None:
    """CR finding: an exception from on_auth_failure() must be normalized to a
    GraphApplyResult (fail closed to provider_4xx_401), not propagated raw out
    of apply() — every sibling branch yields a result, this one must too."""
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(401)

    async def on_auth_failure() -> None:
        raise RuntimeError("db locked mid-drain")

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_401"  # failed closed, not raised
    assert counter["n"] == 1  # never got to a retry (refresh raised)


async def test_401_refresh_noop_token_unchanged_still_bounded() -> None:
    """CR Decision-item shape: if the refresh hook runs but leaves the token
    cell unchanged (the periodic task hasn't rotated oauth_state yet), the retry
    re-sends the SAME token → 401 again → terminal. Proves the no-op-refresh
    residual is bounded (no infinite loop) and surfaces the real 401."""
    counter = {"n": 0}
    refresh_calls = {"n": 0}
    cell = {"value": "stale-token"}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(401)

    async def on_auth_failure() -> None:
        refresh_calls["n"] += 1
        # no-op: token cell left unchanged (oauth_state not rotated yet)

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=lambda: cell["value"],
        transport=_mock_transport(handler),
        on_auth_failure=on_auth_failure,
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ))
    assert out.ok is False
    assert out.error == "provider_4xx_401"
    assert refresh_calls["n"] == 1  # refreshed once, no-op, then gave up
    assert counter["n"] == 2  # initial 401 + 1 retry, bounded


# ---- defensive paths ---------------------------------------------------------


async def test_missing_email_id_for_id_required_action_returns_error() -> None:
    """MARK_READ requires email_id; passing None must surface a clean error
    rather than crash inside URL construction."""
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(_ok_handler()),
    )
    out = await adapter.apply(_row(action_type=ActionType.MARK_READ, email_id=None))
    assert out.ok is False
    assert out.error is not None
    assert out.error.startswith("missing_email_id_for_")


# ---- Story 10-2: move pre-state read ------------------------------------------


async def test_read_move_pre_state_parses_parent_folder_id() -> None:
    """Story 10-2 AC-1: the pre-state read is GET /me/messages/{id}
    ?$select=parentFolderId via the same token seam; parentFolderId lands in
    GraphReadResult.source_folder_id."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["select"] = req.url.params.get("$select")
        return httpx.Response(
            200, json={"parentFolderId": "folder-abc", "changeKey": "ck-1"},
        )

    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token, transport=_mock_transport(handler),
    )
    result = await adapter.read_move_pre_state("e-1")
    assert result.ok is True
    assert result.source_folder_id == "folder-abc"
    assert captured["method"] == "GET"
    assert "/me/messages/e-1" in captured["url"]
    assert captured["select"] == "parentFolderId"


async def test_read_move_pre_state_404_fails_closed() -> None:
    """Story 10-2: a 4xx on the pre-state read surfaces ok=False so the
    drainer fails the row (pre_state_capture_failed) instead of dispatching
    an irreversible move."""
    adapter = OutlookGraphWriteAdapter(
        access_token_provider=_fake_token,
        transport=_mock_transport(lambda req: httpx.Response(404, json={})),
    )
    result = await adapter.read_move_pre_state("e-gone")
    assert result.ok is False
    assert result.source_folder_id is None
    assert result.error is not None
    assert "4xx" in result.error or "404" in result.error
