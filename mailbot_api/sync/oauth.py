"""OAuth refresh-token rotation + persistence per architecture §AR-D9-1/2.

`oauth_state` is the runtime source of truth for the Microsoft Graph refresh
token. `.env` (OUTLOOK_REFRESH_TOKEN) is the **bootstrap seed only** — used on
first run when the table row doesn't exist. After that, rotation events update
the row in place, and `.env` is never re-read for the refresh token.

Why this lives in `sync/` (not `db/queries.py`): the queries.py file is the SQL
boundary; this module composes those queries into the oauth-rotation policy.
For Story 1-6 we accept the simpler pattern of using `db.fetchone` / `db.execute_write`
directly from here; the broader Rule C move (consolidating ALL SQL literals into
queries.py) is a future epic-2 follow-up.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from mailbot_api.config import get_secret, get_secret_optional, is_public_client_mode
from mailbot_api.db.connection import execute_write, execute_write_returning, fetchone
from mailbot_api.db.queries import (
    OAUTH_STATE_BUMP_REFRESH_FAILURE,
    OAUTH_STATE_INSERT_SEED,
    OAUTH_STATE_SELECT,
    OAUTH_STATE_UPDATE_AFTER_EXCHANGE,
)
from mailbot_api.observability.logging import sanitize as _sanitize_for_persistence
from mailbot_api.observability.scheduler import upsert_worker_health
from mailbot_api.observability.timestamps import utc_z_now
from mailbot_api.router.pause import get_pause_state
from mailbot_api.sync.graph_client import (
    _DEFAULT_SCOPE,
    _REFRESH_LEEWAY_SECONDS,
    _TOKEN_URL_TEMPLATE,
    GraphAuthError,
)

logger = logging.getLogger(__name__)

_PROVIDER = "microsoft_graph"

# Story 6-15: when consecutive_refresh_failures crosses this threshold, the
# `mailbot status` `oauth_refresh_failing` alarm fires AND the router is
# auto-paused with reason="oauth_refresh_failing" (AC-3, AC-4 Path B).
OAUTH_REFRESH_FAIL_THRESHOLD = 3

# Story 6-15: stable pause-reason string so the auto-resume path can match
# against `pause_state.reason` and only resume if we were the ones who paused.
_OAUTH_PAUSE_REASON = "oauth_refresh_failing"

# Story 6-15: stable worker_health component name; surfaced by the status
# board's OAuthStatus section.
_OAUTH_WORKER_HEALTH_COMPONENT = "oauth_refresh"

# Story 6-16 (F25 closure): Microsoft's error code for "Public clients can't
# send a client secret." This is raised when an Entra app is registered under
# "Mobile and desktop apps" (public-client) platform but the token-exchange
# call includes `client_secret`. The bug was silent for the lifetime of any
# `.env` that carried OUTLOOK_CLIENT_SECRET against a public-client app — every
# refresh failed but the existing `oauth.refresh.failed` log only carried
# `error_code="invalid_request"`, which the operator-facing /admin/status
# alarm couldn't distinguish from any other 4xx. F25 surfaced as F23's
# misdiagnosed root cause during Story 6-6.5 fourth-pass walk.
_AADSTS_PUBLIC_CLIENT_SECRET_CODE = "AADSTS90023"  # noqa: S105 — Microsoft error-code identifier, not a credential


def _utc_iso8601() -> str:
    """Return the current UTC time as ISO-8601 with Z suffix (AR-PAT-3).

    Microsecond-precision since 2026-06-02 (Epic 4 retro action item #3).
    """
    return utc_z_now()


@dataclass
class OAuthState:
    """In-memory mirror of an `oauth_state` row."""

    provider: str
    refresh_token: str
    access_token: str | None
    access_expires_at: str | None
    last_rotated_at: str | None
    rotation_count: int
    # Story 6-15: tally of consecutive failed `exchange_and_persist` calls
    # since the last success. Source of truth for the
    # `oauth_refresh_failing` alarm field on `mailbot status`.
    consecutive_refresh_failures: int = 0

    def access_token_is_valid(self) -> bool:
        """Return True if access_token is present AND not within the refresh leeway."""
        if not self.access_token or not self.access_expires_at:
            return False
        try:
            # Lenient: accepts both microsecond-precision (post-2026-06-02)
            # and legacy second-precision timestamps via fromisoformat.
            expiry = datetime.fromisoformat(self.access_expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        # Refresh proactively when we're within _REFRESH_LEEWAY_SECONDS of expiry.
        return expiry.timestamp() >= time.time() + _REFRESH_LEEWAY_SECONDS


async def load_oauth_state(db_path: str) -> OAuthState | None:
    """Return the OAuthState row for microsoft_graph, or None if not yet seeded."""
    row = await fetchone(db_path, OAUTH_STATE_SELECT, (_PROVIDER,))
    if row is None:
        return None
    return OAuthState(
        provider=row[0],
        refresh_token=row[1],
        access_token=row[2],
        access_expires_at=row[3],
        last_rotated_at=row[4],
        rotation_count=row[5],
        consecutive_refresh_failures=row[6],
    )


async def seed_oauth_state_from_env(db_path: str) -> OAuthState:
    """First-run path: read OUTLOOK_REFRESH_TOKEN from env and insert the row.

    Idempotent: if the row already exists, this is a no-op that returns the
    existing state.
    """
    existing = await load_oauth_state(db_path)
    if existing is not None:
        return existing

    refresh_token = get_secret("OUTLOOK_REFRESH_TOKEN")
    await execute_write(db_path, OAUTH_STATE_INSERT_SEED, (_PROVIDER, refresh_token))
    logger.info(
        "oauth_state seeded from env",
        extra={"event": "oauth.state.seeded", "provider": _PROVIDER},
    )
    state = await load_oauth_state(db_path)
    if state is None:  # pragma: no cover — INSERT just succeeded
        raise RuntimeError("oauth_state insert succeeded but load returned None")
    return state


async def _record_refresh_failure(db_path: str, *, error_code: str) -> None:
    """Story 6-15: bump the failure counter, write the worker_health row,
    and auto-pause the router on the threshold crossing.

    Threshold-crossing is computed from the post-bump value returned by the
    UPDATE...RETURNING (Story 6-15 CR-2): two concurrent failure callers can
    no longer both decide "we're the threshold-crosser" by snapshotting the
    same stale `prior_failures` — the DB serializes the bumps, and each
    caller sees its own post-bump value.
    """
    row = await execute_write_returning(
        db_path, OAUTH_STATE_BUMP_REFRESH_FAILURE, (_PROVIDER,)
    )
    new_failures = int(row[0]) if row is not None else 0

    # Sanitize the error string before persisting to worker_health: the HTTP
    # error path passes the response body's `error` field, which is operator-
    # controlled but Microsoft-rendered — defense-in-depth against a future
    # `error_description` containing a Bearer/sk- fragment (Story 6-15 CR-12).
    sanitized_error = _sanitize_for_persistence(error_code)
    if isinstance(sanitized_error, str):
        sanitized_error = sanitized_error[:200]
    await upsert_worker_health(
        db_path,
        component=_OAUTH_WORKER_HEALTH_COMPONENT,
        outcome="failed",
        error=sanitized_error,
    )
    # Edge-once: fire only when this caller's post-bump value crosses the
    # threshold from below. Subsequent failures with `new_failures > K` no-op
    # the pause action (already paused).
    if new_failures < OAUTH_REFRESH_FAIL_THRESHOLD:
        return
    # AC-4 Path B: reuse Story 2-9's pause/resume plumbing — the drainer
    # gains a pause-state short-circuit at its loop boundary (Story 6-15
    # drainer touch) so this single call gates Tier-2/3 dispatch.
    # Story 6-15 CR-1: never clobber a foreign pause reason. If the operator
    # paused for "manual_hold" before our threshold crossed, `try_pause_if_unpaused`
    # returns False and we log a warning instead of overwriting their reason.
    try:
        paused_by_us = await get_pause_state().try_pause_if_unpaused(
            db_path, reason=_OAUTH_PAUSE_REASON
        )
        if paused_by_us:
            logger.error(
                "oauth refresh failing — router auto-paused",
                extra={
                    "event": "oauth.refresh.auto_paused",
                    "consecutive_failures": new_failures,
                    "threshold": OAUTH_REFRESH_FAIL_THRESHOLD,
                    "reason": _OAUTH_PAUSE_REASON,
                },
            )
        else:
            existing_reason = get_pause_state().reason()
            logger.warning(
                "oauth refresh failing — router already paused, not overriding",
                extra={
                    "event": "oauth.refresh.auto_pause_skipped",
                    "consecutive_failures": new_failures,
                    "threshold": OAUTH_REFRESH_FAIL_THRESHOLD,
                    "existing_reason": existing_reason,
                },
            )
    except Exception:  # noqa: BLE001 — pause is best-effort; never let it
        # mask the original GraphAuthError that called us.
        logger.exception(
            "oauth refresh auto-pause failed",
            extra={"event": "oauth.refresh.auto_pause_failed"},
        )


async def _record_refresh_success(db_path: str, *, prior_failures: int) -> None:
    """Story 6-15: success bookkeeping. The success-path UPDATE already reset
    `consecutive_refresh_failures` to 0; here we write the worker_health row
    and auto-resume if we still own the pause.

    Story 6-17 (F26 closure): the previous early-return gate on
    `prior_failures < OAUTH_REFRESH_FAIL_THRESHOLD` short-circuited the
    auto-resume path whenever success came via a code path that captured
    `prior_failures` BEFORE the worker bumped the counter past threshold —
    e.g., a `scripts/refresh_outlook_oauth.py` invocation handing a fresh
    refresh token while the worker's earlier failure-tick had ALREADY
    auto-paused the router. The atomic `try_resume_if_reason` helper at
    `pause.py` is already safe under all pause-state shapes: if the router
    isn't paused, it returns False; if the router is paused for a different
    reason (e.g., manual operator hold), it returns False; ONLY when paused
    with our reason does it resume. Removing the threshold gate is therefore
    safe AND closes F26. The `prior_failures` parameter is preserved for
    observability — it still rides through to the auto-resumed log event so
    operators can correlate against the failure history.
    """
    # Story 6-17 CR-2: try_resume BEFORE writing worker_health to eliminate
    # the transient inconsistency window. Between two awaits, the asyncio
    # event loop can yield to other tasks — a parallel observer reading both
    # `worker_health[oauth_refresh].outcome` AND `pause_state` would briefly
    # see `outcome=ok` AND `paused=true reason=oauth_refresh_failing` — a
    # false signal that "OAuth is healthy but the router won't drain." The
    # canonical post-recovery observable order is: (1) router resumed, then
    # (2) health row updated. Resume-then-write matches that order.
    #
    # Story 6-15 CR-10: use the atomic check-and-resume helper. The three
    # prior sync reads (is_paused/reason/resume) had a narrow window where an
    # operator could re-pause between `reason()` and `resume()`, and our
    # resume would clobber it. The helper performs the snapshot reads
    # synchronously (no await between them); the only remaining window is
    # the resume's await itself, which is unavoidable without holding a
    # cross-await lock.
    try:
        resumed = await get_pause_state().try_resume_if_reason(
            db_path, expected_reason=_OAUTH_PAUSE_REASON
        )
        if resumed:
            logger.info(
                "oauth refresh recovered — router auto-resumed",
                extra={
                    "event": "oauth.refresh.auto_resumed",
                    "prior_failures": prior_failures,
                },
            )
    except Exception:  # noqa: BLE001 — resume is best-effort; success has
        # already been persisted via the UPDATE above.
        logger.exception(
            "oauth refresh auto-resume failed",
            extra={"event": "oauth.refresh.auto_resume_failed"},
        )

    await upsert_worker_health(
        db_path,
        component=_OAUTH_WORKER_HEALTH_COMPONENT,
        outcome="ok",
        error=None,
    )


async def exchange_and_persist(
    db_path: str,
    *,
    state: OAuthState,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 30.0,
) -> OAuthState:
    """Exchange the stored refresh token + persist rotated values to oauth_state.

    Returns the updated OAuthState (in-memory dataclass — re-read from DB after
    the write to ensure parity). Raises GraphAuthError on `invalid_grant` or any
    other non-2xx response.

    `transport` is for test injection (httpx.MockTransport); production callers
    leave it None.

    Story 6-15: every failure path bumps `oauth_state.consecutive_refresh_failures`
    AND writes a `worker_health[oauth_refresh]` heartbeat. On the K-th consecutive
    failure (K = OAUTH_REFRESH_FAIL_THRESHOLD), the router auto-pauses with
    reason="oauth_refresh_failing" so the drainer's Tier-2/3 dispatch stops
    burning `budget_consumed=1` per Graph 401. The success path resets the
    counter (via the UPDATE) and auto-resumes if we own the pause.
    """
    prior_failures = state.consecutive_refresh_failures

    client_id = get_secret("OUTLOOK_CLIENT_ID")
    # OPTIONAL — see graph_client.py docstring re: AADSTS90023.
    client_secret = get_secret_optional("OUTLOOK_CLIENT_SECRET") or None
    tenant_id = get_secret("OUTLOOK_TENANT_ID")

    # Story 6-16 AC-2: explicit operator gate. When OUTLOOK_PUBLIC_CLIENT=true,
    # NEVER append client_secret to the form, even if OUTLOOK_CLIENT_SECRET is
    # set. Lets operators flip the gate via .env without scrubbing the legacy
    # secret value (which they may want to keep around for a confidential-client
    # rollback). Belt-and-suspenders alongside AC-1's loud-log on AADSTS90023.
    public_client_mode = is_public_client_mode()
    if public_client_mode:
        # CR-3: AC-2-mandated confirmation event — gives operators a positive
        # signal that the gate is active. Fires per refresh attempt (rather than
        # once at startup) because oauth.py doesn't own a lifespan hook, and
        # operators correlate this against /admin/status periodic checks.
        logger.info(
            "oauth public-client mode active — client_secret suppressed",
            extra={
                "event": "oauth.config.public_client_mode",
                "secret_present_in_env": client_secret is not None,
            },
        )

    token_url = _TOKEN_URL_TEMPLATE.format(tenant=tenant_id)
    form: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": state.refresh_token,
        "scope": _DEFAULT_SCOPE,
    }
    if client_secret is not None and not public_client_mode:
        form["client_secret"] = client_secret

    def _build_http() -> httpx.Client:
        if transport is not None:
            return httpx.Client(transport=transport, timeout=httpx.Timeout(timeout_seconds))
        return httpx.Client(timeout=httpx.Timeout(timeout_seconds))

    with _build_http() as http:
        try:
            response = http.post(token_url, data=form)
        except httpx.RequestError as exc:
            logger.error(
                "oauth refresh transport error",
                extra={
                    "event": "oauth.refresh.failed",
                    "error_kind": "transport",
                    "error_type": type(exc).__name__,
                },
            )
            await _record_refresh_failure(
                db_path,
                error_code=f"transport_error:{type(exc).__name__}",
            )
            raise GraphAuthError("transport_error", type(exc).__name__) from exc

    if response.status_code >= 400:
        payload = _safe_json(response)
        error_code = (
            payload.get("error", "unknown_error") if isinstance(payload, dict) else "unknown_error"
        )
        # Story 6-16 AC-1: detect AADSTS90023 (public-client-with-secret) and
        # fire a DEDICATED event so operator-facing observability can route it
        # to the public-client-misconfig runbook instead of generic 4xx. The
        # error_description field carries the AADSTS code; the outer
        # error_code (Microsoft's high-level "invalid_request") does NOT
        # distinguish this case. We log this BEFORE the generic
        # `oauth.refresh.failed` so the order in the log is detection-first.
        error_description = (
            payload.get("error_description", "") if isinstance(payload, dict) else ""
        )
        # CR-6: also check the numeric `error_codes` array as a fallback for
        # description-text drift (localization, format change). Microsoft's
        # token-error responses include `"error_codes": [90023]` alongside
        # the description string. Robust detection: substring match OR
        # numeric-array membership.
        error_codes = payload.get("error_codes", []) if isinstance(payload, dict) else []
        is_aadsts_90023 = (
            _AADSTS_PUBLIC_CLIENT_SECRET_CODE in error_description
            or 90023 in error_codes
        )
        if is_aadsts_90023:
            logger.error(
                "oauth refresh failed: public client cannot send client_secret",
                extra={
                    "event": "oauth.refresh.public_client_secret_misconfig",
                    "aadsts_code": _AADSTS_PUBLIC_CLIENT_SECRET_CODE,
                    # CR-2: anchor-based pointer survives line-number drift.
                    # `docs/entra-app-registration.md#common-failure-modes`
                    # is the stable section heading for AADSTS90023 triage.
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
                "rotation_count": state.rotation_count,
            },
        )
        await _record_refresh_failure(
            db_path,
            error_code=str(error_code),
        )
        raise GraphAuthError(
            str(error_code),
            f"Graph identity endpoint returned status={response.status_code}",
        )

    body = response.json()
    access_token = body.get("access_token")
    expires_in = body.get("expires_in", 3600)
    rotated_refresh = body.get("refresh_token") or state.refresh_token

    if not access_token:
        logger.error(
            "oauth refresh missing access_token",
            extra={"event": "oauth.refresh.failed", "error_kind": "missing_access_token"},
        )
        await _record_refresh_failure(
            db_path,
            error_code="missing_access_token",
        )
        raise GraphAuthError("missing_access_token", "Token endpoint returned no access_token")

    expiry_iso = datetime.fromtimestamp(time.time() + int(expires_in), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    now_iso = _utc_iso8601()

    new_rotation_count = state.rotation_count + (1 if rotated_refresh != state.refresh_token else 0)

    await execute_write(
        db_path,
        OAUTH_STATE_UPDATE_AFTER_EXCHANGE,
        (
            rotated_refresh,
            access_token,
            expiry_iso,
            now_iso,
            new_rotation_count,
            _PROVIDER,
        ),
    )
    logger.info(
        "oauth token rotated + persisted",
        extra={
            "event": "oauth.token.rotated",
            "persistence": "oauth_state",
            "rotation_count": new_rotation_count,
            "expires_in_s": expires_in,
        },
    )

    await _record_refresh_success(db_path, prior_failures=prior_failures)

    refreshed = await load_oauth_state(db_path)
    if refreshed is None:  # pragma: no cover — UPDATE just succeeded
        raise RuntimeError("oauth_state UPDATE succeeded but load returned None")
    return refreshed


async def get_access_token(
    db_path: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """High-level helper used by the sync worker (story 1-7).

    On first call after a fresh deploy: reads `OUTLOOK_REFRESH_TOKEN` from env,
    inserts the bootstrap row, then exchanges + persists.

    On subsequent calls: reads `oauth_state`, returns cached access_token if
    still valid, otherwise exchanges + persists.
    """
    state = await load_oauth_state(db_path)
    if state is None:
        state = await seed_oauth_state_from_env(db_path)

    if state.access_token_is_valid() and state.access_token is not None:
        return state.access_token

    state = await exchange_and_persist(db_path, state=state, transport=transport)
    assert state.access_token is not None  # exchange_and_persist always writes this  # noqa: S101
    return state.access_token


def _safe_json(response: httpx.Response) -> Any:
    """Parse JSON or return {} — tolerant of malformed identity-endpoint responses."""
    try:
        return response.json()
    except ValueError:
        return {}
