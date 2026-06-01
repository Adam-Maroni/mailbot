"""Unit tests for GraphClient using httpx.MockTransport.

Story 1-5 — tests run against the real GraphClient + a mocked HTTP transport at
the httpx boundary. This is consistent with the Middleware-Real-Bootstrap MailBot
reframing: we don't mock GraphClient itself, we mock the OUTBOUND HTTP layer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from mailbot_api.observability.logging import JsonFormatter
from mailbot_api.sync.graph_client import GraphAuthError, GraphClient

_FAKE_CREDS: dict[str, str] = {
    "client_id": "test-client",
    "client_secret": "test-secret",  # noqa: S106 — test fixture
    "tenant_id": "test-tenant",
    "refresh_token": "rt-original",  # noqa: S106
}


def _make_transport(
    token_response: tuple[int, dict[str, Any]] | None = None,
    me_response: tuple[int, dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    """Build an httpx.MockTransport that responds to /token and /me URLs.

    Each response is a (status_code, json_body) tuple. Defaults are 200 with
    well-formed payloads.
    """
    token_response = token_response or (
        200,
        {
            "access_token": "at-fresh",
            "refresh_token": "rt-rotated",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )
    me_response = me_response or (
        200,
        {
            "displayName": "Adam Aroni",
            "userPrincipalName": "adam@example.onmicrosoft.com",
            "mail": "adam@example.com",
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "login.microsoftonline.com" in request.url.host:
            code, body = token_response
            return httpx.Response(code, json=body)
        if "graph.microsoft.com" in request.url.host:
            code, body = me_response
            return httpx.Response(code, json=body)
        return httpx.Response(404, json={"error": "unhandled-test-url"})

    return httpx.MockTransport(handler)


def test_me_round_trip_succeeds() -> None:
    transport = _make_transport()
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    me = client.me()
    assert me["displayName"] == "Adam Aroni"
    assert me["userPrincipalName"] == "adam@example.onmicrosoft.com"


def test_access_token_cached_across_calls() -> None:
    """Second call should reuse the in-memory token; one token-exchange total."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "login.microsoftonline.com" in request.url.host:
            calls.append("token")
            return httpx.Response(
                200,
                json={
                    "access_token": "at-cached",
                    "refresh_token": "rt-rotated",
                    "expires_in": 3600,
                },
            )
        calls.append("me")
        return httpx.Response(
            200,
            json={"displayName": "x", "userPrincipalName": "y"},
        )

    client = GraphClient(transport=httpx.MockTransport(handler), **_FAKE_CREDS)
    client.me()
    client.me()
    assert calls.count("token") == 1
    assert calls.count("me") == 2


def test_invalid_grant_raises_graph_auth_error() -> None:
    transport = _make_transport(
        token_response=(
            400,
            {
                "error": "invalid_grant",
                "error_description": "Refresh token expired",
            },
        )
    )
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    with pytest.raises(GraphAuthError) as excinfo:
        client.me()
    assert excinfo.value.code == "invalid_grant"


def test_missing_access_token_in_response_raises() -> None:
    transport = _make_transport(token_response=(200, {"expires_in": 3600}))
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    with pytest.raises(GraphAuthError) as excinfo:
        client.me()
    assert excinfo.value.code == "missing_access_token"


def test_me_404_raises_graph_auth_error() -> None:
    transport = _make_transport(me_response=(404, {"error": {"code": "not_found"}}))
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    with pytest.raises(GraphAuthError) as excinfo:
        client.me()
    assert excinfo.value.code == "graph_me_failed"


def test_rotated_refresh_token_stored_in_memory(caplog: pytest.LogCaptureFixture) -> None:
    """If the identity endpoint returns a rotated refresh_token, we update in-memory
    state and emit `event="oauth.token.rotated"` for audit."""
    transport = _make_transport()
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    with caplog.at_level(logging.INFO):
        client.me()
    rotated_events = [
        r for r in caplog.records if getattr(r, "event", None) == "oauth.token.rotated"
    ]
    assert len(rotated_events) == 1


def test_sanitizer_redacts_code_in_logged_url() -> None:
    """NFR-SEC-4 / Story 1-4 sanitizer integration: a URL with `?code=...` is
    redacted before the log line is emitted. Test the sanitizer's behavior on a
    representative LogRecord shape rather than capturing the live client output
    (the client doesn't currently log raw URLs with `?code=`; this is an
    integration-contract test for the future)."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="mailbot_api.sync.graph_client",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="oauth callback",
        args=(),
        exc_info=None,
    )
    record.url = "https://login.microsoftonline.com/cb?code=secret_auth_code_value&state=ok"
    payload = json.loads(formatter.format(record))
    assert "secret_auth_code_value" not in payload["url"]
    assert "[REDACTED_QUERY_TOKEN]" in payload["url"]


def test_prefer_immutable_id_header_on_graph_requests() -> None:
    """Story 1-10 AC-1: every Graph data-plane request carries the header
    `Prefer: IdType="ImmutableId"` so message IDs don't rotate on folder moves.

    The `Prefer` header is NOT applied to the identity endpoint (token
    exchange against login.microsoftonline.com) — only to graph.microsoft.com
    requests. We assert both: present on /me, absent on /token.
    """
    captured_headers: dict[str, dict[str, str]] = {"token": {}, "graph": {}}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        # Snapshot the Prefer header value (or absence) for both endpoints.
        prefer = request.headers.get("Prefer", "")
        if "login.microsoftonline.com" in host:
            captured_headers["token"]["Prefer"] = prefer
            return httpx.Response(
                200,
                json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
            )
        if "graph.microsoft.com" in host:
            captured_headers["graph"]["Prefer"] = prefer
            return httpx.Response(200, json={"displayName": "x", "userPrincipalName": "y"})
        return httpx.Response(404)

    client = GraphClient(transport=httpx.MockTransport(handler), **_FAKE_CREDS)
    client.me()

    # AC-1 hard assertion: Prefer header present on Graph request, with the
    # documented IdType="ImmutableId" payload.
    assert captured_headers["graph"]["Prefer"] == 'IdType="ImmutableId"'
    # Token endpoint did NOT receive the Prefer header (would be a no-op but
    # we keep the surface clean).
    assert captured_headers["token"].get("Prefer", "") == ""


# --------------------------------------------------------------------------- #
# Public-client (no client_secret) path — Story 4-0 Phase 3.5 finding:
# real Entra returns AADSTS90023 when a public client app sends a secret.
# Mock transport doesn't catch the divergence because it returns 200 regardless
# of what's in the form body.
# --------------------------------------------------------------------------- #


def test_public_client_omits_client_secret_from_token_form() -> None:
    """When client_secret is not provided, the refresh-token exchange form body
    MUST omit the key entirely. Real Entra (public client) returns AADSTS90023
    otherwise."""
    captured_forms: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse
        if "login.microsoftonline.com" in request.url.host:
            captured_forms.append(
                dict(urllib.parse.parse_qsl(request.content.decode()))
            )
            return httpx.Response(
                200,
                json={
                    "access_token": "at-fresh",
                    "refresh_token": "rt-rotated",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        if "graph.microsoft.com" in request.url.host:
            return httpx.Response(
                200, json={"displayName": "X", "userPrincipalName": "x@y.com"}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    # Pass client_secret=None explicitly — simulates the public-client setup.
    client = GraphClient(
        transport=transport,
        client_id="cid",
        client_secret=None,
        tenant_id="consumers",
        refresh_token="rt-orig",
    )
    client.me()

    assert len(captured_forms) == 1
    form = captured_forms[0]
    assert "client_secret" not in form, (
        "Public-client refresh-token exchange must omit client_secret entirely; "
        "Entra returns AADSTS90023 if it's present."
    )
    assert form["grant_type"] == "refresh_token"
    assert form["client_id"] == "cid"
    assert form["refresh_token"] == "rt-orig"


def test_confidential_client_includes_client_secret_in_token_form() -> None:
    """Counter-check: when client_secret IS provided, it must appear in the form
    (so Web-platform / confidential-client setups still work)."""
    captured_forms: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse
        if "login.microsoftonline.com" in request.url.host:
            captured_forms.append(
                dict(urllib.parse.parse_qsl(request.content.decode()))
            )
            return httpx.Response(
                200,
                json={
                    "access_token": "at-fresh",
                    "refresh_token": "rt-rotated",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        if "graph.microsoft.com" in request.url.host:
            return httpx.Response(
                200, json={"displayName": "X", "userPrincipalName": "x@y.com"}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = GraphClient(transport=transport, **_FAKE_CREDS)
    client.me()

    assert len(captured_forms) == 1
    form = captured_forms[0]
    assert form["client_secret"] == "test-secret"


def test_authorization_header_never_logged() -> None:
    """The me() call sends `Authorization: Bearer <token>` but does NOT log the
    Authorization header. Heuristic: scan the source for the substring
    `extra={...` and check no extras-payload mentions auth_header / authorization
    as a key. The header is set on the request (legit) but never named as a log
    field."""
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "mailbot_api"
        / "sync"
        / "graph_client.py"
    ).read_text(encoding="utf-8")
    # Find every `extra={...}` block (multi-line allowed).
    extras_blocks = re.findall(r"extra=\{[^}]*\}", source, flags=re.DOTALL)
    assert extras_blocks, "expected at least one extra={...} block in graph_client.py"
    for block in extras_blocks:
        b = block.lower()
        assert "auth_header" not in b, f"auth_header leaked into log extras: {block}"
        assert "authorization" not in b, f"authorization leaked into log extras: {block}"
