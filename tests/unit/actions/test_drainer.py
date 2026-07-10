"""Story 4-4 — drainer unit tests.

Real on-disk SQLite + the FakeGraphWriteAdapter / FailingGraphWriteAdapter.
The drainer must honor: priority order, atomic claim, per-tier checks
(lenient Tier-1/2, strict Tier-3 ETag with email-less skip per CR-2),
action_history pre-state write, terminal status flip, budget consumption on
SEND family (even on failure per AR-D5-2), notifications per AR-D5-4.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.authorization import mint_grant, revoke_grant
from mailbot_api.actions.drainer import (
    PendingActionRow,
    run_tick,
)
from mailbot_api.actions.graph_write import (
    FailingGraphWriteAdapter,
    FakeGraphWriteAdapter,
    GraphApplyResult,
)
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.actions.user_confirmation import record_grant_confirmation
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations

# ---- fixtures ----------------------------------------------------------------


# Story 10.5.2 (F-10-5-8): mint_grant now requires a user-gated confirmation.
# These Story-4-4-era tests mint a grant purely as setup to reach the drainer;
# auto-seed a fresh single-use confirmation before each mint so their intent is
# preserved (the confirmation gate itself is covered by
# tests/integration/test_mint_requires_user_confirmation.py).
@pytest.fixture(autouse=True)
def _auto_confirm_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    import mailbot_api.actions.authorization as _authz

    _real_mint = _authz.mint_grant

    async def _mint_with_confirmation(action_type, email_ids, expires_at, *, db_path):  # type: ignore[no-untyped-def]
        await record_grant_confirmation(
            db_path, action_type=action_type.value, email_ids=list(email_ids),
        )
        return await _real_mint(action_type, email_ids, expires_at, db_path=db_path)

    monkeypatch.setattr(_authz, "mint_grant", _mint_with_confirmation)
    monkeypatch.setattr(
        "tests.unit.actions.test_drainer.mint_grant", _mint_with_confirmation
    )


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply migrations + redirect send_urgent log dir to tmp_path."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    monkeypatch.setenv("MAILBOT_LOGS_PATH", str(tmp_path / "logs"))
    return db_path


async def _seed_email(
    db_path: str,
    *,
    graph_id: str,
    change_marker: str = "cm-v1",
    deleted_at: str | None = None,
) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com",
         change_marker, deleted_at),
    )


def _hours_from_now(n: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=n)


def _read_status(db_path: str, action_id: int) -> tuple[str, str | None, int]:
    """Return (status, failure_reason, budget_consumed) for a pending_actions row."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status, failure_reason, budget_consumed "
            "FROM pending_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
    return (row[0], row[1], int(row[2]))


def _notifications_count(tmp_path: Path) -> int:
    """Story 6-3: count `notifications_outbox` rows (replaces the JSONL
    file-based count). Sync — opens its own short-lived SQLite connection
    to the test DB."""
    import sqlite3

    db_file = tmp_path / "test.db"
    if not db_file.exists():
        return 0
    with sqlite3.connect(str(db_file)) as conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM notifications_outbox").fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row[0]) if row is not None else 0


def _router_calls_by_reason(db_path: str, reason: str) -> int:
    """Count router_calls rows with a given model_chosen_reason (Story 10.5.1
    AC-4 audit assertion)."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM router_calls WHERE model_chosen_reason = ?",
            (reason,),
        ).fetchone()
    return int(row[0]) if row is not None else 0


# ---- Story 10.5.1 (F4, CRITICAL) — drainer cross-process pause gate ----------


async def test_db_level_pause_short_circuits_run_tick_without_worker_initialize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE F4 regression at the drainer level.

    A pause written to the DB by "the API process" (here: a direct DB write /
    a first PauseState instance) must be observed by the drainer's gate even
    though the worker never called get_pause_state().initialize(). Before the
    fix, run_tick read the stale in-memory `is_paused()` mirror (False) and
    dispatched the Graph write 259ms after propose while "paused".
    """
    from mailbot_api.router.pause import (
        PauseState,
        _reset_pause_state_for_test,
        get_pause_state,
    )

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    assert out.ok

    # "API process" pauses (writes the DB row). Then reset the module singleton
    # so the drainer's in-memory mirror is unambiguously stale/False — exactly
    # the worker-process reality that let F4 through.
    api_state = PauseState()
    await api_state.initialize(db_path)
    await api_state.pause(db_path, reason="operator-pause")
    _reset_pause_state_for_test()
    assert get_pause_state().is_paused() is False  # stale mirror (the F4 bug)

    processed = await run_tick(db_path, FakeGraphWriteAdapter())
    assert processed == 0  # gate held — no Graph write dispatched while paused

    # Row stays pending (not claimed/applied) so the post-resume tick gets it.
    status, _reason, _budget = _read_status(db_path, out.action_id)
    assert status == "pending"

    # AC-4: the paused skip left an audit row.
    assert _router_calls_by_reason(db_path, "pause_gate:refused") == 1

    _reset_pause_state_for_test()


async def test_paused_drainer_dispatches_after_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After resume writes the DB row, the very next tick drains the row — no
    worker re-initialize needed (proves the gate reads live DB state)."""
    from mailbot_api.router.pause import (
        PauseState,
        _reset_pause_state_for_test,
    )

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)

    api_state = PauseState()
    await api_state.initialize(db_path)
    await api_state.pause(db_path, reason="operator-pause")
    _reset_pause_state_for_test()

    assert await run_tick(db_path, FakeGraphWriteAdapter()) == 0

    # Resume via a DB-writing instance; drainer must now pick the row up.
    await api_state.resume(db_path)
    _reset_pause_state_for_test()
    processed = await run_tick(db_path, FakeGraphWriteAdapter())
    assert processed == 1
    status, _reason, _budget = _read_status(db_path, out.action_id)
    assert status == "applied"

    _reset_pause_state_for_test()


async def test_mid_tick_pause_releases_claimed_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pause that lands AFTER tick entry but before a row dispatches must
    release the claimed row back to pending and stop further dispatch — via the
    authoritative DB read, and it audits the skip."""
    from mailbot_api.router import pause as pause_mod
    from mailbot_api.router.pause import (
        PauseState,
        _reset_pause_state_for_test,
    )

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    await _seed_email(db_path, graph_id="e-2")
    out1 = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    out2 = await propose_action("e-2", ActionType.MARK_READ, db_path=db_path)

    _reset_pause_state_for_test()  # tick-entry gate sees unpaused (no DB row yet)

    # Patch the authoritative snapshot reader to report: unpaused at tick
    # entry, then paused on the mid-tick re-check (simulating an auto-pause
    # landing mid-tick). The first call is the tick-entry gate; subsequent
    # calls are the per-row mid-tick re-checks. The drainer reads (paused,
    # reason) via snapshot_now.
    calls = {"n": 0}

    async def _fake_snapshot_now(self: PauseState, dbp: str) -> tuple[bool, str | None]:
        calls["n"] += 1
        paused = calls["n"] > 1  # first call False (entry), later True (mid-tick)
        return paused, ("mid-tick" if paused else None)

    monkeypatch.setattr(pause_mod.PauseState, "snapshot_now", _fake_snapshot_now)

    processed = await run_tick(db_path, FakeGraphWriteAdapter())

    # First row claimed then mid-tick pause fired → released → processed -= 1.
    assert processed == 0
    # The released row returns to pending; the other is never claimed.
    s1 = _read_status(db_path, out1.action_id)[0]
    s2 = _read_status(db_path, out2.action_id)[0]
    assert "pending" in (s1, s2)

    _reset_pause_state_for_test()


# ---- Tier-1 happy + failure ---------------------------------------------------


async def test_tier_1_mark_read_happy_path_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    assert out.ok

    processed = await run_tick(db_path, FakeGraphWriteAdapter())
    assert processed == 1
    status, reason, budget = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None
    assert budget == 0  # Tier-1 not in send family

    # action_history row written.
    with get_connection(db_path) as conn:
        h_row = conn.execute(
            "SELECT action_id, pre_state FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()
    assert h_row is not None
    assert h_row[0] == out.action_id
    assert json.loads(h_row[1]) == {}  # Story 4-4 ships empty pre_state per Dev Notes


async def test_tier_1_against_soft_deleted_email_silently_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AR-D4-2 rule 1 + AR-D5-4 silent Tier-1: target_deleted, no urgent fired."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Soft-delete the email AFTER propose but BEFORE drain.
    await execute_write(
        db_path,
        "UPDATE emails SET deleted_at = ? WHERE graph_id = ?",
        ("2026-06-02T01:00:00Z", "e-1"),
    )
    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason == "target_deleted"
    # Silent Tier-1 — no urgent notification fired.
    assert _notifications_count(tmp_path) == 0


# ---- Tier-2 grant flows -------------------------------------------------------


async def test_tier_2_archive_without_grant_reverts_to_pending_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    # Tier-2 propose lands in pending_grant; bump to pending manually so the
    # drainer picks it up (the cooling-off→pending transition is Story 4-6).
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "pending_grant"
    assert reason is None


async def test_tier_2_archive_with_valid_grant_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    # Force into pending so drainer claims.
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    # Mint the matching grant.
    grant_out = await mint_grant(
        ActionType.ARCHIVE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out.ok

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None
    # proposed_by_grant_id should now be set.
    with get_connection(db_path) as conn:
        gid = conn.execute(
            "SELECT proposed_by_grant_id FROM pending_actions WHERE id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert gid == grant_out.grant_id


async def test_tier_2_archive_grant_revoked_before_drain_reverts_to_pending_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-4-4-9: Tier-2 grant revoked AFTER propose but BEFORE drain.

    Adam mints a batch grant, proposes an archive, then changes his mind and
    revokes the grant before the drainer runs. Drainer must revert the row
    to `pending_grant` (not apply it), because `is_grant_valid` checks
    `revoked_at IS NULL` at drain time.
    """
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    # Mint grant, propose action.
    grant_out = await mint_grant(
        ActionType.ARCHIVE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out.ok
    assert grant_out.grant_id is not None
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    # Adam revokes the grant before the drainer fires.
    revoke_out = await revoke_grant(grant_out.grant_id, db_path=db_path)
    assert revoke_out.ok

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "pending_grant", (
        f"revoked grant must not authorize drain; got status={status!r}"
    )
    assert reason is None
    # The action wasn't applied — no notification.
    assert _notifications_count(tmp_path) == 0


# ---- Tier-3 grant + ETag flows ------------------------------------------------


async def test_tier_3_delete_without_grant_within_window_reverts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    # DELETE goes directly to 'pending' — no cooling-off.
    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "pending_grant"
    assert reason is None
    # Tier-3 revert is not a failure → no notification yet.
    assert _notifications_count(tmp_path) == 0


async def test_tier_3_delete_grant_expired_after_window_fails_urgent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past the 30-min grant-wait window → fail with grant_expired_unauthorized + urgent."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    # Backdate proposed_at to 31 minutes ago.
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "UPDATE pending_actions SET proposed_at = ? WHERE id = ?",
        (past_iso, out.action_id),
    )

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason == "grant_expired_unauthorized"
    assert _notifications_count(tmp_path) == 1


async def test_tier_3_delete_with_valid_grant_matching_etag_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-MATCH")
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    await mint_grant(ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path)

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None


async def test_tier_3_delete_with_drifted_etag_fails_state_drift_urgent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    out = await propose_action("e-1", ActionType.DELETE, db_path=db_path)
    await mint_grant(ActionType.DELETE, ["e-1"], _hours_from_now(1), db_path=db_path)
    # Simulate a sync that bumped the marker after propose.
    await execute_write(
        db_path,
        "UPDATE emails SET change_marker = ? WHERE graph_id = ?",
        ("cm-v2-DRIFTED", "e-1"),
    )

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason == "state_drift_etag"
    assert _notifications_count(tmp_path) == 1


async def test_tier_3_modify_inbox_rule_email_less_skips_etag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-2 from 4-2 review: email-less Tier-3 actions skip ETag check."""
    db_path = _setup(tmp_path, monkeypatch)
    out = await propose_action(
        None, ActionType.MODIFY_INBOX_RULE, payload={"rule": "x"}, db_path=db_path,
    )
    # Mint email-less grant.
    await mint_grant(
        ActionType.MODIFY_INBOX_RULE, [], _hours_from_now(1), db_path=db_path,
    )
    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "applied"  # ETag check skipped — no source email to compare
    assert reason is None


# ---- Send-family budget ------------------------------------------------------


async def test_tier_3_send_reply_apply_success_consumes_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    out = await propose_action(
        "e-1", ActionType.SEND_REPLY,
        payload={"body": "Hi", "to": ["x@y.com"]}, db_path=db_path,
    )
    # SEND_REPLY lands in cooling_off; force to pending for drainer.
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    await mint_grant(ActionType.SEND_REPLY, ["e-1"], _hours_from_now(1), db_path=db_path)

    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, budget = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None
    assert budget == 1  # SEND family — consumes 1 budget slot


async def test_tier_3_send_reply_apply_failure_still_consumes_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AR-D5-2: failed sends consume budget too — prevents retry-bombing the cap."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", change_marker="cm-v1")
    out = await propose_action(
        "e-1", ActionType.SEND_REPLY,
        payload={"body": "Hi", "to": ["x@y.com"]}, db_path=db_path,
    )
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    await mint_grant(ActionType.SEND_REPLY, ["e-1"], _hours_from_now(1), db_path=db_path)

    await run_tick(db_path, FailingGraphWriteAdapter(error="provider_500"))
    status, reason, budget = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason == "provider_500"
    assert budget == 1  # AR-D5-2


# ---- Concurrency + batch behavior --------------------------------------------


async def test_atomic_claim_skips_already_draining_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Simulate a concurrent drainer that already flipped to 'draining'.
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'draining' WHERE id = ?",
        (out.action_id,),
    )
    processed = await run_tick(db_path, FakeGraphWriteAdapter())
    assert processed == 0  # nothing was 'pending', nothing to claim


async def test_batch_size_limit_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-4-4-8: prove the batch_size parameter is honored independently of
    the default. The original 30-seed / batch_size=25 test would also pass
    if DEFAULT_BATCH_SIZE were silently changed to 30. By using a small
    explicit batch (5) against a larger seed (10), the assertion is now
    SPECIFIC to the batch_size parameter rather than coincidentally true."""
    db_path = _setup(tmp_path, monkeypatch)
    # Seed 10 emails + 10 Tier-1 propose calls.
    for i in range(10):
        await _seed_email(db_path, graph_id=f"e-{i}")
        await propose_action(f"e-{i}", ActionType.MARK_READ, db_path=db_path)

    # Drain with batch_size=5 → exactly 5 transition; 5 remain.
    processed = await run_tick(db_path, FakeGraphWriteAdapter(), batch_size=5)
    assert processed == 5
    with get_connection(db_path) as conn:
        n_pending = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status = 'pending'"
        ).fetchone()[0]
        n_applied = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status = 'applied'"
        ).fetchone()[0]
    assert n_pending == 5
    assert n_applied == 5

    # Second tick with the same batch size drains the remaining 5.
    processed_2 = await run_tick(db_path, FakeGraphWriteAdapter(), batch_size=5)
    assert processed_2 == 5
    with get_connection(db_path) as conn:
        n_applied_after = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status = 'applied'"
        ).fetchone()[0]
    assert n_applied_after == 10


async def test_action_history_row_exists_after_failure_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-4-4-2: action_history INSERT happens BEFORE adapter.apply, so a
    failed dispatch still leaves an audit record.

    Story 4-8's reverter queries `action_history` by `action_id`; if a
    failed action has no history row, the reverter cannot recover anything.
    The original implementation wrote history only on the success path.
    """
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)

    # Drain with the Failing adapter — dispatch will return ok=False.
    await run_tick(db_path, FailingGraphWriteAdapter(error="graph_5xx"))

    status, _reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"

    # action_history MUST have a row even though the dispatch failed.
    with get_connection(db_path) as conn:
        n_history = conn.execute(
            "SELECT COUNT(*) FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert n_history == 1, (
        "action_history row must exist on the failure path so the reverter "
        "can recover; AC-7 + CR-4-4-2"
    )


async def test_action_history_row_exists_after_adapter_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-4-4-2: history is also written even when the adapter raises.

    The adapter contract is 'return GraphApplyResult', but defensive coding
    in the drainer catches synchronous exceptions and marks the row failed.
    The history row must still be present.
    """

    class _RaisingAdapter:
        async def apply(self, row: PendingActionRow) -> GraphApplyResult:  # pragma: no cover
            raise RuntimeError("simulated adapter bug")

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)

    await run_tick(db_path, _RaisingAdapter())  # type: ignore[arg-type]

    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason is not None and "adapter_exception" in reason

    with get_connection(db_path) as conn:
        n_history = conn.execute(
            "SELECT COUNT(*) FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert n_history == 1


async def test_pre_dispatch_crash_marks_failed_not_stuck_in_draining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-4-4-1: an unexpected exception in a per-tier check / history
    write / send-cap query MUST NOT leave the row stuck in `draining`.

    Patches `_insert_history` to raise on a fresh proposal. After the tick:
      - row status is `failed` with reason `drainer_internal_error:*`
      - row is NOT in `draining`
    The defensive try/except in run_tick recovers the claim.
    """
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)

    # Force an exception inside _process_claimed_row by monkeypatching
    # _insert_history (called before adapter.apply).
    from mailbot_api.actions import drainer as _drainer_mod

    async def _crash(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated disk full")

    monkeypatch.setattr(_drainer_mod, "_insert_history", _crash)

    await run_tick(db_path, FakeGraphWriteAdapter())

    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed", f"row stuck in {status!r} — CR-4-4-1 regression"
    assert reason is not None
    assert reason.startswith("drainer_internal_error:"), reason


# ---- Pre-state snapshot (Story 10-2) -------------------------------------------


async def _insert_revert_row(
    db_path: str,
    *,
    email_id: str,
    destination_folder_id: str,
    revert_of_action_id: int,
) -> int:
    """Insert a reverter-shaped inverse row directly (the reverter inserts via
    PENDING_ACTION_INSERT, NOT via propose_action — which refuses the reserved
    revert_of_action_id payload key)."""
    from mailbot_api.db.connection import execute_insert_returning_id
    from mailbot_api.db.queries import PENDING_ACTION_INSERT

    payload = json.dumps(
        {
            "destination_folder_id": destination_folder_id,
            "revert_of_action_id": revert_of_action_id,
        },
        sort_keys=True,
    )
    return await execute_insert_returning_id(
        db_path,
        PENDING_ACTION_INSERT,
        (
            email_id,
            ActionType.MOVE_TO_TRIAGE_FOLDER.value,
            1,
            payload,
            "2026-07-05T00:00:00Z",
            None,
            None,
            "pending",
        ),
    )


async def test_move_family_captures_pre_state_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 AC-1: a move-family drain writes the real source folder id
    into action_history.pre_state (was '{}' for every action before 10-2)."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    await run_tick(db_path, FakeGraphWriteAdapter(source_folder_id="folder-src-1"))
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None
    with get_connection(db_path) as conn:
        pre_state_json = conn.execute(
            "SELECT pre_state FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    pre_state = json.loads(pre_state_json)
    assert pre_state["source_folder_id"] == "folder-src-1"
    assert pre_state["captured_at"]  # ISO-Z timestamp present


async def test_non_move_action_still_writes_empty_pre_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 regression fence: non-move actions keep pre_state='{}'
    byte-identical (send/delete/category paths untouched)."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    await run_tick(db_path, FakeGraphWriteAdapter())
    with get_connection(db_path) as conn:
        pre_state_json = conn.execute(
            "SELECT pre_state FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert json.loads(pre_state_json) == {}


async def test_pre_state_read_failure_fails_closed_without_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 AC-1 fail-closed: a failed pre-state read marks the row
    failed (pre_state_capture_failed:*) and NEVER calls adapter.apply — a
    move dispatched without pre_state would be irreversible-by-construction.
    Check-class failure → no history row (consistent with target_deleted et al.)."""
    from mailbot_api.actions.graph_write import GraphReadResult

    class _PreStateReadFailingAdapter:
        def __init__(self) -> None:
            self.apply_calls = 0

        async def apply(self, row: PendingActionRow) -> GraphApplyResult:
            self.apply_calls += 1
            return GraphApplyResult(ok=True, error=None, retry_count=0)

        async def read_move_pre_state(self, email_id: str) -> GraphReadResult:
            return GraphReadResult(ok=False, error="forced_read_failure")

    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    adapter = _PreStateReadFailingAdapter()
    await run_tick(db_path, adapter)  # type: ignore[arg-type]
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "failed"
    assert reason is not None
    assert reason.startswith("pre_state_capture_failed")
    assert adapter.apply_calls == 0
    with get_connection(db_path) as conn:
        n_history = conn.execute(
            "SELECT COUNT(*) FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert n_history == 0


async def test_revert_marked_row_bypasses_target_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 (F5 landmine): the original move soft-deletes the local row
    via delta sync, so the inverse row would always fail target_deleted. Rows
    carrying the reserved revert_of_action_id payload key bypass the lenient
    deleted-gate; ordinary rows on the same email still refuse."""
    db_path = _setup(tmp_path, monkeypatch)
    # Two separate soft-deleted emails: the revert row's success repairs ITS
    # email's soft-delete (Task 3.3), which would un-gate a plain row sharing
    # the same email — so the gate-intact assertion gets its own subject.
    await _seed_email(db_path, graph_id="e-1", deleted_at="2026-07-05T00:00:10Z")
    await _seed_email(db_path, graph_id="e-2", deleted_at="2026-07-05T00:00:10Z")

    # Ordinary Tier-1 move on a soft-deleted email → target_deleted (gate intact).
    plain = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    # Revert-marked row on a soft-deleted email → drains + applies.
    revert_id = await _insert_revert_row(
        db_path, email_id="e-2", destination_folder_id="folder-orig",
        revert_of_action_id=plain.action_id,
    )

    await run_tick(db_path, FakeGraphWriteAdapter(source_folder_id="folder-dst"))
    plain_status, plain_reason, _ = _read_status(db_path, plain.action_id)
    assert plain_status == "failed"
    assert plain_reason == "target_deleted"
    revert_status, revert_reason, _ = _read_status(db_path, revert_id)
    assert revert_status == "applied"
    assert revert_reason is None


async def test_tier_2_move_family_also_captures_pre_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 AC-2 interpretation pin: ALL five move-family actions capture
    pre_state (cheap, audit-valuable) — revert support extends only to the
    Tier-1 member (test_revert_tier_2_refused pins the ONLY_TIER_1_REVERTIBLE
    half of the pair)."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1")
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'pending' WHERE id = ?",
            (out.action_id,),
        )
        conn.commit()
    grant_out = await mint_grant(
        ActionType.ARCHIVE, ["e-1"], _hours_from_now(1), db_path=db_path,
    )
    assert grant_out.ok

    await run_tick(db_path, FakeGraphWriteAdapter(source_folder_id="folder-inbox"))
    status, reason, _ = _read_status(db_path, out.action_id)
    assert status == "applied"
    assert reason is None
    with get_connection(db_path) as conn:
        pre_state_json = conn.execute(
            "SELECT pre_state FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert json.loads(pre_state_json)["source_folder_id"] == "folder-inbox"


async def test_revert_marked_row_repairs_local_soft_delete_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10-2 (10-1 evidence §5 item 5): a successful revert clears
    deleted_at/removed_reason on the local email row — otherwise the
    'reverted' email stays invisible to every read verb (F5+F6 interaction)."""
    db_path = _setup(tmp_path, monkeypatch)
    await _seed_email(db_path, graph_id="e-1", deleted_at="2026-07-05T00:00:10Z")
    await execute_write(
        db_path,
        "UPDATE emails SET removed_reason = 'deleted' WHERE graph_id = ?",
        ("e-1",),
    )
    revert_id = await _insert_revert_row(
        db_path, email_id="e-1", destination_folder_id="folder-orig",
        revert_of_action_id=999,
    )
    await run_tick(db_path, FakeGraphWriteAdapter())
    status, reason, _ = _read_status(db_path, revert_id)
    assert status == "applied"
    assert reason is None
    with get_connection(db_path) as conn:
        deleted_at, removed_reason = conn.execute(
            "SELECT deleted_at, removed_reason FROM emails WHERE graph_id = ?",
            ("e-1",),
        ).fetchone()
    assert deleted_at is None
    assert removed_reason is None
