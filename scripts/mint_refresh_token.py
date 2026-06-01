"""One-time interactive bootstrap for the Microsoft Graph refresh token (Story 1-9).

Runs the OAuth 2.0 Authorization Code flow on a local dev machine:

  1. Build the `/authorize` URL with a random `state` per auth-v2-user.md §Step 1.
  2. Open the URL in the default browser; user consents to delegated scopes.
  3. Wait on a local `http.server` (127.0.0.1:8765) for the `?code=...&state=...`
     callback.
  4. Verify `state` matches; exchange the code for tokens against
     `login.microsoftonline.com/{tenant}/oauth2/v2.0/token`.
  5. Print the refresh token in a marker block to stdout for hand-copy to the
     VPS `.env`.

This script targets `login.microsoftonline.com` (identity), NOT
`graph.microsoft.com` — Rule B (only `mailbot_api/sync/graph_client.py` may
touch the Graph data plane) is preserved.

Exit codes:
  0    — success; refresh token printed
  2    — token endpoint returned 4xx/5xx; sanitized body on stderr
  3    — state mismatch on callback (possible CSRF)
  4    — transport error (network, DNS, timeout) before/during exchange
  130  — KeyboardInterrupt (operator aborted)

Usage:
    python scripts/mint_refresh_token.py \\
        --client-id <APP_ID> --tenant consumers --client-secret <SECRET>

Env-var fallback (one per arg): OUTLOOK_CLIENT_ID, OUTLOOK_TENANT_ID,
OUTLOOK_CLIENT_SECRET, OUTLOOK_REDIRECT_URI.
"""

from __future__ import annotations

import argparse
import http.server
import os
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from typing import Any

import httpx

from mailbot_api.observability.logging import sanitize

# Identity endpoint templates per auth-v2-user.md.
_AUTHORIZE_URL_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
)
_TOKEN_URL_TEMPLATE = (
    "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # noqa: S105
)

# Delegated permissions MailBot needs (matches docs/entra-app-registration.md AC-1).
_SCOPES = "offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send"

_DEFAULT_REDIRECT = "http://localhost:8765/callback"
_DEFAULT_CALLBACK_HOST = "127.0.0.1"
_DEFAULT_CALLBACK_PORT = 8765
_CALLBACK_PATH = "/callback"

# Loopback hosts only — binding to any non-loopback interface would expose the
# single-use auth `code` to the LAN during the ~10s callback window.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})

# Allowed Entra tenant routing values per auth-v2-user.md parameters table:
# `consumers` / `common` / `organizations` / a directory GUID.
_TENANT_RE = re.compile(
    r"^(consumers|common|organizations|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)

_TOKEN_EXCHANGE_TIMEOUT_SECONDS = 30.0


# --------------------------------------------------------------------------- #
# Exceptions / exit-code contract
# --------------------------------------------------------------------------- #


class StateMismatchError(RuntimeError):
    """Raised when the callback's `state` does not match the freshly-minted value."""


class TokenExchangeError(RuntimeError):
    """Raised when the /token endpoint returns a non-2xx response.

    Carries the HTTP status and a sanitized representation of the body so callers
    can render a single FATAL line without re-sanitizing.
    """

    def __init__(self, status_code: int, sanitized_body: Any) -> None:
        super().__init__(
            f"token exchange failed status={status_code} body={sanitized_body!r}"
        )
        self.status_code = status_code
        self.sanitized_body = sanitized_body


# --------------------------------------------------------------------------- #
# Pure helpers (unit-testable without network or browser)
# --------------------------------------------------------------------------- #


def _verify_state(received: str, expected: str) -> None:
    """Raise StateMismatchError if `received` != `expected`.

    Constant-time comparison via `secrets.compare_digest` so a timing side-channel
    can't be used to brute-force the state token (defense in depth — the token is
    already 32 hex chars).
    """
    if not secrets.compare_digest(received, expected):
        raise StateMismatchError(
            "callback state did not match freshly-minted value"
        )


def _validate_tenant(tenant: str) -> None:
    """Reject anything not in {consumers, common, organizations, <GUID>}.

    Raw operator input is `.format()`-substituted into the authorize/token URLs;
    a malformed value (full URL, path-traversal, `?`-injection) would redirect
    traffic to an attacker-influenced endpoint.
    """
    if not _TENANT_RE.match(tenant):
        raise SystemExit(
            "FATAL: --tenant must be 'consumers', 'common', 'organizations', "
            "or a directory GUID"
        )


def build_authorize_url(
    *,
    client_id: str,
    tenant: str,
    redirect_uri: str,
    state: str,
    scope: str = _SCOPES,
) -> str:
    """Build the /authorize URL per auth-v2-user.md §Step 1."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scope,
        "state": state,
    }
    base = _AUTHORIZE_URL_TEMPLATE.format(tenant=tenant)
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(
    *,
    code: str,
    client_id: str,
    tenant: str,
    client_secret: str,
    redirect_uri: str,
    scope: str = _SCOPES,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = _TOKEN_EXCHANGE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens.

    Raises:
      TokenExchangeError on non-2xx (carries sanitized body).
      httpx.RequestError on transport failure.

    `transport` is for test injection (httpx.MockTransport); production callers
    leave it None so real network IO happens.
    """
    url = _TOKEN_URL_TEMPLATE.format(tenant=tenant)
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }

    if transport is not None:
        http = httpx.Client(transport=transport, timeout=httpx.Timeout(timeout_seconds))
    else:
        http = httpx.Client(timeout=httpx.Timeout(timeout_seconds))
    with http:
        response = http.post(url, data=form)

    if response.status_code >= 400:
        try:
            raw_body: Any = response.json()
        except ValueError:
            raw_body = response.text
        raise TokenExchangeError(response.status_code, sanitize(raw_body))

    try:
        body: Any = response.json()
    except ValueError:
        raise TokenExchangeError(
            response.status_code,
            sanitize({"error": "non_json_2xx_body", "body": response.text}),
        ) from None
    if not isinstance(body, dict):
        raise TokenExchangeError(
            response.status_code,
            sanitize({"error": "unexpected_body_type", "body": body}),
        )
    return body


# --------------------------------------------------------------------------- #
# Local callback server (the interactive surface — not unit-tested)
# --------------------------------------------------------------------------- #


class _CallbackResult:
    """Tiny mutable holder shared between the request handler and the main thread."""

    def __init__(self) -> None:
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None
        self.error_description: str | None = None


def _make_handler_class(
    result: _CallbackResult, shutdown_event: threading.Event, callback_path: str
) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a request-handler class that captures the OAuth callback once.

    Only requests to ``callback_path`` carrying ``code`` or ``error`` query
    params terminate the wait loop. Other paths (favicon, prefetch, root) get
    a 404 without shutting the server down — otherwise a Chrome favicon prefetch
    would race the real callback and exit with empty ``code``/``state``.
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server API
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            is_callback = parsed.path == callback_path
            has_oauth_payload = "code" in params or "error" in params
            if not (is_callback and has_oauth_payload):
                self._send_html(404, "<h1>Not found</h1>")
                return

            if "error" in params:
                result.error = params["error"][0]
                if "error_description" in params:
                    result.error_description = params["error_description"][0]
                self._send_html(
                    400,
                    "<h1>Auth error</h1><p>You may close this tab.</p>",
                )
            else:
                result.code = params.get("code", [""])[0]
                result.state = params.get("state", [""])[0]
                self._send_html(
                    200,
                    "<h1>Success</h1><p>You may close this tab. "
                    "Return to your terminal.</p>",
                )
            shutdown_event.set()

        def _send_html(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            # Silence default access-log noise on stderr; the operator only cares
            # about the marker block.
            return

    return _Handler


def _wait_for_callback(
    *,
    host: str,
    port: int,
    callback_path: str = _CALLBACK_PATH,
    timeout_seconds: float = 600.0,
) -> _CallbackResult:
    """Bind a single-request HTTP server on host:port and return the callback params."""
    result = _CallbackResult()
    shutdown_event = threading.Event()
    handler_cls = _make_handler_class(result, shutdown_event, callback_path)

    server = http.server.HTTPServer((host, port), handler_cls)
    server.timeout = 1.0  # poll cadence so the shutdown_event can be checked

    deadline = threading.Event()
    timer = threading.Timer(timeout_seconds, deadline.set)
    timer.daemon = True
    timer.start()
    try:
        while not shutdown_event.is_set() and not deadline.is_set():
            server.handle_request()
    finally:
        timer.cancel()
        server.server_close()

    if not shutdown_event.is_set():
        raise TimeoutError(
            f"no callback received on {host}:{port} within {timeout_seconds:.0f}s"
        )
    return result


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mint a Microsoft Graph refresh token via the OAuth 2.0 Authorization "
            "Code flow. Prints the refresh token to stdout for hand-copy to "
            "the VPS .env. See docs/entra-app-registration.md."
        )
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("OUTLOOK_CLIENT_ID"),
        help="Application (client) ID. Default: $OUTLOOK_CLIENT_ID.",
    )
    parser.add_argument(
        "--tenant",
        default=os.environ.get("OUTLOOK_TENANT_ID"),
        help=(
            "Tenant routing value: 'consumers' for personal Microsoft accounts, "
            "a directory GUID for work/school, or 'common' for mixed-mode. "
            "Default: $OUTLOOK_TENANT_ID."
        ),
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("OUTLOOK_CLIENT_SECRET"),
        help="Client secret value from Entra. Default: $OUTLOOK_CLIENT_SECRET.",
    )
    parser.add_argument(
        "--redirect-uri",
        default=os.environ.get("OUTLOOK_REDIRECT_URI", _DEFAULT_REDIRECT),
        help=(
            "OAuth redirect URI registered for the app. Must point at the local "
            f"callback server. Default: {_DEFAULT_REDIRECT}."
        ),
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> None:
    missing = [
        flag
        for flag, value in (
            ("--client-id (or OUTLOOK_CLIENT_ID)", args.client_id),
            ("--tenant (or OUTLOOK_TENANT_ID)", args.tenant),
            ("--client-secret (or OUTLOOK_CLIENT_SECRET)", args.client_secret),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "FATAL: required values not set: " + ", ".join(missing)
        )
    _validate_tenant(args.tenant)


def _resolve_callback_bind(redirect_uri: str) -> tuple[str, int, str]:
    """Resolve (bind_host, bind_port, callback_path) from the redirect URI.

    Constrains the bind host to loopback (`127.0.0.1`) regardless of what the
    operator pasted; a `0.0.0.0` or LAN-IP redirect URI would otherwise expose
    the single-use auth `code` to the network during the callback window.
    """
    parsed = urllib.parse.urlparse(redirect_uri)
    hostname = (parsed.hostname or "").lower()
    if hostname not in _LOOPBACK_HOSTS:
        raise SystemExit(
            "FATAL: --redirect-uri host must be loopback "
            f"(localhost / 127.0.0.1 / ::1); got {hostname!r}"
        )
    port = parsed.port or _DEFAULT_CALLBACK_PORT
    path = parsed.path or _CALLBACK_PATH
    return (_DEFAULT_CALLBACK_HOST, port, path)


def _is_headless() -> bool:
    """Best-effort detection of WSL / headless-Linux dev boxes.

    `webbrowser.open` can return True from a `GenericBrowser` whose subprocess
    silently exits, leaving the operator stuck waiting for a browser that never
    opened. When this returns True, always print the manual-URL fallback.
    """
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        _validate_args(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        callback_host, callback_port, callback_path = _resolve_callback_bind(
            args.redirect_uri
        )
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    expected_state = secrets.token_hex(16)
    authorize_url = build_authorize_url(
        client_id=args.client_id,
        tenant=args.tenant,
        redirect_uri=args.redirect_uri,
        state=expected_state,
    )

    print(
        f"Opening browser to {args.tenant} consent page; "
        f"awaiting callback on http://{callback_host}:{callback_port}{callback_path} ...",
        file=sys.stderr,
    )
    try:
        opened = webbrowser.open(authorize_url)
    except webbrowser.Error:
        opened = False
    # `webbrowser.open` can return True on WSL/headless even when no browser
    # actually opened — always print the manual fallback on those hosts.
    if not opened or _is_headless():
        print(
            "Open this URL manually in any browser:\n" + authorize_url,
            file=sys.stderr,
        )

    try:
        result = _wait_for_callback(
            host=callback_host, port=callback_port, callback_path=callback_path
        )
    except KeyboardInterrupt:
        print("aborted by operator", file=sys.stderr)
        return 130
    except TimeoutError as exc:
        print(
            f"FATAL: no callback received within timeout: {exc}",
            file=sys.stderr,
        )
        return 4
    except OSError as exc:
        print(
            f"FATAL: could not bind callback server on "
            f"{callback_host}:{callback_port}: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 4

    if result.error is not None:
        # Entra returned `?error=...` on the redirect (consent declined, etc.).
        sanitized = sanitize(
            {
                "error": result.error,
                "error_description": result.error_description,
            }
        )
        print(
            f"FATAL: consent flow returned error body={sanitized!r}",
            file=sys.stderr,
        )
        return 2

    if not result.code or not result.state:
        print(
            "FATAL: callback missing required `code`/`state` query params",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_state(result.state, expected_state)
    except StateMismatchError:
        print(
            "FATAL: state mismatch — possible CSRF; aborting",
            file=sys.stderr,
        )
        return 3

    try:
        token_response = exchange_code_for_tokens(
            code=result.code,
            client_id=args.client_id,
            tenant=args.tenant,
            client_secret=args.client_secret,
            redirect_uri=args.redirect_uri,
        )
    except TokenExchangeError as exc:
        print(
            f"FATAL: token exchange failed status={exc.status_code} "
            f"body={exc.sanitized_body!r}",
            file=sys.stderr,
        )
        return 2
    except httpx.RequestError as exc:
        print(
            f"FATAL: transport error: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 4

    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        print(
            "FATAL: token endpoint returned no refresh_token "
            "(was `offline_access` granted?)",
            file=sys.stderr,
        )
        return 2

    expires_in = token_response.get("expires_in", "<unknown>")
    granted_scope = token_response.get("scope", "<unknown>")

    print("===== REFRESH TOKEN (paste into VPS .env as OUTLOOK_REFRESH_TOKEN) =====")
    print(refresh_token)
    print("===== END =====")
    print(f"expires_in: {expires_in}")
    print(f"granted_scope: {granted_scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
