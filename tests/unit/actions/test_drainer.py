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

import pytest

from mailbot_api.actions.authorization import mint_grant
from mailbot_api.actions.drainer import (
    PendingActionRow,
    _build_pre_state,
    run_tick,
)
from mailbot_api.actions.graph_write import (
    FailingGraphWriteAdapter,
    FakeGraphWriteAdapter,
)
from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations

# ---- fixtures ----------------------------------------------------------------


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
    """Read notifications_pending.jsonl and count rows."""
    log_file = tmp_path / "logs" / "notifications_pending.jsonl"
    if not log_file.exists():
        return 0
    return sum(1 for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip())


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
    db_path = _setup(tmp_path, monkeypatch)
    # Seed 30 emails + 30 Tier-1 propose calls.
    for i in range(30):
        await _seed_email(db_path, graph_id=f"e-{i}")
        await propose_action(f"e-{i}", ActionType.MARK_READ, db_path=db_path)

    processed = await run_tick(db_path, FakeGraphWriteAdapter(), batch_size=25)
    assert processed == 25
    # 5 rows still pending.
    with get_connection(db_path) as conn:
        n_pending = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status = 'pending'"
        ).fetchone()[0]
        n_applied = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE status = 'applied'"
        ).fetchone()[0]
    assert n_pending == 5
    assert n_applied == 25


# ---- Pre-state snapshot -------------------------------------------------------


def test_build_pre_state_returns_empty_dict_for_now() -> None:
    """Story 4-4 ships empty pre_state for every action; Story 4-8 fills."""
    row = PendingActionRow(
        id=1,
        email_id="e-1",
        action_type=ActionType.MARK_READ,
        tier=1,
        payload={},
        proposed_at="2026-06-02T00:00:00Z",
        proposed_by_grant_id=None,
        change_marker_at_propose=None,
        status="draining",
        retry_count=0,
        failure_reason=None,
        terminal_at=None,
        budget_consumed=0,
    )
    assert _build_pre_state(row) == {}
