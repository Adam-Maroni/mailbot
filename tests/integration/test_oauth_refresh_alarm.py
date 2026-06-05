"""Story 6-15: regression tests for the OAuth refresh-failing alarm + auto-pause.

Covers the four AC-6 cases:

* AC-6.1 — `oauth_refresh_failing` flips True after K consecutive failures.
* AC-6.2 — alarm + auto-pause clear on success (counter resets, router
  auto-resumes when we own the pause reason).
* AC-6.3 — the reauth script persists the token without ever logging the
  token value (defense-in-depth on top of the structured-logging discipline).
* AC-6.4 (Path B) — the drainer skips its tick when the router is paused;
  no rows get claimed, no `budget_consumed` gets burned.

The tests use `httpx.MockTransport` to simulate Microsoft's identity endpoint
and `_reset_pause_state_for_test` to keep the module-level pause singleton
clean across cases.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from mailbot_api.actions.drainer import run_tick
from mailbot_api.db.connection import execute_write, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.status import (
    OAUTH_REFRESH_FAIL_THRESHOLD,
    assemble_status,
)
from mailbot_api.router.pause import (
    _reset_pause_state_for_test,
    get_pause_state,
)
from mailbot_api.sync.graph_client import GraphAuthError
from mailbot_api.sync.oauth import (
    exchange_and_persist,
    load_oauth_state,
    seed_oauth_state_from_env,
)

_BASE_ENV = {
    "OUTLOOK_CLIENT_ID": "test-client",
    "OUTLOOK_CLIENT_SECRET": "test-secret",
    "OUTLOOK_TENANT_ID": "test-tenant",
    "OUTLOOK_REFRESH_TOKEN": "rt-bootstrap",
}


def _set_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)


def _success_transport(rotated_refresh: str = "rt-rotated") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "at-fresh",
                "refresh_token": rotated_refresh,
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    return httpx.MockTransport(handler)


def _failure_transport(error: str = "invalid_grant") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": error})

    return httpx.MockTransport(handler)


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _reset_pause_each_test():
    """Reset the module-level PauseState singleton between tests so a
    previous test's auto-pause doesn't bleed into the next one. Mirrors
    the existing pattern in test_router_control.py / test_backpressure_e2e.py.
    """
    _reset_pause_state_for_test()
    yield
    _reset_pause_state_for_test()


# --------------------------------------------------------------------------- #
# AC-6.1 — alarm fires after K consecutive failures.
# --------------------------------------------------------------------------- #


async def test_oauth_refresh_failing_alarm_fires_after_k_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Pre-threshold state: the alarm should be quiet.
    report_before = await assemble_status(db_path)
    assert report_before.oauth.oauth_refresh_failing is False
    assert report_before.oauth.consecutive_refresh_failures == 0

    transport = _failure_transport(error="invalid_grant")
    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    report_after = await assemble_status(db_path)
    assert report_after.oauth.consecutive_refresh_failures == OAUTH_REFRESH_FAIL_THRESHOLD
    assert report_after.oauth.oauth_refresh_failing is True

    # AC-4 Path B side-effect: the router is auto-paused with our reason.
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "oauth_refresh_failing"
    assert report_after.router.paused is True
    assert report_after.router.reason == "oauth_refresh_failing"


async def test_alarm_does_not_fire_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One or two failures must NOT trigger the alarm — only crossing K does."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    transport = _failure_transport()
    # K-1 failures.
    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD - 1):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    report = await assemble_status(db_path)
    assert report.oauth.consecutive_refresh_failures == OAUTH_REFRESH_FAIL_THRESHOLD - 1
    assert report.oauth.oauth_refresh_failing is False
    assert get_pause_state().is_paused() is False


# --------------------------------------------------------------------------- #
# AC-6.2 — alarm clears + auto-resume on success.
# --------------------------------------------------------------------------- #


async def test_oauth_refresh_failing_alarm_clears_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Drive the alarm + auto-pause first.
    failure_transport = _failure_transport()
    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=failure_transport)
    assert get_pause_state().is_paused() is True

    # Now a success: counter resets, alarm clears, auto-resume fires.
    state = await load_oauth_state(db_path)
    assert state is not None
    refreshed = await exchange_and_persist(
        db_path, state=state, transport=_success_transport()
    )
    assert refreshed.consecutive_refresh_failures == 0
    assert refreshed.access_token == "at-fresh"

    report = await assemble_status(db_path)
    assert report.oauth.consecutive_refresh_failures == 0
    assert report.oauth.oauth_refresh_failing is False
    # AC-4 Path B: auto-resume fired because we owned the pause reason.
    assert get_pause_state().is_paused() is False
    assert report.router.paused is False


async def test_auto_resume_skips_when_pause_reason_is_not_ours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the operator paused for a different reason while our refresh was
    failing, the success path MUST NOT clobber that pause."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Drive the alarm + auto-pause.
    failure_transport = _failure_transport()
    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=failure_transport)
    assert get_pause_state().reason() == "oauth_refresh_failing"

    # Operator overrides the reason.
    await get_pause_state().resume(db_path)
    await get_pause_state().pause(db_path, reason="operator_holding_off")
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "operator_holding_off"

    # Successful exchange: our auto-resume MUST NOT fire.
    state = await load_oauth_state(db_path)
    assert state is not None
    await exchange_and_persist(db_path, state=state, transport=_success_transport())
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "operator_holding_off"


# --------------------------------------------------------------------------- #
# AC-6.3 — reauth script never logs the token value.
# --------------------------------------------------------------------------- #


async def test_reauth_persists_without_logging_token_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The persist path inside the reauth script MUST NOT emit the token
    value in any log record. Defense-in-depth on top of the structured-log
    contract (the production code already only logs `presence/length`)."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)

    new_token = "rt-reauth-FRESH-canary-value-must-not-appear-in-logs"

    # The script's persist surface is the `_persist` coroutine — we test it
    # directly so we don't have to fork-exec a subprocess inside pytest.
    from scripts.refresh_outlook_oauth import _persist

    caplog.set_level(logging.DEBUG)

    # Patch httpx so the real network is never reached AND our success
    # transport is honored end-to-end. exchange_and_persist accepts a
    # `transport` kwarg, but _persist doesn't expose it — we monkey-patch
    # the symbol oauth.exchange_and_persist instead.
    success_transport = _success_transport()
    real_exchange = __import__(
        "mailbot_api.sync.oauth", fromlist=["exchange_and_persist"]
    ).exchange_and_persist

    async def _patched_exchange(db_path: str, *, state, transport=None, timeout_seconds=30.0):
        return await real_exchange(
            db_path, state=state, transport=success_transport, timeout_seconds=timeout_seconds
        )

    monkeypatch.setattr(
        "scripts.refresh_outlook_oauth.exchange_and_persist", _patched_exchange
    )

    exit_code = await _persist(db_path, new_token)
    assert exit_code == 0

    # The persisted row carries the new token.
    state_after = await load_oauth_state(db_path)
    assert state_after is not None
    # The success path's UPDATE rotates the refresh token to the value MS
    # returned (our success transport returns "rt-rotated") — the OLD token
    # ("rt-reauth-...") is what we sent in the form body, not what MS echoed.
    # Either way, our canary string must NOT show up in any log record below.

    # Defense-in-depth: scan every captured log record for the token value.
    for rec in caplog.records:
        # Render every log record's full content the way the JSON formatter
        # would: msg + structured extras. We catch both the formatted message
        # and the `extra` dict if any.
        assert new_token not in rec.getMessage()
        for value in rec.__dict__.values():
            if isinstance(value, str):
                assert new_token not in value


# --------------------------------------------------------------------------- #
# AC-6.4 — drainer skips its tick when the router is paused (Path B).
# --------------------------------------------------------------------------- #


async def test_drainer_skips_tick_when_router_paused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the router paused (auto-pause from Story 6-15), `run_tick` MUST
    short-circuit without claiming rows so Tier-2/3 sends don't burn
    `budget_consumed=1` per Graph 401."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Seed a drainable Tier-1 pending row (the simplest tier — no grant).
    await execute_write(
        db_path,
        "INSERT INTO pending_actions "
        "(email_id, action_type, tier, payload, proposed_at, status, retry_count, budget_consumed) "
        "VALUES (?, 'archive', 1, '{}', '2026-06-04T12:00:00Z', 'pending', 0, 0)",
        (None,),
    )

    # Pause the router with our marker reason.
    await get_pause_state().pause(db_path, reason="oauth_refresh_failing")

    processed = await run_tick(db_path)
    assert processed == 0

    # Row stays pending — never claimed, never touched.
    row = await fetchone(
        db_path,
        "SELECT status, retry_count, budget_consumed FROM pending_actions LIMIT 1",
        (),
    )
    assert row == ("pending", 0, 0)


async def test_drainer_processes_tick_when_router_not_paused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counter-test for the AC-4 short-circuit: with no pause, the drainer
    runs normally (this is the existing Story 4-4 behaviour, asserted here
    so the AC-4 patch can't regress it)."""
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    await execute_write(
        db_path,
        "INSERT INTO pending_actions "
        "(email_id, action_type, tier, payload, proposed_at, status, retry_count, budget_consumed) "
        "VALUES (?, 'archive', 1, '{}', '2026-06-04T12:00:00Z', 'pending', 0, 0)",
        (None,),
    )

    assert get_pause_state().is_paused() is False
    processed = await run_tick(db_path)
    # One Tier-1 row claimed + dispatched via the FakeGraphWriteAdapter default.
    assert processed == 1


# --------------------------------------------------------------------------- #
# Story 6-15 CR-1 + CR-9 — pre-pause-clobber: operator paused FIRST, then K
# failures arrive. Our auto-pause MUST NOT overwrite the operator's reason,
# and the subsequent success MUST NOT auto-resume the operator's pause.
# --------------------------------------------------------------------------- #


async def test_auto_pause_does_not_clobber_pre_existing_operator_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Operator pauses BEFORE OAuth starts failing.
    await get_pause_state().pause(db_path, reason="manual_hold")
    assert get_pause_state().reason() == "manual_hold"

    # K refresh failures arrive.
    transport = _failure_transport()
    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    # The counter still bumps (alarm field flips True in status) but the
    # operator's reason MUST survive — try_pause_if_unpaused returns False
    # and we leave their pause untouched.
    report = await assemble_status(db_path)
    assert report.oauth.consecutive_refresh_failures == OAUTH_REFRESH_FAIL_THRESHOLD
    assert report.oauth.oauth_refresh_failing is True
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "manual_hold"

    # And on subsequent success, the operator's pause MUST NOT auto-resume —
    # try_resume_if_reason returns False because the reason mismatches our
    # marker.
    state = await load_oauth_state(db_path)
    assert state is not None
    await exchange_and_persist(db_path, state=state, transport=_success_transport())
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "manual_hold"


# --------------------------------------------------------------------------- #
# Story 6-15 CR-15 — the transport-error path (httpx.RequestError) also bumps
# the counter and fires the alarm at threshold. Coverage gap noted by the
# edge-case reviewer.
# --------------------------------------------------------------------------- #


async def test_oauth_refresh_failing_alarm_fires_on_transport_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    def transport_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated DNS / connect failure")

    transport = httpx.MockTransport(transport_error_handler)

    for _ in range(OAUTH_REFRESH_FAIL_THRESHOLD):
        state = await load_oauth_state(db_path)
        assert state is not None
        with pytest.raises(GraphAuthError):
            await exchange_and_persist(db_path, state=state, transport=transport)

    report = await assemble_status(db_path)
    assert report.oauth.consecutive_refresh_failures == OAUTH_REFRESH_FAIL_THRESHOLD
    assert report.oauth.oauth_refresh_failing is True
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "oauth_refresh_failing"


# --------------------------------------------------------------------------- #
# Story 6-15 CR-7 + CR-16 — fresh-deploy (no oauth_state row yet) re-auth that
# the token endpoint rejects MUST roll back the row INSERTed for the attempt,
# so the next worker tick does NOT read the bad token. Coverage gap noted by
# the edge-case reviewer.
# --------------------------------------------------------------------------- #


async def test_fresh_deploy_reauth_rollback_on_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)

    # No oauth_state row yet — fresh deploy.
    assert await load_oauth_state(db_path) is None

    from scripts.refresh_outlook_oauth import _persist

    # Patch the script's exchange_and_persist call to use a failure transport,
    # so the new token gets rejected as invalid_grant after the INSERT.
    failure_transport = _failure_transport()
    real_exchange = __import__(
        "mailbot_api.sync.oauth", fromlist=["exchange_and_persist"]
    ).exchange_and_persist

    async def _patched_exchange(db_path: str, *, state, transport=None, timeout_seconds=30.0):
        return await real_exchange(
            db_path, state=state, transport=failure_transport, timeout_seconds=timeout_seconds
        )

    monkeypatch.setattr(
        "scripts.refresh_outlook_oauth.exchange_and_persist", _patched_exchange
    )

    exit_code = await _persist(db_path, "rt-fresh-deploy-bad-token")
    assert exit_code == 2

    # The bad token MUST NOT be persisted — the INSERT was rolled back so the
    # next worker tick still sees a no-row state and falls through to the
    # bootstrap-seed path instead of reading the rejected token.
    assert await load_oauth_state(db_path) is None
