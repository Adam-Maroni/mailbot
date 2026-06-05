"""Microsoft Graph HTTP client per architecture §AR-PAT-1 Rule B.

This module is the ONLY file in the codebase that touches graph.microsoft.com.
Selective-import boundary enforced by scripts/check_boundaries.py.

Story 1-5: token exchange via refresh_token + `GET /me`. Access token held in
memory only — Story 1-6 adds oauth_state persistence + refresh-token rotation
to SQLite.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from mailbot_api.config import get_secret, get_secret_optional

logger = logging.getLogger(__name__)


_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # noqa: S105
_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_DEFAULT_SCOPE = "https://graph.microsoft.com/.default offline_access"
# Token validity buffer: refresh proactively this many seconds before expiry.
_REFRESH_LEEWAY_SECONDS = 60

# Header applied to every Graph data-plane request (NOT the identity endpoint).
# Without this header, Graph returns the default `id` which rotates on folder
# move; with it, IDs stay stable across moves (per message.md). See Story 1-10.
# Exported publicly so sync_worker._fetch_page_with_retry can reuse the same
# value without duplicating the constant — one source of truth across both
# Graph touchpoints.
PREFER_IMMUTABLE_ID = 'IdType="ImmutableId"'


class GraphAuthError(RuntimeError):
    """Raised when the refresh-token exchange fails.

    Subclass distinct from generic httpx errors so callers (sync worker, story 1-7)
    can react specifically (e.g., fire the sync-health alarm in story 1-8).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class _TokenState:
    access_token: str
    expires_at: float  # Unix epoch seconds


class GraphClient:
    """Synchronous HTTP client for Microsoft Graph.

    The client lazy-fetches an access token on the first call to `me()` (or any
    other Graph endpoint). Subsequent calls reuse the cached access token until
    `expires_at - _REFRESH_LEEWAY_SECONDS`, then re-exchange the refresh token.

    Story 1-6 will refactor `_exchange_refresh_token` to persist the rotated
    refresh token to `oauth_state` and read the bootstrap seed from there
    instead of from env on every restart.
    """

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        refresh_token: str | None = None,
        scope: str = _DEFAULT_SCOPE,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Build a GraphClient.

        All credential parameters fall back to env via `config.get_secret` if unset.
        `transport` is an httpx transport override (used by tests to install
        `httpx.MockTransport`); production callers leave it None.
        """
        self._client_id = client_id or get_secret("OUTLOOK_CLIENT_ID")
        # client_secret is OPTIONAL: public clients (Mobile and desktop apps
        # platform — the recommended Entra setup for personal MS accounts) MUST
        # NOT send a secret on token exchange (AADSTS90023). Only confidential
        # clients (Web platform) require it. See docs/entra-app-registration.md.
        #
        # Story 6-16 CR-5: capture the resolved secret value at __init__ time
        # (matches Story 1-5's constructor-resolution pattern), BUT the
        # is_public_client_mode() gate is re-checked per-call in
        # `_exchange_refresh_token` for symmetry with oauth.py (runtime
        # reactive to env hot-flip). Without that per-call check, an operator
        # who set OUTLOOK_PUBLIC_CLIENT=true post-startup would see the gate
        # silently inactive until container restart.
        self._client_secret: str | None = client_secret or (
            get_secret_optional("OUTLOOK_CLIENT_SECRET") or None
        )
        self._tenant_id = tenant_id or get_secret("OUTLOOK_TENANT_ID")
        self._refresh_token = refresh_token or get_secret("OUTLOOK_REFRESH_TOKEN")
        self._scope = scope
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport
        self._token_state: _TokenState | None = None

    def _build_http(self) -> httpx.Client:
        """Construct an httpx.Client honoring an optional injected transport."""
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=self._timeout)
        return httpx.Client(timeout=self._timeout)

    def _exchange_refresh_token(self) -> _TokenState:
        """Exchange the stored refresh token for a fresh access token.

        Returns the new _TokenState. Raises GraphAuthError on `invalid_grant`
        or any other non-2xx response from the identity endpoint.

        IMPORTANT: the response also contains a (possibly rotated) refresh_token.
        Story 1-6 will persist that to oauth_state; in 1-5 we hold it in memory
        only — surviving until the process restarts.

        Story 6-16 (CR-4 + CR-5): public-client gate re-checked per-call
        (symmetric with oauth.py) so an operator hot-flip of
        OUTLOOK_PUBLIC_CLIENT is reactive without container restart. AADSTS90023
        detection mirrors oauth.py's dedicated event so the legacy Story 1-5
        sync path also emits the operator-routable misconfig signal.
        """
        from mailbot_api.config import is_public_client_mode  # local to avoid cycles

        token_url = _TOKEN_URL_TEMPLATE.format(tenant=self._tenant_id)
        form: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": self._refresh_token,
            "scope": self._scope,
        }
        # CR-5: per-call public-client gate (runtime reactive); CR-3: emit
        # the AC-2-mandated confirmation event when gate is active.
        public_client_mode = is_public_client_mode()
        if public_client_mode:
            logger.info(
                "oauth public-client mode active — client_secret suppressed",
                extra={
                    "event": "oauth.config.public_client_mode",
                    "secret_present_in_env": self._client_secret is not None,
                },
            )
        if self._client_secret is not None and not public_client_mode:
            form["client_secret"] = self._client_secret

        with self._build_http() as http:
            try:
                response = http.post(token_url, data=form)
            except httpx.RequestError as exc:
                # Sanitize: do NOT include exc.request.url (may contain tenant).
                logger.error(
                    "oauth refresh transport error",
                    extra={
                        "event": "oauth.refresh.failed",
                        "error_kind": "transport",
                        "error_type": type(exc).__name__,
                    },
                )
                raise GraphAuthError("transport_error", type(exc).__name__) from exc

        if response.status_code >= 400:
            payload = self._safe_json(response)
            error_code = payload.get("error", "unknown_error") if isinstance(payload, dict) else "unknown_error"
            # CR-4 + CR-6: AADSTS90023 detection mirrored from oauth.py (with
            # substring + error_codes numeric-array fallback). The legacy
            # Story 1-5 sync path is also operator-routable now.
            error_description = (
                payload.get("error_description", "") if isinstance(payload, dict) else ""
            )
            error_codes = payload.get("error_codes", []) if isinstance(payload, dict) else []
            if "AADSTS90023" in error_description or 90023 in error_codes:
                logger.error(
                    "oauth refresh failed: public client cannot send client_secret",
                    extra={
                        "event": "oauth.refresh.public_client_secret_misconfig",
                        "aadsts_code": "AADSTS90023",
                        "remediation_doc": "docs/entra-app-registration.md#common-failure-modes",
                        "remediation_env_gate": "set OUTLOOK_PUBLIC_CLIENT=true",
                    },
                )
            logger.error(
                "oauth refresh failed",
                extra={
                    "event": "oauth.refresh.failed",
                    "status_code": response.status_code,
                    "error_code": error_code,
                },
            )
            raise GraphAuthError(
                str(error_code),
                f"Graph identity endpoint returned status={response.status_code}",
            )

        body = response.json()
        access_token = body.get("access_token")
        expires_in = body.get("expires_in", 3600)
        rotated_refresh = body.get("refresh_token")

        if not access_token:
            logger.error(
                "oauth refresh missing access_token",
                extra={"event": "oauth.refresh.failed", "error_kind": "missing_access_token"},
            )
            raise GraphAuthError("missing_access_token", "Token endpoint returned no access_token")

        # Update in-memory refresh token if rotated (story 1-6 adds persistence).
        if rotated_refresh and rotated_refresh != self._refresh_token:
            self._refresh_token = rotated_refresh
            logger.info(
                "oauth refresh token rotated (in-memory)",
                extra={"event": "oauth.token.rotated", "persistence": "memory-only"},
            )

        state = _TokenState(
            access_token=access_token,
            expires_at=time.time() + max(0, int(expires_in)),
        )
        self._token_state = state
        logger.info(
            "oauth refresh succeeded",
            extra={"event": "oauth.refresh.ok", "expires_in_s": expires_in},
        )
        return state

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        """Parse JSON or return {} — tolerant of malformed identity-endpoint responses."""
        try:
            return response.json()
        except ValueError:
            return {}

    def _access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        state = self._token_state
        if state is None or time.time() >= state.expires_at - _REFRESH_LEEWAY_SECONDS:
            state = self._exchange_refresh_token()
        return state.access_token

    def me(self) -> dict[str, Any]:
        """GET /me — fetch the authenticated user's mailbox metadata.

        Returns the raw JSON dict (Pydantic models for Graph responses land in
        story 1-7 alongside the message-shape).
        """
        token = self._access_token()
        url = f"{_GRAPH_BASE_URL}/me"
        # We log the URL but rely on the observability sanitizer to redact any
        # accidentally-leaked tokens. Authorization header is NOT logged.
        with self._build_http() as http:
            response = http.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Prefer": PREFER_IMMUTABLE_ID,
                },
            )
        if response.status_code != 200:
            logger.error(
                "graph /me call failed",
                extra={
                    "event": "graph.me.failed",
                    "status_code": response.status_code,
                },
            )
            raise GraphAuthError(
                "graph_me_failed",
                f"GET /me returned status={response.status_code}",
            )
        data = response.json()
        logger.info(
            "graph /me ok",
            extra={
                "event": "graph.me.ok",
                "display_name": data.get("displayName"),
                "user_principal_name": data.get("userPrincipalName"),
            },
        )
        return data  # type: ignore[no-any-return]
