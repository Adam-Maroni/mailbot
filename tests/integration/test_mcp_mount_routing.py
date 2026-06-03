"""Story 6-6.6 — F6 closure regression tests.

The bug (Story 6-0 walk discovery + Story 6-6.6 investigation):

  1. FastMCP's default `streamable_http_path="/mcp"` registers an inner
     Starlette `Route("/mcp", ...)` inside the app returned by
     `streamable_http_app()`.
  2. `mailbot_api/main.py` mounts that whole app at `/mcp` via
     `Mount("/mcp", app=streamable_http_app)`. The effective full inner
     path becomes `/mcp/mcp`.
  3. Hermes POSTs to `http://mailbot-api:8000/mcp` (no slash). FastAPI's
     Mount semantics REQUIRE a trailing slash to enter the mount —
     `redirect_slashes=True` (default) issues 307 → `/mcp/`. Hermes's
     MCP client does NOT follow 307 on the bidirectional POST transport.
     Gives up after 3 attempts: `MCP server 'mailbot-api' initial
     connection failed (3/3)`.
  4. Even if 307 were followed: after the slash redirect, FastAPI strips
     `/mcp` prefix → inner path is `""` (or `/`). The inner FastMCP route
     is at `/mcp`, NOT `/`. Inner match fails → 404.

The fix (Story 6-6.6, two-part):

  Part A (server-side): `FastMCP(..., streamable_http_path="/")` in
    `build_mcp_server`. The inner route becomes `Route("/", ...)`, so
    that when FastAPI's Mount strips the `/mcp` prefix and routes the
    empty path, the inner `Route("/")` matches and serves the request.
  Part B (client-side config): `hermes-config/config.yaml`'s
    `mcp_servers.mailbot-api.url` becomes `http://mailbot-api:8000/mcp/`
    (trailing slash). FastAPI's Mount matches directly; no 307 redirect;
    Hermes hits the MCP handler on attempt 1.

These tests guard against re-introduction:

  1. STRUCTURAL: assert the FastMCP server's inner route is at `/`, not
     `/mcp`. Catches the case where a FastMCP version bump changes the
     default OR a refactor removes the explicit `streamable_http_path="/"`
     kwarg.
  2. END-TO-END: boot the real FastAPI app with TestClient and POST to
     `/mcp/` (the URL Hermes is now configured with). Response MUST be
     non-404 — the inner route is reachable. F6 regression would
     re-introduce 404 here.
  3. CONFIG-SHAPE: the Hermes config URL ends with a trailing slash. A
     refactor that drops the slash re-introduces F6 from the client side.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.mcp_server import build_mcp_server


def test_streamable_http_app_inner_route_is_root(tmp_path: Path) -> None:
    """STRUCTURAL: FastMCP's inner Starlette route MUST be at `/` so the
    outer `Mount("/mcp", ...)` in main.py produces effective path `/mcp`
    (not `/mcp/mcp`)."""
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    inner_app = server.streamable_http_app()

    # FastMCP's streamable_http_app returns a Starlette app with the MCP
    # transport mounted at `settings.streamable_http_path`. We require it
    # to be `/` so the outer Mount prefix-strip doesn't leave a dangling
    # `/mcp` segment that triggers the 307→404 redirect chain.
    inner_paths = [getattr(route, "path", None) for route in inner_app.routes]
    assert "/" in inner_paths, (
        f"FastMCP inner route is not `/` — got {inner_paths!r}. "
        "This would re-trigger F6 (POST /mcp → 307 → 404). "
        "Fix: `FastMCP(..., streamable_http_path=\"/\")` in build_mcp_server."
    )
    assert server.settings.streamable_http_path == "/", (
        f"streamable_http_path is {server.settings.streamable_http_path!r} "
        "but must be `/`. See Story 6-6.6 closure notes."
    )


def _bootstrap_app_env(
    monkeypatch: pytest.MonkeyPatch, db_path: str
) -> None:
    """Set the env vars required to boot mailbot_api.main:app in a test
    without requiring real Anthropic/Outlook secrets — the lifespan loads
    policy.yaml + sensitivity_patterns.yaml from the repo root, and we
    point MAILBOT_DB_PATH at our test-scoped sqlite. Mirrors the pattern
    from tests/integration/test_db_connection.py."""
    apply_pending_migrations(db_path)
    repo_root = Path(__file__).resolve().parent.parent.parent
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    monkeypatch.setenv("MAILBOT_SKIP_DB", "0")
    monkeypatch.setenv("MAILBOT_SKIP_MCP", "0")
    monkeypatch.setenv(
        "MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml")
    )
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH",
        str(repo_root / "router" / "sensitivity_patterns.yaml"),
    )


def test_post_to_mcp_trailing_slash_reaches_handler_not_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """END-TO-END: POST to `/mcp/` (the trailing-slash URL Hermes is now
    configured with) MUST reach the FastMCP handler.

    A 404 response means the inner-route + outer-Mount routing is broken
    again — the original F6 bug. A 307 response means the FastAPI Mount
    routing inverted (`/mcp` works but `/mcp/` doesn't). Both are
    regressions. Any other status (400 for missing session headers, 200
    for a valid initialize, etc.) means the request reached the MCP
    handler.
    """
    _bootstrap_app_env(monkeypatch, str(tmp_path / "f6_e2e.db"))

    # Boot the real FastAPI app via the lifespan-aware TestClient. The
    # lifespan mounts the MCP server per main.py — exactly the path Hermes
    # consumes in production.
    from mailbot_api.main import app

    # TestClient uses httpx; follow_redirects=False mirrors Hermes's
    # MCP-transport behavior (no 307-follow on POST).
    with TestClient(app) as client:
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Content-Type": "application/json"},
            follow_redirects=False,
        )

    # The specific success shape isn't what this test asserts — the MCP
    # transport requires specific session-init headers that the bare POST
    # doesn't provide, so 400/406/421 are realistic responses. What
    # MATTERS is the request resolved to the handler. 404 means F6 bug
    # back. 307 means we'd loop without ever reaching the handler.
    assert response.status_code != 404, (
        "POST /mcp/ returned 404 — the MCP handler is unreachable. "
        "F6 routing bug re-introduced. Check `streamable_http_path=\"/\"` "
        "on FastMCP construction in `build_mcp_server` AND verify "
        "`mailbot_api/main.py` still mounts `streamable_http_app()` at "
        "`/mcp` (not somewhere else)."
    )
    assert response.status_code != 307, (
        f"POST /mcp/ returned 307 — the Mount path is misconfigured. "
        f"Location: {response.headers.get('location')!r}. "
        f"Expected: handler reached directly on the trailing-slash URL."
    )


def test_post_to_mcp_no_slash_redirects_or_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """END-TO-END: POST to `/mcp` (no slash) is acceptable as EITHER:
      - a 307 redirect to `/mcp/` (FastAPI Mount's default behavior);
      - a direct handler response (some Mount configs serve both shapes).

    What must NOT happen: 404. The Hermes config uses `/mcp/` per Story
    6-6.6's two-part fix, so this test exists to document and protect the
    no-slash behavior — a future operator who configures Hermes with the
    no-slash URL would see at worst a 307 to `/mcp/`, which most HTTP
    clients (including Hermes when configured for redirect-following)
    handle correctly. 404 here is the failure mode.
    """
    _bootstrap_app_env(monkeypatch, str(tmp_path / "f6_no_slash.db"))

    from mailbot_api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Content-Type": "application/json"},
            follow_redirects=False,
        )

    assert response.status_code != 404, (
        "POST /mcp (no slash) returned 404 — neither `/mcp` nor `/mcp/` "
        "resolves. F6 routing bug re-introduced."
    )
    # If 307, the Location must contain `/mcp/` so a redirect-following
    # client would succeed. CR LOW-1 fix: previous form had identical
    # branches (`endswith("/mcp/") or endswith("/mcp/")`); replaced with
    # `in` so both relative (`/mcp/`) and absolute
    # (`http://host/mcp/`) Location forms are accepted.
    if response.status_code == 307:
        loc = response.headers.get("location", "")
        assert "/mcp/" in loc, (
            f"307 Location is {loc!r}, expected to contain `/mcp/`. "
            "F6 redirect chain has changed shape."
        )


def test_hermes_config_url_has_trailing_slash() -> None:
    """CONFIG-SHAPE regression guard: `hermes-config/config.yaml`'s
    `mcp_servers.mailbot-api.url` MUST end with a trailing slash per
    Story 6-6.6 Part B. A future refactor that drops the slash
    re-introduces F6 from the client side (Hermes hits 307, doesn't
    follow, gives up after 3 attempts)."""
    import yaml

    config_path = (
        Path(__file__).resolve().parents[2]
        / "hermes-config"
        / "config.yaml"
    )
    text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(text)
    url = config["mcp_servers"]["mailbot-api"]["url"]
    assert url.endswith("/"), (
        f"hermes-config/config.yaml mcp_servers.mailbot-api.url is {url!r}; "
        "must end with `/` (F6 Story 6-6.6 Part B). Without the trailing "
        "slash, Hermes POSTs to /mcp, FastAPI's Mount issues 307→/mcp/, "
        "Hermes MCP client does not follow the redirect, and tool "
        "discovery fails after 3 attempts."
    )


# ---------------------------------------------------------------------------
# Story 6-6.7 — F7 closure regression tests
# ---------------------------------------------------------------------------
#
# The bug (live discovery during Epic 6 Phase 3.5 CP-2 walk, 2026-06-03):
#
#   1. Story 6-6.6 fixed the F6 routing chain (server-side path "/" +
#      client-side trailing slash). Story 6-6.6's e2e tests use FastAPI's
#      TestClient which sends `Host: testserver` by default.
#   2. FastMCP 1.27.2 enables DNS-rebinding protection by default via the
#      `TransportSecurityMiddleware`. When `enable_dns_rebinding_protection
#      is True` and `allowed_hosts` is empty (the FastMCP default), EVERY
#      incoming Host header fails the allow-list check → HTTP 421
#      "Misdirected Request" with body "Invalid Host header".
#   3. Live discovery: Hermes reaches mailbot-api as `mailbot-api:8000`
#      (Docker service hostname on the `mailbot-net` network). FastMCP's
#      transport security rejected `mailbot-api:8000` with 421. Hermes's
#      MCP client surfaced "Client error '421 Misdirected Request' for url
#      'http://mailbot-api:8000/mcp/'" and gave up after 3 retries. All
#      22 MCP tools were silently absent from Hermes's tool registry.
#   4. Story 6-6.6's tests didn't catch this because they don't customize
#      the Host header (TestClient defaults to `testserver`, which IS in
#      the new allow-list — so the test's default behavior is preserved,
#      and the new regression test below covers the production hostname
#      explicitly).
#
# The fix (Story 6-6.7):
#
#   `build_mcp_server` constructs FastMCP with an explicit
#   `transport_security=TransportSecuritySettings(...)` that allow-lists
#   the Docker-internal hostname, localhost shapes, and TestClient's
#   `testserver`. Protection stays ENABLED (belt-and-suspenders against
#   any future browser-reachable surface); we just provide the missing
#   allow-list. The setting lives in code (not config) because the
#   Docker service hostname is fixed by docker-compose.yml.
#
# These tests guard against re-introduction of either:
#   (a) the empty-allow-list case (server constructed without the kwarg
#       at all), or
#   (b) a refactor that drops `mailbot-api:8000` from the allow-list.


def test_mcp_transport_security_allows_docker_hostname(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F7 closure: POST /mcp/ with `Host: mailbot-api:8000` (the live
    Docker-internal hostname) MUST NOT return 421.

    A 421 means FastMCP's `TransportSecurityMiddleware` rejected the
    Host header. In production this is the failure that broke Hermes's
    MCP discovery in CP-2: every retry returned 421, Hermes gave up,
    zero tools registered.
    """
    _bootstrap_app_env(monkeypatch, str(tmp_path / "f7_docker_host.db"))

    from mailbot_api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={
                "Content-Type": "application/json",
                "Host": "mailbot-api:8000",
            },
            follow_redirects=False,
        )

    assert response.status_code != 421, (
        f"POST /mcp/ with Host: mailbot-api:8000 returned 421 — "
        f"FastMCP DNS-rebinding protection rejected the Docker-internal "
        f"hostname. F7 regression. Body: {response.text!r}. "
        f"Fix: add 'mailbot-api:8000' to `allowed_hosts` in "
        f"`TransportSecuritySettings` inside `build_mcp_server`."
    )


def test_mcp_transport_security_settings_include_docker_host(
    tmp_path: Path,
) -> None:
    """STRUCTURAL: the FastMCP server MUST be constructed with explicit
    `allowed_hosts` containing the Docker-internal hostname.

    Catches the case where someone refactors `build_mcp_server` to drop
    the `transport_security` kwarg entirely — the live e2e test above
    would still pass under TestClient's `testserver` default, but Hermes
    would break in production.
    """
    server = build_mcp_server(db_path=str(tmp_path / "x.db"))
    settings = server.settings.transport_security
    assert settings is not None, (
        "FastMCP server constructed without explicit `transport_security`. "
        "F7 regression: the default `TransportSecuritySettings()` with "
        "DNS-rebinding-protection disabled is a security regression; the "
        "default-enabled config with empty allow-list breaks Hermes. "
        "Fix: pass `TransportSecuritySettings(enable_dns_rebinding_protection"
        "=True, allowed_hosts=[...])` in `build_mcp_server`."
    )
    assert "mailbot-api:8000" in settings.allowed_hosts, (
        f"`mailbot-api:8000` missing from allow-list: "
        f"{settings.allowed_hosts!r}. Hermes reaches the server via this "
        f"Docker service hostname; without it, every live request returns "
        f"421 and tool discovery fails."
    )
