"""Story 6-17 F26 regression tests: auto-resume MUST fire on script-driven
exchange success even when `prior_failures` < OAUTH_REFRESH_FAIL_THRESHOLD.

Background: F26 was observed during Story 6-6.5 fourth-pass walk on
2026-06-05. Pre-fix, `_record_refresh_success` early-returned when
`prior_failures < OAUTH_REFRESH_FAIL_THRESHOLD` — short-circuiting the
auto-resume path. The race window:

  1. Worker tick #N captured `state.consecutive_refresh_failures = 0` (or low
     value), failed, bumped DB counter, and on the K-th tick auto-paused with
     reason="oauth_refresh_failing".
  2. Operator runs `scripts/refresh_outlook_oauth.py` with a fresh refresh
     token. The script captures `existing.consecutive_refresh_failures` from
     a DB read at script entry — but if there was an intervening transient
     success between steps 1 and 2 (or if the script read after a partial
     counter reset), `prior_failures` ends up below the threshold.
  3. Script-driven exchange succeeds, but `_record_refresh_success`
     short-circuits because the threshold gate at oauth.py:231 triggers the
     early return BEFORE the atomic `try_resume_if_reason` helper runs.
  4. Result: router stays paused with reason="oauth_refresh_failing", no
     `oauth.refresh.auto_resumed` log, operator must manually `mailbot
     resume`.

Story 6-15 CR-10's atomic helper `try_resume_if_reason` already handles every
pause-state shape safely (returns False if not paused, returns False if paused
for a different reason, resumes ONLY when paused with our reason). The
threshold gate at line 231-232 was therefore redundant AND was the F26 root
cause. Story 6-17 ships Option A: remove the threshold gate entirely.

The test below locks the fix: simulate the F26 race (pre-state = paused with
our reason + prior_failures=0), drive a successful exchange, assert the
auto-resume fires.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.pause import _reset_pause_state_for_test, get_pause_state
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


async def _prepare_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.fixture(autouse=True)
def _reset_pause_each_test():
    """Reset the module-level PauseState singleton between tests so a previous
    test's auto-pause doesn't bleed into the next."""
    _reset_pause_state_for_test()
    yield
    _reset_pause_state_for_test()


# --------------------------------------------------------------------------- #
# AC-3 — F26 regression test: auto-resume fires when prior_failures is BELOW
# the threshold but the pause state is ours.
# --------------------------------------------------------------------------- #


async def test_auto_resume_fires_when_prior_failures_below_threshold_and_pause_is_ours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """F26 regression (AC-3): given a pre-state where the router IS paused with
    reason="oauth_refresh_failing" BUT `oauth_state.consecutive_refresh_failures`
    has already been reset to 0 (the F26 race window — e.g., a transient
    intermediate success reset the counter, or the script's DB read captured
    `prior_failures=0` after the worker tick that originally auto-paused),
    when a successful exchange lands, `_record_refresh_success` MUST still
    auto-resume the router and emit `oauth.refresh.auto_resumed`.

    Pre-fix (Story 6-15), the threshold gate at oauth.py:231-232 short-circuited
    in this exact case, leaving the router permanently paused until manual
    intervention. The fix (Story 6-17) removes the threshold gate; the atomic
    `try_resume_if_reason` helper is the only safety check needed.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Simulate the F26 race window: counter is 0 (already reset) BUT the
    # router IS paused with our reason (lingering from the original failure
    # streak before the counter got reset).
    await get_pause_state().pause(db_path, reason="oauth_refresh_failing")
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "oauth_refresh_failing"

    state = await load_oauth_state(db_path)
    assert state is not None
    assert state.consecutive_refresh_failures == 0  # the F26 race precondition

    # Drive a successful exchange.
    with caplog.at_level(logging.INFO, logger="mailbot_api.sync.oauth"):
        await exchange_and_persist(
            db_path, state=state, transport=_success_transport()
        )

    # Pre-fix: this assertion would have FAILED — router would stay paused.
    # Post-fix: try_resume_if_reason runs unconditionally, sees our reason
    # matches, and resumes.
    assert get_pause_state().is_paused() is False, (
        "F26 regression: auto-resume failed to fire when prior_failures=0 "
        "AND pause_state.reason is ours. The threshold gate at oauth.py:231 "
        "must remain removed."
    )

    # The `oauth.refresh.auto_resumed` event MUST have fired.
    resumed_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "oauth.refresh.auto_resumed"
    ]
    assert len(resumed_events) == 1, (
        f"expected exactly one oauth.refresh.auto_resumed event; got "
        f"{len(resumed_events)}. events: "
        f"{[getattr(r, 'event', None) for r in caplog.records]}"
    )
    # prior_failures rides through to the log for observability even when 0.
    assert getattr(resumed_events[0], "prior_failures", None) == 0


# --------------------------------------------------------------------------- #
# Regression guard: auto-resume STILL skips when pause reason is not ours
# --------------------------------------------------------------------------- #


async def test_auto_resume_skips_when_pause_reason_is_not_ours_even_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counter-test to AC-3: removing the threshold gate MUST NOT break the
    pause-reason-is-not-ours safety. If an operator paused for `manual_hold`
    (or any reason other than `oauth_refresh_failing`), a successful refresh
    exchange MUST NOT clobber that pause.

    This is the Story 6-15 CR-10 atomic-helper contract — the only safety
    gate that remains after Story 6-17 removes the redundant threshold gate.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # Operator pauses for an unrelated reason.
    await get_pause_state().pause(db_path, reason="operator_holding_off")
    assert get_pause_state().reason() == "operator_holding_off"

    state = await load_oauth_state(db_path)
    assert state is not None
    assert state.consecutive_refresh_failures == 0  # below threshold

    # Drive a successful exchange — auto-resume MUST NOT clobber the
    # operator's pause.
    await exchange_and_persist(
        db_path, state=state, transport=_success_transport()
    )
    assert get_pause_state().is_paused() is True
    assert get_pause_state().reason() == "operator_holding_off", (
        "auto-resume must NOT override a pause with a different reason "
        "(Story 6-15 CR-10 atomic-helper contract preserved post-F26 fix)."
    )


# --------------------------------------------------------------------------- #
# AC-4 — Script-driven success path explicitly tested through the script's
# `_persist` coroutine (matches Story 6-15 AC-6.3 harness pattern).
# --------------------------------------------------------------------------- #


async def test_script_driven_success_auto_resumes_paused_router_f26_e2e(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4 + AC-3 end-to-end via the script harness: invoke
    `scripts.refresh_outlook_oauth._persist` against a paused pre-state where
    `consecutive_refresh_failures = 0` (the F26 race precondition), and assert
    the router auto-resumes.

    This tests the same path Story 6-15 AC-6.3 exercises (script's `_persist`
    coroutine + monkey-patched exchange) but with the F26 pre-state. Locks the
    full script-driven success → auto-resume contract end-to-end.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    await seed_oauth_state_from_env(db_path)

    # F26 pre-state: router paused with our reason, counter at 0.
    await get_pause_state().pause(db_path, reason="oauth_refresh_failing")
    state = await load_oauth_state(db_path)
    assert state is not None
    assert state.consecutive_refresh_failures == 0
    assert get_pause_state().is_paused() is True

    # Wire the script's exchange path to our success transport (same pattern
    # as Story 6-15 AC-6.3 test). CR-3: use module-level import for clarity
    # and static analysis (vs the prior `__import__` dynamic import).
    from mailbot_api.sync.oauth import exchange_and_persist as _real_exchange
    from scripts.refresh_outlook_oauth import _persist

    success_transport = _success_transport()

    async def _patched_exchange(
        db_path: str, *, state, transport=None, timeout_seconds=30.0
    ):
        return await _real_exchange(
            db_path,
            state=state,
            transport=success_transport,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr(
        "scripts.refresh_outlook_oauth.exchange_and_persist", _patched_exchange
    )

    exit_code = await _persist(db_path, "rt-script-driven-fresh-token")
    assert exit_code == 0

    # Post-fix assertion: F26 race window closed.
    assert get_pause_state().is_paused() is False, (
        "F26 regression at the script-driven path: the router stayed paused "
        "after a successful exchange via scripts/refresh_outlook_oauth.py "
        "with prior_failures=0. The atomic try_resume_if_reason helper must "
        "fire regardless of the threshold gate."
    )


# --------------------------------------------------------------------------- #
# Coverage: auto-resume fires for both threshold-crossed AND below-threshold
# success paths (regression for the merged contract).
# --------------------------------------------------------------------------- #


async def test_auto_resume_fires_when_router_not_paused_no_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Negative-control: if the router is NOT paused at all (the common case —
    every successful refresh in steady state), `_record_refresh_success` runs
    `try_resume_if_reason` which returns False (no pause to resume) and does
    NOT emit `oauth.refresh.auto_resumed`. The post-Story-6-17 change must
    NOT introduce spurious resume logs on healthy refreshes.
    """
    db_path = await _prepare_db(tmp_path)
    _set_creds(monkeypatch)
    await seed_oauth_state_from_env(db_path)

    # No pause pre-state.
    assert get_pause_state().is_paused() is False

    state = await load_oauth_state(db_path)
    assert state is not None

    with caplog.at_level(logging.INFO, logger="mailbot_api.sync.oauth"):
        await exchange_and_persist(
            db_path, state=state, transport=_success_transport()
        )

    # No spurious auto-resume log.
    resumed_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "oauth.refresh.auto_resumed"
    ]
    assert len(resumed_events) == 0, (
        "auto-resume MUST NOT log when there's no pause to resume; got "
        f"{len(resumed_events)} spurious events."
    )
    assert get_pause_state().is_paused() is False
