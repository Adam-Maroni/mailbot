"""Story 4-8 — Tier-1 24-hour reverter unit tests.

Real SQLite. Tests every refusal branch + the inverse-action map.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mailbot_api.actions.propose import propose_action
from mailbot_api.actions.reverter import REVERT_WINDOW, revert_action
from mailbot_api.actions.types import ActionType
from mailbot_api.db.connection import execute_write, get_connection
from mailbot_api.db.migrations_runner import apply_pending_migrations


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    return db_path


async def _seed_email(db_path: str, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, "
        "change_marker, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        (graph_id, "2026-06-02T00:00:00Z", "Subject", "alice@example.com", "cm-v1", None),
    )


async def _mark_applied_with_history(
    db_path: str, action_id: int, *, terminal_at: str | None = None,
    pre_state: str = "{}",
) -> None:
    """Simulate a successful drain: status='applied' + action_history row.

    `pre_state` defaults to the legacy '{}' (pre-10-2 shape); Story 10-2 move
    tests pass a populated JSON snapshot."""
    if terminal_at is None:
        terminal_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'applied', terminal_at = ? WHERE id = ?",
        (terminal_at, action_id),
    )
    await execute_write(
        db_path,
        "INSERT INTO action_history (action_id, pre_state, applied_at) VALUES (?, ?, ?)",
        (action_id, pre_state, terminal_at),
    )


async def test_revert_mark_read_within_24h_succeeds_with_mark_unread_inverse(
    tmp_path: Path,
) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    assert rev.original_action_id == out.action_id
    assert rev.revert_action_id is not None
    assert rev.revert_action_id != out.action_id

    # New pending_actions row has the inverse action_type.
    with get_connection(db_path) as conn:
        new_row = conn.execute(
            "SELECT action_type, tier, status FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()
        history_revoked = conn.execute(
            "SELECT reverted_at FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert new_row[0] == "mark_unread"
    assert new_row[1] == 1
    assert new_row[2] == "pending"
    assert history_revoked is not None


async def test_revert_mark_unread_inverse_pairs_to_mark_read(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_UNREAD, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    with get_connection(db_path) as conn:
        action_type = conn.execute(
            "SELECT action_type FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()[0]
    assert action_type == "mark_read"


async def test_revert_add_local_category_inverse_pairs_to_remove(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.ADD_LOCAL_CATEGORY, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    with get_connection(db_path) as conn:
        action_type = conn.execute(
            "SELECT action_type FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()[0]
    assert action_type == "remove_local_category"


async def test_revert_tier_2_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.ARCHIVE, db_path=db_path)
    # Manually push to applied for the test.
    await _mark_applied_with_history(db_path, out.action_id)

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error is not None
    assert rev.error.code == "ONLY_TIER_1_REVERTIBLE"


async def test_revert_not_applied_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    # Don't mark applied — stays 'pending'.
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "NOT_APPLIED"


async def test_revert_beyond_24h_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    old_iso = (
        datetime.now(timezone.utc) - REVERT_WINDOW - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")
    await _mark_applied_with_history(db_path, out.action_id, terminal_at=old_iso)
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "REVERT_WINDOW_EXPIRED"


async def test_revert_already_reverted_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action("e-1", ActionType.MARK_READ, db_path=db_path)
    await _mark_applied_with_history(db_path, out.action_id)
    first = await revert_action(out.action_id, db_path=db_path)
    assert first.ok is True
    second = await revert_action(out.action_id, db_path=db_path)
    assert second.ok is False
    assert second.error.code == "ALREADY_REVERTED"


async def test_revert_move_with_pre_state_queues_inverse_move(tmp_path: Path) -> None:
    """Story 10-2 AC-2: revert of an applied MOVE_TO_TRIAGE_FOLDER with
    populated pre_state queues a Tier-1 inverse move back to the source
    folder, carrying the reserved revert_of_action_id marker, and marks the
    original history row reverted."""
    import json

    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    await _mark_applied_with_history(
        db_path, out.action_id,
        pre_state='{"captured_at": "2026-07-05T00:00:00Z", "source_folder_id": "folder-src"}',
    )

    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is True
    assert rev.revert_action_id is not None

    with get_connection(db_path) as conn:
        new_row = conn.execute(
            "SELECT action_type, tier, status, payload FROM pending_actions WHERE id = ?",
            (rev.revert_action_id,),
        ).fetchone()
        reverted_at = conn.execute(
            "SELECT reverted_at FROM action_history WHERE action_id = ?",
            (out.action_id,),
        ).fetchone()[0]
    assert new_row[0] == "move_to_triage_folder"
    assert new_row[1] == 1
    assert new_row[2] == "pending"
    payload = json.loads(new_row[3])
    assert payload["destination_folder_id"] == "folder-src"
    assert payload["revert_of_action_id"] == out.action_id
    assert reverted_at is not None


async def test_revert_move_missing_pre_state_refused(tmp_path: Path) -> None:
    """Story 10-2 AC-2: legacy rows (pre-10-2, pre_state='{}' — e.g. the real
    10-1 walk action id=4) and rows with NO history row at all both refuse
    with PRE_STATE_MISSING rather than guessing a destination."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")

    # Scenario A: history row exists but pre_state is the legacy '{}'.
    legacy = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    await _mark_applied_with_history(db_path, legacy.action_id)  # pre_state='{}'
    rev_a = await revert_action(legacy.action_id, db_path=db_path)
    assert rev_a.ok is False
    assert rev_a.error.code == "PRE_STATE_MISSING"

    # Scenario B: applied row with NO history row at all (the static-map
    # types tolerate this per 4-4 legacy; the move branch must NOT guess).
    orphan = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'applied', terminal_at = ? WHERE id = ?",
        (now_iso, orphan.action_id),
    )
    rev_b = await revert_action(orphan.action_id, db_path=db_path)
    assert rev_b.ok is False
    assert rev_b.error.code == "PRE_STATE_MISSING"


async def test_revert_move_twice_refused_already_reverted(tmp_path: Path) -> None:
    """Story 10-2 AC-4 idempotency: the second revert of the same move hits
    the existing ALREADY_REVERTED gate."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    await _mark_applied_with_history(
        db_path, out.action_id,
        pre_state='{"captured_at": "2026-07-05T00:00:00Z", "source_folder_id": "folder-src"}',
    )
    first = await revert_action(out.action_id, db_path=db_path)
    assert first.ok is True
    second = await revert_action(out.action_id, db_path=db_path)
    assert second.ok is False
    assert second.error.code == "ALREADY_REVERTED"


async def test_revert_dispatch_failed_move_refused_not_applied(tmp_path: Path) -> None:
    """Story 10-2 AC-1 structural pair: a move that failed at dispatch keeps
    its pre-dispatch audit trail but can never be reverted — its pre_state
    cannot mislead the revert path because status != 'applied'.

    CR-10-2-3: seed the CR-4-4-2 history row with a POPULATED pre_state (the
    drainer writes it before dispatch, so a dispatch-failed move really has
    one) — proving the refusal fires on status alone even when a real
    source_folder_id is present."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    await execute_write(
        db_path,
        "INSERT INTO action_history (action_id, pre_state, applied_at) VALUES (?, ?, ?)",
        (
            out.action_id,
            '{"captured_at": "2026-07-05T00:00:00Z", "source_folder_id": "folder-src"}',
            now_iso,
        ),
    )
    await execute_write(
        db_path,
        "UPDATE pending_actions SET status = 'failed', failure_reason = 'provider_4xx_404', "
        "terminal_at = ? WHERE id = ?",
        (now_iso, out.action_id),
    )
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "NOT_APPLIED"


async def test_revert_claim_loser_refused_without_duplicate_inverse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-10-2-1: two concurrent revert_action calls can both pass the
    ALREADY_REVERTED gate read (each DB call is its own transaction). The
    loser must lose at the atomic reverted_at claim (ACTION_HISTORY_MARK_REVERTED
    rowcount 0) and refuse WITHOUT queueing a duplicate inverse row — for a
    move, the duplicate would be a second real Graph dispatch.

    Simulated deterministically: the DB already has reverted_at set (the
    winner), while the loser's gate read is served a stale reverted_at=NULL
    view of the history row."""
    import mailbot_api.actions.reverter as reverter_mod
    from mailbot_api.db.queries import ACTION_HISTORY_SELECT_BY_ACTION_ID

    db_path = _setup(tmp_path)
    await _seed_email(db_path, "e-1")
    out = await propose_action(
        "e-1", ActionType.MOVE_TO_TRIAGE_FOLDER,
        payload={"destination_folder_id": "folder-dst"}, db_path=db_path,
    )
    await _mark_applied_with_history(
        db_path, out.action_id,
        pre_state='{"captured_at": "2026-07-05T00:00:00Z", "source_folder_id": "folder-src"}',
    )
    # The winner reverted between the loser's gate read and its claim.
    await execute_write(
        db_path,
        "UPDATE action_history SET reverted_at = ? WHERE action_id = ?",
        ("2026-07-05T00:00:01Z", out.action_id),
    )
    real_fetchone = reverter_mod.fetchone

    async def stale_fetchone(path: str, query: str, params: tuple = ()) -> tuple | None:
        row = await real_fetchone(path, query, params)
        if query == ACTION_HISTORY_SELECT_BY_ACTION_ID and row is not None:
            return (row[0], row[1], None)  # stale view: winner's mark not yet visible
        return row

    monkeypatch.setattr(reverter_mod, "fetchone", stale_fetchone)
    rev = await revert_action(out.action_id, db_path=db_path)
    assert rev.ok is False
    assert rev.error is not None
    assert rev.error.code == "ALREADY_REVERTED"
    with get_connection(db_path) as conn:
        n_inverse = conn.execute(
            "SELECT COUNT(*) FROM pending_actions WHERE payload LIKE '%revert_of_action_id%'",
        ).fetchone()[0]
    assert n_inverse == 0


async def test_revert_nonexistent_action_refused(tmp_path: Path) -> None:
    db_path = _setup(tmp_path)
    rev = await revert_action(99999, db_path=db_path)
    assert rev.ok is False
    assert rev.error.code == "ACTION_NOT_FOUND"
