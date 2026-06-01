"""Integration tests for scripts/mint_refresh_token.py (Story 1-9 AC-6).

Covers the **token-exchange path** via httpx.MockTransport (the network boundary).
The browser-spawn + local-HTTP-callback path is not covered here — that path
requires a real browser and is verified manually per docs/entra-app-registration.md
§ "First-time mint walkthrough".

Pattern mirrors tests/integration/test_oauth_state.py (Story 1-6): real httpx
client driven by a MockTransport handler closure; no mocks of the script's own
logic.
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import pytest


def _load_mint_module() -> Any:
    """Import scripts/mint_refresh_token.py once for the test session.

    The `scripts/` folder is not a package, so we load by file path. Cached
    under `sys.modules` so subsequent imports are cheap.
    """
    cached = sys.modules.get("mint_refresh_token")
    if cached is not None:
        return cached
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "mint_refresh_token.py"
    spec = importlib.util.spec_from_file_location("mint_refresh_token", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mint_refresh_token"] = module
    spec.loader.exec_module(module)
    return module


mint = _load_mint_module()


def _token_transport(
    *,
    status: int = 200,
    body: dict[str, Any] | None = None,
    raise_exc: Exception | None = None,
) -> httpx.MockTransport:
    """Build a MockTransport returning a fixed token-endpoint response.

    If `raise_exc` is provided, the handler raises it instead of returning
    a response — used to simulate transport errors.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        return httpx.Response(status, json=body or {})

    return httpx.MockTransport(handler)


# --------------------------------------------------------------------------- #
# build_authorize_url
# --------------------------------------------------------------------------- #


def test_build_authorize_url_includes_all_required_params() -> None:
    url = mint.build_authorize_url(
        client_id="abc-123",
        tenant="consumers",
        redirect_uri="http://localhost:8765/callback",
        state="deadbeef",
    )
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)

    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/consumers/oauth2/v2.0/authorize"
    assert qs["client_id"] == ["abc-123"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["http://localhost:8765/callback"]
    assert qs["response_mode"] == ["query"]
    assert qs["state"] == ["deadbeef"]
    assert "offline_access" in qs["scope"][0]
    assert "User.Read" in qs["scope"][0]
    assert "Mail.Read" in qs["scope"][0]
    assert "Mail.ReadWrite" in qs["scope"][0]
    assert "Mail.Send" in qs["scope"][0]


# --------------------------------------------------------------------------- #
# _verify_state
# --------------------------------------------------------------------------- #


def test_verify_state_returns_silently_on_match() -> None:
    # Should not raise.
    mint._verify_state("deadbeef", "deadbeef")


def test_verify_state_raises_on_mismatch() -> None:
    with pytest.raises(mint.StateMismatchError):
        mint._verify_state("attacker-supplied", "freshly-minted")


# --------------------------------------------------------------------------- #
# exchange_code_for_tokens — happy path
# --------------------------------------------------------------------------- #


def test_successful_exchange_returns_refresh_token() -> None:
    transport = _token_transport(
        status=200,
        body={
            "access_token": "at-x",
            "refresh_token": "rt-x",
            "expires_in": 3600,
            "scope": "offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send",
            "token_type": "Bearer",
        },
    )
    body = mint.exchange_code_for_tokens(
        code="auth-code-1",
        client_id="abc",
        tenant="consumers",
        client_secret="shh",
        redirect_uri="http://localhost:8765/callback",
        transport=transport,
    )
    assert body["refresh_token"] == "rt-x"
    assert body["access_token"] == "at-x"
    assert body["expires_in"] == 3600


def test_successful_exchange_posts_form_encoded_body() -> None:
    """Verify the POST carries grant_type=authorization_code + all required fields."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["form"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        )

    mint.exchange_code_for_tokens(
        code="code-1",
        client_id="cid",
        tenant="consumers",
        client_secret="secret-1",
        redirect_uri="http://localhost:8765/callback",
        transport=httpx.MockTransport(handler),
    )

    assert captured["url"] == (
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    )
    assert "application/x-www-form-urlencoded" in captured["content_type"]
    form = captured["form"]
    assert form["grant_type"] == "authorization_code"
    assert form["client_id"] == "cid"
    assert form["client_secret"] == "secret-1"
    assert form["code"] == "code-1"
    assert form["redirect_uri"] == "http://localhost:8765/callback"
    assert "offline_access" in form["scope"]


# --------------------------------------------------------------------------- #
# exchange_code_for_tokens — error paths
# --------------------------------------------------------------------------- #


def test_invalid_grant_raises_token_exchange_error_with_status() -> None:
    transport = _token_transport(
        status=400,
        body={
            "error": "invalid_grant",
            "error_description": (
                "AADSTS70008: The provided authorization code or refresh token has expired"
            ),
        },
    )
    with pytest.raises(mint.TokenExchangeError) as exc_info:
        mint.exchange_code_for_tokens(
            code="stale-code",
            client_id="abc",
            tenant="consumers",
            client_secret="shh",
            redirect_uri="http://localhost:8765/callback",
            transport=transport,
        )
    assert exc_info.value.status_code == 400
    body = exc_info.value.sanitized_body
    assert isinstance(body, dict)
    assert body["error"] == "invalid_grant"


def test_error_body_with_token_shaped_leak_is_sanitized() -> None:
    """If an error body accidentally contained a Bearer-token-shaped string,
    the sanitizer must redact it before TokenExchangeError carries it forward."""
    transport = _token_transport(
        status=400,
        body={
            "error": "invalid_grant",
            "error_description": "rejected token: Bearer ABCdef.ghi-jkl_mno12345",
        },
    )
    with pytest.raises(mint.TokenExchangeError) as exc_info:
        mint.exchange_code_for_tokens(
            code="x",
            client_id="abc",
            tenant="consumers",
            client_secret="shh",
            redirect_uri="http://localhost:8765/callback",
            transport=transport,
        )
    body = exc_info.value.sanitized_body
    assert isinstance(body, dict)
    description: str = body["error_description"]
    assert "Bearer ABCdef.ghi-jkl_mno12345" not in description
    assert "[REDACTED_BEARER]" in description


def test_unparseable_error_body_falls_back_to_text() -> None:
    """If the 4xx body is not JSON, the script captures `.text` instead and
    still sanitizes — never raises a JSONDecodeError that would leak the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            content=b"<html>Internal Server Error</html>",
            headers={"content-type": "text/html"},
        )

    with pytest.raises(mint.TokenExchangeError) as exc_info:
        mint.exchange_code_for_tokens(
            code="x",
            client_id="abc",
            tenant="consumers",
            client_secret="shh",
            redirect_uri="http://localhost:8765/callback",
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.status_code == 500
    # Lock in the str-fallback shape so a future refactor doesn't silently
    # change the type (dict `in` matches keys and would pass the substring check).
    assert isinstance(exc_info.value.sanitized_body, str)
    assert "<html>" in exc_info.value.sanitized_body


def test_transport_error_propagates_as_httpx_request_error() -> None:
    """A transport-layer failure (ConnectError) propagates unchanged so main()
    can map it to exit code 4."""
    transport = _token_transport(raise_exc=httpx.ConnectError("simulated DNS failure"))
    with pytest.raises(httpx.RequestError):
        mint.exchange_code_for_tokens(
            code="x",
            client_id="abc",
            tenant="consumers",
            client_secret="shh",
            redirect_uri="http://localhost:8765/callback",
            transport=transport,
        )
