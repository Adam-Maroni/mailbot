"""Story 6-16 F25 regression tests: OUTLOOK_CLIENT_SECRET MUST NOT leak into
the token-exchange form when the Entra app is a public client AND the
AADSTS90023 error MUST surface as a dedicated event distinguishable from
generic 4xx failures.

Background: F25 was the misdiagnosed root cause of F23 (filed 2026-06-05
during Story 6-6.5 fourth-pass walk). Pre-fix, `mailbot_api/sync/oauth.py:286`
unconditionally appended `client_secret` to the token-exchange form if
OUTLOOK_CLIENT_SECRET was set in `.env` — even when the Entra app was
registered as a public client (the recommended setup for personal MS accounts).
Microsoft rejected every refresh with AADSTS90023 ("Public clients can't send
a client secret"), but the existing `oauth.refresh.failed` log only carried
`error_code="invalid_request"` so operator-facing observability could not
route the error to the public-client-misconfig runbook. The bug was silent
for the lifetime of any `.env` that carried a stale OUTLOOK_CLIENT_SECRET
against a public-client app.

The tests below lock the fix in three layers (Story AC-5):

  (1) **AC-5.1** AADSTS90023 detection → dedicated event
      `oauth.refresh.public_client_secret_misconfig` fires alongside the
      existing `oauth.refresh.failed`.
  (2) **AC-5.2** OUTLOOK_PUBLIC_CLIENT=true env gate suppresses client_secret
      in the token-exchange form even when OUTLOOK_CLIENT_SECRET is set.
  (3) **AC-5.3** Default confidential-client behavior preserved — secret IS
      sent when OUTLOOK_PUBLIC_CLIENT is unset.
"""

from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

import httpx
import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.sync.graph_client import GraphAuthError
from mailbot_api.sync.oauth import exchange_and_persist, seed_oauth_state_from_env

_BASE_ENV = {
    "OUTLOOK_CLIENT_ID": "test-client",
    "OUTLOOK_CLIENT_SECRET": "should-not-leak",
    "OUTLOOK_TENANT_ID": "test-tenant",
    "OUTLOOK_REFRESH_TOKEN": "rt-bootstrap",
}


def _set_creds(monkeypatch: pytest.MonkeyPatch, *, public_client: bool = False) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    if public_client:
        monkeypatch.setenv("OUTLOOK_PUBLIC_CLIENT", "true")
    else:
        monkeypatch.delenv("OUTLOOK_PUBLIC_CLIENT", raising=False)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


# --------------------------------------------------------------------------- #
# AC-5.1 — AADSTS90023 detection fires dedicated event
# --------------------------------------------------------------------------- #


async def test_public_client_secret_misconfig_logs_loud_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Given an Entra-public-client `.env` (CLIENT_SECRET set, real Entra app
    registered as public client) and an httpx.MockTransport returning the
    AADSTS90023 body, assert the new `oauth.refresh.public_client_secret_misconfig`
    event fires with the remediation pointer.

    This is the canonical F25 production trace: Microsoft returned
    `{"error": "invalid_request", "error_description": "AADSTS90023: Public
    clients can't send a client secret. ..."}`. Pre-fix, only `oauth.refresh.failed`
    fired with `error_code="invalid_request"` — generic-4xx — so the operator
    had no signal to consult docs/entra-app-registration.md:235.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch, public_client=False)  # client_secret IS in env

    state = await seed_oauth_state_from_env(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_request",
                "error_description": (
                    "AADSTS90023: Public clients can't send a client secret. "
                    "Trace ID: 00000000-0000-0000-0000-000000000000 "
                    "Correlation ID: 00000000-0000-0000-0000-000000000000"
                ),
            },
        )

    transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.ERROR, logger="mailbot_api.sync.oauth"):
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    # The dedicated event MUST fire.
    misconfig_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "oauth.refresh.public_client_secret_misconfig"
    ]
    assert len(misconfig_events) == 1, (
        f"expected exactly one oauth.refresh.public_client_secret_misconfig event; "
        f"got {len(misconfig_events)}. events: "
        f"{[getattr(r, 'event', None) for r in caplog.records]}"
    )
    event = misconfig_events[0]
    assert getattr(event, "aadsts_code", None) == "AADSTS90023"
    # CR-2: anchor-based remediation_doc (line-number-stable across doc edits).
    assert getattr(event, "remediation_doc", None) == "docs/entra-app-registration.md#common-failure-modes"
    assert "OUTLOOK_PUBLIC_CLIENT" in getattr(event, "remediation_env_gate", "")

    # The existing generic event MUST also still fire (defense-in-depth — separate
    # event for the specific class, parallel to existing visibility).
    failed_events = [
        r for r in caplog.records if getattr(r, "event", None) == "oauth.refresh.failed"
    ]
    assert len(failed_events) >= 1


# --------------------------------------------------------------------------- #
# CR-6 — error_codes numeric-array fallback (description-text-drift safety)
# --------------------------------------------------------------------------- #


async def test_public_client_secret_misconfig_detected_via_error_codes_array(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """CR-6: AADSTS90023 detection MUST also fire when the substring is absent
    from `error_description` but `error_codes` contains the integer `90023`.

    This protects against Microsoft localizing or restructuring the description
    text (silent regression of the AC-1 dedicated event) — the numeric error
    code is a stable identifier across all Microsoft response shapes.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch, public_client=False)

    state = await seed_oauth_state_from_env(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_request",
                # Description-text-drift simulation: description does NOT contain
                # the literal string "AADSTS90023" anymore (e.g., Microsoft
                # localized it to French, or restructured the response format).
                "error_description": (
                    "Les clients publics ne peuvent pas envoyer de secret client."
                ),
                # But the numeric array is stable across all Microsoft response shapes.
                "error_codes": [90023],
            },
        )

    transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.ERROR, logger="mailbot_api.sync.oauth"):
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    misconfig_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "oauth.refresh.public_client_secret_misconfig"
    ]
    assert len(misconfig_events) == 1, (
        f"CR-6: error_codes=[90023] fallback failed to detect AADSTS90023 when "
        f"error_description was localized away. got "
        f"{[getattr(r, 'event', None) for r in caplog.records]}"
    )


# --------------------------------------------------------------------------- #
# AC-5.2 — OUTLOOK_PUBLIC_CLIENT=true gates client_secret suppression
# --------------------------------------------------------------------------- #


async def test_public_client_mode_fires_confirmation_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """CR-3 + AC-2: when OUTLOOK_PUBLIC_CLIENT=true is active, a confirmation
    `oauth.config.public_client_mode` event MUST fire so operators have a
    positive observability signal that the gate is engaged."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch, public_client=True)

    state = await seed_oauth_state_from_env(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "at-pub",
                "refresh_token": "rt-pub-rotated",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.INFO, logger="mailbot_api.sync.oauth"):
        await exchange_and_persist(db_path, state=state, transport=transport)

    config_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "oauth.config.public_client_mode"
    ]
    assert len(config_events) == 1, (
        f"AC-2 mandates a confirmation event when the public-client gate is "
        f"active; got {len(config_events)}. events: "
        f"{[getattr(r, 'event', None) for r in caplog.records]}"
    )
    # secret_present_in_env carries the original .env state so operators can
    # spot the rollback-friendly setup (gate on + secret still in env).
    assert getattr(config_events[0], "secret_present_in_env", None) is True


async def test_public_client_env_flag_suppresses_secret_in_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given OUTLOOK_PUBLIC_CLIENT=true AND OUTLOOK_CLIENT_SECRET=<value>, the
    outgoing token-exchange form does NOT contain `client_secret`. This is the
    explicit operator gate per AC-2 — operators can keep the legacy secret in
    .env for a confidential-client rollback path without it leaking on every
    refresh exchange.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch, public_client=True)  # SECRET set + PUBLIC_CLIENT=true

    state = await seed_oauth_state_from_env(db_path)

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(urllib.parse.parse_qsl(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "access_token": "at-pub",
                "refresh_token": "rt-pub-rotated",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    await exchange_and_persist(db_path, state=state, transport=transport)

    assert len(captured) == 1
    form = captured[0]
    assert "client_secret" not in form, (
        "OUTLOOK_PUBLIC_CLIENT=true MUST suppress client_secret even when "
        "OUTLOOK_CLIENT_SECRET is set; this is the AC-2 operator gate that "
        "closes F25 without forcing operators to scrub .env."
    )
    # Sanity: the secret value MUST NOT appear ANYWHERE in the form.
    assert "should-not-leak" not in str(form).lower(), (
        "OUTLOOK_CLIENT_SECRET value leaked into the form despite public-client mode."
    )
    # The other required fields MUST still be present.
    assert form["grant_type"] == "refresh_token"
    assert form["client_id"] == "test-client"
    assert form["refresh_token"] == "rt-bootstrap"


# --------------------------------------------------------------------------- #
# AC-5.3 — Confidential-client default still sends secret (regression guard)
# --------------------------------------------------------------------------- #


async def test_confidential_client_default_still_sends_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given OUTLOOK_CLIENT_SECRET=<value> AND OUTLOOK_PUBLIC_CLIENT UNSET, the
    outgoing token-exchange form DOES contain `client_secret`. This is the
    regression guard for confidential-client deployments — Story 6-16 must NOT
    accidentally break the legacy Web-platform Entra registration path that
    Story 1-5/1-6 originally supported.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch, public_client=False)  # SECRET set, PUBLIC_CLIENT unset

    state = await seed_oauth_state_from_env(db_path)

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(urllib.parse.parse_qsl(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "access_token": "at-conf",
                "refresh_token": "rt-conf-rotated",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handler)
    await exchange_and_persist(db_path, state=state, transport=transport)

    assert len(captured) == 1
    form = captured[0]
    assert form.get("client_secret") == "should-not-leak", (
        "Confidential-client default (OUTLOOK_PUBLIC_CLIENT unset) MUST still "
        "send OUTLOOK_CLIENT_SECRET. Story 6-16 must not regress confidential-"
        "client deployments."
    )


# --------------------------------------------------------------------------- #
# Bonus: env-var parsing edge cases for is_public_client_mode
# --------------------------------------------------------------------------- #


def test_is_public_client_mode_recognizes_truthy_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OUTLOOK_PUBLIC_CLIENT parsing: recognize 'true', '1', 'yes', 'on'
    (case-insensitive); reject 'false', '0', '', 'unset', None."""
    from mailbot_api.config import is_public_client_mode

    for truthy in ("true", "True", "TRUE", "1", "yes", "YES", "on", "ON"):
        monkeypatch.setenv("OUTLOOK_PUBLIC_CLIENT", truthy)
        assert is_public_client_mode() is True, f"{truthy!r} should be truthy"

    for falsy in ("false", "False", "0", "no", "off", "", "anything-else"):
        monkeypatch.setenv("OUTLOOK_PUBLIC_CLIENT", falsy)
        assert is_public_client_mode() is False, f"{falsy!r} should be falsy"

    monkeypatch.delenv("OUTLOOK_PUBLIC_CLIENT", raising=False)
    assert is_public_client_mode() is False, "unset should be falsy (default)"
